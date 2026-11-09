<a id="turkce"></a>

# Sentinel · İşlem İzleme ve Alarm Sistemi (IzlemeAlarm)

**Türkçe** · [English](#english)

Sentinel, banka işlemleri için bir **işlem izleme (transaction monitoring) MVP'sidir**. Müşteri, hesap ve işlem verilerini CSV ile alır; **20 kural** (R01–R18, S1, S2) ile şüpheli davranışları puanlar; alarmları önce analistin, sonra uyum görevlisinin incelemesine sunar ve her adımı değiştirilemez bir denetim kaydına yazar.

> Uygulama **sentetik veriyle, öğrenme ve demo amaçlıdır**. Kural eşikleri örnektir; gerçek risk kararları için kullanılmamalıdır.

Mimari, iş akışı, kurallar ve API'nin ayrıntılı açıklaması için **[Proje Rehberi](./PROJECT_GUIDE.md)** dosyasına bakın.

## Özellikler

- **Alarm iş akışı:** analist alarmı kapatır veya uyum görevlisine yükseltir; uyum görevlisi şüpheli olarak onaylar, kapatır ya da analiste geri gönderir. Her kararda not zorunludur; yükselten kişi karar veremez (**dört göz**).
- **Müşteri bazlı alarm kuyruğu:** gruplama, sıralama, arama ve sayfalama sunucuda; bir müşterinin birden çok alarmına tek ve bölünmez kararla karar verilir.
- **"Neden tetiklendi?":** her alarm, kuralın o anki parametreleri ve adım adım hesabıyla açıklanır.
- **20 tespit kuralı:** parametreler müşteri tipine göre (Bireysel/Kurumsal) ayrı ayarlanır, her değişiklik gerekçeyle kaydedilir, değişiklik geçmişi ve kural isabeti izlenir.
- **Kişisel veri koruması:** maskeleme sunucuda yapılır; müşteri verisinin her görüntülenmesi denetim kaydına yazılır.
- **Denetim kaydı:** kararlar, kural değişiklikleri, yüklemeler, girişler ve yetkisiz denemeler; veritabanı tetikleyicileri kayıtların değiştirilmesini ve silinmesini engeller.
- **CSV yükleme:** satır bazlı hata raporu, şablonlar ve yükleme geçmişi; işlem yüklemesinden sonra kurallar kendiliğinden çalışır.
- **Panolar:** özet, alarm akışı (huni) ve kural performansı; işlem analizi ve hesap akış diyagramı.
- **Demo laboratuvarı:** her kuralı tetikleyen tekrarlanabilir sentetik veri seti (32 müşteri, 93 işlem, 20 senaryo).
- **React arayüzü:** Türkçe/İngilizce, açık/koyu tema.

## Roller

| Rol | Yapabildikleri |
| --- | --- |
| **Analist** | Kuyruktaki alarmları inceler; kapatır veya yükseltir. Kuralları salt okunur görür. |
| **Uyum görevlisi** | Yükseltilen alarmlara karar verir; müşteri ve işlem analizine erişir; kural eşiklerini gerekçeyle değiştirir; denetim kaydını görür. |
| **Yönetici** | Kullanıcıları, CSV yüklemeyi ve sistem durumunu yönetir. |

Yetki kontrolü API'de yapılır; arayüzde bir butonu gizlemek yalnızca kolaylıktır. **Not:** Geliştirme süresince yönetici rolü tüm izinlere sahiptir (migrasyon `0007`). Tasarımdaki kısıtlamaya (yönetici müşteri ve alarm içeriğini görmez) dönmek için: `alembic downgrade 0006_alert_workflow`.

## Teknoloji yığını

| Katman | Teknoloji |
| --- | --- |
| API | Python, FastAPI, Pydantic, Uvicorn |
| Veritabanı | PostgreSQL |
| ORM ve migrasyon | SQLAlchemy 2, Alembic |
| Kimlik doğrulama | PyJWT (30 dakikalık token), bcrypt |
| Arayüz | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router, zod, i18next, Radix UI |
| Test | pytest, httpx; Vitest, Testing Library, MSW, axe |
| Konteyner | Docker (Python 3.12 slim, Node 22 alpine, nginx alpine) |

## Proje yapısı

```
IzlemeAlarm/
├── backend/               FastAPI uygulaması
│   ├── main.py            Uygulama girişi (uvicorn backend.main:app)
│   ├── api/routes/        HTTP uç noktaları
│   ├── services/          İş akışları (alarm kararları, kurallar, yükleme, maskeleme…)
│   ├── repositories/      Veritabanı erişimi
│   ├── detection/         Kural motoru, puanlama ve kurallar (rules/ altında her kural bir dosya)
│   ├── demo.py            Demo veri seti ve senaryolar
│   └── scripts/           create_admin.py (ilk yönetici)
├── frontend-v2/           React arayüzü (birincil arayüz)
├── frontend/              Streamlit arayüzü (eski; güncel API'ye uyarlanmadı)
├── alembic/               Veritabanı migrasyonları (0001–0007)
├── database/              Migrasyonların SQL karşılıkları (V1–V6)
├── tests/                 Backend testleri (integration/ gerçek veritabanında çalışır)
├── Dockerfile.backend     API imajı
├── Dockerfile.frontend-v2 React arayüzü imajı (derleme + nginx)
├── Dockerfile.frontend    Streamlit imajı
├── .env.example           Ortam değişkenleri şablonu
└── PROJECT_GUIDE.md       Ayrıntılı proje rehberi
```

## Kurulum

**Gereksinimler:** Python 3.10+, PostgreSQL, Node.js 20+ (arayüz için), isteğe bağlı Docker.

```powershell
# 1. Python ortamı
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

# 2. Ortam değişkenleri: .env.example'ı .env olarak kopyalayın,
#    en az DATABASE_URL ve JWT_SECRET değerlerini doldurun
copy .env.example .env

# 3. Veritabanı şeması
.\.venv\Scripts\alembic.exe upgrade head

# 4. İlk yönetici (kullanıcı adı ve şifre sorulur)
python -m backend.scripts.create_admin

# 5. Arayüz bağımlılıkları
cd frontend-v2
npm install
```

Depoda varsayılan kullanıcı veya şifre yoktur. Analist ve uyum görevlisi kullanıcılarını yönetici **Kullanıcı yönetimi** ekranından oluşturur. `.env` dosyasını paylaşmayın veya commit etmeyin.

Migrasyon geçmişi olmayan ama orijinal şemaya sahip bir veritabanında önce `alembic stamp 0001_existing_schema_baseline`, sonra `alembic upgrade head` çalıştırın. `database\V1__initial_schema.sql` dosyasını mevcut bir şemaya tekrar uygulamayın.

## Çalıştırma

**VS Code:** `.venv` yorumlayıcısını seçin, **Run and Debug** bölümünden **Start project (API + React UI)** yapılandırmasını başlatın (`F5`).

**Terminal:**

```powershell
# API — Swagger: http://127.0.0.1:8000/docs
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Arayüz — http://localhost:5173
cd frontend-v2
npm run dev
```

Vite, `/api/*` isteklerini API'ye iletir; bu yüzden API'de CORS ayarı gerekmez.

**Demo verisi:** `.env` içinde `ENABLE_DEMO_ENDPOINTS=true` yapın, **API'yi yeniden başlatın**, yönetici olarak **Demo laboratuvarı** ekranında **Demo veriyi oluştur ve değerlendir** düğmesine basın.

**Sık karşılaşılan sorunlar:**

| Belirti | Neden |
| --- | --- |
| Backend değişiklikleri görünmüyor | API `--reload` olmadan çalışıyor (VS Code başlatıcısı da yeniden yüklemez). API'yi yeniden başlatın. |
| "Demo seeding is disabled" | Çalışan API'de `ENABLE_DEMO_ENDPOINTS=true` değil. `.env`'i değiştirdikten sonra API'yi yeniden başlatın. |
| API başlamıyor | `JWT_SECRET` tanımlı değil. |
| Tüm ekranlarda sunucu hatası | `GET /health`, `DATABASE_URL` ve `alembic current` / `alembic heads` değerlerini kontrol edin. |

## Docker

Üç ayrı Dockerfile vardır; `docker-compose` dosyası yoktur. İmaj adları örnektir.

```powershell
# API (PORT varsayılanı 8000; DATABASE_URL ve JWT_SECRET gerekir)
docker build -f Dockerfile.backend -t sentinel-api .
docker run -p 8000:8000 --env-file .env sentinel-api

# React arayüzü (nginx; PORT varsayılanı 8080, /api/* isteklerini API_UPSTREAM'e iletir)
docker build -f Dockerfile.frontend-v2 -t sentinel-ui .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 sentinel-ui
```

Konteyner içinden `localhost` konteynerin kendisidir; host'taki PostgreSQL için `host.docker.internal` kullanın.

## Yapılandırma

| Değişken | Kullanan | Açıklama |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic, entegrasyon testleri | PostgreSQL adresi, ör. `postgresql+psycopg2://KULLANICI:PAROLA@localhost:5432/izleme_alarm`. Zorunlu. |
| `JWT_SECRET` | API | Token imzalama anahtarı; uzun ve rastgele. Zorunlu. |
| `PROXY_SHARED_SECRET` | API + nginx | Hız sınırlarında istemci adresinin nginx'ten geldiğini kanıtlar; iki tarafta aynı olmalı. Yalnızca nginx arkasında gerekir. |
| `ENABLE_DEMO_ENDPOINTS` | API | `true` ise demo verisi oluşturulabilir. Varsayılan `false`; yalnızca geliştirmede açın. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `create_admin` | İsteğe bağlı; yoksa betik sorar. |
| `VITE_API_PROXY_TARGET` | Vite geliştirme sunucusu | `/api` isteklerinin hedefi. Varsayılan `http://127.0.0.1:8000`. |
| `API_UPSTREAM`, `PORT` | React imajı (nginx) | API adresi (varsayılan `http://backend:8000`) ve port (varsayılan `8080`). |
| `API_BASE_URL` | Streamlit (eski) | Streamlit'in çağırdığı API adresi. |

## Testler

```powershell
# Backend (depo kökünden)
.\.venv\Scripts\python.exe -m pytest tests -q

# Arayüz (frontend-v2 içinden)
npm test
npm run typecheck
npm run lint
npm run build
```

`tests/integration/` altındaki testler `DATABASE_URL`'deki veritabanında, her biri geri alınan bir işlem içinde çalışır; `DATABASE_URL` yoksa atlanır. **Bu adresin yerel bir test veritabanı olduğundan emin olun**, ortak veya canlı bir veritabanı olmamalıdır.

## Lisans

[LICENSE](./LICENSE) dosyasına bakın.

---

<a id="english"></a>

# Sentinel · Transaction Monitoring and Alert System (IzlemeAlarm)

[Türkçe](#turkce) · **English**

Sentinel is a **transaction monitoring MVP** for bank transactions. It imports customer, account and transaction data from CSV files, scores suspicious behaviour with **20 rules** (R01–R18, S1, S2), routes alerts to an analyst and then to a compliance officer, and writes every step to an audit log that cannot be changed.

> The application uses **synthetic data and is for learning and demonstration only**. Rule thresholds are examples; do not use it for real risk decisions.

For a detailed explanation of the architecture, workflow, rules and API, see the **[Project Guide](./PROJECT_GUIDE.md)**.

## Features

- **Alert workflow:** the analyst closes an alert or escalates it to compliance; the compliance officer confirms it as suspicious, closes it, or returns it to the analyst. Every decision needs a note, and whoever escalated an alert cannot decide on it (**four eyes**).
- **Customer-grouped alert queue:** grouping, sorting, search and paging on the server; one atomic decision can cover several alerts of a customer.
- **"Why did it trigger?":** every alert is explained with the rule's parameters at that moment and its step-by-step calculation.
- **20 detection rules:** separate parameters per customer type (individual/corporate), every change saved with a reason, plus change history and hit rate per rule.
- **Personal data protection:** masking happens on the server; every view of customer data is written to the audit log.
- **Audit log:** decisions, rule changes, uploads, sign-ins and refused attempts; database triggers stop records from being changed or deleted.
- **CSV upload:** row-level error reports, templates and upload history; rules run automatically after a transaction upload.
- **Dashboards:** summary, alert funnel and rule performance; transaction analysis with an account flow diagram.
- **Demo lab:** a repeatable synthetic dataset that triggers every rule (32 customers, 93 transactions, 20 scenarios).
- **React interface:** Turkish/English, light/dark theme.

## Roles

| Role | Can do |
| --- | --- |
| **Analyst** | Reviews alerts in the queue; closes or escalates them. Sees rules read-only. |
| **Compliance officer** | Decides on escalated alerts; uses customer and transaction analysis; changes rule thresholds with a reason; reads the audit log. |
| **Administrator** | Manages users, CSV uploads and system status. |

Permissions are enforced by the API; hiding a button in the interface is only a convenience. **Note:** during development the administrator has every permission (migration `0007`). To restore the design restriction (the administrator does not see customer or alert content), run `alembic downgrade 0006_alert_workflow`.

## Tech stack

| Layer | Technology |
| --- | --- |
| API | Python, FastAPI, Pydantic, Uvicorn |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy 2, Alembic |
| Authentication | PyJWT (30-minute tokens), bcrypt |
| Interface | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router, zod, i18next, Radix UI |
| Tests | pytest, httpx; Vitest, Testing Library, MSW, axe |
| Containers | Docker (Python 3.12 slim, Node 22 alpine, nginx alpine) |

## Project structure

```
IzlemeAlarm/
├── backend/               FastAPI application
│   ├── main.py            Entry point (uvicorn backend.main:app)
│   ├── api/routes/        HTTP endpoints
│   ├── services/          Workflows (alert decisions, rules, uploads, masking…)
│   ├── repositories/      Database access
│   ├── detection/         Rule engine, scoring and rules (one file per rule in rules/)
│   ├── demo.py            Demo dataset and scenarios
│   └── scripts/           create_admin.py (first administrator)
├── frontend-v2/           React interface (primary)
├── frontend/              Streamlit interface (legacy; not updated for the current API)
├── alembic/               Database migrations (0001–0007)
├── database/              SQL mirrors of the migrations (V1–V6)
├── tests/                 Backend tests (integration/ runs against a real database)
├── Dockerfile.backend     API image
├── Dockerfile.frontend-v2 React image (build + nginx)
├── Dockerfile.frontend    Streamlit image
├── .env.example           Environment template
└── PROJECT_GUIDE.md       Detailed project guide
```

## Setup

**Requirements:** Python 3.10+, PostgreSQL, Node.js 20+ (for the interface), Docker optional.

```powershell
# 1. Python environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

# 2. Environment: copy .env.example to .env and fill in at least DATABASE_URL and JWT_SECRET
copy .env.example .env

# 3. Database schema
.\.venv\Scripts\alembic.exe upgrade head

# 4. First administrator (prompts for username and password)
python -m backend.scripts.create_admin

# 5. Interface dependencies
cd frontend-v2
npm install
```

The repository ships no default user or password. The administrator creates analyst and compliance users on the **Kullanıcı yönetimi** (user management) screen. Never share or commit `.env`.

For a database that has the original schema but no migration history, run `alembic stamp 0001_existing_schema_baseline` first, then `alembic upgrade head`. Do not re-run `database\V1__initial_schema.sql` on an existing schema.

## Running

**VS Code:** select the `.venv` interpreter, then start **Start project (API + React UI)** from **Run and Debug** (`F5`).

**Terminal:**

```powershell
# API — Swagger: http://127.0.0.1:8000/docs
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Interface — http://localhost:5173
cd frontend-v2
npm run dev
```

Vite forwards `/api/*` requests to the API, so the API needs no CORS settings.

**Demo data:** set `ENABLE_DEMO_ENDPOINTS=true` in `.env`, **restart the API**, then as the administrator press **Demo veriyi oluştur ve değerlendir** on the **Demo laboratuvarı** screen.

**Common problems:**

| Symptom | Cause |
| --- | --- |
| Backend changes have no effect | The API runs without `--reload` (the VS Code launcher does not reload either). Restart the API. |
| "Demo seeding is disabled" | `ENABLE_DEMO_ENDPOINTS=true` is not set in the running API. Restart the API after editing `.env`. |
| The API does not start | `JWT_SECRET` is missing. |
| Server errors on every screen | Check `GET /health`, `DATABASE_URL`, and `alembic current` against `alembic heads`. |

## Docker

There are three separate Dockerfiles and no `docker-compose` file. Image names are examples.

```powershell
# API (PORT defaults to 8000; needs DATABASE_URL and JWT_SECRET)
docker build -f Dockerfile.backend -t sentinel-api .
docker run -p 8000:8000 --env-file .env sentinel-api

# React interface (nginx; PORT defaults to 8080, forwards /api/* to API_UPSTREAM)
docker build -f Dockerfile.frontend-v2 -t sentinel-ui .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 sentinel-ui
```

Inside a container, `localhost` is the container itself; use `host.docker.internal` to reach PostgreSQL on the host.

## Configuration

| Variable | Used by | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic, integration tests | PostgreSQL URL, e.g. `postgresql+psycopg2://USER:PASSWORD@localhost:5432/izleme_alarm`. Required. |
| `JWT_SECRET` | API | Token signing key; long and random. Required. |
| `PROXY_SHARED_SECRET` | API + nginx | Proves to the rate limits that a client address came from nginx; same value on both. Only needed behind nginx. |
| `ENABLE_DEMO_ENDPOINTS` | API | `true` allows seeding demo data. Default `false`; development only. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `create_admin` | Optional; otherwise the script asks. |
| `VITE_API_PROXY_TARGET` | Vite dev server | Where `/api` requests go. Default `http://127.0.0.1:8000`. |
| `API_UPSTREAM`, `PORT` | React image (nginx) | API address (default `http://backend:8000`) and port (default `8080`). |
| `API_BASE_URL` | Streamlit (legacy) | API address used by Streamlit. |

## Tests

```powershell
# Backend (from the repository root)
.\.venv\Scripts\python.exe -m pytest tests -q

# Interface (from frontend-v2)
npm test
npm run typecheck
npm run lint
npm run build
```

Tests in `tests/integration/` run against the database in `DATABASE_URL`, each inside a transaction that is rolled back, and are skipped when `DATABASE_URL` is not set. **Make sure it points to a local test database**, never a shared or production one.

## License

See [LICENSE](./LICENSE).
