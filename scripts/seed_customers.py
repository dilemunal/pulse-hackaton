"""
Seed ~1500 synthetic customers into Postgres (Pulse demo).

Creates:
- customers table (CRM truth source)

Design goals :
- Realistic-ish but intentionally "messy" data (no-bias)
- AI-derived fields are left empty ("Not Processed") for persona job later
"""

from __future__ import annotations

import os
import random
from typing import List, Tuple

from dotenv import load_dotenv

from src.db.connection import db_cursor

TR_NAMES_MALE = ["Ahmet", "Mehmet", "Mustafa", "Can", "Burak", "Emre", "Murat", "Hakan", "Oğuz", "Serkan", "Tolga", "Kerem", "Barış", "Efe", "Arda", "Kaan", "Mert"]
TR_NAMES_FEMALE = ["Ayşe", "Fatma", "Zeynep", "Elif", "Selin", "Gamze", "Buse", "Esra", "Merve", "İrem", "Derya", "Seda", "Gizem", "Hande", "Aslı", "Defne"]
LAST_NAMES = ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Öztürk", "Aydın", "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç"]
CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana", "Gaziantep", "Kocaeli", "Muğla", "Eskişehir", "Trabzon", "Samsun"]

ALL_DEVICES = [
    "iPhone 15 Pro Max", "Samsung S24 Ultra", "iPhone 14", "iPhone 11",
    "Samsung A55", "Samsung A54", "Redmi Note 13", "Huawei Nova 11", "Honor 90",
    "Samsung J7", "Redmi 9", "GM 22", "Poco M5", "Vivo Y36", "Reeder S19",
    "Nokia 3310 (New)", "iPhone 7"
]

ALL_VAS = ["Netflix", "Spotify", "YouTube Premium", "Amazon Prime", "Gamer Pass", "BeinConnect", "Exxen", "BluTV", "Tidal", "Duolingo", "LinkedIn Premium"]


def _safe_load_env() -> None:
    load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))


def seed_customers(*, n_customers: int = 1500, random_seed: int = 42) -> int:
    _safe_load_env()
    random.seed(random_seed)

    household_pool = [random.randint(10000, 99999) for _ in range(400)]

    with db_cursor() as (_conn, cur):
        cur.execute("DROP TABLE IF EXISTS customer_behavior CASCADE;")
        cur.execute("DROP TABLE IF EXISTS purchase_history CASCADE;")
        cur.execute("DROP TABLE IF EXISTS customers CASCADE;")

        cur.execute(
            """
            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                msisdn VARCHAR(20) UNIQUE,
                name VARCHAR(100),
                gender VARCHAR(10),
                age INTEGER,
                city VARCHAR(50),

                subscription_type VARCHAR(50),
                tariff_segment VARCHAR(50),

                tenure_months INTEGER,
                arpu DECIMAL(10,2),

                contract_expiry_days INTEGER,
                data_usage_gb DECIMAL(6,2),
                data_quota_usage_percent INTEGER,
                app_monthly_login_count INTEGER,
                active_vas_subscriptions TEXT[],
                marketing_permission BOOLEAN,

                home_internet_type VARCHAR(50),
                home_internet_speed INTEGER,
                is_convergence_customer BOOLEAN DEFAULT FALSE,

                device_model VARCHAR(100),
                device_age_months INTEGER,
                network_experience_score INTEGER,

                wallet_active BOOLEAN,
                last_month_wallet_spend DECIMAL(10,2),
                credit_score INTEGER,
                payment_method VARCHAR(50),

                churn_risk_score INTEGER,
                digital_score INTEGER,
                commute_type VARCHAR(50),
                is_frequent_traveler BOOLEAN,
                derived_interests TEXT[] DEFAULT '{}',
                ai_segmentation_label TEXT DEFAULT 'Not Processed',

                household_id INTEGER,
                last_nps_score INTEGER,
                has_open_complaint BOOLEAN DEFAULT FALSE
            );
            """
        )

        rows: List[Tuple] = []

        for _ in range(n_customers):
            if random.random() < 0.5:
                gender = "Male"
                name = f"{random.choice(TR_NAMES_MALE)} {random.choice(LAST_NAMES)}"
            else:
                gender = "Female"
                name = f"{random.choice(TR_NAMES_FEMALE)} {random.choice(LAST_NAMES)}"

            age = random.randint(18, 85)
            city = random.choice(CITIES)

            sub_type = random.choices(["Postpaid", "Prepaid"], weights=[60, 40])[0]

            if sub_type == "Postpaid":
                segment = random.choice(["Red", "Uyumlu", "FreeZone"])
                contract_days = random.randint(1, 730)
                payment_method = random.choice(["Auto-Pay", "Manual"])
                arpu = random.uniform(200, 3000)
            else:
                segment = random.choice(["Kolay Paket", "FreeZone"])
                contract_days = 0
                payment_method = "Manual"
                arpu = random.uniform(50, 400)

            device = random.choice(ALL_DEVICES)
            device_age = random.randint(0, 60)

            home_net = random.choice(["Fiber", "DSL", "No-Internet"])
            is_conv = True if home_net != "No-Internet" else False
            home_speed = random.choice([16, 24, 50, 100, 200, 500, 1000]) if home_net != "No-Internet" else 0

            data_usage = random.uniform(0.5, 150.0)
            quota_percent = random.randint(5, 100)
            app_login = random.randint(0, 100)

            has_vas = random.random() < 0.4
            active_vas = random.sample(ALL_VAS, k=random.randint(1, 3)) if has_vas else []

            wallet_active = random.choice([True, False])
            wallet_spend = random.uniform(0, 5000) if wallet_active else 0
            credit_score = random.randint(600, 1900)

            msisdn = f"5{random.choice(['42','32','55','44','49'])}{random.randint(1000000,9999999)}"

            rows.append(
                (
                    msisdn, name, gender, age, city,
                    sub_type, segment,
                    random.randint(1, 240), round(arpu, 2),
                    contract_days, round(data_usage, 2), quota_percent, app_login, active_vas, random.choice([True, False]),
                    home_net, home_speed, is_conv,
                    device, device_age, random.randint(1, 5),
                    wallet_active, round(wallet_spend, 2), credit_score, payment_method,
                    None, None, None, None, [], "Not Processed",
                    random.choice(household_pool), random.randint(0, 10), random.choice([True, False]),
                )
            )

        cur.executemany(
            """
            INSERT INTO customers (
                msisdn, name, gender, age, city,
                subscription_type, tariff_segment,
                tenure_months, arpu,
                contract_expiry_days, data_usage_gb, data_quota_usage_percent,
                app_monthly_login_count, active_vas_subscriptions, marketing_permission,
                home_internet_type, home_internet_speed, is_convergence_customer,
                device_model, device_age_months, network_experience_score,
                wallet_active, last_month_wallet_spend, credit_score, payment_method,
                churn_risk_score, digital_score, commute_type, is_frequent_traveler, derived_interests, ai_segmentation_label,
                household_id, last_nps_score, has_open_complaint
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )

        return len(rows)


if __name__ == "__main__":
    total = seed_customers()
    print(f"✅ Seed OK: {total} müşteri customers tablosuna basıldı.")
