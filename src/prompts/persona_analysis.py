# DOSYA: src/prompts/persona_analysis.py
"""
Persona analysis prompt builder (Pulse demo).

What this module does:
- Defines the SYSTEM prompt (stable behavioral contract)
- Defines the USER prompt template (how we feed customer features)
- Enforces: output must be a deterministic JSON object

AI concept note:
- Prompt template = reusable contract.
- Output schema = deterministic JSON so DB updates don't depend on free-form text.

Language contract:
- label, reasoning, interests MUST be Turkish.
- predicted_commute_type is a fixed enum in English (stable downstream).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


# ----------------------------
# Output schema (inline, demo)
# ----------------------------
# Later you can move this into: config/schemas/persona_result.schema.json
PERSONA_OUTPUT_SCHEMA_HINT: Dict[str, Any] = {
    "results": [
        {
            "id": "int (customer id)",
            "calculated_churn_risk": "int 0-100",
            "calculated_digital_score": "int 0-100",
            "predicted_commute_type": "Driver | Public Transport | HomeOffice | Passenger",
            "is_frequent_traveler": "boolean",
            "reasoning": "string (evidence-based, short, Turkish)",
            "label": "string (3-5 words persona title, Turkish)",
            "interests": ["string", "string", "string (Turkish)"],
        }
    ]
}


# ----------------------------
# System prompt
# ----------------------------
def build_persona_system_prompt() -> str:
    """
    System prompt: stable behavioral contract.

    Keep this relatively stable.
    Put "rules" here, and put "data" into the user prompt.
    """
    return """
Sen Vodafone'un "Lead Data Scientist" ve "Davranışsal Analist" yapay zekasısın.
Görevin: Müşteri verilerindeki sinyalleri birleştirerek (connecting the dots) persona çıkarmak
ve eksik metrikleri hesaplamak.

Dil kuralları:
- ÇIKTI DİLİ: label, reasoning ve interests alanları mutlaka TÜRKÇE olmalı.
- İngilizce kelime kullanma (5G, iPhone, TikTok gibi özel isimler hariç).
- predicted_commute_type alanı SADECE şu enumlardan biri olmalı (bu enum İngilizce kalacak):
  Driver | Public Transport | HomeOffice | Passenger

Kurallar (demo ama deterministik yaklaşım):
- Asla uydurma veri ekleme. Sadece verilen alanlardan çıkarım yap.
- Çelişki görürsen bunu PERSONA'nın bir parçası olarak açıkla (ör: "faturasız ama premium cihaz").
- Hesapladığın skorlar 0-100 aralığında olsun ve uç kararları gerekçelendir.
- Çıktıyı SADECE JSON olarak ver (metin açıklama yok).
- PII: İsim/numara gibi alanları yeniden üretme; sadece "id" ile referans ver.

Hesaplama rehberi:
1) CHURN RİSKİ (0-100):
   - Network experience kötü (4-5) => risk yüksek.
   - ARPU yüksek + cihaz eski + network kötü => çok yüksek (90+).
   - App giriş yüksek + VAS var => risk düşür.
    - Eğer data usage çok düşükse (aylık 1GB altı) risk artır.
    - Eğer contract_expiry_days azsa (30 gün altı) risk artır.
    - Eğer credit_score düşükse (800 altı) risk artır.
    - Eğer wallet_active ise risk azalt.
    - Eğer payment_method "direct debit" ise risk azalt. 
2) DİJİTAL SKOR (0-100):
   - App login + wallet_active + cihaz yaşı (daha yeni daha iyi) + genç/yaşlı adaptasyonu.
   - 70+ olup app kullanıyorsa, adapte olmuş kabul et ve yüksek skor ver.
   - Eğer device_model üst segment ise (iPhone 15+ / Galaxy S20+) skor artır.
   - Eğer data_usage yüksekse (aylık 35GB+) skor artır.
   - Eğer network_experience iyi (1-2) ise skor artır.
   -
3) COMMUTE (ulaşım) tahmini:
   - İstanbul + düşük kredi => Public Transport
   - Vodafone Pay veya Faturana Yansıt ile İstanbulkart yüklemesi yapılıyorsa
   - 30-50 + yüksek kredi => Driver
   - Genç + yüksek data usage + app login => Passenger
   - Ev interneti yok + data çok yüksek => HomeOffice / Mobile worker sinyali
   - Eğer şehir küçükse ve kredi yüksekse Driver.
   - Eğer şehir büyükse ve kredi düşükse Public Transport.
4) SIK SIK SEYAHAT EDEN Mİ? (boolean):
   - Eğer şehirlerarası data kullanımı yüksekse (aylık 10GB+)

4) PERSONA LABEL (3-5 kelime):
   - Çelişkileri yakala ve yaratıcı ama veriye dayalı isim ver.
   - Örn: "Teknoloji Meraklısı Genç Profesyonel", "Ekonomik Düşünen Aile Babası", "Sık Seyahat Eden Dijital Göçebe"
   -
5) INTERESTS (3 adet):
   - VAS ve davranış sinyallerinden türet.
   - Örn: "Mobil Oyunlar", "Sosyal Medya", "Online Alışveriş", "Video Akış", "Müzik Dinleme", "Seyahat ve Gezi", "Finans ve Yatırım", "Sağlık ve Fitness", "Teknoloji ve Gadget'lar"

Çıktı formatı:
- SADECE JSON döndür.
- Sadece Türkçe çıktılar ver.
- En üstte { "results": [...] } objesi olmalı.
""".strip()


# ----------------------------
# User prompt
# ----------------------------
def build_persona_user_prompt(customers: List[Dict[str, Any]]) -> str:
    """
    customers: list of dicts.

    We pass JSON to reduce formatting drift and prompt injection via string concat.

    Recommended keys per customer:
    - id (int)
    - gender, age, city
    - subscription_type, tariff_segment
    - arpu, contract_expiry_days
    - data_usage_gb, data_quota_usage_percent, app_monthly_login_count
    - active_vas_subscriptions (list[str])
    - device_model, device_age_months, network_experience_score
    - credit_score, wallet_active, payment_method
    - home_internet_type
    """
    payload = json.dumps(customers, ensure_ascii=False, indent=2)

    return f"""
Aşağıda JSON formatında müşteri verileri var.
Her müşteri için çıktı üret.

MÜŞTERİ VERİLERİ (JSON):
{payload}

ÇIKTI ŞEMASI İPUCU:
{json.dumps(PERSONA_OUTPUT_SCHEMA_HINT, ensure_ascii=False)}

Kurallar:
- SADECE JSON döndür.
- "results" listesi her müşteri için 1 çıktı içermeli.
- label/reasoning/interests TÜRKÇE olmalı.
- predicted_commute_type enum: Driver | Public Transport | HomeOffice | Passenger
""".strip()
