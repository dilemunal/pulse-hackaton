"""
Sales Workflow (Pulse demo) — "Brain" of the system

- Pulse'un asıl farkı: GÜNDEM (World Context) + müşteri bağlamı + ürün kataloğu bilgisi.
- Sales workflow, bir "pazarlamacı/satışçı" gibi davranır:
  - O anki gündemdeki somut haber başlıklarını kullanır
  - Müşterinin profilini/ilgisini/geçmişini kullanır
  - Ürün kataloğundan (RAG) en mantıklı ürünü seçer
  - Türkçe, samimi ve kişisel bir mesaj üretir
  - Neden bu kararı verdiğini yazılı  şekilde kaydeder

Data sources:
1) World Context: data/cache/intelligence.json (Trend Job çıktısı)
2) Customer 360: Postgres
3) Product Catalog RAG: Chroma (collection: pulse_products)

Output:
- Postgres table: sales_opportunities
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx
from openai import AsyncOpenAI
from loguru import logger  # Demo için eklendi

from config.settings import SETTINGS
from src.db.connection import db_cursor
from src.adapters.embeddings import EmbeddingsClient
from src.adapters.vector_store import VectorStore

# --- DEMO İÇİN ÖZEL LOGGER AYARLARI ---
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
    level="INFO",
    colorize=True
)
# ---------------------------------------


# DB: Setup 
def setup_sales_table() -> None:
    with db_cursor() as (conn, cur):
        cur.execute("DROP TABLE IF EXISTS sales_opportunities;")
        cur.execute(
            """
            CREATE TABLE sales_opportunities (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
                persona_label TEXT,
                current_intent TEXT,
                suggested_product TEXT,
                marketing_headline TEXT,
                marketing_content TEXT,
                ai_reasoning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(customer_id)
            );
            """
        )
        conn.commit()


# World context loader

def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def load_world_context(path: str = "data/cache/intelligence.json") -> Dict[str, Any]:
    # Demo logu
    logger.opt(colors=True).info(f"<dim>Gündem verisi yükleniyor: {path}</dim>")

    if not os.path.exists(path):
        logger.warning("Dosya bulunamadı! Trend Job çalıştırılmalı.")
        return {"context_summary": "Veri Yok", "news_titles": [], "signals": []}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"JSON hatası: {e}")
        return {"context_summary": "Veri Bozuk", "news_titles": [], "signals": []}

    intel = data.get("intelligence")
    if not intel:
        return {"context_summary": "Eksik Veri", "news_titles": [], "signals": []}
    
    signals = intel.get("marketable_signals")
    news_titles = []

    if isinstance(signals, list):
        for s in signals:
            if isinstance(s, dict) and s.get("title"):
                news_titles.append(str(s["title"]).strip())

    return {
        "context_summary": str(intel.get("context_summary", "Gündem Verisi")),
        "news_titles": news_titles,
        "signals": signals if isinstance(signals, list) else [],
    }


# Customer 360 
def fetch_customer_batch(*, limit: int, offset: int) -> List[Dict[str, Any]]:
    with db_cursor() as (_conn, cur):
        cur.execute(
            """
            SELECT
                c.id,
                c.name,
                c.age,
                c.tariff_segment,
                c.subscription_type,
                c.device_model,
                c.ai_segmentation_label,
                c.churn_risk_score,
                c.derived_interests,
                b.metrics_json
            FROM customers c
            JOIN customer_behavior b ON c.id = b.customer_id
            WHERE c.ai_segmentation_label IS NOT NULL
              AND c.ai_segmentation_label != 'Not Processed'
            ORDER BY c.id ASC
            LIMIT %s OFFSET %s;
            """,
            (limit, offset),
        )
        rows = cur.fetchall()

        batch: List[Dict[str, Any]] = []
        for r in rows:
            cid = int(r[0])

            # history (last 5)
            cur.execute(
                """
                SELECT product_name, channel
                FROM purchase_history
                WHERE customer_id = %s
                ORDER BY purchase_date DESC
                LIMIT 5;
                """,
                (cid,),
            )
            hist = cur.fetchall()
            history_str = " | ".join([f"{h[0]} ({h[1]})" for h in hist]) if hist else "Geçmiş satın alma yok."

            raw_json = r[9] or {}
            footprint = (raw_json.get("digital_footprint") or {}) if isinstance(raw_json, dict) else {}
            live = (raw_json.get("live_status") or {}) if isinstance(raw_json, dict) else {}
            billing = live.get("billing") or {}

            intent = str(footprint.get("current_intent", "Bilinmiyor"))[:80]
            data_left = float(live.get("remaining_data_gb", 0) or 0)

            bill_status = (
                str(billing.get("bill_status", "OK"))[:40]
                if r[4] == "Postpaid"
                else f"TL: {billing.get('credit_balance_tl', 0)}"
            )

            interests_list = r[8] if r[8] else ["Genel"]
            if not isinstance(interests_list, list):
                interests_list = ["Genel"]
            interests_list = [str(x)[:40] for x in interests_list][:3]

            age = int(r[2]) if r[2] is not None else None
            full_name = str(r[1] or "").strip()
            first_name = (full_name.split()[0] if full_name else "")

            batch.append(
                {
                    "id": cid,
                    "full_name": full_name,
                    "first_name": first_name,
                    "age": age,
                    "city": None,
                    "tariff_segment": r[3],
                    "subscription_type": r[4],
                    "device_model": r[5],
                    "persona": r[6],
                    "risk": int(r[7] or 0),
                    "interests": interests_list,
                    "history": history_str,
                    "intent": intent,
                    "data_left_gb": data_left,
                    "bill_status": bill_status,
                }
            )

    return batch


# Product retrieval (RAG candidates)

def _product_name_from_doc(doc: str) -> str:
    first = (doc.splitlines()[0] if doc else "").strip()
    if first.startswith("product_name:"):
        return first.replace("product_name:", "").strip()
    return ""


def retrieve_product_candidates(
    *,
    query_text: str,
    collection_name: str = "pulse_products",
    k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve top-k product docs from Chroma.
    """
    emb_client = EmbeddingsClient()
    try:
        query_emb = emb_client.embed_texts([query_text]).vectors[0]
    finally:
        emb_client.close()

    vs = VectorStore()
    col = vs.get_or_create_collection(collection_name)

    res = col.query(
        query_embeddings=[query_emb],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = (res.get("documents") or [[]])[0]
    mds = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: List[Dict[str, Any]] = []
    for doc, md, dist in zip(docs, mds, dists):
        md = md or {}
        out.append(
            {
                "product_code": str(md.get("product_code", "")).strip(),
                "doc": doc or "",
                "metadata": md,
                "distance": float(dist) if dist is not None else None,
                "product_name": _product_name_from_doc(doc or "") or str(md.get("name", "") or "").strip(),
            }
        )
    return out


# AŞAMA 1: STRATEJİST AI 

async def decide_sales_strategy(
    llm: AsyncOpenAI,
    *,
    customer_profile: Dict[str, Any],
    world_context: Dict[str, Any]
) -> Dict[str, Any]:
    
    # DEMO LOG: Stratejist başlıyor
    c_name = customer_profile.get("full_name", "Müşteri")
    c_persona = customer_profile.get("persona", "Bilinmiyor")
    logger.opt(colors=True).info(f"🤖 <cyan>AI STRATEJİST DEVREDE</cyan> | Analiz: <bold>{c_name}</bold> ({c_persona})")

    # Müşteri Profilini Hazırla
    cust_summary = {
        "demographics": {
            "age": customer_profile.get("age"),
            "segment": customer_profile.get("tariff_segment"),
            "persona": customer_profile.get("persona"),
            "device": customer_profile.get("device_model")
        },
        "interests": customer_profile.get("interests", []),
        "history": customer_profile.get("history"),
        "behavior": {
            "current_intent": customer_profile.get("intent"),
            "data_left_gb": customer_profile.get("data_left_gb"),
            "churn_risk": customer_profile.get("risk")
        }
    }

    news_titles = (world_context.get("news_titles") or [])[:25]

    system_prompt = """
    Sen Vodafone Pulse sisteminin "Yaratıcı Satış Stratejisti"sin.
    Görevin: Müşteri verisi ile Gündem arasında "Bağ Kurmak".

    DURUM:
    Müşterilerimiz için "Genel Kampanya" en son çaredir. Bizim farkımız, gündemi kullanarak kişisel bağ kurmaktır.
    
    TALİMATLAR:
    1. Asla hemen pes edip "GENEL_KAMPANYA" seçme. 
    2. YARATICI BAĞLAR KUR:
       - Haber: "Hafta sonu yağmurlu" -> Strateji: "Evde kalıp film izle (Video Pass)" veya "Oyun oyna (Gamer Pass)".
       - Haber: "Okullar tatil" -> Strateji: "Gençler için sosyal medya paketi" veya "Karne hediyesi cihaz".
       - Haber: "Popüler şarkı viral" -> Strateji: "Spotify/Müzik Pass".
    3. Eğer müşterinin ilgisi ile haber arasında %10 bile alaka varsa, o haberi SEÇ.

    ÇIKTI FORMATI (JSON):
    {
        "selected_news_title": "Seçilen haber başlığı",
        "strategy_reasoning": "Mantık (Örn: Haber X, ama müşteri Video seviyor, 'Hafta Sonu Keyfi' konseptiyle bağlıyorum.)",
        "search_query": "Ürün kataloğu için arama terimi"
    }
    """

    user_payload = {
        "customer_analysis_data": cust_summary,
        "available_agenda_items": news_titles
    }

    try:
        resp = await llm.chat.completions.create(
            model=SETTINGS.LLM_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
            extra_body={"metadata": {"username": SETTINGS.username, "pwd": SETTINGS.pwd}},
        )
        result = json.loads(resp.choices[0].message.content)
        
        # DEMO LOG: Strateji sonucu
        s_news = result.get("selected_news_title", "Yok")
        s_query = result.get("search_query", "-")
        logger.opt(colors=True).info(f"   📰 <cyan>Seçilen Gündem:</cyan> {s_news}")
        logger.opt(colors=True).info(f"   🧠 <cyan>Strateji:</cyan> {s_query}")
        
        return result

    except Exception as e:
        logger.error(f"Strateji AI Hatası: {e}")
        return {
            "selected_news_title": "YOK",
            "search_query": f"{cust_summary['demographics']['segment']} paket",
            "strategy_reasoning": "Fallback"
        }


# AŞAMA 2: SALES BRAIN 

def build_sales_brain_system_prompt() -> str:
    return """
Sen Pulse sistemindeki "Satış & Pazarlama Beyni"sin. 

Görevin:
1. Sana verilen "selected_news" (Gündem) ve "product_candidates" (Aday Ürünler) arasından en mantıklı eşleşmeyi yap.
2. Müşteriye özel, samimi, Türkçe bir pazarlama mesajı yaz.

Kırmızı çizgiler:
- Uydurma yok: SADECE sana verilen haber başlığını ve ürünleri kullan.
- "Vodafone X ortaklığı", "bedava" gibi iddialar YAZMA.
- Türkçe yaz. Samimi, kişisel, sıcak. "Aşırı satış" yok.

ÇIKTI (JSON):
{
  "selected_news_titles": ["..."],            
  "chosen_product_code": "....",             
  "suggested_product": "....",               
  "marketing_headline": "....",              
  "marketing_content": "....",               
  "ai_reasoning": {                          
    "customer_facts_used": ["..."],     
    "product_facts_used": ["..."],      
    "why_this_product_now": ["..."]     
  }
}
""".strip()


async def run_sales_brain(
    llm: AsyncOpenAI,
    *,
    world: Dict[str, Any],
    cust: Dict[str, Any],
    product_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    
    # DEMO LOG: Brain Başlıyor
    logger.opt(colors=True).info("💡 <yellow>SALES BRAIN (YARATICI KATMAN) DEVREDE</yellow>")
    logger.opt(colors=True).info("   <dim>Vektör veritabanından gelen ürünler ile gündem birleştiriliyor...</dim>")

    payload = {
        "world": {
            "selected_news": world.get("selected_news", ""),
            "context_summary": world.get("context_summary", ""),
        },
        "customer": cust,
        "product_candidates": [
            {
                "product_code": c.get("product_code"),
                "product_name": c.get("product_name"),
                "distance": c.get("distance"),
                "category": (c.get("metadata", {}) or {}).get("category"),
                "segment": (c.get("metadata", {}) or {}).get("segment"),
                "doc": (c.get("doc", "")[:700]),
            }
            for c in product_candidates[:8]
        ],
    }

    resp = await llm.chat.completions.create(
        model=SETTINGS.LLM_CHAT_MODEL,
        messages=[
            {"role": "system", "content": build_sales_brain_system_prompt()},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.35,
        response_format={"type": "json_object"},
        extra_body={"metadata": {"username": SETTINGS.username, "pwd": SETTINGS.pwd}},
    )
    
    result = json.loads(resp.choices[0].message.content)
    
    # DEMO LOG: Sonuç
    headline = result.get("marketing_headline", "")
    prod = result.get("suggested_product", "")
    logger.opt(colors=True).info(f"   🎁 <yellow>Önerilen Ürün:</yellow> {prod}")
    logger.opt(colors=True).info(f"   📢 <yellow>Manşet:</yellow> <bold>{headline}</bold>")
    
    return result


def _pick_candidate_by_code(candidates: List[Dict[str, Any]], code: str) -> Optional[Dict[str, Any]]:
    code = (code or "").strip()
    if not code:
        return None
    for c in candidates:
        if (c.get("product_code") or "").strip() == code:
            return c
    return None


def _safe_str(x: Any, max_len: int) -> str:
    s = str(x or "").strip()
    return s[:max_len]


# DB: Save results

def save_opportunities(rows: List[Tuple]) -> None:
    if not rows:
        return
    with db_cursor() as (conn, cur):
        cur.executemany(
            """
            INSERT INTO sales_opportunities (
                customer_id, persona_label, current_intent, suggested_product,
                marketing_headline, marketing_content, ai_reasoning
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (customer_id) DO UPDATE SET
                persona_label = EXCLUDED.persona_label,
                current_intent = EXCLUDED.current_intent,
                suggested_product = EXCLUDED.suggested_product,
                marketing_headline = EXCLUDED.marketing_headline,
                marketing_content = EXCLUDED.marketing_content,
                ai_reasoning = EXCLUDED.ai_reasoning,
                created_at = CURRENT_TIMESTAMP;
            """,
            rows,
        )
        conn.commit()


# Orchestrator

async def run_sales_workflow(*, batch_size: int = 10, max_total: Optional[int] = 30) -> int:
    logger.opt(colors=True).info("<bold><green>🚀 PULSE SALES MOTORU BAŞLATILIYOR...</green></bold>")
    
    setup_sales_table()
    world = load_world_context()

    processed = 0
    offset = 0

    async with httpx.AsyncClient(verify=False, timeout=120.0) as http_client:
        llm = AsyncOpenAI(
            base_url=SETTINGS.MODEL_GATEWAY_URL,
            api_key=SETTINGS.token,
            http_client=http_client,
        )

        while True:
            if max_total is not None and processed >= max_total:
                break

            customers = fetch_customer_batch(limit=batch_size, offset=offset)
            if not customers:
                break
            
            logger.info(f"Batch işleniyor: {len(customers)} müşteri...")

            out_rows: List[Tuple] = []

            for cust in customers:
                # --- 1. STRATEJİST AI ---
                strategy = await decide_sales_strategy(
                    llm,
                    customer_profile=cust,
                    world_context=world
                )

                ai_search_query = strategy.get("search_query", "")
                selected_news = strategy.get("selected_news_title", "")
                strategy_reasoning = strategy.get("strategy_reasoning", "")
                
                if not ai_search_query:
                    ai_search_query = f"{cust.get('tariff_segment')} paket"

                # --- 2. RAG RETRIEVAL ---
                # Demo için log azaltıldı, sadece stratejist ve brain öne çıksın
                candidates = retrieve_product_candidates(
                    query_text=ai_search_query,
                    k=6,
                )

                # --- 3. SALES BRAIN ---
                focused_world = world.copy()
                if selected_news and selected_news != "YOK":
                    focused_world["selected_news"] = selected_news
                
                decision = await run_sales_brain(
                    llm,
                    world=focused_world,
                    cust=cust,
                    product_candidates=candidates,
                )

                chosen_code = _safe_str(decision.get("chosen_product_code"), 120)
                chosen = _pick_candidate_by_code(candidates, chosen_code)

                if not chosen and candidates:
                    chosen = candidates[0]
                    chosen_code = (chosen.get("product_code") or "").strip()

                suggested_product = _safe_str(decision.get("suggested_product"), 200)
                if not suggested_product and chosen:
                    suggested_product = _safe_str(chosen.get("product_name"), 200)

                ai_reasoning_obj = decision.get("ai_reasoning")
                if not isinstance(ai_reasoning_obj, dict):
                    ai_reasoning_obj = {}
                
                ai_reasoning_obj["strategist_reasoning"] = strategy_reasoning
                ai_reasoning_obj["grounding"] = {
                    "selected_news": selected_news,
                    "search_query": ai_search_query,
                    "chosen_product_code": chosen_code
                }

                out_rows.append(
                    (
                        cust["id"],
                        _safe_str(cust.get("persona"), 600),
                        _safe_str(cust.get("intent"), 120),
                        _safe_str(suggested_product or "Size Özel Fırsat", 200),
                        _safe_str(decision.get("marketing_headline"), 140),
                        _safe_str(decision.get("marketing_content"), 900),
                        json.dumps(ai_reasoning_obj, ensure_ascii=False)[:6000],
                    )
                )
                print("-" * 50) # Müşteriler arası ayraç

            save_opportunities(out_rows)

            processed += len(customers)
            offset += batch_size
            
            logger.success(f"✅ Batch tamamlandı. Toplam İşlenen: {processed}")

    return processed


if __name__ == "__main__":
    asyncio.run(run_sales_workflow(batch_size=5, max_total=10))