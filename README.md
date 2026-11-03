# İşlem İzleme ve Alarm Sistemi (IzlemeAlarm)

IzlemeAlarm, banka işlemleri için bir **işlem izleme (transaction monitoring) MVP'sidir**. Sistem; müşteri, hesap ve işlem verilerini CSV ile alır, yapılandırılabilir ve deterministik **R01–R15 kurallarıyla** şüpheli davranışları tespit eder ve üretilen alarmları (alert) analistlerin incelemesine sunar. Kimlik doğrulama JWT bearer token ile yapılır; yetkiler veritabanındaki rol ve izin tablolarından (RBAC) okunur.

Uygulama **yalnızca sentetik veri ve öğrenme amaçlıdır**; gerçek risk kararları için kullanılmamalıdır.

Ayrıntılı mimari ve özellik açıklaması için [Proje Rehberi](./PROJECT_GUIDE.md) dosyasına bakın.

## Özellikler

- CSV ile müşteri, hesap ve işlem içe aktarma; satır bazlı hata raporu ve şablon indirme
- R01–R15 tespit kuralları; eşik ve aktiflik durumlarının kural yönetim ekranından değiştirilmesi
- Alarm inceleme: filtreleme, ilgili işlemler ve müşteri geçmişi, analist notu, durum güncelleme
- İşlem analizi: gelen/giden akış, eşik yakını işlemler, müşteri/hesap bazlı bağlantı izleme
- Rol tabanlı yetkilendirme (`admin`, `analyst`) ve denetim kaydı (audit log)
- Streamlit arayüzü ve Türkçe/İngilizce, açık/koyu temalı React arayüzü (aynı API'yi kullanır)

## Teknoloji yığını

| Katman | Teknoloji |
| --- | --- |
| API | Python, FastAPI, Uvicorn |
| Veritabanı | PostgreSQL |
| ORM ve migrasyon | SQLAlchemy 2.x, Alembic |
| Kimlik doğrulama | PyJWT, bcrypt |
| Streamlit arayüzü | Streamlit, pandas, requests |
| React arayüzü | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router, i18next, Radix UI |
| Test | pytest, httpx (backend); Vitest, Testing Library, MSW (frontend-v2) |
| Konteyner | Docker (Python 3.12 slim, Node 22 alpine, nginx 1.27 alpine) |

## Proje yapısı

```
IzlemeAlarm/
├── backend/                FastAPI uygulaması
│   ├── main.py             Uygulama girişi (uvicorn backend.main:app)
│   ├── api/routes/         HTTP uç noktaları (auth, alerts, analysis, rules, uploads, users, audit, transactions)
│   ├── services/           İş kuralları / servis katmanı
│   ├── repositories/       Veritabanı erişimi
│   ├── detection/          R01–R15 kuralları, puanlama ve değerlendirme motoru
│   ├── scripts/            create_admin.py (ilk yönetici)
│   └── requirements.txt
├── frontend/               Streamlit arayüzü (app.py, app_pages/, components/, utils/)
├── frontend-v2/            React + TypeScript + Vite arayüzü (ayrıntı: frontend-v2/README.md)
├── alembic/                Veritabanı migrasyonları (0001–0005)
├── database/               Elle çalıştırılabilen SQL şemaları (V1–V4)
├── tests/                  pytest testleri
├── .streamlit/             Streamlit tema ayarları
├── .vscode/                VS Code başlatma yapılandırmaları (launch.json)
├── Dockerfile.backend      API imajı
├── Dockerfile.frontend     Streamlit imajı
├── Dockerfile.frontend-v2  React arayüzü imajı (build + nginx)
├── alembic.ini
├── .env.example            Ortam değişkenleri şablonu
└── PROJECT_GUIDE.md        Ayrıntılı proje rehberi
```

## Gereksinimler

- Python 3.10 veya üzeri (Docker imajı Python 3.12 kullanır)
- PostgreSQL
- Node.js 20 veya üzeri (yalnızca React arayüzü için)
- Docker (isteğe bağlı, konteyner ile çalıştırmak için)

## Yerel geliştirme kurulumu

### 1. Python ortamı

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m pip install -r frontend\requirements.txt
```

### 2. Ortam değişkenleri

`.env.example` dosyasını `.env` olarak kopyalayın ve en az `DATABASE_URL` ile `JWT_SECRET` değerlerini doldurun. `JWT_SECRET` tanımlı değilse API başlamaz. Yerel `.env` dosyasını paylaşmayın veya commit etmeyin.

Ortam değişkenlerinin tam listesi için [Yapılandırma](#yapılandırma) bölümüne bakın.

### 3. Veritabanı migrasyonları

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

- Boş bir veritabanında bu komut orijinal şemayı oluşturur, RBAC ve tespit kuralı çerçevesini uygular ve pasif R04–R15 kural kayıtlarını ekler.
- Migrasyon geçmişi olmayan, ancak tam orijinal şemaya sahip mevcut bir veritabanında önce temel revizyonu işaretleyin, sonra migrasyonu uygulayın:

  ```powershell
  .\.venv\Scripts\alembic.exe stamp 0001_existing_schema_baseline
  .\.venv\Scripts\alembic.exe upgrade head
  ```

- `0002_rbac` revizyonunu, RBAC migrasyonu elle uygulanmadıysa işaretlemeyin.
- `database\V1__initial_schema.sql` dosyasını mevcut bir şemaya tekrar çalıştırmayın.

### 4. İlk yönetici kullanıcısı

```powershell
python -m backend.scripts.create_admin
```

Betik kullanıcı adı ve şifreyi sorar. Alternatif olarak süreç ortamındaki `ADMIN_USERNAME` ve `ADMIN_PASSWORD` değişkenlerini okuyabilir. Depoda varsayılan bir yönetici veya şifre bulunmaz.

### 5. Uygulamayı çalıştırma

**API (FastAPI):**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Swagger dokümantasyonu: `http://127.0.0.1:8000/docs`

**Streamlit arayüzü:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend\app.py
```

**React arayüzü:**

```powershell
cd frontend-v2
npm install
npm run dev
```

Arayüz `http://localhost:5173` adresinde açılır. Vite geliştirme sunucusu `/api/*` isteklerini `http://127.0.0.1:8000` adresindeki API'ye yönlendirir; bu nedenle API'de CORS ayarı gerekmez. Hedef adres `VITE_API_PROXY_TARGET` ile değiştirilebilir.

### VS Code ile çalıştırma

Proje kök dizinini açın, `.venv` Python yorumlayıcısını seçin ve **Run and Debug** bölümünden:

- **Start project (API + UI)**: FastAPI + Streamlit
- **Start project (API + React UI)**: FastAPI + React

başlatma yapılandırmasını çalıştırın (`F5`). API adresi `http://127.0.0.1:8000/docs`, Streamlit arayüzü ise tarayıcıda açılır.

## Docker ile çalıştırma

Depoda üç ayrı Dockerfile bulunur; `docker-compose` dosyası yoktur. Her imaj ayrı ayrı derlenir ve çalıştırılır. Aşağıdaki imaj adları örnektir.

**API:** Konteyner `PORT` ortam değişkenini (varsayılan `8000`) dinler. `DATABASE_URL` ve `JWT_SECRET` değerleri çalışma zamanında beklenir.

```powershell
docker build -f Dockerfile.backend -t izleme-alarm-api .
docker run -p 8000:8000 --env-file .env izleme-alarm-api
```

Not: `.env` içindeki `localhost` adresi konteyner içinden veritabanını göstermez. Host'taki PostgreSQL'e erişmek için adresi `host.docker.internal` ile değiştirin (Windows/macOS Docker Desktop).

**Streamlit arayüzü:** Varsayılan port `8501`'dir (`PORT` ile değiştirilebilir).

```powershell
docker build -f Dockerfile.frontend -t izleme-alarm-ui .
docker run -p 8501:8501 izleme-alarm-ui
```

**React arayüzü:** nginx, derlenmiş arayüzü sunar ve `/api/*` isteklerini `API_UPSTREAM` adresindeki API'ye (`/api` öneki kaldırılarak) yönlendirir. Varsayılan `PORT` `8080`, varsayılan `API_UPSTREAM` `http://backend:8000` değeridir.

```powershell
docker build -f Dockerfile.frontend-v2 -t sentinel-frontend-v2 .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 sentinel-frontend-v2
```

Arayüz `http://localhost:8080` adresinde açılır. API'nin de ayakta olması gerekir.

## Yapılandırma

Değişkenler `.env` dosyasından (VS Code başlatıcısı ve `python-dotenv` ile) veya doğrudan süreç ortamından okunur.

| Değişken | Kullanıldığı yer | Açıklama |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic | PostgreSQL bağlantı adresi (ör. `postgresql+psycopg2://KULLANICI:PAROLA@localhost:5432/izleme_alarm`). Zorunlu. |
| `JWT_SECRET` | API | JWT imzalama anahtarı. Zorunlu; uzun ve rastgele olmalıdır. |
| `ADMIN_USERNAME` | `create_admin` betiği | İlk yöneticinin kullanıcı adı (isteğe bağlı; yoksa betik sorar). |
| `ADMIN_PASSWORD` | `create_admin` betiği | İlk yöneticinin şifresi (isteğe bağlı; yoksa betik sorar). |
| `ENABLE_DEMO_ENDPOINTS` | API | `true` ise `POST /demo/seed` ve arayüzdeki demo eylemi etkinleşir. Varsayılan `false`; yalnızca geliştirme ortamında açın. |
| `API_BASE_URL` | Streamlit arayüzü | Streamlit'in çağıracağı API adresi. `.env.example` değeri `http://127.0.0.1:8000`. |
| `VITE_API_PROXY_TARGET` | React arayüzü (Vite) | Geliştirme sunucusunun `/api` isteklerini ileteceği adres. Varsayılan `http://127.0.0.1:8000`. |
| `PORT` | API ve Streamlit imajları, React imajı | Konteynerin dinleyeceği port. Varsayılanlar: API `8000`, Streamlit `8501`, React `8080`. |
| `API_UPSTREAM` | React imajı (nginx) | `/api/*` isteklerinin yönlendirileceği API adresi. Varsayılan `http://backend:8000`. |

`.env.example` dosyasındaki değerler yer tutucudur; gerçek kimlik bilgilerini bu dosyaya yazmayın.

## Rol tabanlı erişim

- `admin` rolü, tohumlanmış tüm izinleri alır.
- `analyst` rolü yalnızca `alert:view`, `alert:update` ve `dashboard:view` izinlerini alır. Alarm detayında ilgili müşteri ve işlemler görünür; alarm bağlamındaki müşteri geçmişi o alarmın müşterisiyle sınırlıdır.
- Genel müşteri, hesap ve işlem gezintisi `customer:view` izni gerektirir.
- Yetki sınırı API'dir; Streamlit'teki izne dayalı menü yalnızca kullanım kolaylığı sağlar.
- Giriş: `POST /auth/login`. Rol ve izinler: `GET /auth/me`. Denetim kaydı: `GET /audit-log` (`audit:view` izni gerekir).
- Token'lar 30 dakika geçerlidir.

## Tespit kuralları

Etkin tespit motoru 15 bağımsız kural içerir: R01 eşik yakını işlem, R02 büyük işlem, R03 tekrarlayan nakit yatırma, R04 gelir-hacim uyuşmazlığı, R05 olağandışı tutar, R06 hız artışı, R07 uykudaki hesap hareketi, R08 yeni hesap hareketi, R09 nakit yoğunluğu, R10 pass-through, R11 fan-in, R12 fan-out, R13 katmanlama zincirleri, R14 döngü/ping-pong, R15 doğrulanmış şüpheli temas.

R04–R15 kuralları başlangıçta pasiftir ve `UNSET` parametrelerle gelir; yapılandırılıp onaylanana kadar etkinleştirilemez. Kurallar ve eşikler arayüzdeki **Rule Management** ekranında yönetilir.

Not: İşlem analizi ekranı ayrıca eski R1–R4 göstergelerini içerir; bunlar R01–R15 alarm hattından ayrıdır.

## Veri içe aktarma

- Yalnızca UTF-8 CSV dosyaları; dosya boyutu en fazla 5 MB, satır sayısı en fazla 5000.
- Sıra: önce müşteriler, sonra hesaplar, en son işlemler.

## Testler

Backend testleri `tests/` klasöründedir (`test_application.py`, `test_detection_strategies.py`, `test_rbac.py`, `test_system_overview.py`, `test_transaction_flow.py`) ve `pytest` ile çalışır. React arayüzü için `frontend-v2` içinde `npm run typecheck`, `npm run lint`, `npm run test` ve `npm run build` komutları tanımlıdır.

## Notlar

- Orijinal şemadan gelen `demo-system` kaydı veritabanında kalmış olabilir; istek bazlı işlemler (yükleme, kural, alarm geçmişi, denetim) artık kimliği doğrulanmış kullanıcının ID'sini kullanır.
- Demo verisi için **Operations → Demo lab** ekranı kullanılabilir; demo değerlendirmesi, demo olmayan işlemlerden ayrı çalışır.
- Ayrıntılı ekran ve iş akışları için [PROJECT_GUIDE.md](./PROJECT_GUIDE.md), React arayüzü için [frontend-v2/README.md](./frontend-v2/README.md) dosyalarına bakın.
