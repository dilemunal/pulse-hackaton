# DOSYA: scripts/seed_behavior.py
"""
Seed customer_behavior (JSONB) table (Pulse demo).

Creates:
- customer_behavior table

Stores:
- live_status (data/minutes/billing)
- digital_footprint (mood, session_time, network issues, intent)
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from src.db.connection import db_cursor


def _safe_load_env() -> None:
    load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))


def seed_behavior(*, random_seed: int = 42) -> int:
    _safe_load_env()
    random.seed(random_seed)

    with db_cursor() as (_conn, cur):
        cur.execute("DROP TABLE IF EXISTS customer_behavior CASCADE;")
        cur.execute(
            """
            CREATE TABLE customer_behavior (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
                metrics_json JSONB
            );
            """
        )

        cur.execute("SELECT id, tariff_segment, subscription_type, age, arpu FROM customers;")
        customers = cur.fetchall()

        rows: List[Tuple[int, str]] = []

        for cid, segment, sub_type, age, arpu in customers:
            # Data quota baseline
            if segment == "Red" or "FreeZone" in str(segment):
                total_data = random.randint(20, 60)
            else:
                total_data = random.randint(5, 15)

            remaining_data = round(random.uniform(0.0, float(total_data)), 2)
            used_percent = int((1 - (remaining_data / total_data if total_data else 1)) * 100)

            total_min = random.choice([500, 750, 1000, 2000])
            remaining_min = random.randint(0, total_min)

            # Billing / balance
            if sub_type == "Postpaid":
                current_bill = round(float(arpu) * random.uniform(0.9, 1.2), 2)
                days_left = random.randint(1, 30)
                billing: Dict[str, Any] = {
                    "bill_status": "Unpaid",
                    "current_amount": current_bill,
                    "due_date_days_left": days_left,
                    "is_overdue": True if days_left < 3 and random.random() < 0.2 else False,
                }
            else:
                balance = round(random.uniform(0, 150), 2)
                package_days_left = random.randint(0, 28)
                billing = {
                    "credit_balance_tl": balance,
                    "package_expiry_days_left": package_days_left,
                    "is_low_balance": True if balance < 20 else False,
                }

            live_status = {
                "remaining_data_gb": remaining_data,
                "total_data_gb": total_data,
                "data_usage_percent": used_percent,
                "remaining_minutes": remaining_min,
                "billing": billing,
            }

            digital_footprint: Dict[str, Any] = {
                "tobi_mood": random.choices(["Positive", "Neutral", "Frustrated"], weights=[40, 50, 10])[0],
                "app_session_time_avg": random.randint(10, 60) if age < 30 else random.randint(1, 15),
                "recent_network_issues": random.choices([0, 1, 5], weights=[80, 15, 5])[0],
            }

            if segment == "Red":
                digital_footprint["travel_intent_score"] = random.randint(0, 100)
                digital_footprint["most_visited_page"] = random.choice(["International Packs", "Bill Details", "Apple Watch"])
            elif "FreeZone" in str(segment):
                digital_footprint["gaming_latency_complaint"] = random.choice([True, False, False])
                digital_footprint["most_visited_page"] = random.choice(["Wheel of Fortune", "Food Discounts", "Gamer Packs"])
                digital_footprint["night_data_usage_percent"] = random.randint(20, 90)
            elif sub_type == "Prepaid":
                digital_footprint["topup_frequency"] = random.choice(["Regular", "Irregular"])
                digital_footprint["most_visited_page"] = random.choice(["TL Topup", "Budget Packs", "Call Me Back"])
            else:
                digital_footprint["most_visited_page"] = "Invoice Summary" if sub_type == "Postpaid" else "Balance Check"

            # Intent
            current_intent = "General Browsing"
            if remaining_data / total_data * 100 < 10 if total_data else False:
                current_intent = "Urgent Data Need"
            elif sub_type == "Postpaid" and billing.get("due_date_days_left", 99) < 3:
                current_intent = "Bill Payment Check"
            elif sub_type == "Prepaid" and billing.get("credit_balance_tl", 999) < 15:
                current_intent = "TopUp Needed"
            elif digital_footprint.get("travel_intent_score", 0) > 80:
                current_intent = "Roaming Search"

            digital_footprint["current_intent"] = current_intent

            final_metrics = {"live_status": live_status, "digital_footprint": digital_footprint}
            rows.append((cid, json.dumps(final_metrics, ensure_ascii=False)))

        cur.executemany("INSERT INTO customer_behavior (customer_id, metrics_json) VALUES (%s, %s);", rows)
        return len(rows)


if __name__ == "__main__":
    total = seed_behavior()
    print(f"✅ Seed OK: {total} customer_behavior kaydı basıldı.")
