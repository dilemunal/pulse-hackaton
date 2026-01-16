"""
Seed ~120 realistic Vodafone TR-like products into Postgres for Pulse (demo).

What this gives you:
- A "stable" Product Catalog knowledge source (SQL truth)
- Enough variety + metadata for RAG filters (category/segment/channel/contract/eligibility hints)

AI concept note:
- This is the "catalog truth source". RAG index will be derived from here.
"""

from __future__ import annotations
import os
import sys

# Allow running this file directly: `python3 scripts/products_seed.py`
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import json
import random
from typing import Any, Dict, List, Tuple

from src.db.connection import db_cursor


def _p(code: str, name: str, category: str, price: float, specs: Dict[str, Any]) -> Tuple[str, str, str, float, str]:
    return (code, name, category, float(price), json.dumps(specs, ensure_ascii=False))


def seed_products(*, random_seed: int = 42) -> int:
    random.seed(random_seed)

    with db_cursor() as (_conn, cur):
        # Recreate table (demo)
        cur.execute("DROP TABLE IF EXISTS products CASCADE;")
        cur.execute(
            """
            CREATE TABLE products (
                id SERIAL PRIMARY KEY,
                product_code VARCHAR(100) UNIQUE,
                name VARCHAR(255),
                category VARCHAR(100),
                price DECIMAL(10, 2),
                currency VARCHAR(10) DEFAULT 'TRY',
                specifications JSONB,
                is_active BOOLEAN DEFAULT TRUE
            );
            """
        )

        products: List[Tuple[str, str, str, float, str]] = []
        n = 1

        # ------------------------------------------------------------
        # 1) Faturalı Tarifeler (Red, Online Fırsat, vb.)
        # Vodafone site isim kalıpları: "Online Fırsat 2025 20 GB" vb. :contentReference[oaicite:1]{index=1}
        # ------------------------------------------------------------
        red_core = [
            ("Red 20GB", 520),
            ("Red 30GB", 620),
            ("Red 40GB", 740),
            ("Red Sınırsız İletişim 40GB", 790),
            ("Red Sınırsız Video 60GB", 890),
            ("Red Elite Sınırsız", 1190),
        ]
        for base_name, base_price in red_core:
            # Store version
            code = f"TRF-{n:04d}"
            products.append(
                _p(
                    code,
                    base_name,
                    "Tariff",
                    base_price,
                    {
                        "segment": "Red",
                        "subscription_type": "Postpaid",
                        "channel": "Store",
                        "contract_months": 12,
                        "eligible": {"requires_no_overdue_bill": True},
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

            # Online exclusive variant (slightly cheaper)
            code = f"TRF-{n:04d}"
            products.append(
                _p(
                    code,
                    f"{base_name} (Online'a Özel)",
                    "Tariff",
                    max(base_price - 60, 0),
                    {
                        "segment": "Red",
                        "subscription_type": "Postpaid",
                        "channel": "Online",
                        "contract_months": 12,
                        "discount": True,
                        "eligible": {"requires_esim_or_courier_activation": True},
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        # Online Fırsat 2025 style
        online_firsat = [
            ("Online Fırsat 2025 20 GB", 520),
            ("Online Fırsat 2025 30 GB", 620),
            ("Online Fırsat 2025 40 GB", 740),
        ]
        for name, price in online_firsat:
            code = f"TRF-{n:04d}"
            products.append(
                _p(
                    code,
                    name,
                    "Tariff",
                    price,
                    {
                        "segment": "Online",
                        "subscription_type": "Postpaid",
                        "channel": "Online",
                        "contract_months": 12,
                        "perks": ["Online'a özel avantajlar"],
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 2) FreeZone / Genç tarifeler (isim örnekleri sayfada geçiyor) :contentReference[oaicite:2]{index=2}
        # ------------------------------------------------------------
        freezone_base = [
            ("Genç Bütçe Dostu 32GB Paketi", 399),
            ("Genç Bütçe Dostu 40GB Paketi", 449),
            ("FreeZone Gamer 30GB", 430),
            ("FreeZone 10GB", 249),
            ("FreeZone 20GB", 319),
        ]
        for name, price in freezone_base:
            # Store
            code = f"TRF-{n:04d}"
            products.append(
                _p(
                    code,
                    name,
                    "Tariff",
                    price,
                    {
                        "segment": "FreeZone",
                        "subscription_type": "Postpaid",
                        "channel": "Store",
                        "contract_months": 12,
                        "perks": ["FreeZone ayrıcalıkları"],
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

            # Online
            code = f"TRF-{n:04d}"
            products.append(
                _p(
                    code,
                    f"{name} (Online'a Özel)",
                    "Tariff",
                    max(price - 40, 0),
                    {
                        "segment": "FreeZone",
                        "subscription_type": "Postpaid",
                        "channel": "Online",
                        "contract_months": 12,
                        "discount": True,
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 3) Faturasız / Kolay Paket
        # ------------------------------------------------------------
        prepaid = [
            ("Kolay Paket 10GB", 250),
            ("Kolay Paket 20GB", 320),
            ("Kolay Paket 30GB", 390),
            ("Haftalık 1GB", 49),
            ("Haftalık 5GB", 99),
            ("Günlük 1GB", 25),
        ]
        for name, price in prepaid:
            code = f"PP-{n:04d}"
            products.append(
                _p(
                    code,
                    name,
                    "Prepaid",
                    price,
                    {
                        "segment": "Prepaid",
                        "subscription_type": "Prepaid",
                        "channel": random.choice(["SMS", "Yanımda App", "USSD", "Store"]),
                        "validity": "Daily" if "Günlük" in name else "Weekly" if "Haftalık" in name else "Monthly",
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 4) Pass / Add-on paketleri (Video/Sosyal/Müzik/Gaming) (demo)
        # ------------------------------------------------------------
        passes = ["Gaming Pass", "Video Pass", "Sosyal Pass", "Müzik Pass", "İletişim Pass", "Red Pass"]
        for p in passes:
            # Unlimited monthly
            code = f"ADD-{n:04d}"
            products.append(
                _p(
                    code,
                    f"Sınırsız {p}",
                    "Addon",
                    129,
                    {"type": "Pass", "quota": "Unlimited", "validity": "Monthly", "channel": "Yanımda App"},
                )
            )
            n += 1

            # Daily
            code = f"ADD-{n:04d}"
            products.append(
                _p(
                    code,
                    f"Günlük {p}",
                    "Addon",
                    29,
                    {"type": "Pass", "quota": "Unlimited", "validity": "24 Hours", "channel": "Yanımda App"},
                )
            )
            n += 1

        extras = [
            ("Ek 1GB", 35),
            ("Ek 5GB", 89),
            ("Ek 10GB", 129),
            ("Durma Özelliği", 0),
            ("Güvenli İnternet", 19),
        ]
        for name, price in extras:
            code = f"ADD-{n:04d}"
            products.append(
                _p(code, name, "Addon", price, {"type": "TopUp", "channel": random.choice(["SMS", "Yanımda App", "Web"])})
            )
            n += 1

        # ------------------------------------------------------------
        # 5) Ev interneti & RedBox (sayfalarda ürün isim kalıbı var) :contentReference[oaicite:3]{index=3}
        # ------------------------------------------------------------
        home = [
            ("Evde Fiber 200", 799),
            ("Evde Fiber 1000", 1149),
            ("Evde Fiber 100", 699),
            ("Evde Fiber 500", 999),
        ]
        for name, price in home:
            code = f"HOME-{n:04d}"
            products.append(
                _p(
                    code,
                    name,
                    "HomeInternet",
                    price,
                    {
                        "segment": "Home",
                        "contract_months": 12,
                        "includes": ["Modem", "Kurulum"],
                        "speed_mbps": int("".join([c for c in name if c.isdigit()]) or "0"),
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        redbox = [
            ("5G RedBox 200GB", 499),
            ("5G RedBox 300GB", 599),
            ("5G RedBox Sınırsız", 799),
        ]
        for name, price in redbox:
            code = f"HOME-{n:04d}"
            products.append(
                _p(
                    code,
                    name,
                    "HomeInternet",
                    price,
                    {
                        "segment": "RedBox",
                        "type": "WirelessHomeInternet",
                        "contract_months": 12,
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 6) Roaming / Pasaport / Yurt Dışı paketleri (sayfada yer alıyor) :contentReference[oaicite:4]{index=4}
        # ------------------------------------------------------------
        roaming = [
            ("Yurt Dışı 1GB Paketi", 199),  # sayfada fiyat güncellemesi bilgisi geçiyor :contentReference[oaicite:5]{index=5}
            ("Pasaport Avrupa (Günlük)", 190),
            ("Pasaport Dünya (Günlük)", 230),
            ("Her Şey Dahil Pasaport", 299),
            ("Yurt Dışı 3GB Paketi", 399),
            ("Yurt Dışı 5GB Paketi", 549),
        ]
        for name, price in roaming:
            code = f"ROAM-{n:04d}"
            products.append(
                _p(
                    code,
                    name,
                    "Roaming",
                    price,
                    {
                        "segment": "Roaming",
                        "validity": "Daily" if "Günlük" in name else "Weekly",
                        "eligible": {"requires_identity_verification": True},
                        "source": "vodafone_tr_like",
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 7) Cihazlar (faturaya ek ürün sayfaları var; isimleri gerçekçi) :contentReference[oaicite:6]{index=6}
        # ------------------------------------------------------------
        phones = [
            "iPhone 15 Pro Max",
            "iPhone 15 Pro",
            "iPhone 15",
            "iPhone 14",
            "Samsung Galaxy S24 Ultra",
            "Samsung Galaxy S24",
            "Samsung Galaxy S24 FE",
            "Samsung Galaxy A55",
            "Xiaomi Redmi Note 13 Pro",
            "Huawei Nova 11",
        ]
        storages = ["128GB", "256GB", "512GB"]
        for model in phones:
            for st in storages:
                # Çok kaba demo fiyat (gerçek birebir olması şart değil)
                base = 25000 if "A55" in model else 35000 if "Redmi" in model else 45000
                if "S24 Ultra" in model:
                    base = 70000
                if "iPhone 15 Pro Max" in model:
                    base = 85000
                if "iPhone 15 Pro" in model:
                    base = 75000
                if "iPhone 15" in model:
                    base = 58000
                if "iPhone 14" in model:
                    base = 45000

                add = 0
                if st == "256GB":
                    add = 4000
                if st == "512GB":
                    add = 9000

                code = f"DEV-{n:04d}"
                products.append(
                    _p(
                        code,
                        f"{model} {st}",
                        "Device",
                        base + add,
                        {
                            "brand": model.split()[0],
                            "storage": st,
                            "payment": "Faturaya Ek",
                            "installments": 12,
                            "eligible": {
                                "requires_no_overdue_bill": True,
                                "requires_no_recent_sim_change_48h": True,
                            },
                            "source": "vodafone_tr_like",
                        },
                    )
                )
                n += 1

        # Accessories / wearables (demo)
        accessories = [
            ("Apple Watch Series 9", 17000, "Apple"),
            ("AirPods Pro (2. Nesil)", 9000, "Apple"),
            ("Samsung Galaxy Watch 6", 7000, "Samsung"),
            ("Samsung Galaxy Buds2 Pro", 3500, "Samsung"),
            ("JBL Flip 6", 4000, "JBL"),
            ("PlayStation 5 Slim", 24000, "Sony"),
        ]
        for name, price, brand in accessories:
            code = f"ACC-{n:04d}"
            products.append(_p(code, name, "Accessory", price, {"brand": brand, "payment": "Faturaya Ek", "installments": 12}))
            n += 1

        # ------------------------------------------------------------
        # 8) Dijital servisler / finans / güvenlik (demo)
        # ------------------------------------------------------------
        services = [
            ("Vodafone Pay Kart", 20, "Finance"),
            ("Mobil Ödeme", 0, "Finance"),
            ("Güvenli Depo 500GB", 39, "Service"),
            ("E-Fatura", 59, "Business"),
            ("Bulut Santral", 89, "Business"),
            ("TV+ Premium", 49, "Service"),
        ]
        for name, price, cat in services:
            code = f"MSC-{n:04d}"
            products.append(_p(code, name, cat, price, {"type": cat, "channel": "Yanımda App"}))
            n += 1

        # Ensure we are at least 100+
        # If still below 100 due to list size changes, create extra realistic variants
        while len(products) < 120:
            # Create tariff variants: quota & online
            gb = random.choice([5, 10, 15, 20, 30, 40, 60])
            seg = random.choice(["Red", "FreeZone", "Uyumlu"])
            ch = random.choice(["Store", "Online"])
            price = 199 + gb * 10 + (80 if seg == "Red" else 0) - (30 if ch == "Online" else 0)
            code = f"TRF-{n:04d}"
            products.append(
                _p(
                    code,
                    f"{seg} {gb}GB {'(Online’a Özel)' if ch == 'Online' else ''}".strip(),
                    "Tariff",
                    price,
                    {
                        "segment": seg,
                        "subscription_type": "Postpaid",
                        "channel": ch,
                        "contract_months": 12,
                        "quota_gb": gb,
                        "source": "vodafone_tr_like_generated",
                    },
                )
            )
            n += 1

        # Insert
        cur.executemany(
            "INSERT INTO products (product_code, name, category, price, specifications) VALUES (%s, %s, %s, %s, %s)",
            products,
        )

        return len(products)


if __name__ == "__main__":
    total = seed_products()
    print(f"✅ Seed OK: {total} ürün products tablosuna basıldı.")
