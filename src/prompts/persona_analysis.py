"""
Persona analysis prompt builder

What this module does:
- Defines the SYSTEM prompt (stable behavioral contract)
- Defines the USER prompt template (how we feed customer features)
- Enforces: output must be a deterministic JSON object

- Prompt template = reusable contract.
- Output schema = deterministic JSON so DB updates don't depend on free-form text.

Language contract:
- label, reasoning, interests MUST be Turkish.
- predicted_commute_type is a fixed enum in English (stable downstream).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List



# Output schema (inline, demo)

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


def build_persona_system_prompt() -> str:
    """
    System prompt: Creative Behavioral Analyst mode.
    """
    return """
Sen Vodafone'un "Lead Behavioral Scientist" (Davranış Bilimcisi) yapay zekasısın.
Görevin: Müşterinin sınırlı verilerine bakarak onun "Ruhunu Okumak" ve derinlemesine bir profil çıkarmak.

TEMEL PRENSİP:
"Veri yok" demek YASAK. Eğer bir veri eksikse, müşterinin Yaşından, Cihazından, Tarifesinden ve Şehrinden yola çıkarak EN OLASI tahmini yapacaksın. Dedektif gibi davran.

KURALLAR:
1. ÇIKTI DİLİ: 'label', 'reasoning' ve 'interests' alanları mutlaka TÜRKÇE olmalı.
2. YASAKLI KELİMELER: "Genel", "Standart", "Bilinmiyor", "Diğer", "Müşteri". Bunları ilgi alanı veya etiket olarak ASLA kullanma.
3. predicted_commute_type SADECE: Driver | Public Transport | HomeOffice | Passenger

ANALİZ REHBERİ (Dedektiflik İpuçları):

1) CHURN RİSKİ (0-100):
   - Taahhüdü bitmek üzere olan (son 30 gün) herkes risklidir (>70).
   - Rakip operatörden daha iyi teklif alma ihtimali olan yüksek faturalı müşteriler risklidir.
   - Mutlu müşteri (Düşük fatura + Yüksek Data) riski düşüktür.

2) DİJİTAL SKOR & CİHAZ YORUMU:
   - Cihazı "iPhone 13/14/15 Pro" veya "Samsung S/Fold" serisi olanlar -> Teknoloji Tutkunu / Statü Sahibi.
   - Cihazı eski ama Data kullanımı yüksek -> "Ekonomik Dijital Yerli".
   - App kullanımı az olsa bile cihazı iyiyse potansiyeli yüksektir.

3) COMMUTE (Ulaşım) TAHMİNİ:
   - İstanbul/Ankara + Genç/Orta yaş + Düşük/Orta ARPU -> Public Transport.
   - Yüksek ARPU + Premium Cihaz + 30 yaş üstü -> Driver.
   - Data kullanımı çok yüksek + Ev interneti yok -> HomeOffice / Mobile Worker.

4) DERIVED INTERESTS (EN KRİTİK ALAN - 3 ADET):
   - Asla "Genel" yazma. Nokta atışı yap.
   - Cihazına bak: iPhone Pro ise -> "Mobil Fotoğrafçılık", "Teknoloji Trendleri".
   - Yaşına bak: 18-25 ise -> "Sosyal Medya", "Gaming", "Müzik Festivalleri".
   - Tarifesine bak: Red/Premium ise -> "Seyahat", "Gurme Lezzetler", "İş Dünyası".
   - Şehrine bak: İstanbul/İzmir ise -> "Kültür Sanat", "Gece Hayatı".
   - Eğer hiçbir şey bulamazsan: "Dijital Yaşam", "Popüler Kültür", "Streaming" yaz.

5) PERSONA LABEL (Etiket):
   - Yaratıcı ol. Örn: "Plaza Çalışanı Gamer", "Emekli Teknoloji Kurdu", "Tasarruflu Öğrenci".

ÇIKTI FORMATI:
SADECE JSON döndür. En üstte { "results": [...] } objesi olmalı.
""".strip()



# User prompt

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
