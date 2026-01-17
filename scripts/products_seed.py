# DOSYA: scripts/products_seed.py
"""
Seed ~120 realistic Vodafone TR-like products into Postgres for Pulse (demo).
(GELİŞTİRİLMİŞ VERSİYON - AI DOSTU AÇIKLAMALAR İLE)

Değişiklikler:
- Ürünlere 'description' ve 'keywords' eklendi.
- Video Pass ile İletişim Pass arasındaki fark yapay zekaya öğretildi.
- Red tarifelerine ve cihazlara persona ipuçları eklendi.
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
                        # AI İÇİN EKLENEN KISIM:
                        "description": "Bol internetli, yurt dışında da geçerli, her şey dahil premium tarife. Seyahat edenler ve iş insanları için ideal.",
                        "keywords": ["seyahat", "yurt dışı", "premium", "iş", "konfor", "sınırsız", "roaming"],
                        "best_for_persona": "Gezgin / İş İnsanı"
                    },
                )
            )
            n += 1

            # Online exclusive variant
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
                        "description": "Online'a özel indirimli Red tarifesi. Yüksek veri ve premium ayrıcalıklar.",
                        "keywords": ["online", "indirim", "fırsat", "red", "premium"]
                    },
                )
            )
            n += 1

        # Online Fırsat
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
                        "description": "İnternetten başvuranlara özel yüksek GB'lı avantajlı tarife.",
                        "keywords": ["ekonomik", "bol internet", "fırsat", "dijital"]
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 2) FreeZone / Genç
        # ------------------------------------------------------------
        freezone_base = [
            ("Genç Bütçe Dostu 32GB Paketi", 399),
            ("Genç Bütçe Dostu 40GB Paketi", 449),
            ("FreeZone Gamer 30GB", 430),
            ("FreeZone 10GB", 249),
            ("FreeZone 20GB", 319),
        ]
        for name, price in freezone_base:
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
                        "description": "26 yaş altı gençler için bol internetli, oyun ve sosyal medya avantajlı tarife.",
                        "keywords": ["genç", "öğrenci", "oyun", "sosyal medya", "ekonomik", "freezone"],
                        "best_for_persona": "Genç / Öğrenci"
                    },
                )
            )
            n += 1

            # Online variant
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
                        "discount": True,
                        "description": "Gençlere özel online indirimli bol internet paketi.",
                        "keywords": ["genç", "indirim", "online", "gamer"]
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
                        "channel": "Yanımda App",
                        "validity": "Daily" if "Günlük" in name else "Weekly" if "Haftalık" in name else "Monthly",
                        "description": "Taahhütsüz, yükle-kullan faturasız paket. Kısa süreli ihtiyaçlar veya bütçe kontrolü için.",
                        "keywords": ["faturasız", "taahhütsüz", "kontörlü", "kolay paket", "pratik"]
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 4) Pass / Add-on (KRİTİK GÜNCELLEME: Video vs İletişim Ayrımı)
        # ------------------------------------------------------------
        passes = ["Gaming Pass", "Video Pass", "Sosyal Pass", "Müzik Pass", "İletişim Pass", "Red Pass"]
        for p in passes:
            # Yapay Zeka için Açıklamalar
            desc = ""
            keys = []
            
            if "Video" in p:
                desc = "YouTube, Netflix, Amazon Prime gibi uygulamalarda video İZLEMEK için sınırsız internet. Görüntülü konuşma (FaceTime/WhatsApp) için DEĞİLDİR."
                keys = ["izleme", "dizi", "film", "youtube", "netflix", "eğlence", "video akış"]
            elif "İletişim" in p:
                desc = "WhatsApp, Messenger, FaceTime, Telegram gibi uygulamalarda mesajlaşma ve GÖRÜNTÜLÜ KONUŞMA için sınırsız internet. Sevdiklerinizle iletişim kurun."
                keys = ["konuşma", "görüntülü", "whatsapp", "facetime", "iletişim", "aramak", "sesli"]
            elif "Sosyal" in p:
                desc = "Instagram, Facebook, Twitter (X) gibi sosyal medya uygulamaları için sınırsız internet."
                keys = ["sosyal medya", "instagram", "twitter", "facebook", "gezinti", "paylaşım"]
            elif "Gaming" in p:
                desc = "PUBG, LoL, Mobile Legends gibi mobil oyunlar için kotadan yemeyen sınırsız internet. Düşük ping sağlar."
                keys = ["oyun", "gamer", "pubg", "hız", "düşük ping", "rekabet"]
            elif "Müzik" in p:
                desc = "Spotify, Apple Music gibi platformlarda sınırsız müzik dinleme."
                keys = ["müzik", "spotify", "şarkı", "podcast"]
            else:
                desc = "Popüler uygulamalarda geçerli sınırsız internet kullanımı."
                keys = ["sınırsız", "pass", "ek paket"]

            # Unlimited monthly
            code = f"ADD-{n:04d}"
            products.append(
                _p(
                    code,
                    f"Sınırsız {p}",
                    "Addon",
                    129,
                    {
                        "type": "Pass",
                        "quota": "Unlimited",
                        "validity": "Monthly",
                        "channel": "Yanımda App",
                        "description": desc,
                        "keywords": keys
                    },
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
                    {
                        "type": "Pass",
                        "quota": "Unlimited",
                        "validity": "24 Hours",
                        "channel": "Yanımda App",
                        "description": f"24 saat boyunca geçerli. {desc}",
                        "keywords": keys + ["günlük", "kısa süreli", "24 saat"]
                    },
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
            desc = "Ekstra internet paketi."
            keys = ["ek internet", "kota doldu", "internet lazım"]
            
            if "Güvenli" in name:
                desc = "Zararlı içeriklerden ve dolandırıcılıktan koruyan güvenli internet servisi. Aileler ve yaşlılar için önerilir."
                keys = ["güvenlik", "koruma", "aile", "çocuk", "dolandırıcılık önleme"]

            products.append(
                _p(code, name, "Addon", price, {
                    "type": "TopUp", 
                    "channel": "Yanımda App",
                    "description": desc,
                    "keywords": keys
                })
            )
            n += 1

        # ------------------------------------------------------------
        # 5) Ev interneti & RedBox
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
                        "description": "Yüksek hızlı fiber ev interneti. Evden çalışanlar, oyuncular ve kalabalık aileler için.",
                        "keywords": ["ev interneti", "fiber", "hız", "sınırsız", "wifi", "evden çalışma"]
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 6) Roaming / Yurt Dışı
        # ------------------------------------------------------------
        roaming = [
            ("Yurt Dışı 1GB Paketi", 199),
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
                        "description": "Yurt dışında kendi tarifenizi veya ek paketinizi kullanmanızı sağlayan roaming paketi.",
                        "keywords": ["yurt dışı", "seyahat", "gezi", "roaming", "pasaport", "avrupa"]
                    },
                )
            )
            n += 1

        # ------------------------------------------------------------
        # 7) Cihazlar (iPhone vb.)
        # ------------------------------------------------------------
        phones = [
            "iPhone 15 Pro Max", "iPhone 15 Pro", "iPhone 15", "iPhone 14",
            "Samsung Galaxy S24 Ultra", "Samsung Galaxy S24", "Samsung Galaxy S24 FE",
            "Samsung Galaxy A55", "Xiaomi Redmi Note 13 Pro", "Huawei Nova 11",
        ]
        storages = ["128GB", "256GB", "512GB"]
        for model in phones:
            for st in storages:
                base = 25000 if "A55" in model else 35000 if "Redmi" in model else 45000
                if "S24 Ultra" in model: base = 70000
                if "iPhone 15 Pro Max" in model: base = 85000
                if "iPhone 15 Pro" in model: base = 75000
                if "iPhone 15" in model: base = 58000
                if "iPhone 14" in model: base = 45000

                add = 0
                if st == "256GB": add = 4000
                if st == "512GB": add = 9000

                # AI için açıklama üretimi
                desc = "Akıllı telefon."
                keys = ["telefon", "cihaz"]
                if "Pro" in model or "Ultra" in model:
                    desc = "En son teknolojiye sahip, yüksek performanslı ve prestijli akıllı telefon. Profesyonel kamera ve yüksek hız arayanlar için."
                    keys = ["lüks", "prestij", "fotoğraf", "kamera", "teknoloji", "yüksek performans", "yeni"]
                elif "A55" in model or "Redmi" in model or "FE" in model:
                    desc = "Fiyat/performans oranı yüksek, modern akıllı telefon. Günlük kullanım ve bütçe dostu yenileme için ideal."
                    keys = ["fiyat performans", "ekonomik", "yeni telefon", "android", "öğrenci"]

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
                            "eligible": {"requires_no_overdue_bill": True},
                            "description": desc,
                            "keywords": keys,
                            "best_for_persona": "Teknoloji Meraklısı" if "Pro" in model else "Genel"
                        },
                    )
                )
                n += 1

        # Accessories
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
            products.append(_p(code, name, "Accessory", price, {
                "brand": brand, 
                "payment": "Faturaya Ek", 
                "installments": 12,
                "description": "Teknolojik aksesuar ve giyilebilir teknoloji ürünü.",
                "keywords": ["aksesuar", "kulaklık", "saat", "akıllı saat", "hoparlör", "hediye"]
            }))
            n += 1

        # ------------------------------------------------------------
        # 8) Dijital servisler / Finans
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
            products.append(_p(code, name, cat, price, {
                "type": cat, 
                "channel": "Yanımda App",
                "description": "Dijital katma değerli servis.",
                "keywords": ["servis", "dijital", "finans", "iş"]
            }))
            n += 1

        # Fill up to 120
        while len(products) < 120:
            gb = random.choice([5, 10, 15, 20, 30, 40, 60])
            seg = random.choice(["Red", "FreeZone", "Uyumlu"])
            ch = random.choice(["Store", "Online"])
            price = 199 + gb * 10
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
                        "quota_gb": gb,
                        "description": f"{seg} dünyasından bol internetli tarife.",
                        "keywords": ["tarife", "internet", seg.lower()]
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