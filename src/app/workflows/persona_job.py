"""
Persona Job Workflow (Pulse demo)

What it does:
- Fetches customers from Postgres where ai_segmentation_label is Not Processed
- Calls LLM with a deterministic prompt contract
- Validates output shape (lightweight)
- Updates customers table with derived persona fields

AI concept note:
- This is the "offline enrichment job" that turns raw CRM-ish rows into AI-enriched features.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from config.settings import SETTINGS
from src.db.connection import db_cursor
from src.prompts.persona_analysis import (
    build_persona_system_prompt,
    build_persona_user_prompt,
)


# -----------------------------
# DB: Fetch batch
# -----------------------------
def fetch_unprocessed_customers(*, limit: int, offset: int) -> List[Dict[str, Any]]:
    """
    Returns list of dicts that match prompt expectations.
    """
    with db_cursor() as (_conn, cur):
        cur.execute(
            """
            SELECT
                id,
                gender, age, city,
                subscription_type, tariff_segment,
                arpu, contract_expiry_days,
                data_usage_gb, data_quota_usage_percent, app_monthly_login_count,
                active_vas_subscriptions,
                device_model, device_age_months, network_experience_score,
                credit_score, wallet_active, payment_method,
                home_internet_type
            FROM customers
            WHERE ai_segmentation_label = 'Not Processed' OR ai_segmentation_label IS NULL
            ORDER BY id ASC
            LIMIT %s OFFSET %s;
            """,
            (limit, offset),
        )
        rows = cur.fetchall()

    customers: List[Dict[str, Any]] = []
    for r in rows:
        customers.append(
            {
                "id": int(r[0]),
                "gender": r[1],
                "age": int(r[2]) if r[2] is not None else None,
                "city": r[3],
                "subscription_type": r[4],
                "tariff_segment": r[5],
                "arpu": float(r[6]) if r[6] is not None else 0.0,
                "contract_expiry_days": int(r[7]) if r[7] is not None else 0,
                "data_usage_gb": float(r[8]) if r[8] is not None else 0.0,
                "data_quota_usage_percent": int(r[9]) if r[9] is not None else 0,
                "app_monthly_login_count": int(r[10]) if r[10] is not None else 0,
                "active_vas_subscriptions": list(r[11]) if r[11] else [],
                "device_model": r[12],
                "device_age_months": int(r[13]) if r[13] is not None else 0,
                "network_experience_score": int(r[14]) if r[14] is not None else 3,
                "credit_score": int(r[15]) if r[15] is not None else 1000,
                "wallet_active": bool(r[16]) if r[16] is not None else False,
                "payment_method": r[17],
                "home_internet_type": r[18],
            }
        )

    return customers


# -----------------------------
# Validation (lightweight demo)
# -----------------------------
def _as_int_0_100(x: Any) -> int:
    v = int(x)
    if v < 0:
        return 0
    if v > 100:
        return 100
    return v


def _validate_one(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize and validate one result item. Raises ValueError on hard mismatch.
    """
    required = [
        "id",
        "calculated_churn_risk",
        "calculated_digital_score",
        "predicted_commute_type",
        "is_frequent_traveler",
        "reasoning",
        "label",
        "interests",
    ]
    for k in required:
        if k not in item:
            raise ValueError(f"Missing key: {k}")

    commute = str(item["predicted_commute_type"])
    allowed = {"Driver", "Public Transport", "HomeOffice", "Passenger"}
    if commute not in allowed:
        # Demo: force safe default
        commute = "Passenger"

    interests = item.get("interests") or []
    if not isinstance(interests, list):
        interests = []
    
    # Temizle ve string'e çevir
    interests = [str(x)[:50] for x in interests if x and str(x).lower() != "genel"]
    
    # Eğer hiç ilgi alanı yoksa, "Keşfetmeye Açık" gibi daha pozitif bir etiket kullan
    # ya da Sales AI'ın "Genel" kelimesine alerjisi olduğu için boş bırak.
    if not interests:
         interests = ["Dijital Yaşam"] # 'Genel' yerine daha havalı bir dolgu
    
    # 3'e tamamlama zorunluluğunu (while döngüsünü) KALDIRIN.
    # Postgres Array tipi zaten değişken uzunluğu destekler.
    # LLM 2 tane bulduysa 2 tane kalsın, zorla "Genel" eklemeyelim.

    label = str(item.get("label", "Müşteri"))[:80] # 'Genel Persona' yerine 'Müşteri' veya 'Değerli Üyemiz'
    reasoning = str(item.get("reasoning", "")).strip()[:400]

    return {
        "id": int(item["id"]),
        "calculated_churn_risk": _as_int_0_100(item["calculated_churn_risk"]),
        "calculated_digital_score": _as_int_0_100(item["calculated_digital_score"]),
        "predicted_commute_type": commute,
        "is_frequent_traveler": bool(item["is_frequent_traveler"]),
        "reasoning": reasoning,
        "label": label,
        "interests": interests,
    }


def validate_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Payload is not a dict")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Payload.results is not a list")

    normalized: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append(_validate_one(item))
    return normalized


# -----------------------------
# DB: Update
# -----------------------------
def update_customers(results: List[Dict[str, Any]]) -> int:
    """
    Writes enrichment back into customers table.
    """
    if not results:
        return 0

    with db_cursor() as (conn, cur):
        for r in results:
            # dashboard-friendly label like old code: [Label] reasoning
            final_label = f"[{r['label']}] {r['reasoning']}".strip()

            cur.execute(
                """
                UPDATE customers
                SET
                    churn_risk_score = %s,
                    digital_score = %s,
                    commute_type = %s,
                    is_frequent_traveler = %s,
                    derived_interests = %s,
                    ai_segmentation_label = %s
                WHERE id = %s;
                """,
                (
                    r["calculated_churn_risk"],
                    r["calculated_digital_score"],
                    r["predicted_commute_type"],
                    r["is_frequent_traveler"],
                    r["interests"],
                    final_label,
                    r["id"],
                ),
            )
        conn.commit()

    return len(results)


# -----------------------------
# LLM call
# -----------------------------
async def call_persona_llm(customers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calls Vodafone gateway LLM and expects JSON object output.
    """
    system_prompt = build_persona_system_prompt()
    user_prompt = build_persona_user_prompt(customers)

    async with httpx.AsyncClient(verify=False, timeout=120.0) as http_client:
        client = AsyncOpenAI(
            base_url=SETTINGS.MODEL_GATEWAY_URL,
            api_key=SETTINGS.token,
            http_client=http_client,
        )

        resp = await client.chat.completions.create(
            model=SETTINGS.LLM_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            extra_body={"metadata": {"username": SETTINGS.username, "pwd": SETTINGS.pwd}},
        )

    return json.loads(resp.choices[0].message.content)


# -----------------------------
# Orchestrator
# -----------------------------
async def run_persona_job(*, batch_size: int = 25, max_total: Optional[int] = 300) -> int:
    """
    Runs enrichment until no more unprocessed customers (or max_total reached).
    """
    offset = 0
    total_updated = 0

    while True:
        if max_total is not None and total_updated >= max_total:
            break

        customers = fetch_unprocessed_customers(limit=batch_size, offset=offset)
        if not customers:
            break

        payload = await call_persona_llm(customers)
        normalized = validate_payload(payload)
        updated = update_customers(normalized)

        total_updated += updated
        offset += batch_size

        print(f"✅ Persona batch updated: {updated} (total={total_updated})")

    return total_updated


# Local run helper
if __name__ == "__main__":
    asyncio.run(run_persona_job(batch_size=20))
