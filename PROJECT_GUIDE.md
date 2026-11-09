# Sentinel — Project Guide

This guide explains how the transaction monitoring system works: what it does,
how its parts fit together, how to run it, and how to change it safely. Read
sections 1–3 for the big picture; the rest is reference material you can jump
into when you need it.

> **Scope.** Sentinel is a learning and demonstration MVP built on synthetic
> data. Its rules are transparent, deterministic examples with provisional
> thresholds. It is not a production fraud-decision system and uses no machine
> learning.

## Contents

1. [What Sentinel does](#1-what-sentinel-does)
2. [Architecture](#2-architecture)
3. [Repository map](#3-repository-map)
4. [Running it locally](#4-running-it-locally)
5. [Users, roles and permissions](#5-users-roles-and-permissions)
6. [The alert workflow](#6-the-alert-workflow)
7. [The detection engine](#7-the-detection-engine)
8. [Data model](#8-data-model)
9. [API reference](#9-api-reference)
10. [CSV upload](#10-csv-upload)
11. [The demo lab](#11-the-demo-lab)
12. [The interfaces](#12-the-interfaces)
13. [Database migrations](#13-database-migrations)
14. [Configuration](#14-configuration)
15. [Testing](#15-testing)
16. [How to change things](#16-how-to-change-things)
17. [Limits and open items](#17-limits-and-open-items)
18. [Glossary](#18-glossary)

---

## 1. What Sentinel does

A bank must spot suspicious transactions, have a compliance officer decide on
them, and be able to show later who decided what and why. Sentinel models that
process end to end:

1. **Data comes in.** Customers, accounts and transactions are uploaded as CSV
   files. Invalid rows are rejected with a reason; valid rows are stored.
2. **Rules look for patterns.** Twenty rules (R01–R18, S1, S2) score every
   customer between 0 and 1. A score of 0.5 or more on an alerting rule opens
   an **alert**.
3. **An analyst reviews.** The analyst works from a queue grouped by customer,
   sees why each rule fired ("Neden tetiklendi?"), and either closes the alert
   as a false positive or escalates it.
4. **A compliance officer decides.** Escalated alerts are confirmed as
   suspicious, closed, or returned to the analyst. Whoever escalated an alert
   may not make the final decision on it (**four eyes**).
5. **Everything is recorded.** Decisions, rule changes, uploads, logins,
   refused access attempts and views of customer data go to an append-only
   audit log that the database itself refuses to edit or delete.

Three roles take part: **analyst**, **compliance officer** and
**administrator** (section 5).

## 2. Architecture

```text
 Browser ── React UI (frontend-v2) ──/api──► FastAPI ──SQLAlchemy──► PostgreSQL
            served by Vite (dev) or nginx       │
                                                └── detection engine (Python)
```

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Interface | React 19, TypeScript, Vite, TanStack Query, Tailwind | Screens. Calls only its own origin under `/api`; Vite (dev) or nginx (container) forwards to FastAPI, so the API needs no CORS. |
| API | FastAPI, Pydantic, Uvicorn | Authentication, permission checks, validation, business workflows, the rule engine. |
| Data | PostgreSQL, SQLAlchemy 2, Alembic | The system of record. Constraints and triggers protect integrity even if the API has a bug. |

**The single rule that matters most:** the API enforces every permission.
Hiding a button in the interface is a convenience only; a request sent directly
to the API is checked the same way, and a refused attempt is logged as
`ACCESS_DENIED`.

### How a request travels

Example: the analyst escalates two alerts.

1. React posts `POST /api/alerts/decisions` with the alert IDs, target status
   and note. Vite strips `/api` and forwards to FastAPI.
2. `require_permission("alert:view")` reads the bearer token, reloads the user,
   role and permissions from the database and rejects inactive users.
3. The route (`backend/api/routes/alerts.py`) only translates HTTP. It calls
   `AlertService` (`backend/services/`), which runs the workflow checks.
4. The service uses a repository (`backend/repositories/`) for all SQL. The
   whole decision is written in **one database transaction**: either every
   alert changes or none does.
5. The response is shaped by a Pydantic `response_model`
   (`backend/api/responses.py`). Fields not in the model are dropped, so an
   accidental extra field never reaches the browser.
6. React validates the response with a zod schema (`src/api/schemas/`), then
   refreshes the affected cached queries (queue, dashboards).

Layer rules: routes translate HTTP and map errors to status codes; services
hold workflows; repositories own queries; rule strategies are pure
calculations. Keep SQL out of routes and HTTP out of services.

## 3. Repository map

| Path | What is there |
| --- | --- |
| `backend/main.py` | FastAPI app; `uvicorn backend.main:app` starts it. |
| `backend/api/routes/` | HTTP endpoints by area: `alerts`, `analysis` (dashboards, health, demo, system), `audit`, `auth`, `customers`, `rules`, `transactions`, `uploads`, `users`. |
| `backend/api/dependencies.py` | Builds services per request; `require_permission(...)`. |
| `backend/api/responses.py` | Response models (what each endpoint may return). |
| `backend/api_schemas.py` | Request bodies (e.g. a decision, a rule update). |
| `backend/services/` | Workflows: `alert_service`, `alert_workflow` (transition table, four eyes), `detection_service`, `rule_service`, `upload_service`, `demo_service`, `masking`, `audit_service`, … |
| `backend/repositories/` | SQLAlchemy queries and writes; `customer_view_log.py` writes `customer.viewed` audit rows. |
| `backend/detection/` | The engine (`engine.py`), parameter models (`parameters.py`), scoring (`scoring.py`), severity and keys (`evidence.py`), the rule registry, and one file per rule in `rules/`. |
| `backend/demo.py` | The synthetic demo fixture and its per-rule scenarios. |
| `backend/models.py` | SQLAlchemy entities. |
| `backend/security.py` | Password hashing (bcrypt) and JWT tokens (30 minutes). |
| `backend/scripts/create_admin.py` | Creates the first administrator. |
| `alembic/versions/` | Migrations `0001`–`0007` (section 13). |
| `database/` | `V1`–`V6` SQL files mirroring the migrations, for manual setup and review. |
| `frontend-v2/` | The React interface (section 12). Has its own `README.md`. |
| `frontend/` | The original Streamlit interface — legacy, see section 12. |
| `tests/` | Backend unit tests; `tests/integration/` runs against a real database. |
| `Dockerfile.backend`, `Dockerfile.frontend-v2`, `Dockerfile.frontend` | Container images for the API, the React UI (nginx) and Streamlit. |
| `.vscode/launch.json` | One-click launch configurations. |
| `.env.example` | Configuration template. |

## 4. Running it locally

### Prerequisites

- Python 3.10+ (the Docker image uses 3.12)
- PostgreSQL with an empty database you can use for development
- Node.js 20+ for the React interface

### First-time setup

```powershell
# 1. Python environment and dependencies
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

# 2. Configuration: copy the template and fill in DATABASE_URL and JWT_SECRET
copy .env.example .env

# 3. Create or upgrade the schema
.\.venv\Scripts\alembic.exe upgrade head

# 4. Create the first administrator (prompts for username and password)
python -m backend.scripts.create_admin

# 5. React dependencies
cd frontend-v2
npm install
```

### Starting it

**In VS Code:** open **Run and Debug** and start
**Start project (API + React UI)**. This runs the API on
`http://127.0.0.1:8000` (interactive docs at `/docs`) and the React app on
`http://localhost:5173`.

**From a terminal:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend-v2; npm run dev
```

### Seeing demo data

1. Set `ENABLE_DEMO_ENDPOINTS=true` in `.env` and restart the API.
2. Sign in as a user with `upload:create` (by default only the administrator).
3. Open **Demo laboratuvarı** and press **Demo veriyi oluştur ve değerlendir**.

To try the full workflow you need at least one analyst and one compliance
officer. The administrator creates them on **Kullanıcı yönetimi**.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Backend changes have no effect | The API was started without `--reload` (the VS Code launch configuration does not reload). Restart it. |
| "Demo seeding is disabled" | `ENABLE_DEMO_ENDPOINTS` is not `true` in the environment of the **running** API. Restart after changing `.env`. |
| API refuses to start | `JWT_SECRET` is missing. |
| Every screen shows a server error | Check `GET /health`; then `DATABASE_URL`, that PostgreSQL is up, and `alembic current` vs `alembic heads`. |
| A screen says "no permission" | Expected: the role lacks that permission (section 5). |

## 5. Users, roles and permissions

### Roles

| Permission | Analyst | Compliance officer | Administrator |
| --- | :-: | :-: | :-: |
| `alert:view` — see alerts and the queue | ● | ● | ● ¹ |
| `alert:update` — close a **new** alert (false positive) | ● | | ● ¹ |
| `alert:escalate` — send a new alert to compliance | ● | | ● |
| `alert:confirm` — decide on escalated alerts; see any alert's customer data | | ● | ● |
| `customer:view` — customers, accounts, transaction analysis | | ● | ● ¹ |
| `dashboard:view` — overview and demo lab | ● | ● | ● |
| `rule:view` — read rules | ● | ● | ● |
| `rule:edit` — change rules, run rules now | | ● | ● |
| `audit:view` — audit log | | ● | ● |
| `upload:create`, `upload:view` — CSV upload and reports | | | ● |
| `user:manage` — users and system overview | | | ● |
| `role:manage` — reserved, no endpoint yet | | | ● |

¹ **Development setting.** The design (decision K13) says the administrator
manages the system but never sees alert or customer content. Migration `0006`
implements that; migration `0007` deliberately gives the administrator every
permission again while the project is in development. To restore K13, run
`alembic downgrade 0006_alert_workflow`. Any permission added by a future
migration must also be granted to the administrator in that migration.

The compliance officer intentionally does **not** have `alert:update`: they
cannot close a `new` alert directly and skip the analyst step.

A legacy `auditor` role exists only if an old database contained auditor users;
it has no permissions.

### Authentication

- `POST /auth/login` takes a form (`username`, `password`) and returns an HS256
  bearer token valid for **30 minutes**. Wrong password, unknown user and
  inactive user all get the same answer, so usernames cannot be probed.
- Every protected request reloads the user, role and permissions from the
  database, so deactivating a user or changing a role takes effect immediately.
- Public endpoints: `POST /auth/login` and `GET /health` only.
- The React app keeps the token in memory and `sessionStorage` (a refresh keeps
  the session; closing the tab ends it) and signs out on expiry or any 401.
- A user cannot change their own role or deactivate themselves (403).
- Users are never deleted, only deactivated.

## 6. The alert workflow

### Statuses and transitions

```text
          analyst: escalate                 compliance: confirm
   new  ───────────────────►  in_review  ───────────────────►  confirmed_suspicious
    │   ◄───────────────────      │
    │     compliance: return      │ compliance: close
    │ analyst: close              ▼
    └──────────────────────────► closed
```

| From → To | Needs | Meaning in the UI |
| --- | --- | --- |
| `new` → `closed` | `alert:update` | Kapat · yanlış alarm |
| `new` → `in_review` | `alert:escalate` | Uyum görevlisine yükselt |
| `in_review` → `confirmed_suspicious` | `alert:confirm` | Şüpheli olarak onayla |
| `in_review` → `closed` | `alert:confirm` | Kapat · açıklaması var |
| `in_review` → `new` | `alert:confirm` | Analiste geri gönder |

`closed` and `confirmed_suspicious` are final. The table lives in
`backend/services/alert_workflow.py`; the React form mirrors it in
`features/alerts/workflow.ts`.

### Rules every decision follows

- **A note is required** for every decision (1–2,000 characters).
- **Four eyes:** the user who made the latest escalation of an alert cannot
  confirm or close it. This holds even with a single compliance officer, and
  even for the administrator.
- **Group decisions are atomic.** `POST /alerts/decisions` takes 1–50 alerts of
  **one customer in one status**. If any alert fails a check, nothing changes.
  Each alert gets its own history row and audit row; they share a
  `decision_id`.
- **Check order** (so error messages never reveal what a user may not do):
  401 not signed in → 403 no permission for the target status → 422 invalid
  body → 404 alert missing → 422 different customers/statuses → 422 transition
  not in the table → 403 no permission for this transition → 403 four eyes.

### The queue (`GET /alerts/queue`)

One row per **customer**, built on the server: all of the customer's pending
alerts, the rules that fired, the highest severity, the oldest alert, and
summary counts over **all** matching alerts (not just the visible page).

- Analysts default to `status=new`, sorted by severity, then oldest alert.
- Compliance defaults to `status=in_review&sort=waiting` (longest-waiting
  escalation first). Each row shows who escalated, the analyst's note and how
  long it has waited; more than 2 days is highlighted.
- A case sent back by compliance shows "Geri gönderildi · name" and the note.
- Compliance also has **Tüm alarmlar** (`/all-alerts`): every alert in any
  status, with a count per status, 25 per page.

### The alert detail page

Top to bottom: the decision context ("Analist neden yükseltti?", the reason it
was returned, or the final decision summary), **Neden tetiklendi?** (the rule's
own stored calculation, section 7), linked transactions, customer context, the
decision form, the history (with who did what) and the customer's other alerts.

### Customer data, masking and view logging

- **Customer context** (`GET /alerts/{id}/customer-context`): profile, masked
  accounts, last-30-day totals and up to **6 months** of masked transactions.
  Analysts may load it only while the alert is `new`; compliance for any
  status (`alert:confirm`).
- **Masking happens on the server**, because anything sent to the browser is
  readable in its developer tools. Individuals: `Ömer Kılıç` → `Ö. Kılıç`;
  companies: `Nehir Lojistik A.Ş.` → `Nehir L. A.`; account numbers: `…7781`.
  Users with `customer:view` receive full values on the alert detail page.
- **Every view of a customer's personal data writes a `customer.viewed` audit
  row** (BDDK information-systems regulation, article 13). Repeat views of the
  same customer by the same user within 30 minutes are not logged again. If the
  audit row cannot be written, the data is not returned (503).
- Audit readers without alert/customer access see notes and viewed customer
  numbers as `[gizli]`.

## 7. The detection engine

### When rules run

- After a CSV upload of transactions with at least one accepted row (attributed
  to the uploader).
- When a user with `rule:edit` presses **Kuralları çalıştır**
  (`POST /rules/evaluate`).
- During the demo seed, restricted to demo data.

There is no scheduled (nightly) run.

### One run, step by step

1. Load active customers, active transactions and every rule row.
2. Run each **active** rule. Order matters: transaction rules first
   (R01–R16, S1, S2), then **R18** (it combines this run's scores), then
   **R17** (it acts on saved alerts).
3. For each rule and customer, store a `rule_result`: parameter snapshot,
   status, raw value `x`, score and a step-by-step trace, plus links to the
   evidence transactions (`rule_result_transaction`). Every run is recorded in
   `detection_run`.
4. Open or update alerts (below), then apply R17.
5. Commit everything in one transaction.

### Parameters

Each rule stores two parameter sets in `monitoring_rule.thresholds`, one per
customer type (`BIREYSEL`, `KURUMSAL`), each with a status:

| Status | Effect |
| --- | --- |
| `UNSET` | Customers of that type are skipped (recorded as `skipped_unset`). |
| `PROVISIONAL` | Evaluated; alerts warn that thresholds are not approved yet. |
| `APPROVED` | Evaluated with institution-approved values. |

A rule can be activated only when at least one type is not `UNSET`. Values are
validated by the rule's Pydantic model (`backend/detection/parameters.py`), and
every change requires a written reason. The rule screen offers "copy Bireysel
values to Kurumsal" because some rules (R13, R14, R17, R18) are meant to use
one set. Each rule also has a **weight** (0–1) used only by R18.

### Scoring

Most rules turn their raw value `x` into a score with a sigmoid anchored on two
parameters: `x = x_esik` gives **0.5**, `x = x_kesin` gives **0.9**
(`backend/detection/scoring.py`; the curve is scaled by ln 9 so both anchors
are exact). Some rules differ: R02 is binary (0 or 1), R14 takes the larger of
its cycle and ping-pong scores, R15 gives 1 for direct contact and `gamma` for
one intermediary, and R18 returns its combined value directly.

| Score | Result | Severity |
| --- | --- | --- |
| < 0.5 | No alert | — |
| 0.5 – < 0.7 | Alert | low |
| 0.7 – < 0.9 | Alert | medium |
| ≥ 0.9 | Alert | high |

### How alerts are opened (no duplicates)

- If the customer already has an **open** (`new` or `in_review`) alert for the
  same rule, no new alert is opened. A higher score updates the alert's score
  and severity (logged as `alert.rescored`) and new evidence is attached.
  Severity never goes down.
- Otherwise a new alert is opened. If the rule fires again after the earlier
  alert was closed, a new alert is opened (with a numbered deduplication key).
- A database advisory lock stops two simultaneous runs from opening the same
  alert twice.
- Signal-only rules (S1, S2) never open alerts.

### "Neden tetiklendi?"

Every alert links back to the `rule_result` that produced its current score.
The detail page shows a one-sentence summary per rule, the raw value against
`x_esik`/`x_kesin`, and the full step list. Because the parameters are
snapshotted, the explanation stays correct even after the rule is changed.

### The rules

| Code | Name | Mode | Idea in one line |
| --- | --- | --- | --- |
| R01 | Bölme (structuring) | Alert | Several outgoing transfers just below the limit. |
| R02 | Büyük tek işlem | Alert | One transaction at or above the limit (binary). |
| R03 | Çok sayıda nakit yatırma | Alert | Repeated below-limit cash deposits into one account. |
| R04 | Gelir-hacim uyumsuzluğu | Alert | Recent volume far above monthly income. |
| R05 | Olağandışı tutar | Alert | Amount unusual against own history and income peers (robust z). |
| R06 | Hız artışı | Alert | This week's count improbably high against prior weeks. |
| R07 | Uyuyan hesap uyanması | Alert | High activity after a dormant period. |
| R08 | Yeni hesapta yüksek hareket | Alert | High volume on a recently opened account. |
| R09 | Nakit yoğunluğu | Alert | Cash share rising against the previous period. |
| R10 | Geçiş hesabı | Alert | Money in, quickly out to new recipients. |
| R11 | Para toplama (fan-in) | Alert | Many new senders. |
| R12 | Dağıtma (fan-out) | Alert | Many new recipients, similar amounts. |
| R13 | Katmanlama zinciri | Alert | Fast chain of transfers, each slightly smaller. |
| R14 | Döngü ve ping-pong | Alert | Money returns to its start, or goes back and forth. |
| R15 | Şüpheli hesapla temas | Alert | Direct or one-step contact with a confirmed-suspicious customer. |
| R16 | Listelenmiş ülke | Alert | Volume with listed (high-risk) countries. |
| S1 | Yuvarlak tutar | Signal only | Share of big outgoing transfers that are round amounts. |
| S2 | Merkez hesap | Signal only | Far more counterparties than peers of the same type. |
| R17 | Çoklu uyarı | Severity raise | Open alerts from ≥ `min_rules` different rules raise their severity one step (once per alert). No score. |
| R18 | Birleşik risk skoru | Alert | `A = min(1, (Σ (weight·score)^p)^(1/p))` over this run's scores; alert when `A ≥ alert_threshold`. |

Each rule's file in `backend/detection/rules/` holds its exact steps,
parameters and analyst review notes; the rules screen shows the same
information. New rules start **inactive and `UNSET`**.

The legacy rules **R1–R4** (from the original schema) remain in the database,
inactive, with no implementation. Their old alerts keep working but have no
"Neden tetiklendi?" calculation.

## 8. Data model

```text
customer 1──* account 1──* transaction (as sender)
                      1──* transaction (as receiver)
customer 1──* alert *──* transaction        (alert_transaction)
monitoring_rule 1──* alert
detection_run 1──* rule_result *──* transaction   (rule_result_transaction)
app_role *──* permission (role_permission);  app_user *──1 app_role
```

| Table | Holds |
| --- | --- |
| `customer`, `account`, `transaction` | Monitored data. Numbers are unique; amounts positive; channel and country formats checked. |
| `monitoring_rule` | Code, name, active flag, weight, thresholds (JSONB). |
| `detection_run`, `rule_result`, `rule_result_transaction` | Every run, every rule/customer result with its trace, and its evidence. |
| `alert`, `alert_transaction` | Alerts (status, severity, score, deduplication key) and their evidence. |
| `alert_status_history` | Every status change: who, when, from, to, note. |
| `rule_change_log` | Old and new thresholds for every rule edit. |
| `audit_log` | Every significant action (JSONB details). |
| `upload_batch`, `upload_row_error` | Upload reports and rejected rows. |
| `app_user`, `app_role`, `permission`, `role_permission` | Identity and RBAC. |

**Append-only:** database triggers reject `UPDATE` and `DELETE` on
`audit_log`, `alert_status_history` and `rule_change_log`. These records must
be kept for at least five years; nothing in the application deletes or
archives them.

## 9. API reference

Live, always-current reference: `http://127.0.0.1:8000/docs`.

**Conventions.** JSON in and out (except login: form; upload: multipart).
Dates are ISO 8601 local time. Money and scores are strings (`"45000.00"`,
`"0.8127"`) so no precision is lost. Paged lists return
`{"total": n, "items": [...]}` with `offset` and `limit`. Errors return
`{"detail": "<English text>"}`; the React app shows a Turkish translation, and
a test fails if a backend message has none (`tests/test_error_translations.py`).

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| `POST /auth/login` | public | Get a token. |
| `GET /auth/me` | signed in | Username, role, permissions. |
| `GET /health` | public | API and database up? |
| **Alerts** | | |
| `GET /alerts/queue` | `alert:view` | Customer-grouped queue with summary counts. |
| `GET /alerts` | `alert:view` | Alert list with filters; `include_counts=true` adds counts per status. |
| `GET /alerts/rule-codes` | `alert:view` | Rule filter options. |
| `GET /alerts/{id}` | `alert:view` | Detail, evidence, history with actors, escalated-by, explanation. |
| `GET /alerts/{id}/customer-context` | `alert:view` (+ `alert:confirm` unless `new`) | Masked customer context; logs a view. |
| `PATCH /alerts/{id}/status` | per transition | One alert decision. |
| `POST /alerts/decisions` | per transition | Atomic decision on 1–50 alerts of one customer. |
| `GET /dashboard/my-summary` | `alert:view` | The signed-in user's own counts and returned cases. |
| **Dashboards** | | |
| `GET /dashboard/summary?days=` | `dashboard:view` | Totals, distributions, daily trend. |
| `GET /dashboard/funnel?days=` | `dashboard:view` | Where alerts went (created = closed + open + escalated). |
| `GET /dashboard/rule-performance?days=` | `dashboard:view` | Per rule: evaluated, alerts, average score, hit rate. |
| **Customers and transactions** | | |
| `GET /customers`, `GET /customers/{no}`, `GET /accounts` | `customer:view` | Lists and profile; profile views are logged. |
| `GET /transactions` | `customer:view` | Filtered transactions; logs views. |
| `GET /transactions/summary` | `customer:view` | Totals, timeline and account-to-account routes computed in SQL. |
| **Rules** | | |
| `GET /rules` | `rule:view` | Rules with parameters, weight and metadata. |
| `GET /rules/{code}/history` | `rule:view` | Saved changes: who, when, why, old → new per field. |
| `PUT /rules/{code}` | `rule:edit` | Save parameters, weight, active flag; reason required. |
| `POST /rules/evaluate` | `rule:edit` | Run active rules now. |
| **Uploads** | | |
| `POST /uploads?entity=` | `upload:create` | Upload a CSV (`customer`, `account`, `transaction`). |
| `GET /uploads`, `GET /uploads/{id}` | `upload:view` | History and report; rejected row content only for the uploader. |
| **Administration** | | |
| `GET /users`, `GET /users/roles`, `POST /users`, `PATCH /users/{id}` | `user:manage` | User management. |
| `GET /admin/system-overview` | `user:manage` | Health, schema revision, rule engine, volumes, security settings (numbers only). |
| `GET /audit-log` | `audit:view` | Filtered audit events (`action`, `exclude_action`, actor, record, dates). The screen hides `customer.viewed` by default. A detection run's R17 raises are returned as one event with the alerts in `grouped`; each alert keeps its own stored row. |
| **Demo** | | |
| `GET /demo/status` | `dashboard:view` | Demo fixture inventory and scenarios. |
| `POST /demo/seed` | `upload:create` + `ENABLE_DEMO_ENDPOINTS=true` | Seed the demo data and evaluate it (404 when disabled). |

## 10. CSV upload

Upload **customers first, then accounts, then transactions**: each refers to
rows of the previous kind.

1. The file must be `.csv`, UTF-8 (a BOM is fine), at most **5 MB** and
   **5,000 rows**, with the required headers.
2. Each row is validated on its own. Invalid rows are rejected with a row
   number and reason; valid rows are accepted. Row numbering starts at 2 (row 1
   is the header).
3. Accepted rows, rejected rows, the batch counts and an audit entry are saved
   in one transaction.
4. After a transaction upload with accepted rows, the rules run automatically.

| Entity | Main checks |
| --- | --- |
| Customer | Customer number and full name required; text lengths; income non-negative, max 2 decimals. |
| Account | Existing customer; account number; 3-letter currency. |
| Transaction | Existing sender and receiver accounts; positive amount (max 2 decimals); channel; 2-letter country; currency matching the accounts; ISO timestamp. |
| All | No missing or duplicate IDs, in the file or in the database. |

The **Veri yönetimi** screen offers templates, shows the result and lists past
uploads.

## 11. The demo lab

`backend/demo.py` builds a repeatable synthetic fixture reserved under `DEMO-*`
numbers: **32 customers, 32 TRY accounts and 93 transactions**, with **one
scenario per rule (20)**. Each scenario names the target customer and the
activity designed to trigger the rule.

- **Default mode** evaluates every rule with demo-only `PROVISIONAL`
  parameters. Saved rule settings and active flags are not touched.
- **Saved-settings mode** uses the rules as configured; inactive rules show as
  not evaluated.
- Only demo customers and transactions between them are evaluated, so real
  data is never affected. Seeding is repeatable: it repairs the fixture, moves
  timestamps relative to now and never deletes anything.
- A scenario passes when its score is ≥ 0.50. Signal-only S1 and S2 pass on
  score alone; R18 targets the S1 customer, showing a signal turned into an
  alert. R17 has no score, so it passes when its saved trace shows it raised
  severity (open alerts from at least `min_rules` rules).
- `DEMO-022` is the synthetic "confirmed suspicious" customer for R15; no real
  alert history is created for it.

Passing scenarios show that a rule can fire, not that its thresholds are
right. The demo customers trigger many rules at once, so R18 alerts on most of
them.

## 12. The interfaces

### React (`frontend-v2/`) — the primary interface

| Screen | Path | Who |
| --- | --- | --- |
| Tespit özeti (overview: Özet / Alarm akışı / Kurallar tabs) | `/overview` | `dashboard:view` |
| Alarm inceleme (queue) and alert detail | `/alerts`, `/alerts/:id` | `alert:view` |
| Tüm alarmlar | `/all-alerts` | `alert:confirm` |
| İşlem analizi | `/transactions` | `customer:view` |
| Müşteriler and customer profile | `/customers`, `/customers/:no` | `customer:view` |
| Veri yönetimi | `/data` | `upload:create` or `upload:view` |
| Demo laboratuvarı | `/demo` | `dashboard:view` |
| Kural yönetimi | `/rules` | `rule:view` (editing: `rule:edit`) |
| Sistem özeti, Kullanıcı yönetimi | `/system`, `/users` | `user:manage` |
| Denetim kaydı | `/audit` | `audit:view` |

Code layout:

- `src/features/<area>/` — one folder per screen: the page, its `api.ts`
  (TanStack Query hooks) and its tests.
- `src/api/client.ts` and `src/api/schemas/` — the HTTP client and the zod
  schema of every response. When an API response changes, update its schema
  in the same change.
- `src/app/navigation.ts` — menu items and the permission each needs (route
  guards use the same list).
- `src/i18n/locales/tr.ts` and `en.ts` — all text. Turkish is the default;
  English, light and dark themes are available.
- `src/test/` — MSW request mocks and shared test data.

Conventions: money stays a string and is summed in integer cents; dashboards
are cached for 60 seconds and refreshed after a decision; overview tabs load
only when opened.

### Streamlit (`frontend/`) — legacy

The original interface. It has **not** been updated for the current API: some
pages call endpoints that were removed (for example the alert investigation
page), and it does not know the compliance workflow. Keep it only for
reference; new work goes into React.

## 13. Database migrations

Alembic records the applied revision in `alembic_version`. Never edit a
migration that has been applied; add a new one. Every migration is mirrored as
a SQL file in `database/`.

| Revision | Mirror | What it does |
| --- | --- | --- |
| `0001_existing_schema_baseline` | `V1` | Creates the original schema on an empty database, or adopts an existing complete one. Stops if only some tables exist. |
| `0002_rbac` | `V2` | Roles, permissions and `role_permission`; seeds admin and analyst. |
| `0003_rule_framework` | `V3` | `detection_run`, `rule_result`, weights and scores; seeds R01–R03; deactivates legacy R1–R4. |
| `0004_extended_detection_rules` | — | Seeds R04–R15 (inactive, `UNSET`). |
| `0005_system_overview_metrics` | `V4` | Adds `account.created_at` and `detection_run.duration_ms` for the system overview. |
| `0006_alert_workflow` | `V5` | Compliance role, `alert:escalate` and `alert:confirm`, K13 admin restriction; seeds R16, R17, R18, S1, S2. |
| `0007_admin_all_permissions` | `V6` | **Development only:** the admin gets every permission again. |

Common commands:

```powershell
.\.venv\Scripts\alembic.exe upgrade head      # apply everything
.\.venv\Scripts\alembic.exe current           # what is applied
.\.venv\Scripts\alembic.exe heads             # what the code expects
```

A database created by hand from the original SQL (no `alembic_version`): run
`alembic stamp 0001_existing_schema_baseline`, then `alembic upgrade head`.

## 14. Configuration

Read from `.env` (or the process environment). Never commit `.env`.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic, integration tests | PostgreSQL URL, e.g. `postgresql+psycopg2://USER:PASSWORD@localhost:5432/izleme_alarm`. Required. |
| `JWT_SECRET` | API | Token signing key; long and random. Required. |
| `ENABLE_DEMO_ENDPOINTS` | API | `true` enables `POST /demo/seed`. Default `false`; development only. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `create_admin` | Optional; otherwise the script asks. |
| `VITE_API_PROXY_TARGET` | React dev server | Where `/api` goes. Default `http://127.0.0.1:8000`. |
| `API_UPSTREAM`, `PORT` | React container (nginx) | API address (default `http://backend:8000`) and port (default `8080`). |
| `API_BASE_URL` | Streamlit | API address for the legacy interface. |

Inside a container, `localhost` is the container itself. Use
`host.docker.internal` to reach a database on the host.

## 15. Testing

```powershell
# Backend (from the repository root)
.\.venv\Scripts\python.exe -m pytest tests -q

# React (from frontend-v2)
npm test
npm run typecheck
npm run lint
npm run build
```

- **Backend unit tests** (`tests/*.py`) need no database: rules and scoring,
  parameter validation, route permissions, audit redaction, error
  translations, the demo fixture.
- **Integration tests** (`tests/integration/`) run against the database in
  `DATABASE_URL`, each inside a transaction that is rolled back, so nothing
  persists. They are skipped when `DATABASE_URL` is not set. **Point it at a
  local test database, never at a shared or production one.** They cover the
  workflow, four eyes, the queue, customer access and masking, dashboards,
  rule history and the new rules end to end.
- **React tests** use Vitest, Testing Library and MSW; unhandled requests fail
  the test. Accessibility checks run with axe.

When something looks wrong in the interface, check in this order: the browser's
network tab (the request and response), then `/docs` (call the API directly),
then the API log. That shows which layer is at fault.

## 16. How to change things

**Add a rule.**

1. Create `backend/detection/rules/<code>_<name>.py` with a `RuleStrategy`
   subclass: a `RuleDefinition` (code, name, steps, parameters, alert mode)
   and `evaluate_raw`. The registry finds it automatically.
2. Add its parameter model to `backend/detection/parameters.py`.
3. Add a migration that inserts its `monitoring_rule` row (inactive, `UNSET`)
   and a mirror SQL file. The engine refuses to run if a rule has no row.
4. Add its fields to `frontend-v2/src/features/rules/model.ts` and its
   summary sentence to the locale files.
5. Add demo parameters and a scenario in `backend/demo.py`. A test fails if a
   registered rule has no scenario.

**Add an endpoint.** Route in `backend/api/routes/` with
`require_permission(...)` and a `response_model`; logic in a service; SQL in a
repository. Add a permission case to `tests/test_rbac.py` (nothing checks this
automatically), a Turkish translation for any new error text, a zod schema and
a hook in React.

**Add a permission.** Add it in a migration, grant it to the right roles **and
to admin** (see section 5), mirror it in `database/`, and add it to
`frontend-v2/src/auth/permissions.ts`.

**Change an error message.** Change it in the backend and in `tr.ts`/`en.ts`
together; the translation test enforces this.

## 17. Limits and open items

- **Admin permissions:** K13 is suspended in development by migration `0007`
  (section 5). Restore it before any real deployment.
- **No scheduler:** rules run on upload, on demand and in the demo only.
- **Provisional thresholds:** rule parameters are examples, not calibrated
  policy. The hit-rate review mark ("Gözden geçir": below 10% over 30 days,
  with at least 5 decided alerts) is a proposal awaiting the mentor's view.
- **Currencies:** no exchange-rate conversion; income is assumed to be TRY
  where a rule needs it.
- **Graph rules (R13, R14)** may be slow on dense data; measured only on the
  small demo graph.
- **Growth:** `rule_result` gets one row per rule and customer per run; a
  retention policy and extra indexes are needed at real volumes.
- **Identity:** no MFA, SSO or password reset. Swagger (`/docs`) should be
  closed or internal-only outside development.
- **Uploads:** synchronous, with no malware scan or streaming import.
- **No production operations:** backups, monitoring and secrets management are
  out of scope.
- **Not built on purpose:** rule simulation ("etkisini gör", decision K5) and
  export of customer data from the screens.

## 18. Glossary

| Term | Meaning |
| --- | --- |
| Alert | A rule's finding about one customer, reviewed by people. |
| Score `s` | A rule's result between 0 and 1; 0.5 or more opens an alert. |
| `x`, `x_esik`, `x_kesin` | The rule's raw measurement; the value scoring 0.5; the value scoring 0.9. |
| Signal-only rule | A rule that never alerts alone and only feeds R18 (S1, S2). |
| Escalation (yükseltme) | The analyst sending an alert to compliance (`new` → `in_review`). |
| Four eyes (dört göz) | The person who escalated cannot make the final decision. |
| Detection run | One execution of the rules (`detection_run`), with a result per rule and customer (`rule_result`). |
| Step trace | The stored, step-by-step calculation behind a result; it powers "Neden tetiklendi?". |
| Hit rate (isabet) | confirmed ÷ (confirmed + closed) for a rule's alerts. |
| Masking | Hiding part of personal data on the server (`Ö. Kılıç`, `…7781`). |
| Append-only | Rows can be added but not changed or deleted; enforced by database triggers. |
| `UNSET` / `PROVISIONAL` / `APPROVED` | A parameter set's status: not configured (skipped) / temporary / institution-approved. |
| K1–K13 | Design decisions in the API design document (v0.6). |
| MASAK, BDDK, KVKK | Turkey's financial crimes board, banking regulator, and personal data protection law. |
