"""
Seed purchase_history table (Pulse demo) 

Amaç:
- Rastgele veri yerine tutarlı satın alma geçmişi oluşturmak.
- Böylece AI, geçmişe bakınca "Bu müşteri Gamer", "Bu müşteri Gezgin" diyebilsin.
"""

from __future__ import annotations

import os
import random
from typing import List, Tuple

from dotenv import load_dotenv

from src.db.connection import db_cursor

# Gamer Profili (Gençler, FreeZone)
PRODUCTS_GAMER = [
    "Gamer Pass (Sınırsız Oyun)", "PubG Mobile 60 UC", "Valorant VP", 
    "Steam Cüzdan Kodu 100 TL", "Discord Nitro Üyeliği", "Twitch Bit Paketi",
    "Sınırsız Discord & Twitch"
]

# Gezgin Profili (Red, Yüksek Gelir)
PRODUCTS_TRAVELER = [
    "Yurt Dışı 1GB Roaming", "Her Şey Dahil Pasaport (Günlük)", 
    "Yurt Dışı Konuşma 60 DK", "Pasaport Dünya", "Yurt Dışı Avantaj Paketi",
    "Seyahat Yanımda Sigortası"
]

# Dijital/Video Profili (Video tüketenler)
PRODUCTS_STREAMER = [
    "Sınırsız Video Pass", "YouTube Premium Üyeliği", "Netflix Standart Paket",
    "Sınırsız Sosyal Pass", "Spotify Premium", "Apple Music Üyeliği"
]

# Geleneksel/Standart (Daha yaşlı veya düşük bütçe)
PRODUCTS_BASIC = [
    "Haftalık 1GB", "Günlük 500MB", "SMS Paketi", 
    "1000 DK Konuşma", "Fatura Ödeme", "Tarife Yenileme",
    "Ekstra 2GB İnternet"
]

# Kanal Tercihleri
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

        # Müşterileri çek (Yaş ve Segment verisi kritik)
        cur.execute("SELECT id, tariff_segment, subscription_type, age, arpu FROM customers;")
        customers = cur.fetchall()

        insert_query = """
            INSERT INTO purchase_history (customer_id, product_name, purchase_date, channel, price_paid, offer_engagement_score)
            VALUES (%s, %s, CURRENT_DATE - CAST(%s AS INT), %s, %s, %s)
        """

        rows: List[Tuple] = []

        for cid, segment, sub_type, age, arpu in customers:
            # Pattern Injection
            # Müşteriye bir "Karakter" biçiyoruz ki geçmişi tutarlı olsun.
            
            archetype = "STANDARD"
            
            # Kural: 30 yaş altı ve FreeZone ise yüksek ihtimal Gamer veya Streamer
            if age < 30 and ("FreeZone" in str(segment) or "Genç" in str(segment)):
                archetype = random.choices(["GAMER", "STREAMER", "STANDARD"], weights=[0.5, 0.3, 0.2])[0]
            
            # Kural: Red segmenti veya yüksek ARPU ise Gezgin olma ihtimali var
            elif str(segment) == "Red" or float(arpu or 0) > 400:
                archetype = random.choices(["TRAVELER", "STREAMER", "STANDARD"], weights=[0.4, 0.3, 0.3])[0]
            
            # Kural: Yaşlı veya Ön Ödemeli ise Standart
            elif age > 50 or sub_type == "Prepaid":
                archetype = "STANDARD"

            # --- 3. HARCAMA ÜRETİMİ ---
            purchase_count = random.randint(1, 10) # En az 1 hareket olsun
            
            for _ in range(purchase_count):
                # Archetype'a göre ürün havuzunu seç
                if archetype == "GAMER":
                    # %80 ihtimalle oyun, %20 genel
                    pool = PRODUCTS_GAMER if random.random() < 0.8 else PRODUCTS_BASIC + PRODUCTS_STREAMER
                elif archetype == "TRAVELER":
                    pool = PRODUCTS_TRAVELER if random.random() < 0.7 else PRODUCTS_STREAMER + PRODUCTS_BASIC
                elif archetype == "STREAMER":
                    pool = PRODUCTS_STREAMER if random.random() < 0.8 else PRODUCTS_BASIC
                else:
                    pool = PRODUCTS_BASIC

                product = random.choice(pool)
                
                # Fiyat belirle (Ürün adına göre kabaca)
                if "Pass" in product or "Üyelik" in product:
                    price = random.uniform(80, 200)
                elif "Roaming" in product or "Pasaport" in product:
                    price = random.uniform(150, 400)
                elif "UC" in product or "Cüzdan" in product:
                    price = random.uniform(50, 300)
                else:
                    price = random.uniform(20, 100)

                # Kanal seçimi (Gençler dijital, yaşlılar fiziksel)
                if age < 40:
                    channel = random.choice(CHANNELS_DIGITAL)
                else:
                    channel = random.choice(CHANNELS_DIGITAL + CHANNELS_PHYSICAL)

                days_ago = random.randint(1, 360)
                score = random.randint(1, 5) # AI için engagement skoru

                rows.append((cid, product, days_ago, channel, round(price, 2), score))

        cur.executemany(insert_query, rows)
        return len(rows)


if __name__ == "__main__":
    total = seed_history()
    print(f"✅ Smart Seed OK: {total} adet tutarlı purchase_history kaydı basıldı.")