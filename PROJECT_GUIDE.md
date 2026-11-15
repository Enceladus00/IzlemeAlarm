# IzlemeAlarm project guide

This is the reference for how IzlemeAlarm works and how to change it. The
interface calls itself **Sentinel**; both names refer to the same system.

Sections 1–3 give the overall picture. The rest is reference material, ordered
roughly from what a user sees (workflow, rules) to what an operator needs
(migrations, configuration, deployment).

IzlemeAlarm is a learning and demonstration project. It runs on synthetic data,
its rules are deterministic formulas with provisional thresholds, and it uses
no machine learning. It is not meant to make real risk decisions.

## Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Repository layout](#3-repository-layout)
4. [Local development](#4-local-development)
5. [Roles, permissions and sign-in](#5-roles-permissions-and-sign-in)
6. [Alert workflow](#6-alert-workflow)
7. [Customer data protection](#7-customer-data-protection)
8. [Request limits](#8-request-limits)
9. [Detection engine](#9-detection-engine)
10. [Data model](#10-data-model)
11. [API reference](#11-api-reference)
12. [CSV upload](#12-csv-upload)
13. [Demo lab and example data](#13-demo-lab-and-example-data)
14. [User interfaces](#14-user-interfaces)
15. [Database migrations](#15-database-migrations)
16. [Configuration](#16-configuration)
17. [Testing](#17-testing)
18. [CI and deployment](#18-ci-and-deployment)
19. [Making changes](#19-making-changes)
20. [Known limits](#20-known-limits)
21. [Design decisions K1–K13](#21-design-decisions-k1k13)
22. [Glossary](#22-glossary)

---

## 1. Overview

Banks have to find suspicious transactions, have someone accountable decide on
each case, and later be able to show who decided what and on what basis.
IzlemeAlarm covers that process from start to finish:

1. Customers, accounts and transactions are uploaded as CSV files. Each row is
   validated separately; rejected rows are reported with a reason.
2. Twenty rules (R01–R18, S1, S2) give each customer a score between 0 and 1. A
   score of 0.5 or more on an alerting rule opens an alert.
3. An analyst works through a queue grouped by customer. For each alert the
   system shows the calculation that produced it. The analyst either closes
   the alert as a false positive or escalates it.
4. A compliance officer confirms escalated alerts as suspicious, closes them,
   or sends them back to the analyst. The person who escalated an alert cannot
   decide on it (four eyes).
5. Decisions, rule changes, uploads, sign-ins, refused requests and every view
   of customer data go to an audit log. Database triggers block edits and
   deletes on it.

The roles are analyst, compliance officer and administrator (section 5).

What the system does not do: it does not score transactions in real time,
convert currencies, file reports with regulators, or learn from past
decisions.

## 2. Architecture

```text
Development
  Browser ── Vite dev server :5173 ──/api──► FastAPI :8000 ──► PostgreSQL (local or Neon)

Production (AWS ECS Express, eu-north-1)
  Browser ──► frontend service: nginx :8080 ──/api──► backend service: FastAPI :8000 ──► Neon PostgreSQL
              (static React build)                    (one Fargate task)
```

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Interface | React 19, TypeScript, Vite, TanStack Query, Tailwind CSS 4 | Screens. Calls only its own origin under `/api`; Vite or nginx forwards to FastAPI without the prefix, so the API needs no CORS. |
| API | FastAPI, Pydantic, Uvicorn | Authentication, permission checks, validation, workflows, the detection engine. |
| Data | PostgreSQL, SQLAlchemy 2, Alembic | System of record. Constraints and triggers protect integrity even if the API has a bug. |

Permissions are enforced by the API. The interface hides screens and buttons
the user cannot use, but that is only for convenience: a request sent straight
to the API gets the same checks, and a refused request is logged as
`ACCESS_DENIED`.

### Request path

Example: an analyst escalates two alerts of one customer.

1. React sends `POST /api/alerts/decisions` with the alert IDs, the target
   status and a note. Vite (or nginx) strips `/api` and forwards the request.
2. Two middlewares run first (`backend/request_guards.py`): a body-size limit
   and a per-address limit for requests without a valid token.
3. `require_permission("alert:view")` decodes the bearer token and reloads the
   user, role and permissions from the database. Inactive users are refused.
4. The route (`backend/api/routes/alerts.py`) only translates HTTP. It calls
   `AlertService`, which checks the transition table, permissions and four
   eyes.
5. The repository (`backend/repositories/alert_repository.py`) writes the whole
   decision in one transaction: status changes, history rows and audit rows
   for every alert, or nothing.
6. The response is filtered through a Pydantic `response_model`
   (`backend/api/responses.py`), so fields outside the model never leave the
   server.
7. React parses the response with a zod schema (`src/api/schemas/`) and
   invalidates the cached queries that depend on it (queue, dashboards).

Layer rules: routes map HTTP to service calls and exceptions to status codes;
services hold workflows; repositories own SQL; rule strategies are pure
calculations with no database access. A `RuntimeError` that escapes a route
becomes a 503 with its message (`backend/main.py`).

### Conventions across the stack

- Money and scores travel as JSON strings (`"45000.00"`, `"0.8127"`) to keep
  `Decimal` precision. The React app sums money in integer cents.
- Timestamps are ISO 8601 without a time zone and are shown as stored.
- Paged lists return `{"total": n, "items": [...]}` and take `offset` and
  `limit`.
- Errors return `{"detail": "<English text>"}`. The interface shows a Turkish
  (or English) wording for each known message, and
  `tests/test_error_translations.py` fails if a backend message has no
  translation.

## 3. Repository layout

| Path | Contents |
| --- | --- |
| `backend/main.py` | Builds the FastAPI app, middlewares and routers. Start with `uvicorn backend.main:app`. |
| `backend/api/routes/` | Endpoints by area: `alerts`, `analysis` (dashboards, health, system overview, demo), `audit`, `auth`, `customers`, `rules`, `transactions`, `uploads`, `users`. |
| `backend/api/dependencies.py` | Per-request service construction, `require_permission(...)`, `rate_limited(...)`. |
| `backend/api/responses.py` | Response models: the exact shape each endpoint may return. |
| `backend/api_schemas.py` | Request bodies (decisions, rule updates, users). |
| `backend/services/` | Workflows. `alert_workflow.py` holds the transition table and four-eyes check; `masking.py` the masking rules; others per area. |
| `backend/repositories/` | All SQL. `customer_view_log.py` writes `customer.viewed` audit rows. |
| `backend/detection/` | `engine.py` (runs rules), `parameters.py` (parameter models), `scoring.py`, `evidence.py` (severity, deduplication keys), `registry.py`, `metadata.py`, and `rules/` with one file per rule. |
| `backend/demo.py` | The synthetic demo fixture and one scenario per rule. |
| `backend/models.py` | SQLAlchemy entities. |
| `backend/security.py` | bcrypt hashing and HS256 JWT tokens. |
| `backend/rate_limit.py`, `backend/request_guards.py` | In-memory rate limits; body-size and anonymous-request middlewares. |
| `backend/scheduler.py` | Optional daily detection run inside the API (section 9). |
| `backend/scripts/` | `create_admin.py`, `seed_example_data.py`, `check_rule_coverage.py`, `run_detection.py` (section 4). |
| `alembic/versions/` | Migrations `0001`–`0008` (section 15). |
| `database/` | `V1`–`V7` SQL files mirroring the migrations, for review and manual setup. |
| `frontend-v2/` | React interface (section 14). Has its own `README.md` on its conventions. |
| `frontend/` | Original Streamlit interface. Legacy; does not match the current API. |
| `tests/` | Backend unit tests; `tests/integration/` runs against a local PostgreSQL. |
| `.github/workflows/` | `ci.yml`, `tests.yml`, `deploy.yml`, `deploy-frontend.yml` (section 18). |
| `.aws/` | IAM policies used by the deployment (for reference; applied by hand). |
| `Dockerfile.backend`, `Dockerfile.frontend-v2`, `Dockerfile.frontend` | Images for the API, the React interface (nginx), and Streamlit. |
| `.vscode/launch.json` | Launch configurations (section 4). |
| `.env.example`, `frontend-v2/.env.example` | Configuration templates. |
| `Supheli_Islem_Proje_Durumu.pdf` | Rule design status report of 27 October 2026, written before the rules were coded. Kept as history: R02 now opens alerts instead of only feeding R18, and the weights it proposes were replaced in the November threshold review. |
| `project_file_structure.txt` | Tree of the tracked files. Regenerate it with the command in its header after adding or removing files. |

## 4. Local development

### Requirements

- Python 3.10 or newer (CI and the Docker image use 3.12)
- PostgreSQL with an empty database for development (CI uses PostgreSQL 16)
- Node.js 20 or newer for the React interface (CI and the image use 22)

### First-time setup

```powershell
# Python environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

# Configuration: copy the template, then set DATABASE_URL and JWT_SECRET
copy .env.example .env

# Schema
.\.venv\Scripts\alembic.exe upgrade head

# First administrator (asks for a username and password)
python -m backend.scripts.create_admin

# React dependencies
cd frontend-v2
npm install
```

There are no default users or passwords. After signing in as the
administrator, create an analyst and a compliance officer on
**Kullanıcı yönetimi**; the workflow needs both.

`.env` decides which database every command touches: the API, Alembic, the
scripts and the integration tests all read the same `DATABASE_URL`. Check it
before running anything that writes.

A database that already has the original schema but no `alembic_version`
table: run `alembic stamp 0001_existing_schema_baseline`, then
`alembic upgrade head`. Do not run `database/V1__initial_schema.sql` against an
existing schema.

### Starting the system

In VS Code, select the `.venv` interpreter and start
**Start project (API + React UI)** from Run and Debug. The configurations in
`.vscode/launch.json`:

| Configuration | Starts |
| --- | --- |
| API (FastAPI) | Uvicorn on `127.0.0.1:8000`, with `.env`, under the debugger. No auto-reload. |
| UI v2 (React) | `npm run dev` in `frontend-v2` (port 5173). |
| UI (Streamlit) | The legacy interface. |
| Start project (API + React UI) | API + React. |
| Start project (API + UI) | API + Streamlit. |

From a terminal:

```powershell
# API, with reload. Interactive docs: http://127.0.0.1:8000/docs
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# React, in a second terminal: http://localhost:5173
cd frontend-v2
npm run dev
```

### Test data

Two ways to get data that triggers rules:

- **Demo lab** (section 13). Set `ENABLE_DEMO_ENDPOINTS=true` in `.env`,
  restart the API, sign in with a user that has `upload:create`, open
  **Demo laboratuvarı** and press **Demo veriyi oluştur ve değerlendir**.
- **Example data script.** `python -m backend.scripts.seed_example_data
  [--batches N] [--seed S]` inserts customers, accounts and transactions built
  from the demo scenarios but with random Turkish names, `MUS-*` customer
  numbers and IBAN-style account numbers. It only inserts rows. Then run the
  rules from **Kural yönetimi** or `POST /rules/evaluate`.

`python -m backend.scripts.check_rule_coverage [--prefix MUS-]` runs every
implemented rule in memory against those customers, using the saved
parameters, and prints the best score and the number of customers that would
get an alert per rule. It writes nothing.

`python -m backend.scripts.run_detection` runs every active rule over all
data once, as the system, exactly like the daily scheduled run (section 9). It
writes alerts and a `detection.auto_run` audit event.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Backend changes have no effect | The API runs without `--reload` (the VS Code configuration does not reload). Restart it. |
| "Demo seeding is disabled" | `ENABLE_DEMO_ENDPOINTS` is not `true` in the running API's environment. Restart after editing `.env`. |
| The API exits at start-up | `JWT_SECRET` is not set. |
| Every screen shows a server error | Call `GET /health`. Then check `DATABASE_URL`, that PostgreSQL is running, and `alembic current` against `alembic heads`. |
| "Too many requests" | A rate limit (section 8). Counters reset when the API restarts. |
| A screen says "no permission" | The role lacks that permission (section 5). |
| Integration tests are all skipped | `DATABASE_URL` is unset or does not point at `localhost` (section 17). |

When the interface shows something wrong, look in this order: the browser's
network tab (request and response), the same call in `/docs`, then the API
log. That tells you which layer is at fault.

## 5. Roles, permissions and sign-in

### Permissions by role

| Permission | Allows | Analyst | Compliance | Admin |
| --- | --- | :-: | :-: | :-: |
| `alert:view` | See alerts and the queue | ✓ | ✓ | ✓¹ |
| `alert:update` | Close a `new` alert as a false positive | ✓ | | ✓¹ |
| `alert:escalate` | Send a `new` alert to compliance | ✓ | | ✓ |
| `alert:confirm` | Decide on escalated alerts; see any alert's customer context | | ✓ | ✓ |
| `customer:view` | Customers, accounts, transaction analysis | | ✓ | ✓¹ |
| `dashboard:view` | Detection overview and demo lab | ✓ | ✓ | ✓ |
| `rule:view` | Read rules | ✓ | ✓ | ✓ |
| `rule:edit` | Change rules; run rules on demand | | ✓ | ✓ |
| `audit:view` | Audit log | | ✓ | ✓ |
| `upload:create`, `upload:view` | CSV upload and upload reports | | | ✓ |
| `user:manage` | Users and system overview | | | ✓ |
| `role:manage` | Reserved; no endpoint uses it | | | ✓ |

¹ Development setting. Decision K13 says the administrator runs the system but
never sees alert or customer content; migration `0006` implements that.
Migration `0007` gives the administrator every permission again for
development. Run `alembic downgrade 0006_alert_workflow` to restore K13. A
migration that adds a permission must also grant it to the administrator.

The compliance officer does not have `alert:update`, so they cannot close a
`new` alert themselves and skip the analyst.

A legacy `auditor` role exists only in databases that had auditor users before
the RBAC migration. It has no permissions.

### Sign-in and sessions

- `POST /auth/login` takes form fields `username` and `password` and returns an
  HS256 bearer token valid for 30 minutes. Tokens cannot be refreshed.
- A wrong password, an unknown user and an inactive user get the same
  response. For unknown usernames a dummy bcrypt check still runs, so response
  time does not reveal whether a user exists.
- Passwords longer than 72 UTF-8 bytes are rejected (a bcrypt limit).
- Every protected request reloads the user from the database, so deactivation
  and role changes take effect on the next request.
- Unauthenticated endpoints: `POST /auth/login` and `GET /health`.
- The React app keeps the token in memory and in `sessionStorage`: refreshing
  the page keeps the session, closing the tab ends it. It signs out when the
  token expires or any request returns 401, and shows a countdown before
  expiry.
- Users cannot change their own role or deactivate themselves (403). Users are
  never deleted, only deactivated.

## 6. Alert workflow

### Statuses

```text
          analyst: escalate                 compliance: confirm
   new  ───────────────────►  in_review  ───────────────────►  confirmed_suspicious
    │   ◄───────────────────      │
    │     compliance: return      │ compliance: close
    │ analyst: close              ▼
    └──────────────────────────► closed
```

| From → to | Permission | Button in the interface |
| --- | --- | --- |
| `new` → `closed` | `alert:update` | Kapat · yanlış alarm |
| `new` → `in_review` | `alert:escalate` | Uyum görevlisine yükselt |
| `in_review` → `confirmed_suspicious` | `alert:confirm` | Şüpheli olarak onayla |
| `in_review` → `closed` | `alert:confirm` | Kapat · açıklaması var |
| `in_review` → `new` | `alert:confirm` | Analiste geri gönder |

`closed` and `confirmed_suspicious` are final. The table is defined in
`backend/services/alert_workflow.py` and mirrored for the form in
`frontend-v2/src/features/alerts/workflow.ts`.

### Decision rules

- Every decision needs a note of 1–2,000 characters.
- Four eyes: the user who made the most recent escalation of an alert cannot
  confirm or close it. This applies to the administrator too, and it means a
  case escalated by the only compliance-capable user cannot be decided.
- `POST /alerts/decisions` takes 1–50 alerts that belong to one customer and
  share one status. If any of them fails a check, none changes. Each alert gets
  its own history row and audit row, linked by a shared `decision_id`.
  `PATCH /alerts/{id}/status` is the single-alert form.
- Checks run in a fixed order so that an error never reveals more than the
  user may know: 401 not signed in → 403 no permission for the target status →
  422 invalid body → 404 alert not found → 422 mixed customers or statuses →
  422 transition not allowed → 403 no permission for this transition → 403
  four eyes.

### Queue

`GET /alerts/queue` returns one row per customer, built on the server: the
customer's pending alerts, which rules fired, the highest severity, the oldest
alert, and summary counts over every matching alert (not only the current
page).

- Analysts see `status=new` by default, sorted by severity and then by the
  oldest alert.
- Compliance sees `status=in_review&sort=waiting` by default: longest-waiting
  escalation first, with who escalated it, their note and the waiting time.
  Cases waiting more than two days are highlighted.
- A case returned by compliance shows "Geri gönderildi" with the name and note.
- **Tüm alarmlar** (`/all-alerts`, compliance only) lists every alert in any
  status with a count per status, 25 per page.
- **Panelim** (`/my-panel`, for users with `alert:escalate`) is the analyst's
  landing page: their own counts and cases returned to them, from
  `GET /dashboard/my-summary`.

### Alert detail

From top to bottom: decision context (why the analyst escalated, why the case
was returned, or the final decision), **Neden tetiklendi?** (the stored
calculation, section 9), linked transactions, customer context, the decision
form, the status history with the user behind each change, and the customer's
other alerts.

## 7. Customer data protection

These measures follow KVKK (Turkey's personal data protection law) and the
BDDK information systems regulation.

**Masking on the server.** Anything sent to the browser can be read in its
developer tools, so masking happens before the response is built
(`backend/services/masking.py`).

| Data | Example |
| --- | --- |
| Individual name | `Ömer Kılıç` → `Ö. Kılıç` |
| Company name | `Nehir Lojistik A.Ş.` → `Nehir L. A.` |
| Account number | `…7781`; flow diagram labels look like `TR..4410` |

Users with `customer:view` get full values on the alert detail page.

**Customer context on an alert** (`GET /alerts/{id}/customer-context`): the
profile, masked accounts, last-30-day totals per currency and up to six months
of masked transactions. Analysts can load it only while the alert is `new`;
`alert:confirm` allows it for any status.

**View logging.** Every response that reveals a customer's personal data
writes a `customer.viewed` audit row (BDDK regulation, article 13). This covers
alert customer context, customer profiles and analysis, account lists, and
transaction lists (by account owner, or every customer on an unfiltered page).
Repeat views of the same customer by the same user within 30 minutes are not
logged again. If the audit row cannot be written, the data is not returned
(503).

**Redaction in the audit log.** Readers without alert or customer access (the
administrator once K13 is restored) see decision notes and viewed customer
numbers as `[gizli]`.

**Rejected upload rows** contain raw customer data, so only the user who
uploaded the file gets them back.

**Network graph references.** The transaction network graph expands a
counterparty without sending its account number. The server issues an
`account_ref` of the form `<account_id>.<HMAC>` (signed with `JWT_SECRET`), and
`GET /transactions/summary?account_ref=...` rejects any reference it did not
sign, so clients cannot enumerate account IDs.

## 8. Request limits

All limits are in `backend/rate_limit.py` and `backend/request_guards.py`.
Exceeding one returns 429 with a `Retry-After` header.

| Limit | Value |
| --- | --- |
| Failed logins, one account from one address | 5 per 15 minutes |
| Failed logins, one address, any account | 30 per 15 minutes |
| Concurrent password checks | 4; further logins get 503 with `Retry-After` |
| Authenticated requests, per user | 300 per minute |
| CSV uploads, per user | 10 per hour |
| Demo seeds, per user | 10 per hour |
| Rule evaluations (`POST /rules/evaluate`), per user | 20 per hour |
| Requests without a valid token, per address | 120 per minute |
| Request body | 1 MB; 6 MB for `/uploads` (413 above that) |

Login limits are checked before the password. The first refused login of a
block writes one `LOGIN_RATE_LIMITED` audit row.

Counters live in process memory and reset on restart. That is correct only
while the API runs as a single task with one worker, which is how it is
deployed. Running more tasks needs shared storage for the counters first,
otherwise each task allows the full limit.

**Client address.** Behind nginx the API cannot trust `X-Forwarded-For`. nginx
takes the rightmost address of that header (written by the load balancer) and
sends it as `X-Client-Address`, together with `X-Proxy-Secret`. The API uses
`X-Client-Address` only when the secret matches `PROXY_SHARED_SECRET`;
otherwise it uses the socket address.

## 9. Detection engine

### When rules run

- After a CSV upload of transactions with at least one accepted row (the run is
  attributed to the uploader).
- When a user with `rule:edit` presses **Kuralları çalıştır**
  (`POST /rules/evaluate`).
- During a demo seed, limited to demo data.
- Once a day, when `DETECTION_SCHEDULE_TIME` is set (below).
- From `python -m backend.scripts.run_detection`.

### Daily run

Set `DETECTION_SCHEDULE_TIME` to a time `HH:MM` and the API starts a
background thread (`backend/scheduler.py`) that runs every active rule over
all data at that time each day. Unset or empty means no scheduled run; a
malformed value stops the API at start-up.

- The time is read on the API process's clock. Containers run on UTC, so
  `23:00` there is 02:00 in Türkiye.
- The run has no user. Its audit event is `detection.auto_run` with no actor
  (shown as "Sistem") and `"trigger": "scheduled"` in the details. Runs from
  `run_detection` carry `"trigger": "manual-script"`.
- A failed run is logged and the schedule continues the next day. A run missed
  while the API was down is not repeated.
- It assumes one API task. Several tasks would each run the rules; the
  advisory lock and deduplication keep that from creating duplicate alerts.
- To run on an external scheduler instead (cron, an ECS scheduled task), leave
  the variable empty and call `run_detection`.

### A run, step by step

1. Load active customers, active transactions and every rule row.
2. Evaluate each active rule in stages: transaction rules (R01–R16, S1, S2),
   then R18 (combines this run's scores), then R17 (acts on stored alerts).
3. For each rule and customer, store a `rule_result` with the parameter
   snapshot, status, raw value `x`, score and a step-by-step trace, plus the
   evidence transactions (`rule_result_transaction`). The run itself is a
   `detection_run` row with its duration.
4. Open or update alerts, then apply R17.
5. Commit everything in one transaction.

### Parameters

Each rule stores two parameter sets in `monitoring_rule.thresholds`, one per
customer type (`BIREYSEL`, `KURUMSAL`). Each set has a status:

| Status | Effect |
| --- | --- |
| `UNSET` | Customers of that type are skipped (recorded as `skipped_unset`). |
| `PROVISIONAL` | Evaluated. Alerts note that the thresholds are not yet approved. |
| `APPROVED` | Evaluated with institution-approved values. |

- A rule can be switched on only when at least one set is not `UNSET`.
- Values are validated by the rule's Pydantic model in
  `backend/detection/parameters.py`. Unknown keys are rejected. Optional
  settings left empty are not stored.
- Every change needs a written reason (1–500 characters), which goes to the
  audit log; old and new thresholds go to `rule_change_log`. `GET /rules/{code}/history` shows the
  changes field by field.
- The rules screen can copy the individual set to the corporate set; R13, R14,
  R17 and R18 are meant to use one set for both.
- Each rule has a weight between 0 and 1, used only by R18.

The values currently in the production database came from a rule threshold
review in November 2026 and are all `PROVISIONAL`.

### Scoring

Most rules turn their raw value `x` into a score with a logistic curve
anchored on two parameters: `x = x_esik` scores 0.5 and `x = x_kesin` scores
0.9 (`backend/detection/scoring.py`; the slope is scaled by ln 9 so both
anchors are exact). `x_kesin` must be greater than `x_esik`.

Exceptions: R02 is binary (0 or 1). R14 takes the larger of its cycle and
ping-pong scores. R15 scores 1 for direct contact and `gamma` for contact
through one intermediary. R18 returns its combined value directly. R17 has no
score.

| Score | Outcome | Severity |
| --- | --- | --- |
| below 0.5 | no alert | — |
| 0.5 to below 0.7 | alert | low |
| 0.7 to below 0.9 | alert | medium |
| 0.9 or more | alert | high |

### Opening alerts

- If the customer already has an open (`new` or `in_review`) alert from the
  same rule, no new alert is opened. A higher score raises the alert's score
  and severity (audit action `alert.rescored`) and the new evidence is
  attached. Severity never goes down.
- Otherwise a new alert is opened with the deduplication key
  `<rule>:<customer_id>:<date>`. If the rule fires again the same day after
  that alert was closed, the key gets a suffix (`:2`, `:3`, …).
- A PostgreSQL advisory lock (`pg_advisory_xact_lock`) serialises alert writes,
  so an upload-triggered run and a manual run cannot open the same alert
  twice.
- S1 and S2 never open alerts.

### "Neden tetiklendi?"

Each alert points at the `rule_result` that produced its current score. The
detail page shows a one-sentence summary per rule, the raw value against
`x_esik` and `x_kesin`, and the full step list. Because the parameters were
snapshotted with the result, the explanation stays accurate after the rule is
edited.

### The rules

`x` is the raw measurement that gets scored. Feasibility is the rating stored
in each rule's definition: how well the available data supports the rule.

| Code | Name | Mode | What `x` measures | Main parameters | Feasibility |
| --- | --- | --- | --- | --- | --- |
| R01 | Bölme | alert | Number of outgoing transfers just below the limit (`band_low`–1 × limit) within the window, in the income currency | `limits`, `window_days`, `band_low`, `above_check`, `minimum_income_ratio`, `income_currency` | medium |
| R02 | Büyük tek işlem | alert (binary) | Whether one transaction reaches the limit; transfers between the customer's own accounts excluded | `limits` | high |
| R03 | Çok sayıda nakit yatırma | alert | Below-limit cash deposits across all of the customer's accounts, per currency | `limits`, `window_days`, `cash_channels` | medium |
| R04 | Gelir-hacim uyumsuzluğu | alert | Largest recent external in- or outflow relative to monthly income (income assumed TRY) | `window_days`, optional minimum volume `limits` | medium |
| R05 | Olağandışı tutar | alert | Robust z-score of today's transfers against the customer's history and income peer group | `history_days`, `kappa`, `mad_floor`, `income_bands`, optional minimum `limits` | medium |
| R06 | Hız artışı | alert | How improbable the last 7 days' transfer count is against earlier 7-day slices (Poisson or negative binomial) | `history_weeks`, `min_count`, `season_factor`, optional `dispersion_k` | medium |
| R07 | Uyuyan hesap uyanması | alert | Activity this week on an account dormant for `dormant_days` | `limits`, `dormant_days`, `window_days` | high |
| R08 | Yeni hesapta yüksek hareket | alert | Volume since opening on an account younger than `account_age_days` | `limits`, `account_age_days` | high |
| R09 | Nakit yoğunluğu | alert | Cash share of activity in the window against the baseline period | `limits`, `window_days`, `baseline_days`, `cash_channels` | medium |
| R10 | Geçiş hesabı | alert | Share of incoming money passed on to new recipients within `window_hours` | `limits`, `window_hours`, `ratio_low`, `ratio_high`, `cash_accounts` | medium |
| R11 | Para toplama (fan-in) | alert | Number of first-time sender accounts in the window | `window_days`, `cash_accounts` | medium |
| R12 | Dağıtma (fan-out) | alert | Number of new recipients, weighted up when amounts are similar (low coefficient of variation) | `window_days`, `cv_threshold`, `cv_multiplier`, `cash_accounts` | medium |
| R13 | Katmanlama zinciri | alert | Length of fast chains of transfers, each slightly smaller than the one before | `max_step_hours`, `decay_low`, `decay_high`, `max_depth`, optional minimum `limits` | low |
| R14 | Döngü ve ping-pong | alert | Money returning to its origin, or moving back and forth between two accounts | `max_cycle_length`, `min_retained`, `pingpong_tolerance`, optional minimum `limits` | low |
| R15 | Şüpheli hesapla temas | alert | Direct (score 1) or one-intermediary (score `gamma`) contact with a confirmed-suspicious customer | `window_days`, `gamma`, `suspicious_status` | medium |
| R16 | Listelenmiş ülke | alert | ln(volume with listed countries ÷ reference amount) | `countries`, `limits`, `window_days` | high |
| S1 | Yuvarlak tutar | signal only | Share of large outgoing transfers that are round amounts | `limits`, `round_unit`, `min_count`, `window_days` | high |
| S2 | Merkez hesap | signal only | Robust z-score of distinct counterparties against customers of the same type | `mad_floor`, `window_days`, `cash_accounts` | medium |
| R17 | Çoklu uyarı | severity raise | Open alerts from at least `min_rules` different rules raise each one by one severity step, once per alert | `min_rules`, `window_days`, `excluded_rules` (default R02, R17, R18), `open_statuses` | high |
| R18 | Birleşik risk skoru | alert | `A = min(1, (Σ (weight × score)^p)^(1/p))` over this run's scores | `p` (default 4), `alert_threshold` (default 0.5) | high |

R18 does not open an alert when an alerting rule already scored 0.5 or more
for the customer in the same run. Its stored score is then 0 and `A` remains
in the trace.

Every rule except R02, R15, R17 and R18 has `x_esik` and `x_kesin`. Count-based
rules (R01, R03, R11, R13, R14) require whole numbers; S1 requires shares
between 0 and 1.

Each rule file in `backend/detection/rules/` contains its exact steps,
parameter descriptions and review notes for analysts. The rules screen shows
the same text, plus example cases that would and would not trigger. New rules
start inactive and `UNSET`.

The original rules R1–R4 are still in the database, inactive and without an
implementation. Their old alerts still open but have no stored calculation.

## 10. Data model

```text
customer 1──* account 1──* transaction (as sender)
                      1──* transaction (as receiver)
customer 1──* alert *──* transaction                (alert_transaction)
monitoring_rule 1──* alert
alert 1──* alert_status_history
detection_run 1──* rule_result *──* transaction     (rule_result_transaction)
upload_batch 1──* upload_row_error
app_user *──1 app_role *──* permission              (role_permission)
```

| Table | Holds |
| --- | --- |
| `customer` | Customer number, name, type (`BIREYSEL`/`KURUMSAL`), occupation, monthly income, risk level. |
| `account` | Account number, owner, currency, type, opening date, `created_at`. |
| `transaction` | Sender and receiver accounts, positive amount, currency, time, channel (`atm`, `mobile`, `internet`, `branch`), two-letter country code. |
| `monitoring_rule` | Code, name, active flag, weight, `thresholds` (JSONB, two parameter sets). |
| `detection_run` | One row per run: evaluation time (`as_of`), status, start, end, duration. |
| `rule_result`, `rule_result_transaction` | Per run, rule and customer: parameter snapshot, status, `x`, score, trace; and its evidence. |
| `alert`, `alert_transaction` | Alert status, severity, score, deduplication key; its evidence. |
| `alert_status_history` | Every status change: who, when, from, to, note, decision ID. |
| `rule_change_log` | Old and new thresholds for each rule edit, with who and when. The reason is in the matching audit row. |
| `audit_log` | Every significant action, with JSONB details. |
| `upload_batch`, `upload_row_error` | Upload summaries and rejected rows. |
| `app_user`, `app_role`, `permission`, `role_permission` | Users and role-based access. |

Customer, account and transaction numbers are unique. Check constraints cover
amounts, channels and code formats.

`audit_log`, `alert_status_history` and `rule_change_log` are append-only:
database triggers reject `UPDATE` and `DELETE`. These records must be kept for
at least five years, and nothing in the application deletes or archives them.

Migration `0008` adds indexes for the hot lookups: status history by alert and
by actor, alert evidence by transaction, audit rows by entity, open alerts by
rule and customer, and rule results by rule and customer.

## 11. API reference

The interactive reference at `http://127.0.0.1:8000/docs` is generated from
the code and is always current. This table is an overview.

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| **Session** | | |
| `POST /auth/login` | none | Get a token (form fields). |
| `GET /auth/me` | signed in | Username, role, permissions. |
| `GET /health` | none | API and database status. |
| **Alerts** | | |
| `GET /alerts/queue` | `alert:view` | Queue grouped by customer, with summary counts. |
| `GET /alerts` | `alert:view` | Filtered list; `include_counts=true` adds counts per status. |
| `GET /alerts/rule-codes` | `alert:view` | Options for the rule filter. |
| `GET /alerts/{id}` | `alert:view` | Detail, evidence, history with actors, escalation, explanation. |
| `GET /alerts/{id}/customer-context` | `alert:view`, plus `alert:confirm` unless the alert is `new` | Masked customer context. Logs a view. |
| `PATCH /alerts/{id}/status` | depends on the transition | Decision on one alert. |
| `POST /alerts/decisions` | depends on the transition | Atomic decision on 1–50 alerts of one customer. |
| `GET /dashboard/my-summary` | `alert:view` | The signed-in user's own counts and returned cases. |
| **Dashboards** | | |
| `GET /dashboard/summary?days=` | `dashboard:view` | Totals, distributions, daily trend. |
| `GET /dashboard/funnel?days=` | `dashboard:view` | Where alerts went: created = closed + open + escalated, plus decision KPIs. |
| `GET /dashboard/rule-performance?days=` | `dashboard:view` | Per rule: evaluations, alerts, average score, hit rate. |
| **Customers and transactions** | | |
| `GET /customers` | `customer:view` | Customer list with search. |
| `GET /customers/{no}` | `customer:view` | Profile. Logs a view. |
| `GET /customers/{no}/analysis?days=30\|90\|180` | `customer:view` | Monthly in/out per currency, income check, counterparties. Logs a view. |
| `GET /accounts` | `customer:view` | Account search by text, customer or currency. Logs views. |
| `GET /transactions` | `customer:view` | Filtered transactions (account, direction, amount range), up to 500 per page. Logs views. |
| `GET /transactions/summary` | `customer:view` | Totals, timeline and the top 200 account-to-account routes, computed in SQL. Accepts `account_ref`. |
| **Rules** | | |
| `GET /rules` | `rule:view` | Rules with parameters, weight, definition text. |
| `GET /rules/{code}/history` | `rule:view` | Saved changes: who, when, why, old and new value per field. |
| `PUT /rules/{code}` | `rule:edit` | Save parameters, weight and active flag. Reason required. |
| `POST /rules/evaluate` | `rule:edit` | Run the active rules now. |
| **Uploads** | | |
| `POST /uploads?entity=customer\|account\|transaction` | `upload:create` | Upload a CSV. |
| `GET /uploads`, `GET /uploads/{id}` | `upload:view` | History and report; rejected row content only for the uploader. |
| **Administration** | | |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | `user:manage` | List, create, change role or active flag. |
| `GET /users/roles` | `user:manage` | Roles with their permissions. |
| `GET /admin/system-overview` | `user:manage` | Health, schema revision against head, rule engine status, data volumes, security settings. Numbers only. |
| `GET /audit-log` | `audit:view` | Filter by `action`, `exclude_action`, actor, record and dates. R17 raises from one run come back as one event, with the alerts in `grouped`. |
| **Demo** | | |
| `GET /demo/status` | `dashboard:view` | Demo fixture inventory and scenario results. |
| `POST /demo/seed` | `upload:create`, and `ENABLE_DEMO_ENDPOINTS=true` | Create or repair the demo data and evaluate it. 404 when disabled. |

## 12. CSV upload

Upload customers first, then accounts, then transactions, because each refers
to rows of the previous kind. **Veri yönetimi** offers a template for each.

| Entity | Required headers |
| --- | --- |
| `customer` | `customer_no`, `full_name`, `customer_type`, `occupation`, `monthly_income`, `risk_level` |
| `account` | `account_no`, `customer_no`, `currency`, `account_type`, `opened_at` |
| `transaction` | `transaction_no`, `sender_account_no`, `receiver_account_no`, `amount`, `currency`, `tx_time`, `channel`, `country_code` |

1. The file must be `.csv`, UTF-8 (a BOM is accepted), at most 5 MB and 5,000
   rows, with all required headers.
2. Each row is checked on its own. Rejected rows are reported with the row
   number (the header is row 1, so data starts at row 2) and the reason.
3. Accepted rows, rejected rows, the batch summary and an audit row are saved
   in one transaction.
4. A transaction upload with at least one accepted row runs the rules.

| Entity | Checks |
| --- | --- |
| Customer | Number and name required; text lengths; income not negative, at most two decimals. |
| Account | Customer exists; three-letter currency. |
| Transaction | Both accounts exist; amount positive with at most two decimals; channel from the allowed list; two-letter country; currency matches the accounts; ISO timestamp. |
| All | No missing or duplicate keys, within the file or against the database. |

Uploads are processed synchronously. There is no malware scan.

## 13. Demo lab and example data

`backend/demo.py` builds a repeatable synthetic fixture under `DEMO-*`
numbers: 32 customers, 32 TRY accounts and 93 transactions, with one scenario
per rule (20). Each scenario names its target customer and the activity meant
to trigger the rule.

- By default every rule is evaluated with demo-only `PROVISIONAL` parameters.
  Saved rule settings and active flags are not touched.
- In saved-settings mode the rules run as configured; inactive rules show as
  not evaluated.
- Only demo customers and transactions between them are evaluated, so other
  data is never affected. Seeding is repeatable: it repairs the fixture, moves
  timestamps relative to now, and never deletes anything.
- A scenario passes when its score is 0.50 or more. S1 and S2 pass on score
  alone. R18 targets the S1 customer, showing a signal turning into an alert.
  R17 has no score; it passes when its trace shows it raised a severity.
- `DEMO-022` stands in for a confirmed-suspicious customer for R15. No alert
  history is created for it.

A passing scenario shows that a rule can fire, not that its thresholds are
right. Most demo customers already get an alert from one rule, so R18 opens
its own alert only for the S1 customer.

For a larger, less artificial dataset, use `seed_example_data` and
`check_rule_coverage` (section 4).

## 14. User interfaces

### React (`frontend-v2/`)

| Screen | Path | Needs |
| --- | --- | --- |
| Panelim (analyst's own day) | `/my-panel` | `alert:escalate` |
| Tespit özeti (tabs: Özet, Alarm akışı, Kurallar) | `/overview` | `dashboard:view` |
| Alarm inceleme (queue) and alert detail | `/alerts`, `/alerts/:id` | `alert:view` |
| Tüm alarmlar | `/all-alerts` | `alert:confirm` |
| İşlem analizi | `/transactions` | `customer:view` |
| Müşteriler and customer profile | `/customers`, `/customers/:no` | `customer:view` |
| Veri yönetimi | `/data` | `upload:create` or `upload:view` |
| Demo laboratuvarı | `/demo` | `dashboard:view` |
| Kural yönetimi | `/rules` | `rule:view`; editing needs `rule:edit` |
| Sistem özeti | `/system` | `user:manage` |
| Kullanıcı yönetimi | `/users` | `user:manage` |
| Denetim kaydı | `/audit` | `audit:view` |

Users land on the first screen in this list they can open.

Notes on individual screens:

- **İşlem analizi**: the customer or account is chosen with a server-side
  search. It shows per-counterparty in/out bars with alert share and rule
  codes, an in/out timeline, a network graph centred on the customer
  (clicking a counterparty loads the next ring through `account_ref`), and the
  transaction list, 50 at a time, newest first. Without a selection only
  per-currency totals are shown.
- **Customer profile**: an analysis panel for 30, 90 or 180 days with monthly
  in/out per currency, counterparties marked new (no transaction with them in
  the 365 days before the period), and an income check. The check warns when
  the peak calendar month's TRY inflow or outflow reaches three times the
  monthly income (`INCOME_WARNING_MULTIPLE` in
  `backend/services/customer_service.py`).
- **Tespit özeti**: only the open tab loads its data. A rule is marked
  "Gözden geçir" when its hit rate is below 10% over 30 days with at least five
  decided alerts.
- **Kural yönetimi**: each rule's description, a plain-language sentence,
  example cases, parameters per customer type, change history and hit rate.
  Read-only users see no form.
- **Kullanıcı yönetimi**: role cards list each role's permissions.

Code layout:

- `src/features/<area>/`: one folder per screen with the page, its `api.ts`
  (TanStack Query hooks) and its tests.
- `src/api/client.ts` and `src/api/schemas/`: the HTTP client and a zod schema
  per response. Update the schema in the same change as the API response.
- `src/app/navigation.ts`: menu entries and the permissions each needs; route
  guards use the same list.
- `src/i18n/locales/tr.ts` and `en.ts`: all text. Turkish is the default and
  the source of truth; TypeScript enforces that `en.ts` has the same shape.
- `src/test/`: MSW handlers and shared test data.

Conventions: money stays a string and is summed in integer cents; dashboard
data is cached for 60 seconds and refreshed after a decision; language and
theme (light by default, dark available) are saved per browser in
`localStorage`. More detail is in `frontend-v2/README.md`.

### Streamlit (`frontend/`)

The original interface. It was not updated for the current API: some pages
call endpoints that no longer exist, and it knows nothing about the compliance
workflow. It is kept for reference only.

## 15. Database migrations

Alembic records the applied revision in `alembic_version`. Never edit a
migration that has been applied anywhere; add a new one. Mirror each migration
as a SQL file in `database/`. Migrations are additive, so the old backend keeps
working while a new one is deployed (section 18).

| Revision | SQL mirror | Change |
| --- | --- | --- |
| `0001_existing_schema_baseline` | `V1` | Creates the original schema on an empty database, or adopts a complete existing one. Stops if only some tables exist. |
| `0002_rbac` | `V2` | Roles, permissions, `role_permission`; seeds admin and analyst roles. |
| `0003_rule_framework` | `V3` | `detection_run`, `rule_result`, weights, scores; seeds R01–R03; deactivates R1–R4. |
| `0004_extended_detection_rules` | none | Seeds R04–R15 (inactive, `UNSET`). |
| `0005_system_overview_metrics` | `V4` | `account.created_at` and `detection_run.duration_ms`. |
| `0006_alert_workflow` | `V5` | Compliance role, `alert:escalate`, `alert:confirm`, K13 admin restriction; seeds R16, R17, R18, S1, S2. |
| `0007_admin_all_permissions` | `V6` | Development only: the administrator gets every permission again. |
| `0008_query_indexes` | `V7` | Indexes for hot queries (section 10). |

```powershell
.\.venv\Scripts\alembic.exe upgrade head   # apply all
.\.venv\Scripts\alembic.exe current        # applied revision
.\.venv\Scripts\alembic.exe heads          # revision the code expects
```

The system overview screen compares the applied revision with the head and
warns when they differ.

If a migration fails with "already exists", the database was probably changed
by hand. Compare the real schema with the migration before stamping a
revision.

## 16. Configuration

The API reads `.env` from the repository root, then the process environment.
Never commit `.env`.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic, scripts, integration tests | PostgreSQL URL, e.g. `postgresql+psycopg2://USER:PASSWORD@localhost:5432/izleme_alarm`. `postgresql://` and `postgresql+psycopg://` are rewritten to psycopg2. Required. |
| `JWT_SECRET` | API | Signs tokens and `account_ref` values. Long and random. Required; the API will not start without it. |
| `PROXY_SHARED_SECRET` | API and nginx | Proves that `X-Client-Address` came from nginx (section 8). Same value on both. Only needed behind nginx. |
| `ENABLE_DEMO_ENDPOINTS` | API | `true` enables `POST /demo/seed`. Default `false`. |
| `DETECTION_SCHEDULE_TIME` | API | `HH:MM` on the process's clock for the daily rule run (section 9). Empty means off. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `create_admin` | Optional; otherwise the script asks. |
| `VITE_API_PROXY_TARGET` | Vite dev server (`frontend-v2/.env`) | Target of `/api`. Default `http://127.0.0.1:8000`. |
| `API_UPSTREAM` | React image (nginx) | Target of `/api`, no trailing slash. Default `http://backend:8000`. For an `https` upstream the certificate is verified. |
| `PORT` | All images | Listen port. Defaults: API 8000, React 8080, Streamlit 8501. |
| `API_BASE_URL` | Streamlit | API address for the legacy interface. |

### Docker

There is no compose file; build and run the images separately. Image names
below are examples.

```powershell
docker build -f Dockerfile.backend -t izlemealarm-api .
docker run -p 8000:8000 --env-file .env izlemealarm-api

docker build -f Dockerfile.frontend-v2 -t izlemealarm-ui .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 izlemealarm-ui
```

Inside a container `localhost` is the container itself; use
`host.docker.internal` to reach the host.

The backend image (Python 3.12 slim) runs Uvicorn with one worker and does not
run migrations. The React image builds with Node 22 and serves the build from
nginx 1.27. nginx falls back to `index.html` for app routes, caches hashed
assets for a year, never caches `index.html`, allows 6 MB request bodies on
`/api/`, re-resolves the upstream name every 30 seconds, and sets
`X-Content-Type-Options`, `X-Frame-Options: DENY` and
`Referrer-Policy: same-origin`.

## 17. Testing

```powershell
# Backend, from the repository root
.\.venv\Scripts\python.exe -m pytest tests -q

# React, from frontend-v2
npm test
npm run typecheck
npm run lint
npm run build
```

- **Backend unit tests** (`tests/*.py`) need no database. They cover rule
  strategies and scoring, threshold changes, parameter validation, route
  permissions, rate limits, audit redaction, error translations, the system
  overview, the daily scheduler and the demo fixture.
- **Integration tests** (`tests/integration/`) need a PostgreSQL at the
  Alembic head. They run only when `DATABASE_URL` points at `localhost`,
  `127.0.0.1` or `::1`; any other host, such as the production database, makes
  them skip. Each test runs inside one outer transaction that is rolled back,
  so nothing persists and existing rows are left alone. They cover the
  workflow, four eyes, the queue and detail, customer access and masking,
  dashboards and administration, and the newer rules end to end.
- **React tests** use Vitest, Testing Library and MSW. The MSW handlers apply
  the same filters and paging as the real endpoints, and an unhandled request
  fails the test. `src/app/a11y.test.tsx` runs axe-core (WCAG 2.1 A/AA) on
  every screen.

CI runs all of the above on every push (section 18), with integration tests
against a throwaway PostgreSQL 16 container.

## 18. CI and deployment

### Workflows

| Workflow | Trigger | Does |
| --- | --- | --- |
| `tests.yml` (Tests) | Called by the others | Backend: PostgreSQL 16 service, `alembic upgrade head`, `pytest`. Frontend: `npm ci`, `tsc -b`, lint, `vitest run`. |
| `ci.yml` (CI) | Every push and pull request | Runs Tests. On `main`, only when the repository variable `AUTO_DEPLOY` is `true`, detects whether the push changed the backend or the frontend and calls the matching deploy. |
| `deploy.yml` (Deploy backend) | Manual (Actions → Run workflow), or from CI | Production deployment of the API. |
| `deploy-frontend.yml` (Deploy frontend) | Manual, or from CI | Production deployment of the React interface. |

`AUTO_DEPLOY` is `false`, so pushing never deploys; deployments are started by
hand. To change it: `gh variable set AUTO_DEPLOY --body true` (or `false`).
When it is `true` and a push changes both parts, the frontend deploys only
after the backend deploy succeeded. Backend paths are `backend/`, `alembic/`,
`alembic.ini`, `database/` and `Dockerfile.backend`; frontend paths are
`frontend-v2/` and `Dockerfile.frontend-v2*`.

A manual deploy runs the tests first. Deploys only run from `main`, never
overlap, and are never cancelled halfway.

### What a backend deploy does

1. Build the image from `Dockerfile.backend` and push it to ECR
   (`izlemealarm-backend`), tagged with the commit SHA.
2. Read `DATABASE_URL` from SSM and run `alembic upgrade head` against the
   production database (Neon PostgreSQL). The schema is migrated before new
   tasks start; old tasks keep working because migrations are additive.
3. Update the ECS Express service `izlemealarm-backend`: Fargate, 0.25 vCPU,
   512 MB, port 8000, exactly one task.
4. Smoke test: `GET <service URL>/health`.

### What a frontend deploy does

1. Build `Dockerfile.frontend-v2`, push to ECR (`izlemealarm-frontend`).
2. Update the ECS Express service `izlemealarm-frontend`: port 8080, health
   check `/`, one task, `API_UPSTREAM` set to the backend's URL.
3. Smoke test: `GET /` and `GET /api/health`. The second goes through nginx to
   the backend, so it also tests the proxy.

### AWS setup

- Region `eu-north-1`, ECS cluster `default`, two ECS Express Mode services.
  Every service setting is passed explicitly in the workflow, because the
  deploy action does not document whether omitted settings keep their value.
- Secrets are SSM SecureString parameters under `/izlemealarm-backend/`:
  `DATABASE_URL`, `JWT_SECRET`, `PROXY_SHARED_SECRET`. The task execution role
  reads them (`.aws/ecs-execution-ssm-policy.json`); both services read
  `PROXY_SHARED_SECRET`.
- The AWS organisation blocks GitHub OIDC providers, so GitHub uses a
  dedicated IAM user with the least-privilege policy in
  `.aws/github-deploy-policy.json`. Its access keys are secrets of the GitHub
  environment `production`, available only to the deploy jobs.
- Non-secret settings are variables of the `production` environment:
  `SERVICE_URL`, `HEALTH_CHECK_PATH`, `ECS_SUBNETS`, `ECS_SECURITY_GROUPS`,
  `FRONTEND_SECURITY_GROUPS`, `ECS_EXECUTION_ROLE_ARN`,
  `ECS_INFRASTRUCTURE_ROLE_ARN`, `ENABLE_DEMO_ENDPOINTS`,
  `DETECTION_SCHEDULE_TIME`. The last one is not set yet, so production has
  no daily run. To turn it on:
  `gh variable set DETECTION_SCHEDULE_TIME --env production --body 23:00`,
  then run Deploy backend.
- Security groups are per service and per port. Never reuse the backend's
  group for the frontend.
- Creating a new Express service needs more rights than updating one (for
  example `ecs:CreateCluster`, even if the cluster exists). The deploy user
  only has update rights.
- Keep `max-task-count` at 1 until rate-limit counters move to shared storage
  (section 8).

For a failed deploy, start with `gh run view <run-id> --log-failed`.

## 19. Making changes

**Add a rule**

1. Create `backend/detection/rules/<code>_<name>.py` with a `RuleStrategy`
   subclass: a `RuleDefinition` (code, name, description, steps, parameters,
   alert mode, stage, feasibility) and `evaluate_raw`. The registry finds it
   automatically.
2. Add its parameter model to `backend/detection/parameters.py`.
3. Add a migration that inserts its `monitoring_rule` row (inactive, `UNSET`)
   and the mirror SQL file. The engine refuses to run if a registered rule has
   no row.
4. Add its fields to `frontend-v2/src/features/rules/model.ts` and its summary
   sentence and explanation text to both locale files.
5. Add demo parameters and a scenario in `backend/demo.py`. A test fails if a
   registered rule has no scenario.

**Change a rule's thresholds.** Use the rules screen or `PUT /rules/{code}`,
never SQL: the API validates the values, requires a reason and writes the
change log. Making a parameter optional must keep previously saved parameter
sets valid.

**Add an endpoint.** Put the route in `backend/api/routes/` with
`require_permission(...)` and a `response_model`, the logic in a service and the
SQL in a repository. Add a case to `tests/test_rbac.py` (nothing checks this
automatically), a translation for any new error message, a zod schema and a
query hook in React. If the response contains personal data, mask it and log
the view.

**Add a permission.** Insert it in a migration, grant it to the right roles and
to the administrator (section 5), mirror it in `database/`, and add it to
`frontend-v2/src/auth/permissions.ts`.

**Change an error message.** Change the backend text and `tr.ts`/`en.ts` in the
same commit; `tests/test_error_translations.py` enforces this.

**Change the schema.** New Alembic migration plus `database/V<n>__*.sql`.
Keep it additive so the running backend survives the migration step of a
deploy.

## 20. Known limits

- **Administrator permissions.** K13 is suspended by migration `0007` for
  development (section 5). Restore it before any real use.
- **Scheduling.** The daily run lives inside the API process, so it needs the
  API to be up at that time and assumes a single task. It is off in
  production until `DETECTION_SCHEDULE_TIME` is set.
- **Provisional thresholds.** Rule parameters are examples, not calibrated
  policy. The "Gözden geçir" mark (hit rate below 10% over 30 days with at
  least five decided alerts) is a proposal.
- **Currencies.** No exchange-rate conversion. Rules work per currency; where
  income matters it is assumed to be TRY.
- **Graph rules.** R13 and R14 search the whole transaction graph and may be
  slow on dense data. They have been measured only on the demo data.
- **Growth.** `rule_result` gains one row per rule and customer per run. Real
  volumes would need a retention policy and more indexes.
- **Scaling.** Rate limits are in memory, so the API must run as one task.
- **Identity.** No MFA, SSO or password reset. `/docs` is public and should be
  closed or internal outside development.
- **Uploads.** Synchronous, 5,000 rows at most, no malware scan, no streaming.
- **Operations.** Backups, monitoring, alerting and secret rotation are not set
  up beyond what Neon and AWS provide by default.
- **Left out on purpose.** Rule simulation ("etkisini gör", part of K5) and
  exporting customer or alert data from the screens.
- **Legacy.** The Streamlit interface does not work with the current API.

## 21. Design decisions K1–K13

The code cites decisions from the API design document (v0.6) by number. This
is what each refers to and where it is implemented.

| ID | Decision | Where |
| --- | --- | --- |
| K1 | The alert queue is grouped, sorted, searched and paged on the server. | `GET /alerts/queue` |
| K2 | A decision on several alerts of one customer is atomic. | `POST /alerts/decisions`, `alert_repository.py` |
| K3 | The overview has three tabs, and only the open tab loads its data. | `features/detection-overview/` |
| K4 | The alert's customer context is masked on the server. | `masking.py`, customer-context endpoint |
| K5 | Every rule change needs a reason that is written to the audit log. Simulation was not built. | `PUT /rules/{code}` |
| K6 | Every view of customer personal data is logged. | `customer_view_log.py` |
| K7 | The API returns English error text; the interface translates it. | `tr.ts`, `test_error_translations.py` |
| K8 | Each alert explains why it fired from the stored rule result. | `GET /alerts/{id}`, `ExplanationPanel.tsx` |
| K9 | No duplicate open alerts: rescoring, deduplication keys, advisory lock. | `detection_repository.py` |
| K10 | Responses are declared models; history entries carry the actor. | `backend/api/responses.py` |
| K11 | Individual settings can be copied to corporate ones. | Rules screen |
| K12 | Transaction totals and routes are computed on the server over every match; route labels are masked and counterparty names are not sent. | `GET /transactions/summary` |
| K13 | The administrator does not see alert or customer content; rejected upload rows go only to the uploader; audit notes are redacted for readers without access. | Migration `0006` (suspended by `0007`), audit and upload services |

## 22. Glossary

| Term | Meaning |
| --- | --- |
| Alert (alarm) | A rule's finding about one customer, to be reviewed by people. |
| Score | A rule's result between 0 and 1; 0.5 or more opens an alert. |
| `x`, `x_esik`, `x_kesin` | The rule's raw measurement; the value that scores 0.5; the value that scores 0.9. |
| Signal-only rule | A rule that never alerts by itself and only feeds R18 (S1, S2). |
| Escalation (yükseltme) | The analyst passing an alert to compliance (`new` → `in_review`). |
| Four eyes (dört göz) | The person who escalated an alert cannot make the final decision on it. |
| Detection run | One execution of the rules (`detection_run`), with one `rule_result` per rule and customer. |
| Step trace | The stored calculation behind a result; it is what "Neden tetiklendi?" shows. |
| Hit rate (isabet) | Confirmed ÷ (confirmed + closed) for a rule's decided alerts. |
| Masking | Hiding part of personal data on the server (`Ö. Kılıç`, `…7781`). |
| Append-only | Rows can be added but not changed or deleted; enforced by triggers. |
| `UNSET`, `PROVISIONAL`, `APPROVED` | A parameter set that is not configured (skipped), temporary, or approved by the institution. |
| Bireysel, Kurumsal | Individual and corporate customers. |
| MASAK, BDDK, KVKK | Turkey's financial crimes investigation board, banking regulator, and personal data protection law. |
