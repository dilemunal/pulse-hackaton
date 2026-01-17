from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from src.db.connection import db_cursor

app = FastAPI(title="Pulse API", version="0.1.0")


def _parse_ai_reasoning(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return x
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return s
    return str(x)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sales-opportunities/{customer_id}")
def get_sales_opportunity(customer_id: int) -> Dict[str, Any]:
    """
    Sales_Workflow'un yazdığı sales_opportunities tablosundan
    customer_id ile tek kaydı döner.
    """
    with db_cursor() as (_conn, cur):
        cur.execute(
            """
            SELECT
                s.customer_id,
                c.name,
                s.persona_label,
                s.current_intent,
                s.suggested_product,
                s.marketing_headline,
                s.marketing_content,
                s.ai_reasoning,
                s.created_at
            FROM sales_opportunities s
            JOIN customers c ON s.customer_id = c.id
            WHERE s.customer_id = %s
            LIMIT 1;
            """,
            (customer_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No sales_opportunity for customer_id={customer_id}")

    return {
        "customer_id": row[0],
        "name": row[1],
        "persona_label": row[2],
        "current_intent": row[3],
        "suggested_product": row[4],
        "marketing_headline": row[5],
        "marketing_content": row[6],
        "ai_reasoning": _parse_ai_reasoning(row[7]),
        "created_at": row[8].isoformat() if row[8] else None,
    }

# src/app/app/app.py içine (en alta) eklenecek:

@app.get("/api/customers-with-opportunities")
def get_customers_with_opportunities() -> Dict[str, Any]:
    """
    Demo Dashboard için Liste:
    Sadece 'sales_opportunities' tablosunda kaydı olan (işlenmiş) müşterileri getirir.
    Böylece demoda boş müşteriye tıklama riski olmaz.
    """
    with db_cursor() as (_conn, cur):
        cur.execute(
            """
            SELECT
                c.id,
                c.name,
                c.age,
                c.tariff_segment,
                c.device_model,
                s.suggested_product,
                s.marketing_headline
            FROM customers c
            JOIN sales_opportunities s ON c.id = s.customer_id
            ORDER BY s.created_at DESC
            LIMIT 50;
            """
        )
        rows = cur.fetchall()

    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "name": r[1],
            "age": r[2],
            "segment": r[3],
            "device": r[4],
            "opportunity_summary": {
                "product": r[5],
                "headline": r[6]
            }
        })

    return {
        "count": len(results),
        "items": results
    }