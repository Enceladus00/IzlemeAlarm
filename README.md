<a id="turkce"></a>

# IzlemeAlarm: İşlem İzleme ve Alarm Sistemi

**Türkçe** | [English](#english)

IzlemeAlarm, banka işlemlerinde şüpheli davranışları tespit eden ve bu tespitlerin
kimin tarafından, hangi gerekçeyle karara bağlandığını kayıt altına alan bir
işlem izleme sistemidir. Arayüzdeki adı **Sentinel**'dir.

Müşteri, hesap ve işlem verileri CSV ile yüklenir. 20 kural (R01–R18, S1, S2)
her müşteriye 0 ile 1 arasında bir skor verir; 0,5 ve üzeri alarm açar. Analist
alarmı kapatır ya da uyum görevlisine yükseltir, uyum görevlisi son kararı
verir. Yükselten kişi aynı alarma karar veremez (dört göz). Kararlar, kural
değişiklikleri ve müşteri verisinin her görüntülenmesi, veritabanının
değiştirilmesine izin vermediği bir denetim kaydına yazılır.

Proje öğrenme ve gösterim amaçlıdır: sentetik veriyle çalışır, kural eşikleri
geçicidir ve gerçek risk kararlarında kullanılmamalıdır.

## Neler var

- Müşteri bazında gruplanan alarm kuyruğu; bir müşterinin birden çok alarmına tek ve bölünmez karar
- Her alarm için "Neden tetiklendi?": kuralın o anki parametreleri ve adım adım hesabı
- Bireysel ve kurumsal müşteriler için ayrı ayarlanan, değişiklikleri gerekçeyle kaydedilen kurallar
- Sunucu tarafında maskeleme ve müşteri verisi görüntüleme kaydı (KVKK, BDDK)
- Satır bazlı hata raporlu CSV yükleme; işlem yüklemesinden sonra kurallar kendiliğinden çalışır
- İsteğe bağlı günlük kural çalıştırması (`DETECTION_SCHEDULE_TIME`)
- Panolar, işlem analizi (karşı taraf akışı, ağ grafiği), müşteri analizi
- Her kuralı tetikleyen tekrarlanabilir demo veri seti
- Türkçe ve İngilizce, açık ve koyu temalı React arayüzü

## Teknoloji

Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL; React 19, TypeScript,
Vite, TanStack Query, Tailwind CSS 4; pytest, Vitest, MSW. Canlı ortam AWS ECS
(Fargate) ve Neon PostgreSQL üzerinde, GitHub Actions ile elle başlatılan
dağıtımlarla çalışır.

## Hızlı başlangıç

Gereksinimler: Python 3.10+, PostgreSQL, Node.js 20+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

copy .env.example .env          # DATABASE_URL ve JWT_SECRET değerlerini girin
.\.venv\Scripts\alembic.exe upgrade head
python -m backend.scripts.create_admin

cd frontend-v2
npm install
```

Çalıştırmak için VS Code'da **Start project (API + React UI)** yapılandırmasını
başlatın ya da iki terminalde:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend-v2; npm run dev
```

Arayüz `http://localhost:5173`, API belgeleri `http://127.0.0.1:8000/docs`
adresindedir. Depoda varsayılan kullanıcı yoktur; yönetici, analist ve uyum
görevlisi hesaplarını **Kullanıcı yönetimi** ekranından açar. Demo verisi için
`.env` içinde `ENABLE_DEMO_ENDPOINTS=true` yapıp API'yi yeniden başlatın ve
**Demo laboratuvarı** ekranını kullanın.

Testler:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q     # backend
cd frontend-v2; npm test; npm run typecheck; npm run lint
```

Entegrasyon testleri yalnızca `DATABASE_URL` `localhost`'u gösterdiğinde
çalışır ve hiçbir şey kalıcı olarak yazmaz.

## Belgeler

| Belge | İçerik |
| --- | --- |
| [PROJECT_GUIDE.md](./PROJECT_GUIDE.md) | Mimari, roller, alarm akışı, kurallar, veri modeli, API, yapılandırma, testler, dağıtım, sınırlar (İngilizce) |
| [frontend-v2/README.md](./frontend-v2/README.md) | React arayüzünün kuralları ve kod düzeni |
| `http://127.0.0.1:8000/docs` | Koddan üretilen güncel API belgesi |
| [database/](./database/) | Migrasyonların SQL karşılıkları |

## Lisans

[LICENSE](./LICENSE)

---

<a id="english"></a>

# IzlemeAlarm: Transaction Monitoring and Alert System

[Türkçe](#turkce) | **English**

IzlemeAlarm is a transaction monitoring system. It finds suspicious behaviour
in bank transactions and records who decided on each finding and why. The
interface calls itself **Sentinel**.

Customers, accounts and transactions are uploaded as CSV files. Twenty rules
(R01–R18, S1, S2) give each customer a score between 0 and 1, and a score of
0.5 or more opens an alert. An analyst closes the alert or escalates it to a
compliance officer, who makes the final decision. Whoever escalated an alert
cannot decide on it (four eyes). Decisions, rule changes and every view of
customer data are written to an audit log that the database will not let
anyone change.

This is a learning and demonstration project. It runs on synthetic data, its
rule thresholds are provisional, and it should not be used for real risk
decisions.

## Features

- Alert queue grouped by customer; one atomic decision can cover several alerts of a customer
- "Neden tetiklendi?" (why did it fire) on every alert: the rule's parameters at the time and its step-by-step calculation
- Rules configured separately for individual and corporate customers, with every change saved with a reason
- Server-side masking and logging of every view of customer data (KVKK, BDDK)
- CSV upload with row-level error reports; rules run automatically after a transaction upload
- Optional daily rule run (`DETECTION_SCHEDULE_TIME`)
- Dashboards, transaction analysis (counterparty flow, network graph), customer analysis
- A repeatable demo dataset that triggers every rule
- React interface in Turkish and English, light and dark themes

## Technology

Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL; React 19, TypeScript,
Vite, TanStack Query, Tailwind CSS 4; pytest, Vitest, MSW. Production runs on
AWS ECS (Fargate) and Neon PostgreSQL, deployed by manually started GitHub
Actions workflows.

## Quick start

Requirements: Python 3.10+, PostgreSQL, Node.js 20+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

copy .env.example .env          # set DATABASE_URL and JWT_SECRET
.\.venv\Scripts\alembic.exe upgrade head
python -m backend.scripts.create_admin

cd frontend-v2
npm install
```

To run it, start **Start project (API + React UI)** in VS Code, or use two
terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend-v2; npm run dev
```

The interface is at `http://localhost:5173` and the API docs at
`http://127.0.0.1:8000/docs`. The repository ships no default users; the
administrator creates analyst and compliance accounts on the
**Kullanıcı yönetimi** screen. For demo data, set `ENABLE_DEMO_ENDPOINTS=true`
in `.env`, restart the API and use the **Demo laboratuvarı** screen.

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q     # backend
cd frontend-v2; npm test; npm run typecheck; npm run lint
```

Integration tests run only when `DATABASE_URL` points at `localhost`, and they
leave nothing behind.

## Documentation

| Document | Contents |
| --- | --- |
| [PROJECT_GUIDE.md](./PROJECT_GUIDE.md) | Architecture, roles, alert workflow, rules, data model, API, configuration, testing, deployment, limits |
| [frontend-v2/README.md](./frontend-v2/README.md) | Conventions and code layout of the React interface |
| `http://127.0.0.1:8000/docs` | Current API reference generated from the code |
| [database/](./database/) | SQL mirrors of the migrations |

## License

[LICENSE](./LICENSE)
