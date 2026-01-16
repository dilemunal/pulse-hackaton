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
                customer_id,
                persona_label,
                current_intent,
                suggested_product,
                marketing_headline,
                marketing_content,
                ai_reasoning,
                created_at
            FROM sales_opportunities
            WHERE customer_id = %s
            LIMIT 1;
            """,
            (customer_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No sales_opportunity for customer_id={customer_id}")

    return {
        "customer_id": row[0],
        "persona_label": row[1],
        "current_intent": row[2],
        "suggested_product": row[3],
        "marketing_headline": row[4],
        "marketing_content": row[5],
        "ai_reasoning": _parse_ai_reasoning(row[6]),
        "created_at": row[7].isoformat() if row[7] else None,
    }
