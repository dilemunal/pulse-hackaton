# DOSYA: scripts/seed_history.py
"""
Seed purchase_history table (Pulse demo).

Creates:
- purchase_history table

Segment-aware (light):
- Red -> more digital channels
- FreeZone -> mostly digital, some physical
- Prepaid/Kolay Paket -> mixed channels
"""

from __future__ import annotations

import os
import random
from typing import List, Tuple

from dotenv import load_dotenv

from src.db.connection import db_cursor

PRODUCTS_RED = [
    "Red Pass İletişim", "Yurt Dışı 1GB Roaming", "Apple Music Üyeliği",
    "YouTube Premium Ek Paket", "Sınırsız Video Pass", "Red Ekstra 10GB", "Araç İçi Wi-Fi"
]
PRODUCTS_FREEZONE = [
    "Gamer Pass (Sınırsız Oyun)", "Sınırsız Instagram Paketi", "Twitch Bit Paketi",
    "Haftalık 10GB (Hediye Çarkı)", "Spotify Premium Üyeliği", "PubG Mobile UC"
]
PRODUCTS_PREPAID = [
    "Haftalık 5GB", "Günlük 1GB", "100 TL Yükleme", "200 TL Yükleme",
    "Kolay Paket 20GB", "TL Transfer"
]
PRODUCTS_UYUMLU = [
    "Ekstra 1GB İnternet", "1000 DK Konuşma Paketi", "SMS Paketi",
    "Tarife Yenileme", "Güvenli Depo 50GB", "Fatura Ödeme"
]

CHANNELS_DIGITAL = ["Yanımda App", "Web", "Tobi"]
CHANNELS_PHYSICAL = ["Vodafone Store", "Call Center", "SMS"]


def _safe_load_env() -> None:
    load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))


def seed_history(*, random_seed: int = 42) -> int:
    _safe_load_env()
    random.seed(random_seed)

    with db_cursor() as (_conn, cur):
        cur.execute("DROP TABLE IF EXISTS purchase_history CASCADE;")
        cur.execute(
            """
            CREATE TABLE purchase_history (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
                product_name VARCHAR(150),
                purchase_date DATE DEFAULT CURRENT_DATE,
                channel VARCHAR(50),
                price_paid DECIMAL(10,2),
                offer_engagement_score INTEGER
            );
            """
        )

        cur.execute("SELECT id, tariff_segment, subscription_type, age FROM customers;")
        customers = cur.fetchall()

        insert_query = """
            INSERT INTO purchase_history (customer_id, product_name, purchase_date, channel, price_paid, offer_engagement_score)
            VALUES (%s, %s, CURRENT_DATE - CAST(%s AS INT), %s, %s, %s)
        """

        rows: List[Tuple] = []

        for cid, segment, sub_type, age in customers:
            purchase_count = random.randint(0, 8)
            for _ in range(purchase_count):
                if segment == "Red":
                    product = random.choice(PRODUCTS_RED)
                    price = random.uniform(50, 300)
                    channel = random.choice(CHANNELS_DIGITAL)
                elif "FreeZone" in segment:
                    product = random.choice(PRODUCTS_FREEZONE)
                    price = random.uniform(20, 150)
                    channel = random.choice(CHANNELS_DIGITAL) if random.random() < 0.75 else random.choice(CHANNELS_PHYSICAL)
                elif segment == "Kolay Paket" or sub_type == "Prepaid":
                    product = random.choice(PRODUCTS_PREPAID)
                    price = random.uniform(30, 250)
                    channel = random.choice(CHANNELS_DIGITAL + CHANNELS_PHYSICAL)
                else:
                    product = random.choice(PRODUCTS_UYUMLU)
                    price = random.uniform(10, 100)
                    channel = random.choice(CHANNELS_PHYSICAL) if age > 60 else random.choice(CHANNELS_DIGITAL + CHANNELS_PHYSICAL)

                days_ago = random.randint(1, 365)
                score = random.randint(2, 5)

                rows.append((cid, product, days_ago, channel, round(price, 2), score))

        cur.executemany(insert_query, rows)
        return len(rows)


if __name__ == "__main__":
    total = seed_history()
    print(f"✅ Seed OK: {total} purchase_history kaydı basıldı.")
