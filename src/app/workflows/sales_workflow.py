# DOSYA: src/app/workflows/sales_workflow.py
"""
Sales Workflow (Pulse demo) — "Brain" of the system

Core idea (what jury should understand):
- Pulse'un asıl farkı: GÜNDEM (World Context) + müşteri bağlamı + ürün kataloğu bilgisi.
- Sales workflow, bir "pazarlamacı/satışçı" gibi davranır:
  - O anki gündemdeki somut haber başlıklarını kullanır (uydurmaz)
  - Müşterinin profilini/ilgisini/geçmişini kullanır
  - Ürün kataloğundan (RAG) en mantıklı ürünü seçer
  - Türkçe, samimi ve kişisel bir mesaj üretir
  - Neden bu kararı verdiğini yazılı (structured) şekilde kaydeder

Data sources:
1) World Context: data/cache/intelligence.json (Trend Job çıktısı)
   - Beklenen: raw_inputs.news (başlıklar) ve/veya intelligence.marketable_signals
2) Customer 360: Postgres
   - customers + customer_behavior.metrics_json + purchase_history
3) Product Catalog RAG: Chroma (collection: pulse_products)
   - Postgres ürün tablosundan build_catalog_index ile vektörlenmiş katalog

Output:
- Postgres table: sales_opportunities
  - suggested_product
  - marketing_headline
  - marketing_content
  - ai_reasoning (JSON string: selected_news + customer_facts + product_facts + rationale)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
from openai import AsyncOpenAI

from config.settings import SETTINGS
from src.db.connection import db_cursor
from src.adapters.embeddings import EmbeddingsClient
from src.adapters.vector_store import VectorStore


# -----------------------------
# DB: Setup table
# -----------------------------
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


# -----------------------------
# World context loader
# -----------------------------
def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def load_world_context(path: str = "data/cache/intelligence.json") -> Dict[str, Any]:
    """
    Returns a normalized world context payload used by LLM.

    We prefer REAL "news titles" (headlines) over generic hooks.
    Trend Job ideally writes either:
      - raw_inputs.news: [title, title, ...]
      - intelligence.news_items: [{title, source, published_at?}, ...]

    We keep both: "news_titles" + "signals" (brand-agnostic hooks).
    """
    if not os.path.exists(path):
        return {
            "context_summary": "Gündem verisi yok.",
            "news_titles": [],
            "signals": [],
        }

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    intel = data.get("intelligence", {}) or {}
    raw = data.get("raw_inputs", {}) or {}

    # 1) Best effort: use explicit news items/titles if exist
    news_items = _safe_list(intel.get("news_items"))
    news_titles: List[str] = []
    if news_items:
        for it in news_items[:60]:
            if isinstance(it, dict):
                t = str(it.get("title", "")).strip()
                if t:
                    news_titles.append(t)
    else:
        raw_news = raw.get("news")
        if isinstance(raw_news, list):
            news_titles = [str(x).strip() for x in raw_news if str(x).strip()][:60]
        else:
            # legacy trend_job: raw_inputs may not include actual titles; fallback to "news_count" only
            news_titles = []

    # 2) Signals (brand-agnostic)
    signals = _safe_list(intel.get("marketable_signals"))

    context_summary = str(intel.get("context_summary", "")).strip() or "Bugünün gündemi derlendi."

    return {
        "context_summary": context_summary,
        "news_titles": news_titles,
        "signals": signals,
    }


# -----------------------------
# Customer 360 (minimal demo)
# -----------------------------
def fetch_customer_batch(*, limit: int, offset: int) -> List[Dict[str, Any]]:
    """
    Minimal 360:
    - customers (persona/interest/risk)
    - customer_behavior.metrics_json (intent, data_left, billing summary)
    - purchase_history (last 5)
    """
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
                    "city": None,  # if you have it in table later, add
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


# -----------------------------
# Product retrieval (RAG candidates)
# -----------------------------
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
    Returns:
      [{"product_code":..., "doc":..., "metadata":..., "distance":...}, ...]
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


# -----------------------------
# LLM: SALES BRAIN (single step)
# -----------------------------
def build_sales_brain_system_prompt() -> str:
    return """
Sen Pulse sistemindeki "Satış & Pazarlama Beyni"sin.

Bir pazarlamacı gibi düşün:
- En büyük avantajın: anlık GÜNDEM (somut haber başlıkları).
- Müşteri bağlamını biliyorsun: persona / interests / intent / data_left / history.
- Ürün kataloğu adayları (RAG) elinde: sadece bu adaylar içinden ürün seçeceksin.
-Müşterinin ilgi alanları, ihtiyaçları ve geçmiş satın alma davranışlarını dikkate alarak anlık gündemdi kullan ve ürünlerin için kampanya metni oluştur.

Yapman gereken:
1) Haber başlıklarından (news_titles) 1-2 tane seç, müşteriye uygun olanları.
2) Ürün adaylarından (product_candidates) en uygun olanını seç.
3) Kısa, ilgi çekici bir başlık (marketing_headline) oluştur. Kişisel ve gündeme uygun olsun. Haber başlıklarından esinlenebilirsin.
4) Kişisel, samimi ve gündeme bağlı bir içerik (marketing_content) yaz. Herkese hitap etme, müşteriye özel yap. Müşterinin ilk ismini kullanabilirsin. 
 Örnek: "Sena ! Sims4 oyun paketi çıktığını duyduk, sen rahatça oynayabil diye sana özel ekstra 10GB paket sadece X TL ! Keyfini çıkar!"
5) Neden bu kararları verdiğini (seçilen haberler, müşteri bağlamı, ürün özellikleri) yapılandırılmış şekilde açıkla (ai_reasoning).


Kırmızı çizgiler:
- Uydurma yok: haber olarak SADECE verilen news_titles içinden seçtiğin başlığı referans alabilirsin.
- Ürün olarak SADECE verilen product_candidates içinden seçebilirsin.
- “Vodafone X ortaklığı”, “bedava/ücretsiz” gibi doğrulanması zor iddialar YAZMA.
- Türkçe yaz. Samimi, kişisel, sıcak. Ama "aşırı satış/abartı" yok.
- Her mesaj "Selam" ile başlamasın. Yaşa göre hitap değişebilir:
  - genç (<=28) ise first_name ile daha enerjik,
  - yetişkin ise first_name + daha dengeli,
  - first_name yoksa nötr hitap.

ÇIKTI:
SADECE JSON döndür.
Şema:
{
  "selected_news_titles": ["..."],            // 1-2 adet, sadece inputtan
  "chosen_product_code": "....",             // sadece candidates içinden
  "suggested_product": "....",               // chosen ürün adı
  "marketing_headline": "....",              // kısa, ilgi çekici
  "marketing_content": "....",               // 2-4 cümle, kişisel + gündem bağlantılı + ürün önerisi
  "ai_reasoning": {                          // KAYDETMEK İÇİN
    "customer_facts_used": ["...","..."],     // persona, interests, intent, history gibi somut şeyler
    "world_facts_used": ["...","..."],        // seçtiğin haber başlıkları
    "product_facts_used": ["...","..."],      // aday üründen (doc/metadata) aldığın gerçek özellikler
    "why_this_product_now": ["...","..."]     // karar mantığı (gündem + müşteri + ürün)
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
    """
    LLM gets:
    - world.news_titles (real headlines)
    - customer facts
    - product candidates (RAG)
    Produces final output + structured reasons.
    """
    payload = {
        "world": {
            "context_summary": world.get("context_summary", ""),
            "news_titles": (world.get("news_titles") or [])[:40],
            "signals": (world.get("signals") or [])[:12],  # optional fallback context
        },
        "customer": cust,
        "product_candidates": [
            {
                "product_code": c.get("product_code"),
                "product_name": c.get("product_name"),
                "distance": c.get("distance"),
                "category": (c.get("metadata", {}) or {}).get("category"),
                "segment": (c.get("metadata", {}) or {}).get("segment"),
                "channel": (c.get("metadata", {}) or {}).get("channel"),
                "price_try": (c.get("metadata", {}) or {}).get("price_try"),
                "doc": (c.get("doc", "")[:700]),  # keep enough to ground
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
    return json.loads(resp.choices[0].message.content)


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


# -----------------------------
# DB: Save results
# -----------------------------
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


# -----------------------------
# Orchestrator
# -----------------------------
async def run_sales_workflow(*, batch_size: int = 10, max_total: Optional[int] = 30) -> int:
    """
    Demo run:
    - Reads world context once
    - Processes customer batches
    - For each customer:
        1) build a retrieval query (deterministic heuristic + LLM will still choose from candidates)
        2) retrieve candidates via RAG
        3) LLM composes: chosen product + message + structured reasons (grounded)
        4) save to Postgres
    """
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

            out_rows: List[Tuple] = []

            for cust in customers:
                # --- RAG query heuristic (fast, deterministic) ---
                # We intentionally include: interests + intent + device + a hint from headlines if exist.
                interests = ", ".join(cust.get("interests") or [])
                intent = cust.get("intent", "")
                device = cust.get("device_model", "")
                headline_hint = ""
                if world.get("news_titles"):
                    headline_hint = str(world["news_titles"][0])[:80]

                query_text = f"{interests}. intent: {intent}. device: {device}. gündem: {headline_hint}".strip()
                if not query_text:
                    query_text = "Genel iletişim paketi"

                # Metadata filter heuristic (optional)
                # If very low data, prefer addon/data topups
                md_filter: Optional[Dict[str, Any]] = None
                if float(cust.get("data_left_gb", 0) or 0) <= 1.0:
                    md_filter = {"category": "Addon"}

                candidates = retrieve_product_candidates(
                    query_text=query_text,
                    where=md_filter,
                    k=6,
                )

                # If nothing retrieved (shouldn't happen if index exists), keep empty candidates
                decision = await run_sales_brain(
                    llm,
                    world=world,
                    cust=cust,
                    product_candidates=candidates,
                )

                chosen_code = _safe_str(decision.get("chosen_product_code"), 120)
                chosen = _pick_candidate_by_code(candidates, chosen_code)

                # Enforce "no hallucinated product": if code invalid, fallback to first candidate
                if not chosen and candidates:
                    chosen = candidates[0]
                    chosen_code = (chosen.get("product_code") or "").strip()

                suggested_product = _safe_str(decision.get("suggested_product"), 200)
                if not suggested_product and chosen:
                    suggested_product = _safe_str(chosen.get("product_name"), 200)

                # Final structured reasoning (always store)
                ai_reasoning_obj = decision.get("ai_reasoning")
                if not isinstance(ai_reasoning_obj, dict):
                    ai_reasoning_obj = {}

                # Hard-grounding: also store exact artifacts used
                used_news = decision.get("selected_news_titles")
                if not isinstance(used_news, list):
                    used_news = []
                used_news = [str(x)[:220] for x in used_news][:2]

                # Add hard facts (so UI can show "bu yüzden")
                grounding = {
                    "selected_news_titles": used_news,
                    "chosen_product_code": chosen_code,
                    "chosen_product_name": suggested_product,
                    "candidate_snapshot": [
                        {
                            "product_code": c.get("product_code"),
                            "product_name": c.get("product_name"),
                            "category": (c.get("metadata", {}) or {}).get("category"),
                            "distance": c.get("distance"),
                        }
                        for c in candidates[:5]
                    ],
                    "customer_snapshot": {
                        "id": cust.get("id"),
                        "first_name": cust.get("first_name"),
                        "age": cust.get("age"),
                        "persona": cust.get("persona"),
                        "interests": cust.get("interests"),
                        "intent": cust.get("intent"),
                        "data_left_gb": cust.get("data_left_gb"),
                        "history": cust.get("history"),
                    },
                }

                ai_reasoning_obj["grounding"] = grounding

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

            save_opportunities(out_rows)

            processed += len(customers)
            offset += batch_size
            print(f"✅ Sales workflow wrote: {len(customers)} (total={processed})")

    return processed


if __name__ == "__main__":
    asyncio.run(run_sales_workflow(batch_size=10, max_total=30))
