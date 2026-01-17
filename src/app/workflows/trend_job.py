# DOSYA: src/app/workflows/trend_job.py
"""
Trend Job Workflow (Pulse demo) — World Context pipeline

What it does:
- Pulls public signals: RSS (title+summary+published+source), Google Trends, TR official holidays, Istanbul weather
- Cleans/dedups items
- Uses LLM to curate "marketable signals" based on REAL headlines:
    - description: "Haberin ana fikri (1 cümle) - HALÜSİNASYON YOK"
    - marketing_hook: "Segment + Senaryo + İhtiyaç (markasız, iddiasız)"
- Deterministic gates:
    - Brand-safety (src/domain/safety.py)
    - Relevancy (telco individual marketing usefulness)
    - ECONOMY signals are dropped (per requirement)
- Adds deterministic agenda cards (school breaks, holidays, weather, Spotify TR top)
- Saves cache JSON to: data/cache/intelligence.json

Design notes:
- Output SHOULD NOT contain Vodafone/product/partner/free claims.
- It CAN keep: game titles, device names, movie/series names, teams etc. (world context).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
import feedparser
import holidays
from dotenv import load_dotenv
from loguru import logger
from openai import AsyncOpenAI
from openai import APITimeoutError
from pytrends.request import TrendReq

from config.settings import SETTINGS
from src.adapters.http_client import build_async_httpx_client

# deterministic guardrail
from src.domain.safety import filter_texts

# ----------------------------
# Config
# ----------------------------

logger.add("data/logs/trend_job.log", rotation="1 day")

RSS_URLS: List[str] = [
    # 🏢 CİDDİ / HABER / EKONOMİ
    "https://www.trthaber.com/sondakika.rss",
    "https://www.bloomberght.com/rss",
    "https://www.ntv.com.tr/ekonomi.rss",
    # 🎮 OYUN / TECH / GEEK
    "https://tr.ign.com/feed.xml",
    "https://www.webtekno.com/rss.xml",
    "https://shiftdelete.net/feed",
    "https://www.merlininkazani.com/rss",
    # 🔥 SOKAK / VİRAL / MAGAZİN
    "https://onedio.com/support/rss.xml",
    "https://www.hurriyet.com.tr/rss/magazin",
    "https://www.medyatava.com/rss",
    # 🎵 MÜZİK / KÜLTÜR
    "https://www.kralmuzik.com.tr/rss",
    "https://www.ntv.com.tr/sanat.rss",
    # ⚽ SPOR
    "https://www.fanatik.com.tr/rss/futbol",
    # 🚗 OTOMOBİL / YAŞAM / SAĞLIK
    "https://tr.motor1.com/rss/articles/all/",
    "https://www.ntv.com.tr/saglik.rss",
    # 🎬 SİNEMA / DİZİ
    "https://www.beyazperde.com/rss/haberler/",
    # 📱 MOBİL / UYGULAMA
    "https://www.mobilizm.com/feed/",
    # 💼 STARTUP / İŞ
    "https://webrazzi.com/feed/",
    # 🎓 EĞİTİM / ÖĞRETİM
    "https://www.egitime.com/rss.xml",
    # 🎪 YENİ ÜRÜN / LANSMAN
    "https://www.producthunt.com/feed/rss",
    # 🐦 X / TWITTER TREND & GÜNDEM
    "https://rsshub.app/twitter/trends",
    "https://rsshub.app/twitter/trends/tr",
    "https://www.trendsmap.com/rss",
    # 🎧 SPOTIFY / MÜZİK TREND
    "https://spotifycharts.com/regional/tr/daily/latest/rss",
    "https://spotifycharts.com/regional/global/daily/latest/rss",
    "https://spotifycharts.com/viral/tr/daily/latest/rss",
    "https://spotifycharts.com/viral/global/daily/latest/rss",
    # 🎬 Beyazperde alt feedler
    "https://www.beyazperde.com/rss/filmler/",
    "https://www.beyazperde.com/rss/diziler/",
    # 🎥 TIKTOK TREND (DOLAYLI)
    "https://www.dexerto.com/feed/",
    "https://www.hitc.com/en-gb/rss/",
    "https://www.socialmediatoday.com/rss/",
    # 🎮 STREAMER & GAMING
    "https://www.dexerto.com/gaming/feed/",
    "https://www.twitch.tv/p/en/feed/",
    "https://www.gamesindustry.biz/rss",
    "https://trends24.in/turkey/rss.xml",
]

CACHE_PATH = "data/cache/intelligence.json"

MAX_ITEMS_TOTAL = 80
MAX_PER_FEED = 6

# LLM load control (content-only, not http/proxy)
MAX_LLM_ITEMS = 24  # 30 bile bazen ağır; 24 güvenli
LLM_SIGNAL_COUNT_MIN = 8
LLM_SIGNAL_COUNT_MAX = 12

# ----------------------------
# Helpers: text cleaning
# ----------------------------

def _strip_html(text: str) -> str:
    t = text or ""
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def clean_short(text: str, *, max_len: int) -> str:
    return _strip_html(text)[:max_len]

def dedup_items_keep_order(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        title = (it.get("title") or "").strip().lower()
        if not title:
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(it)
    return out

def _norm_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

# ----------------------------
# 1) Calendar signals
# ----------------------------

def get_official_holidays(days_ahead: int = 60) -> List[str]:
    """Resmi tatiller (holidays.TR sadece resmi tatilleri verir)."""
    events: List[str] = []
    today = datetime.now().date()
    tr_holidays = holidays.TR(years=today.year)
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        if d in tr_holidays:
            events.append(f"{d.isoformat()}: {tr_holidays[d]} (Resmi Tatil)")
    return events

def get_school_breaks(days_ahead: int = 90) -> List[str]:
    """
    MEB okul tatilleri (resmi tatil değildir; holidays.TR yakalamaz).
    Yakın dönem odaklı sabit takvim (2025-2026).
    """
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)

    breaks = [
        ("2026-01-19", "2026-01-30", "Yarıyıl Tatili (15 Tatil)"),
        ("2026-03-16", "2026-03-20", "İkinci Dönem Ara Tatili"),
    ]

    events: List[str] = []
    for start_s, end_s, name in breaks:
        start_d = datetime.fromisoformat(start_s).date()
        end_d = datetime.fromisoformat(end_s).date()
        if end_d < today or start_d > end:
            continue
        events.append(f"{start_d.isoformat()} - {end_d.isoformat()}: {name} (MEB)")
    return events

def get_weekend_hint(days_ahead: int = 10) -> Optional[str]:
    """Yakın hafta sonu (deterministik, müşteri davranışı tetikleyici)."""
    today = datetime.now().date()
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        # 5 = Saturday, 6 = Sunday
        if d.weekday() == 5:
            return f"{d.isoformat()}: Hafta sonu başlıyor (Cumartesi)"
    return None

# ----------------------------
# 2) Weather (Istanbul via Open-Meteo)
# ----------------------------

async def fetch_weather_insight(http_client: httpx.AsyncClient) -> str:
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            "latitude=41.0082&longitude=28.9784&daily=weather_code&timezone=auto"
        )
        res = await http_client.get(url, timeout=8.0)
        res.raise_for_status()
        code = res.json()["daily"]["weather_code"][0]

        if code == 0:
            return "Güneşli"
        if code in [1, 2, 3]:
            return "Bulutlu"
        if code >= 51:
            return "Yağışlı/Soğuk"
        return "Normal"
    except Exception:
        return "Bilinmiyor"

# ----------------------------
# 3) Google Trends (TR)
# ----------------------------

async def fetch_google_trends() -> List[str]:
    def _run() -> List[str]:
        try:
            pytrends = TrendReq(hl="tr-TR", tz=180, retries=2, backoff_factor=0.2)
            return pytrends.trending_searches(pn="turkey").head(20)[0].tolist()
        except Exception:
            return []
    return await asyncio.to_thread(_run)

# ----------------------------
# 4) RSS — rich items
# ----------------------------

def _guess_source(url: str) -> str:
    try:
        host = re.sub(r"^https?://", "", url).split("/")[0]
        host = host.replace("www.", "")
        return host[:60]
    except Exception:
        return "unknown"

def _entry_to_item(entry: Any, *, feed_url: str) -> Optional[Dict[str, Any]]:
    title = clean_short(getattr(entry, "title", "") or "", max_len=180)
    if not title:
        return None

    summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
    # Keep short summary in cache pool; LLM view will omit it
    summary = clean_short(summary, max_len=180)

    published = (
        getattr(entry, "published", None)
        or getattr(entry, "updated", None)
        or getattr(entry, "pubDate", None)
        or ""
    )
    published = clean_short(str(published), max_len=80)

    return {
        "title": title,
        "summary": summary,
        "published": published,
        "source": _guess_source(feed_url),
        "_feed_url": feed_url,   # internal only (selection logic)
    }

async def fetch_single_rss(http_client: httpx.AsyncClient, url: str) -> List[Dict[str, Any]]:
    try:
        r = await http_client.get(url, timeout=12.0)
        r.raise_for_status()
        feed = feedparser.parse(r.text)

        items: List[Dict[str, Any]] = []
        for e in feed.entries[:MAX_PER_FEED]:
            it = _entry_to_item(e, feed_url=url)
            if it:
                items.append(it)
        return items
    except Exception:
        return []

# ----------------------------
# 5) Deterministic business gates (safety + relevancy)
# ----------------------------

LOW_VALUE_SOURCES = {
    "producthunt.com",
    "rsshub.app",
    "trendsmap.com",
    "hitc.com",
    "socialmediatoday.com",
    "twitch.tv",
}

HARD_DROP_PATTERNS: List[Tuple[str, str]] = [
    # health generic / medicine low relevance
    (r"\b(hastane|ameliyat|ilaç|reçete|burun spreyi|grip|öksürük|bağımlılık)\b", "health-low-relevance"),
    # startup/VC/valuation/investing (b2b)
    (r"\b(değerleme|yatırım turu|yatırımcı|fon|girişim sermayesi|ser(i|ı)e\s?[abc]|ipo|halka arz)\b", "startup-vc"),
    (r"\b(hisse|borsa|kripto|bitcoin|altcoin|airdrop|forex)\b", "finance-trading"),
    # local admin
    (r"\b(ihale|belediye|valilik|kaymakamlık)\b", "local-admin"),
    # economy is DROP by requirement (we still let rss exist, just drop in selection and sanitize)
    (r"\b(wef|dünya ekonomi|küresel ekonomi|enflasyon|kur|altın fiyat)\b", "economy-drop"),
]

KEEP_INTENT_PATTERNS: List[Tuple[str, str, int]] = [
    # travel / holiday / roaming
    (r"\b(tatil|bayram|arefe|uzun hafta sonu|seyahat|uçuş|uçak|otobüs|otel|vize|pasaport)\b", "travel", 6),
    # entertainment / streaming
    (r"\b(dizi|film|sezon|final|fragman)\b", "entertainment", 5),
    (r"\b(netflix|disney|prime|blu\s?tv|gain|exxen)\b", "entertainment", 6),
    (r"\b(konser|festival|bilet|turne)\b", "entertainment", 5),
    # sports
    (r"\b(derbi|maç|lig|şampiyonlar ligi|uefa|transfer|milli maç)\b", "sports", 6),
    # gaming
    (r"\b(oyun|steam|playstation|ps5|xbox|nintendo|dlc|güncelleme|beta)\b", "gaming", 6),
    # device / mobile
    (r"\b(iphone|samsung|galaxy|xiaomi|redmi|oppo|huawei|pixel|android|ios)\b", "device", 6),
    # security
    (r"\b(dolandırıcılık|phishing|oltalama|siber|veri sızıntısı|hack)\b", "security", 7),
    # education / school
    (r"\b(yarıyıl|15 tatil|ara tatil|okul|meb|yks|lgs|vize final|sınav)\b", "education", 6),
    # music (spotify charts)
    (r"\b(spotify|top\s?50|top\s?100|top\s?200|viral)\b", "music", 7),
    (r"\b(apple\s?music|youtube\s?music|deezer)\b", "music", 5),
]

HOOK_BY_INTENT: Dict[str, str] = {
    "travel": "Segment: Seyahat edenler | Senaryo: Tatil/ziyaret planı | İhtiyaç: yolda ve şehir dışında kesintisiz bağlantı ve internet kullanımı",
    "entertainment": "Segment: Dizi/film izleyenler | Senaryo: Yeni içerikler/izleme maratonu | İhtiyaç: akıcı izleme için stabil bağlantı ve yeterli internet",
    "sports": "Segment: Spor takipçileri | Senaryo: Derbi/maç haftası ve sosyal medya etkileşimi | İhtiyaç: canlı takip için hızlı ve stabil bağlantı",
    "gaming": "Segment: Gamer’lar | Senaryo: Oyun indirme/güncelleme ve online maç | İhtiyaç: düşük gecikme ve yüksek hız",
    "device": "Segment: Cihaz yenileyenler | Senaryo: Yeni telefon gündemi/taşıma-kurulum | İhtiyaç: yoğun kullanımda güçlü bağlantı",
    "security": "Segment: Dijital güvenlik hassasiyeti | Senaryo: Dolandırıcılık uyarıları | İhtiyaç: güvenli internet ve hesap güvenliği farkındalığı",
    "education": "Segment: Öğrenci/aile | Senaryo: Tatil/sınav/online süreçler | İhtiyaç: evde ve dışarıda kesintisiz internet",
    "music": "Segment: Spotify/müzik dinleyenler | Senaryo: Top listeler/viral şarkılar | İhtiyaç: yolda/işte kesintisiz müzik için stabil mobil internet",
    "other": "Segment: Genel | Senaryo: Günlük dijital kullanım | İhtiyaç: bağlantı, içerik tüketimi ve dijital güvenlik",
}

def _combined_item_text(it: Dict[str, Any]) -> str:
    return _norm_text(f"{it.get('title','')} {it.get('summary','')} {it.get('source','')}")

def _source_domain(it: Dict[str, Any]) -> str:
    return (it.get("source") or "").strip().lower()

def _is_spotify_tr_feed(it: Dict[str, Any]) -> bool:
    u = (it.get("_feed_url") or "").lower()
    return "spotifycharts.com" in u and "/tr/" in u

def _is_spotify_global_feed(it: Dict[str, Any]) -> bool:
    u = (it.get("_feed_url") or "").lower()
    return "spotifycharts.com" in u and "/global/" in u

def _is_hard_drop(text: str) -> Optional[str]:
    for pat, reason in HARD_DROP_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return reason
    return None

def _detect_intent(text: str, source: str) -> Tuple[str, int]:
    score = 0
    intent = "other"

    if source in LOW_VALUE_SOURCES:
        score -= 2

    for pat, cand_intent, w in KEEP_INTENT_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            score += w
            intent = cand_intent if w >= 5 else intent

    return intent, score

def filter_and_rank_items_for_llm(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 1) safety filter (politics/terror/death/adult/spam etc.)
    combined_texts = [_combined_item_text(it) for it in items]
    safety = filter_texts(combined_texts)
    allowed_set = set(safety.allowed)

    safe_items: List[Dict[str, Any]] = []
    for it in items:
        txt = _combined_item_text(it)
        if txt in allowed_set:
            safe_items.append(it)

    # 2) relevancy scoring + hard drops
    scored: List[Tuple[int, str, Dict[str, Any]]] = []
    for it in safe_items:
        if _is_spotify_global_feed(it):
            continue  # drop noisy global charts

        txt = _combined_item_text(it)
        if _is_hard_drop(txt):
            continue

        src = _source_domain(it)
        intent, score = _detect_intent(txt, src)

        # boost Spotify TR items
        if _is_spotify_tr_feed(it):
            intent = "music"
            score += 6

        it["_intent"] = intent
        scored.append((score, (it.get("title") or ""), it))

    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    filtered = [it for _, __, it in scored]

    # 3) keep stable variety
    return filtered

async def fetch_rss_items(http_client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    tasks = [fetch_single_rss(http_client, u) for u in RSS_URLS]
    results = await asyncio.gather(*tasks)

    all_items = [it for sub in results for it in sub]
    all_items = dedup_items_keep_order(all_items)

    filtered = filter_and_rank_items_for_llm(all_items)

    # keep some randomness after quality gate
    random.shuffle(filtered)
    return filtered[:MAX_ITEMS_TOTAL]

# ----------------------------
# 6) LLM prompt + sanitize
# ----------------------------

def build_trend_system_prompt() -> str:
    return f"""
Sen bir "Market Intelligence Analyst" yapay zekasısın. Telekomünikasyon şirketi (demo) için gündemi analiz ediyorsun.

Amaç:
- GERÇEK gündemden, bireysel telekom müşterisine satış konuşmasında kullanılabilir sinyaller üret.
- Telco ile bağ kurulamayan başlıkları ELE (sinyale dönüştürme).

Telco bağları (en az biri olmalı):
- mobil internet / video-müzik tüketimi / sosyal medya
- oyun indirme-güncelleme / online oyun
- seyahat / tatil / şehir dışı kullanım
- cihaz gündemi ve kurulum/veri taşıma
- evde internet / streaming yoğunluğu
- dijital güvenlik / dolandırıcılık farkındalığı
- öğrenci/aile takvimi (okul tatili/sınav)

Kurallar:
- description: 1 cümle, somut, HALÜSİNASYON YOK. Başlıkta olmayan teknik/spec/numara uydurma.
- marketing_hook: "Segment: ... | Senaryo: ... | İhtiyaç: ..." formatına yakın, markasız ve iddiasız.
-Marketing Hook yazarken 'Genel ihtiyaç' deme. Olayın kendisine atıf yap. Örn: 'Eurovision finalini canlı izlemek ve oy vermek için...' gibi spesifik ol.

Kırmızı çizgiler:
- Vodafone, kampanya adı, paket adı, ortaklık iddiası YAZMA.
- Bedava/ücretsiz gibi doğrulanması gereken iddialar YAZMA.
- Siyaset/terör/ölüm/nefret içerikleri YAZMA.
- Ekonomi/altın/kur gibi finans gündemlerini SİNYALE ÇEVİRME (drop).
- Çıktı sayısı: {LLM_SIGNAL_COUNT_MIN}-{LLM_SIGNAL_COUNT_MAX} arası.
Dil: Türkçe.
Çıktı: SADECE JSON.
""".strip()

def build_trend_user_prompt(context: Dict[str, Any]) -> str:
    payload = json.dumps(context, ensure_ascii=False)
    return f"""
Aşağıdaki bağlam verisini analiz et ve {LLM_SIGNAL_COUNT_MIN}-{LLM_SIGNAL_COUNT_MAX} adet "marketable_signal" üret.

Önemli:
- Telco ile bağ kurulamayanları ELE.
- Description sadece başlıktan/bağlamdan türesin; uydurma spec/numara olmasın.
- Economy sinyali üretme.

Context (JSON):
{payload}

JSON formatı:
{{
  "context_summary": "string",
  "marketable_signals": [
    {{
      "signal_type": "TECH|GAME|ENTERTAINMENT|HEALTH|SPORTS|LIFESTYLE|MUSIC|OTHER",
      "title": "HABER BAŞLIĞI (kısa)",
      "description": "HABERİN ANA FİKRİ (1 cümle, somut, halüsinasyon yok)",
      "source": "kaynak domain",
      "published": "varsa yayın tarihi (string)",
      "marketing_hook": "Segment + Senaryo + İhtiyaç (markasız)"
    }}
  ]
}}

Kurallar:
- "title/source/published" alanlarını context'ten geldiği kadar doldur.
- Sadece JSON döndür.
""".strip()

BLOCK_PHRASES = [
    "vodafone",
    "vodafone pay",
    "vodafone business",
    "ortaklık",
    "partner",
    "iş birliği",
    "collab",
    "collaboration",
    "bedava",
    "ücretsiz",
    "free",
    "promo",
    "promosyon",
    "kampanya",
]

def _sanitize_text_basic(s: str) -> str:
    s = s or ""
    for p in BLOCK_PHRASES:
        s = re.sub(rf"\b{re.escape(p)}\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _allowed_signal_type(x: str) -> str:
    st = (x or "OTHER").upper().strip()
    allowed = {"TECH", "GAME", "ENTERTAINMENT", "HEALTH", "SPORTS", "LIFESTYLE", "MUSIC", "OTHER"}
    return st if st in allowed else "OTHER"

def _safe_description(title: str, desc: str) -> str:
    """
    Prevent hallucinated specs/numbers: if desc contains numeric/spec-like tokens not present in title,
    fall back to a title-based 1-sentence statement.
    """
    t = _sanitize_text_basic(title)[:180]
    d = _sanitize_text_basic(desc)[:240]

    if not d:
        return f"{t} gündemde."

    # If desc includes numbers/spec patterns and title doesn't, treat as hallucination
    spec_like = bool(re.search(r"(\b\d+(\.\d+)?\b|\bOLED\b|\bHz\b|\bmAh\b|\bGB\b|\b5G\b|\binç\b)", d, flags=re.IGNORECASE))
    title_has_spec = bool(re.search(r"(\b\d+(\.\d+)?\b|\bOLED\b|\bHz\b|\bmAh\b|\bGB\b|\b5G\b|\binç\b)", t, flags=re.IGNORECASE))
    if spec_like and not title_has_spec:
        return f"{t} ile ilgili yeni gelişmeler gündeme geldi."

    return d

def _enforce_hook(hook: str, intent: str) -> str:
    h = _sanitize_text_basic(hook or "")
    markers = ["internet", "bağlantı", "mobil", "ev interneti", "izleme", "müzik", "oyun", "gecikme", "güven", "dolandır", "stream", "online", "wi-fi"]
    if any(m in h.lower() for m in markers) and len(h) >= 16:
        return h[:180]
    return HOOK_BY_INTENT.get(intent or "other", HOOK_BY_INTENT["other"])[:180]

def sanitize_intelligence(intel: Dict[str, Any]) -> Dict[str, Any]:
    signals = intel.get("marketable_signals", []) or []
    cleaned: List[Dict[str, Any]] = []

    for s in signals:
        if not isinstance(s, dict):
            continue

        stype = _allowed_signal_type(str(s.get("signal_type", "OTHER")))

        # ECONOMY drop is strict (and ECONOMY isn't even allowed anymore, but just in case)
        if stype == "ECONOMY":
            continue

        title = _sanitize_text_basic(str(s.get("title", "")))[:180]
        desc = _safe_description(title, str(s.get("description", "")))
        src = clean_short(str(s.get("source", "")), max_len=80)
        pub = clean_short(str(s.get("published", "")), max_len=80)

        # infer intent from title/desc (deterministic)
        intent, _ = _detect_intent(f"{title} {desc}", src)
        hook = _enforce_hook(str(s.get("marketing_hook", "")), intent)

        # final safety pass on generated text
        safety = filter_texts([f"{title} {desc} {hook}"])
        if not safety.allowed:
            continue

        cleaned.append(
            {
                "signal_type": stype,
                "title": title,
                "description": desc[:240],
                "source": src,
                "published": pub,
                "marketing_hook": hook,
            }
        )

    intel["marketable_signals"] = cleaned

    if "context_summary" in intel:
        intel["context_summary"] = _sanitize_text_basic(str(intel["context_summary"]))[:280]

    return intel

# ----------------------------
# 7) Deterministic agenda cards (no LLM required)
# ----------------------------

def _mk_signal(signal_type: str, title: str, description: str, source: str, published: str, intent: str) -> Dict[str, Any]:
    return {
        "signal_type": _allowed_signal_type(signal_type),
        "title": clean_short(title, max_len=180),
        "description": clean_short(description, max_len=240),
        "source": clean_short(source, max_len=80),
        "published": clean_short(published, max_len=80),
        "marketing_hook": HOOK_BY_INTENT.get(intent, HOOK_BY_INTENT["other"])[:180],
    }

def build_music_signals_from_spotify(spotify_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    picks: List[str] = []
    for it in spotify_items[:8]:
        t = clean_short(str(it.get("title", "")), max_len=90)
        if t:
            picks.append(t)

    if not picks:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    title = "Spotify TR: Bugünün öne çıkan şarkıları"
    desc = "Türkiye’de Spotify listelerinde öne çıkan şarkılar gündemde."
    hook = HOOK_BY_INTENT["music"] + " | Örnek başlıklar: " + "; ".join(picks[:6])

    return [{
        "signal_type": "MUSIC",
        "title": title,
        "description": desc,
        "source": "spotifycharts.com",
        "published": today,
        "marketing_hook": hook[:180],
    }]

def build_calendar_signals(official_holidays: List[str], school_breaks: List[str], weather: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    today = datetime.now().strftime("%Y-%m-%d")

    # School breaks (very valuable)
    for e in school_breaks[:2]:
        out.append(
            _mk_signal(
                "LIFESTYLE",
                f"Okul tatili yaklaşıyor: {e}",
                "Okul tatili dönemlerinde ailelerde seyahat ve evde içerik tüketimi artabilir.",
                "meb-calendar",
                today,
                "education",
            )
        )

    # Official holidays
    for h in official_holidays[:2]:
        out.append(
            _mk_signal(
                "LIFESTYLE",
                f"Yaklaşan resmi tatil: {h}",
                "Resmi tatil dönemlerinde seyahat, ziyaret ve yoğun iletişim ihtiyacı artabilir.",
                "official-holidays",
                today,
                "travel",
            )
        )

    # Weekend hint
    w = get_weekend_hint()
    if w:
        out.append(
            _mk_signal(
                "LIFESTYLE",
                f"Hafta sonu yaklaşıyor: {w}",
                "Hafta sonu içerik tüketimi (dizi/film/müzik) ve oyun aktiviteleri artabilir.",
                "calendar",
                today,
                "entertainment",
            )
        )

    # Weather
    if weather and weather != "Bilinmiyor":
        intent = "entertainment" if weather in ("Yağışlı/Soğuk",) else "other"
        out.append(
            _mk_signal(
                "LIFESTYLE",
                f"İstanbul hava durumu: {weather}",
                "Hava koşulları dışarı/evde kalma dengesini etkileyebilir; evde içerik tüketimi artabilir.",
                "open-meteo",
                today,
                intent,
            )
        )

    return out

# ----------------------------
# 8) LLM minimal context (reduce load)
# ----------------------------

def _llm_item_view(it: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal view for LLM to reduce tokens:
    DO NOT include summary.
    """
    return {
        "title": it.get("title", ""),
        "published": it.get("published", ""),
        "source": it.get("source", ""),
    }

def _fallback_intelligence_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    items = context.get("news_items", []) or []
    signals: List[Dict[str, Any]] = []

    for it in items[:10]:
        title = clean_short(str(it.get("title", "")), max_len=180)
        if not title:
            continue
        intent, _ = _detect_intent(title, str(it.get("source", "")))
        signals.append(
            {
                "signal_type": "OTHER",
                "title": title,
                "description": f"{title} gündemde.",
                "source": clean_short(str(it.get("source", "")), max_len=80),
                "published": clean_short(str(it.get("published", "")), max_len=80),
                "marketing_hook": HOOK_BY_INTENT.get(intent, HOOK_BY_INTENT["other"])[:180],
            }
        )

    return {
        "context_summary": "LLM yanıt veremediği için deterministik özet üretildi.",
        "marketable_signals": signals,
    }

# ----------------------------
# 9) Run + Save cache
# ----------------------------

async def run_trend_job() -> Dict[str, Any]:
    load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))

    # IMPORTANT: http/proxy settings unchanged (build_async_httpx_client is the same)
    http_client = build_async_httpx_client(timeout_s=120.0)

    try:
        rss_task = fetch_rss_items(http_client)
        trends_task = fetch_google_trends()
        weather_task = fetch_weather_insight(http_client)

        holiday_list = get_official_holidays()
        school_breaks = get_school_breaks()

        rss_items, trends, weather = await asyncio.gather(rss_task, trends_task, weather_task)

        # Grab spotify TR items for deterministic signal
        spotify_tr = [it for it in rss_items if _is_spotify_tr_feed(it)]

        # Titles for quick visibility (not for LLM load)
        news_titles = [it["title"] for it in rss_items if it.get("title")]

        # LLM payload (minimal)
        curated = rss_items[:MAX_LLM_ITEMS]
        llm_news_items = [_llm_item_view(it) for it in curated]

        # Reduce other payload parts
        context = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "weather": weather,
            "official_holidays": holiday_list[:4],
            "school_breaks": school_breaks[:3],
            "trends": (trends[:8] if isinstance(trends, list) else []),
            "news_titles": news_titles[:10],
            "news_items": llm_news_items,
        }

        llm = AsyncOpenAI(
            base_url=SETTINGS.MODEL_GATEWAY_URL,
            api_key=SETTINGS.token,
            http_client=http_client,
        )

        try:
            resp = await llm.chat.completions.create(
                model=SETTINGS.LLM_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": build_trend_system_prompt()},
                    {"role": "user", "content": build_trend_user_prompt(context)},
                ],
                temperature=0.4,
                response_format={"type": "json_object"},
                extra_body={"metadata": {"username": SETTINGS.username, "pwd": SETTINGS.pwd}},
            )

            intel = json.loads(resp.choices[0].message.content)
            intel = sanitize_intelligence(intel)

        except APITimeoutError:
            logger.warning("LLM timeout — deterministic fallback used.")
            intel = _fallback_intelligence_from_context(context)

        # Deterministic “agenda cards” ALWAYS added (format unchanged)
        deterministic_signals: List[Dict[str, Any]] = []
        deterministic_signals += build_music_signals_from_spotify(spotify_tr)
        deterministic_signals += build_calendar_signals(holiday_list, school_breaks, weather)

        existing = intel.get("marketable_signals", []) or []
        # Merge without duplicating identical titles
        seen_titles = set()
        merged: List[Dict[str, Any]] = []
        for s in deterministic_signals + existing:
            t = (s.get("title") or "").strip().lower()
            if not t or t in seen_titles:
                continue
            seen_titles.add(t)
            # ECONOMY hard drop safety
            if (s.get("signal_type") or "").upper() == "ECONOMY":
                continue
            merged.append(s)

        # cap total
        intel["marketable_signals"] = merged[: (LLM_SIGNAL_COUNT_MAX + 6)]

        final_report = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "intelligence": intel,
            "raw_inputs": {
                "weather": weather,
                "holiday_count": len(holiday_list),
                "school_break_count": len(school_breaks),
                "trends_count": len(trends) if isinstance(trends, list) else 0,
                "news_count": len(news_titles),
                "news_items_count": len(rss_items),
            },
        }

        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(final_report, f, ensure_ascii=False, indent=2)

        logger.success(
            f"Trend job OK. Saved: {CACHE_PATH} signals={len(intel.get('marketable_signals', []))} rss_items={len(rss_items)}"
        )
        return final_report

    finally:
        await http_client.aclose()


if __name__ == "__main__":
    asyncio.run(run_trend_job())
