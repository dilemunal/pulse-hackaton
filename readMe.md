
# Vodafone Pulse - Contextual Sales AI (Hackathon Project)

**Pulse**, telekomünikasyon sektörü için geliştirilmiş, **"World Context" (Dünya Bağlamı)** ile **"Customer DNA" (Müşteri Personası)** verilerini birleştirerek hiper-kişiselleştirilmiş satış fırsatları yaratan yeni nesil bir yapay zeka motorudur.

Standart "Kampanya Yönetimi" sistemlerinin aksine Pulse, sadece müşterinin geçmişine bakmaz; o an dışarıda ne olduğuna (Hava durumu, viral müzik listeleri, yaklaşan tatiller, gündem haberleri) bakar ve müşterinin ihtiyaçlarıyla en alakalı ürünü (RAG kullanarak) eşleştirir.

## 🎯 Projenin Amacı ve Vizyonu

Geleneksel pazarlama genellikle "Herkese aynı SMS" veya sadece "Paketin bitiyor, yenileyelim" mantığıyla çalışır. **Pulse** ise şu soruyu sorar:

> *"Şu an İstanbul'da yağmur yağıyor, hafta sonu geliyor ve bu müşteri bir 'Gamer'. Ona evde kalıp oyun oynaması için ne önerebiliriz?"*

**Temel Yetenekler:**

1. **World Listener (Dünya Dinleyicisi):** RSS kaynaklarını, Google Trends verilerini, resmi tatilleri ve hava durumunu sürekli tarar. LLM ile bu verileri "Pazarlanabilir Sinyallere" (Marketable Signals) dönüştürür.
2. **Persona Enrichment (Persona Zenginleştirme):** Ham CRM verilerini (Data kullanımı, cihaz modeli vb.) alır ve LLM ile müşteriye bir "Ruh" katar (Örn: "Plaza Çalışanı", "Teknoloji Tutkunu Öğrenci").
3. **Semantic Product Search (RAG):** Vodafone ürün kataloğunu vektör veritabanında (ChromaDB) tutar. "Yurt dışına çıkan birine uygun paket" gibi doğal dil sorgularıyla en doğru ürünü bulur.
4. **Sales Brain (Satış Beyni):** Gündem sinyalini, müşteri personasını ve ürünü birleştirerek müşteriye özel, samimi ve ikna edici bir satış metni yazar.

---

## 🏗️ Mimari ve Bileşenler

Demo proje Python tabanlıdır ve modüler bir mikro-servis mimarisine uygun tasarlanmıştır:

* **`src/app/workflows/trend_job.py`**: Dış dünyayı tarar, `data/cache/intelligence.json` dosyasına gündem özetini çıkarır.
* **`src/app/workflows/persona_job.py`**: Müşterileri analiz eder ve veritabanındaki profillerini zenginleştirir.
* **`src/app/workflows/sales_workflow.py`**: Orkestra şefidir. Stratejist AI ve Sales Brain AI ajanlarını çalıştırarak nihai teklifi oluşturur.
* **`src/tools/product_search.py`**: Ürün kataloğu üzerinde RAG (Retrieval-Augmented Generation) araması yapar.
* **Veritabanları:**
* **PostgreSQL:** Müşteri, ürün ve satış geçmişi verileri için.
* **ChromaDB:** Ürün kataloğu vektör indekslemesi için.



---

## 🛠️ Kurulum ve Çalıştırma Rehberi

Bu projeyi kendi lokalinizde veya başka bir sunucuda çalıştırmak için aşağıdaki adımları izleyin.

### 1. Ön Hazırlıklar

* Python 3.10+
* Docker & Docker Compose

### 2. Projeyi Klonlayın

```bash
cd pulse-hackaton
```

### 3. Sanal Ortam (Virtual Environment) Oluşturma

```bash
python -m venv .venv
# Windows için:
.venv\Scripts\activate
# Mac/Linux için:
source .venv/bin/activate

```

### 4. Bağımlılıkları Yükleme

```bash
pip install -r requirements.txt

```

### 5. Çevresel Değişkenler (.env)

Projenin kök dizininde `.env` isimli bir dosya oluşturun. Aşağıdaki şablonu kopyalayıp ilgili alanları (token, şifreler vb.) doldurun.

```ini
# --- AI / LLM Gateway Config ---
MODEL_GATEWAY_URL=https://practicus.vodafone.local/models/model-gateway-ai-hackathon/latest/v1
token=
username=
pwd=
LLM_CHAT_MODEL=practicus/gpt-oss-20b-hackathon
LLM_EMBEDDING_MODEL=practicus/gemma-300m-hackathon

# --- Proxy Ayarları (Gerekliyse) ---
PROXY_IP=
PROXY_PORT=
PROXY_USER=
PROXY_PASS=

# --- Database Config (Docker Compose ile uyumlu) ---
DB_HOST=localhost
DB_PORT=5435
DB_USER=
DB_PASS=
DB_NAME=

# --- Vector DB Config ---
VECTOR_DB_HOST=localhost
VECTOR_DB_PORT=8001

# --- App Settings ---
TREND_TTL_HOURS=6
HTTPX_VERIFY_TLS=False

```

### 6. Altyapıyı Ayağa Kaldırma (Docker)

PostgreSQL ve ChromaDB servislerini başlatın:

```bash
docker-compose up -d

```

### 7. Veri Tohumlama (Data Seeding)

Proje ilk açıldığında veritabanları boştur. Demo için gerekli olan sentetik verileri ve ürün kataloğunu yüklemek için sırasıyla şu scriptleri çalıştırın:

```bash
# 1. Müşteri verilerini oluştur (~1500 adet)
python scripts/seed_customers.py

# 2. Müşteri davranış verilerini oluştur
python scripts/seed_behavior.py

# 3. Satın alma geçmişi oluştur
python scripts/seed_history.py

# 4. Ürün kataloğunu oluştur
python scripts/products_seed.py

```

### 8. Vektör İndeksini Oluşturma (RAG)

Ürünlerin yapay zeka tarafından aranabilmesi için ChromaDB indeksini oluşturun:

```bash
# PYTHONPATH kök dizini görecek şekilde çalıştırılmalıdır
PYTHONPATH=. python3 scripts/index/build_product_catalog_index.py

```

---

## 🚀 Sistemi Çalıştırma (Workflows)

Tüm hazırlıklar tamamlandıktan sonra Pulse motorunu parça parça veya bütün olarak çalıştırabilirsiniz.

**Adım 1: Gündemi Analiz Et (Trend Job)**
Dünyadaki gelişmeleri tarar ve önbelleğe alır.

```bash
PYTHONPATH=. python3 src/app/workflows/trend_job.py

```

**Adım 2: Müşteri Personalarını Çıkar (Persona Job)**
Müşterileri analiz edip etiketler (Örn: "Gamer", "Gezgin").

```bash
PYTHONPATH=. python3 src/app/workflows/persona_job.py

```

**Adım 3: Satış Motorunu Çalıştır (Sales Workflow)**
Tüm verileri birleştirip nihai satış önerilerini ve metinlerini üretir.

```bash
PYTHONPATH=. python3 src/app/workflows/sales_workflow.py

```

### API & Dashboard (Opsiyonel)

Sonuçları JSON olarak sunan basit API'yi ayağa kaldırmak için:

```bash
uvicorn src.app.app.app:app --reload --port 8000

```

Diğer dosyada iletilen IOS app demosunu çalıştırarak veya aşağıdaki curl ile Postman kullanarak responseları görebilirsiniz. :

curl --location 'http://127.0.0.1:8000/api/sales-opportunities/1'

---

## 📁 Proje Yapısı

```
pulse-hackaton/
├── config/             # Ayarlar ve şemalar
├── data/               # Cache ve log dosyaları
├── scripts/            # Veri üretme ve indexleme scriptleri
├── src/
│   ├── adapters/       # LLM, DB ve Vektör DB bağlantı katmanları
│   ├── app/
│   │   ├── workflows/  # Ana iş akışları (Trend, Persona, Sales)
│   │   └── app/        # FastAPI uygulaması
│   ├── domain/         # İş kuralları (Safety filters vb.)
│   └── tools/          # RAG arama aracı
├── docker-compose.yml  # Altyapı servisleri
└── requirements.txt    # Python kütüphaneleri

```

---

**Pixel**