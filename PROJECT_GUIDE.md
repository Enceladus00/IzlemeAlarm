# Project Guide: Understand the Transaction Monitoring MVP

This guide is meant to help you explain how the project works—not just how to
start it. It follows a request from the screen, through the API and business
logic, down to PostgreSQL, and back. It also explains the important trade-offs
and what the current version does **not** do.

> **Scope:** This is a learning/demo MVP. It uses bearer-token login and RBAC,
> but still uses synthetic data and simple deterministic rules; it is not a
> production fraud-decision system and does not use machine learning.

## Table of contents

1. [The project in one minute](#1-the-project-in-one-minute)
2. [Repository map](#2-repository-map)
3. [How to run it](#3-how-to-run-it)
4. [How one request travels through the system](#4-how-one-request-travels-through-the-system)
5. [Database and entity model](#5-database-and-entity-model)
6. [The API, route by route](#6-the-api-route-by-route)
7. [Rule engine: exact behavior and math](#7-rule-engine-exact-behavior-and-math)
8. [The demo dataset](#8-the-demo-dataset)
9. [CSV upload and row-level errors](#9-csv-upload-and-row-level-errors)
10. [The Streamlit screens](#10-the-streamlit-screens)
11. [Migrations and database setup](#11-migrations-and-database-setup)
12. [Configuration and dependencies](#12-configuration-and-dependencies)
13. [Tests and how to verify changes](#13-tests-and-how-to-verify-changes)
14. [Limits and deliberate omissions](#14-limits-and-deliberate-omissions)
15. [Questions you should be able to answer](#15-questions-you-should-be-able-to-answer)
16. [Glossary](#16-glossary)
17. [Role-based access control](#17-role-based-access-control)

## 1. The project in one minute

This application accepts customer, account, and transaction records; evaluates
transactions against four understandable rules; stores any resulting alerts;
and gives a user screens to review alerts, upload CSVs, edit rule parameters,
and see aggregate counts.

It has three runtime pieces:

1. **Streamlit frontend** — draws the screens and sends HTTP requests.
2. **FastAPI backend** — validates requests, runs queries and rule logic, and
   writes changes.
3. **PostgreSQL database** — stores the records, rules, alerts, upload reports,
   and histories.

SQLAlchemy maps Python classes to the existing PostgreSQL tables. Alembic
tracks which database schema revision has been applied. These tools do not
replace PostgreSQL: PostgreSQL remains the system of record.

The normal flow is:

```text
User action in Streamlit
    -> HTTP request to FastAPI
        -> SQLAlchemy session
            -> PostgreSQL query/transaction
        <- result or explicit error
    <- JSON response
<- updated Streamlit screen
```

## 2. Repository map

| Path | Responsibility |
| --- | --- |
| `frontend/app.py` | Streamlit login, permission-based navigation, and optional demo-data action. |
| `frontend/app_pages/` | Detection overview, alert investigation, transaction analysis, data management, rule management, user management, and audit-log pages. |
| `frontend/components/` | Shared page headers, metric layouts, and transaction tables. |
| `frontend/utils/api.py` | Shared HTTP client and user-facing API errors. |
| `backend/main.py` | FastAPI application factory and router composition. |
| `backend/api/routes/` | Thin HTTP adapters grouped by authentication, analysis, alerts, audit, rules, transactions, uploads, and users. |
| `backend/api/dependencies.py` | Constructs application services from the request-scoped database session. |
| `backend/api_schemas.py` | Pydantic request/response data shapes for a few API payloads. |
| `backend/database.py` | Lazily creates the SQLAlchemy engine/session factory and provides a session to each request. |
| `backend/db_url.py` | Normalizes PostgreSQL connection URLs to the installed `psycopg2` driver. |
| `backend/models.py` | SQLAlchemy entity definitions, including users, roles, and permissions. |
| `backend/services/` | Application workflows for authentication, audit, analysis, alerts, demo seeding, detection, rules, transactions, uploads, and users. |
| `backend/repositories/` | SQLAlchemy data-access implementations injected into services, including identity and audit repositories. |
| `backend/detection/` | Detection engine contracts and independent R1–R4 strategy implementations. |
| `backend/rules.py` | Backward-compatible exports for the detection service and deduplication helper. |
| `backend/demo.py` | Creates a small, repeatable set of synthetic data and rule defaults. |
| `database/V1__initial_schema.sql` | Original PostgreSQL schema, constraints, indexes, triggers, and initial rule rows. |
| `alembic.ini`, `alembic/` | Alembic configuration, original baseline, and RBAC migration. |
| `tests/test_application.py`, `tests/test_rbac.py` | Model, rule, and authorization regression tests. |
| `.vscode/launch.json` | VS Code launch buttons for the API, UI, or both together. |
| `.env.example` | Template for local configuration. Copy this to `.env` and set your own database URL. |
| `backend/requirements.txt` | Backend dependencies, including FastAPI, SQLAlchemy, Alembic, bcrypt, PyJWT, and test tools. |
| `frontend/requirements.txt` | Streamlit and its UI/data dependencies. |

FastAPI dependencies wire request-scoped repositories into services. Routers
translate HTTP inputs and domain errors; services coordinate workflows;
repositories own SQLAlchemy queries and persistence. Detection strategies
implement independent algorithms and the detection service runs configured
strategies through the shared engine. Keep UI rendering out of backend models
and database queries out of HTTP adapters.

## 3. How to run it

### Prerequisites

- Python 3.10 or newer.
- A running PostgreSQL server and a database that the configured account can
  access.
- Python dependencies installed from both requirements files.
- A local `.env` file containing a valid `DATABASE_URL`.

### First-time setup

The exact install and run commands are in [README.md](./README.md). In order:

1. Create/select the project's `.venv`.
2. Install backend and frontend dependencies.
3. Configure `.env`.
4. Apply the Alembic baseline with `alembic upgrade head`.
5. In VS Code, select `.venv` as the interpreter.
6. Choose **Start project (API + UI)** under **Run and Debug**, then press
   **F5**.
7. Open `http://127.0.0.1:8000/docs` to inspect/call the API. Streamlit opens
   the interface in a browser, usually at `http://localhost:8501`.
8. Click **Load demo data** in the UI sidebar to
   insert demo rows and evaluate the rules.

The API and UI are separate processes. If the UI opens but shows an API
connection error, check that the API launch configuration is running and that
`API_BASE_URL` points to it. If the API reports a database problem, inspect
`DATABASE_URL`, PostgreSQL availability, and the migration revision.

### VS Code launch configurations

The launch compound starts two children:

- **API (FastAPI):** runs Uvicorn with `backend.main:app` on `127.0.0.1:8000`.
- **UI (Streamlit):** runs `streamlit run frontend/app.py`.
- **Start project (API + UI):** starts both; `stopAll` asks VS Code to stop the
  pair together.

`backend.main:app` means “import the `app` object from `backend/main.py`.”
Uvicorn is the HTTP server; pressing **Run Python File** on `main.py` is not
equivalent to starting Uvicorn.

## 4. How one request travels through the system

Consider clicking **Kuralları şimdi çalıştır** on the summary screen:

1. Streamlit calls `api_request("POST", "/rules/evaluate")`.
2. `api_request` builds an HTTP URL from `API_BASE_URL`, sends a `requests`
   call, and applies a timeout.
3. FastAPI matches `POST /rules/evaluate` to `run_rules` in `backend/main.py`.
4. `Depends(get_db)` asks `backend/database.py` for a SQLAlchemy `Session`.
5. The route calls `evaluate_rules(db)` in `backend/rules.py`.
6. The rule service reads active rules and active transactions, creates alert
   rows and alert/transaction links, then commits.
7. The API returns JSON such as `{"created_alerts": 2}`.
8. Streamlit displays the result and reruns the script to refresh the screen.

If the request cannot reach the API, the frontend turns the `requests` failure
into an `ApiError` and displays it. For non-2xx responses it extracts FastAPI's
`detail` field where possible. Database errors are not converted into fake
successful responses.

### What a SQLAlchemy session does

A `Session` is a unit of database work. Routes receive it from `get_db`; when
the route finishes, the dependency closes it. A route that changes data
explicitly calls `commit()`. If a database operation fails, routes that own
that write roll back before reporting an error.

`create_engine(..., pool_pre_ping=True)` creates the connection pool. The
pre-ping checks a pooled connection before reusing it, helping detect
connections PostgreSQL has already closed. The session factory is lazy: the
connection engine is not created until the first request needs a database.

## 5. Database and entity model

The SQL file describes the PostgreSQL schema; `backend/models.py` describes
that same schema to Python/SQLAlchemy. Model classes do not automatically
create or migrate tables. Alembic handles schema setup separately.

### Main business entities

```text
Customer 1 --- many Account
Account  1 --- many Transaction as sender
Account  1 --- many Transaction as receiver
Customer 1 --- many Alert
Alert    many --- many Transaction (through alert_transaction)
```

- **Customer:** a person or organization being monitored.
- **Account:** belongs to one customer and has a currency.
- **Transaction:** moves a positive amount from one account to another at a
  recorded time. The account foreign keys give the application both sides of
  the transfer.
- **MonitoringRule:** a rule code, name, description, on/off flag, and JSONB
  thresholds.
- **Alert:** one rule's finding for one customer. Its status and severity are
  stored on this row.
- **AlertTransaction:** link table identifying which transactions support an
  alert. Its composite primary key prevents the same transaction from being
  linked twice to the same alert.

### Operational and history entities

- **AppUser:** stores a password hash, active flag, and required role foreign
  key. Request-side audit attribution comes from the authenticated user.
- **AppRole / Permission:** active roles link to permissions through
  `role_permission`.
- **UploadBatch:** one CSV upload, with entity type, file name, row counts, and
  uploader reference.
- **UploadRowError:** rejected CSV row number, reason, and submitted row data.
- **AlertStatusHistory:** append-only record of alert status transitions.
- **RuleChangeLog:** append-only old/new threshold snapshots for a rule edit.
- **AuditLog:** append-only record of significant application actions.

### Constraints and indexes

Database constraints are the last integrity boundary even if API validation is
missed:

- Customer/account/transaction numbers are unique.
- Transactions reference existing sender/receiver accounts and have positive
  amounts.
- Transaction channel and country-code formats are constrained.
- Alert status/severity values are constrained; users reference an active role
  at authentication time.
- Closing or confirming an alert requires a nonblank note.
- Alert deduplication keys are unique.
- SQL triggers reject UPDATE/DELETE on the three append-only history tables.

Indexes help common lookups such as transactions by account/time, alerts by
status/time, alerts by customer, and upload errors by batch.

## 6. The API, route by route

The route implementations are in `backend/main.py`; the interactive reference
is available at `/docs` while the API is running.

| Method and route | Purpose | Access | Important behavior |
| --- | --- | --- | --- |
| `POST /auth/login` | Exchange username/password form for a token. | Public | Returns a 30-minute bearer token; failures use a generic response. |
| `GET /auth/me` | Return current username, role, and sorted permissions. | Authenticated | Reloads role and permissions from the database. |
| `GET /health` | Check database connectivity. | Public | Runs `SELECT 1`; returns 503 when the database cannot be reached. |
| `GET /dashboard/summary` | Return record totals, severity/rule distributions, and recent detection trends. | `dashboard:view` | Uses SQL `COUNT` and `GROUP BY`. |
| `GET /alerts` | List/filter alerts. | `alert:view` | Supports status, severity, rule code, date range, offset, and bounded page size. |
| `GET /alerts/rule-codes` | Return alert rule-filter choices. | `alert:view` | Does not expose rule thresholds. |
| `GET /alerts/{alert_id}` | Show one alert, linked customer, transactions, and status history. | `alert:view` | Returns only transactions linked through `alert_transaction`. |
| `GET /alerts/{alert_id}/customer-transactions` | Load investigation history for the alert's customer. | `alert:view` | Derives customer scope from the alert ID; accepts no customer ID. |
| `PATCH /alerts/{alert_id}/status` | Change status or record analyst reasoning. | `alert:update` | The authenticated user's ID is written to history and audit records. |
| `GET /transactions` | Filter and inspect account-to-account transfers. | `customer:view` | Supports date, customer, direction, and amount filters. |
| `GET /customers/{customer_no}/transactions` | Show a customer's transaction history. | `customer:view` | Generic customer history; analysts use the alert-scoped route instead. |
| `GET /rules` | Read rule descriptions, active flags, and thresholds. | `rule:view` | Rules are returned ordered by code. |
| `PUT /rules/{rule_code}` | Save a rule's active flag and thresholds. | `rule:edit` | Rejects invalid values with 422 and attributes the actor from the token. |
| `POST /rules/evaluate` | Evaluate active rules against stored transactions. | `rule:edit` | Manual evaluation; automatic upload evaluation needs no extra permission. |
| `POST /demo/seed` | Seed demo data and evaluate it. | `upload:create` + `ENABLE_DEMO_ENDPOINTS=true` | Disabled by default; repeat calls avoid duplicate demo records. |
| `POST /uploads?entity=...` | Upload customer/account/transaction CSV. | `upload:create` | Validates CSV and attributes the batch to the authenticated user. |
| `GET /uploads/{batch_id}` | Retrieve one upload report. | `upload:view` | Includes stored row errors; returns 404 for an unknown batch. |
| `GET /users`, `GET /users/roles` | List users and assignable active roles. | `user:manage` | Never returns password hashes. |
| `POST /users`, `PATCH /users/{user_id}` | Create, deactivate, or change a user's role. | `user:manage` | User records are deactivated, never deleted. |
| `GET /audit-log` | View audit events. | `audit:view` | Returns a bounded, newest-first page. |

### Why the frontend calls the API

The Streamlit UI is a client of the API, rather than a direct database client.
That keeps SQL and business logic in one place. The API requires bearer-token
authentication and enforces permissions independently of the UI.

### Alert status transition behavior

The schema accepts `new`, `in_review`, `closed`, and
`confirmed_suspicious`. The API currently permits moving between any of these
valid values; it does not enforce a more restrictive workflow graph. A note is
mandatory only for `closed` and `confirmed_suspicious`. Sending the current
status again returns `changed: false` and creates no history row.

## 7. Rule engine: exact behavior and math

The thresholds are read from each active rule's `thresholds` JSONB field.
Python's `Decimal` is used for amount comparisons so currency math is not based
on binary floating-point arithmetic. The implementation is intentionally
simple and is not a tuned large-scale detection engine.

All rules consider active transactions ordered by `tx_time` and transaction ID.
They attach findings to the sender's customer, except that R2's grouping is
account-based and the alert is attached to that account's owner.

### R1 — Repeated near-limit transactions

Default parameters:

```text
amount_limit       = 10,000
proximity_percent  = 10
transaction_count  = 2
window_minutes     = 60
```

The inclusive lower bound is:

```text
lower_bound = amount_limit * (1 - proximity_percent / 100)
            = 10,000 * (1 - 10 / 100)
            = 9,000
```

For each customer/currency pair, the code keeps **outgoing** transactions
whose amounts satisfy:

```text
9,000 <= amount < 10,000
```

Starting from each candidate transaction in time order, it collects the
candidate transactions no later than `window_minutes` after that start. If the
window contains at least `transaction_count` transactions, it creates one
finding linked to the matching transactions. After a finding, it advances
past that matched group before searching for the next group.

**Demo example:** customer 1 sends 9,500 at 09:20 and 9,600 at 09:45. Both are
in the range and 25 minutes apart, so they satisfy the default R1 rule.

**Boundary example:** 9,000 qualifies; 10,000 does not. The latter is exactly
the configured limit, not “below” it.

### R2 — Rapid in-and-out transfers

Default parameters:

```text
outflow_ratio = 0.8
window_minutes = 60
```

For each account, the code gathers active transactions that touch that account
and have the account's currency. For each transaction time as a possible
window start, it gathers transactions from that time through 60 minutes later,
inclusive. Then it computes:

```text
incoming = sum(amount where account is receiver)
outgoing = sum(amount where account is sender)
ratio    = outgoing / incoming
```

An alert is considered only when `incoming > 0` and `ratio >= 0.8`.

**Demo example:** account 7 receives 1,000 at 09:30 and sends 850 at 09:50.
The ratio is `850 / 1,000 = 0.85`, so it meets the 0.8 threshold.

The implementation uses the same rolling window for both directions; it does
not pair each incoming transfer to a particular outgoing transfer. Transfers
are treated as same-currency totals, not converted across currencies.

### R3 — Unusual transaction amount

Default parameters:

```text
average_multiplier   = 3
minimum_history_count = 5
```

For each customer/currency pair, the engine orders outgoing transactions by
time. For a current transaction it takes the most recent configured number of
**preceding** outgoing transactions; the current transaction is not part of
its own baseline. It requires enough history before comparing:

```text
historical_average = sum(previous N amounts) / N
trigger            = current_amount > historical_average * multiplier
```

The comparison is strictly `>`: equality does not trigger the rule.

**Demo example:** customer 2 has five earlier outgoing transactions of
100, 120, 90, 110, and 80. Their average is 100. A later transaction of 400 is
greater than `100 * 3`, so it triggers R3.

The baseline is the latest N transactions, not a lifetime average over every
previous transaction. The current implementation does not exclude a transfer
back to another account owned by the same customer; it treats any sender-side
transaction as outgoing.

### R4 — Configured country match

Default SQL parameters are disabled with an empty country list. The demo seed
enables R4 and configures `TR` and `IL` so the demo shows this screen/rule
working. When enabled, each active transaction whose country code matches the
configured list creates an R4 candidate.

This is a string match, not a real-world country risk assessment. `TR` and
`IL` are demo examples only. A production country list, ownership, updates,
and policy approval are not part of this project.

### How duplicate alerts are prevented

Each candidate produces a stable key:

1. Sort the linked transaction IDs.
2. Join them into a stable string; for R2 include the account ID as scope.
3. Hash that string with SHA-256.
4. Prefix the result with the rule code.

The database has a unique constraint on `alert.deduplication_key`. Inserts use
PostgreSQL `ON CONFLICT DO NOTHING`, so a second evaluation does not duplicate
the same finding. This also lets PostgreSQL enforce deduplication if two rule
evaluations happen concurrently.

### Severity and evaluation triggers

R1/R2 alerts are marked `medium`; R3/R4 alerts are marked `high`. These are
fixed code choices, not parameters or learned risk scores. Rules run when the
user presses the demo-seed or “run rules now” button, and after a transaction
CSV upload containing accepted rows. There is no scheduled background
evaluation.

## 8. The demo dataset

`backend/demo.py` uses stable external identifiers (`DEMO-001`,
`DEMO-ACC-001`, `DEMO-TX-001`, and so on) and checks for existing rows before
inserting them. This makes repeated clicks safe for the normal intact demo
dataset.

The seed contains:

- 10 synthetic customers.
- 10 TRY accounts (one per customer).
- 20 transactions with deterministic timestamps and amounts.
- Four rules, created if missing.
- The initial schema's legacy `demo-system` row is not used as a request actor.

The seed then invokes the same `evaluate_rules` service used by the explicit
rule-evaluation endpoint. The currently seeded database produced 15 alerts
(R1: 1, R2: 4, R3: 1, R4: 9). Alert row IDs are database-generated and should
not be assumed to be the same on another database.

### A note about repeatability

The seed only creates the transaction set if it finds no row whose transaction
number starts with `DEMO-TX-`. It does not repair a partially deleted demo
transaction set. For this tiny learning dataset, avoiding duplicate rows on a
repeat click is the goal; a general-purpose fixture reset/migration tool is not
implemented.

## 9. CSV upload and row-level errors

The upload endpoint handles three entity types. Their template headers are
defined in the Streamlit UI and required headers are checked in the API.

### Processing steps

1. Confirm that the filename ends in `.csv`.
2. Read at most 5 MB plus one byte; reject files larger than 5 MB.
3. Decode as UTF-8 (with an optional BOM).
4. Parse the CSV in strict mode and check required headers.
5. Reject uploads with more than 5,000 rows.
6. Create an `upload_batch` record and get its generated ID.
7. Parse each data row, using line 2 as the first CSV data row.
8. Keep valid records for insertion; create `upload_row_error` records for
   invalid rows.
9. Insert accepted records, row errors, counts, and an audit event in one
   database commit.
10. After a transaction upload with accepted records, run the rules.
11. Return counts plus any row errors in the response.

### Validation by entity

- **Customer:** requires a customer number and full name; limits text field
  lengths; monthly income, when supplied, must be finite, nonnegative, and at
  most two decimal places.
- **Account:** requires an existing `customer_no`, account number, and a
  three-letter currency code. The customer must be uploaded first.
- **Transaction:** requires existing sender and receiver accounts; requires
  positive finite amount with at most two decimal places; validates channel,
  two-letter country code, three-letter currency, account/currency agreement,
  and a timezone-naive ISO timestamp.
- **All entity types:** reject missing IDs and duplicate IDs within the same
  file or already in the database.

If a row is invalid, the other individually valid rows may still be accepted.
However, if a later database constraint rejects the accepted set during the
commit, the database transaction rolls back the batch and accepted records
together and the endpoint reports a failure. The row-level report is for
validation errors the application can identify before insertion.

Upload customers first, accounts second, and transactions last because foreign
keys require referenced parent rows to exist.

### Downloadable templates

The UI includes small CSV templates for each entity. They demonstrate the
expected headers and formats; a template row is illustrative and may conflict
with existing demo IDs if uploaded unchanged.

## 10. The Streamlit screens

`frontend/app.py` configures `st.navigation` and runs the selected page from
`frontend/app_pages/`. Each page is a separate script; shared HTTP behavior
lives in `frontend/utils/api.py`, and reusable page elements live in
`frontend/components/`.

### Shared API helper

`api_request` is the common HTTP wrapper. It:

- joins `API_BASE_URL` with an API path;
- passes query parameters, JSON bodies, or multipart files;
- uses a 20-second timeout;
- turns network/HTTP errors into readable `ApiError` messages; and
- returns decoded JSON for successful responses.

Individual screens catch `ApiError` and show the message with `st.error`.

### Detection overview

Requests `/dashboard/summary` for analyzed and suspicious transaction totals,
alert status and severity distributions, daily detection counts for the last
30 days, and rule trigger counts. It also displays the latest alerts. The
“Evaluate rules now” button calls `POST /rules/evaluate` and refreshes the
page.

### Alert investigation

The page sends status, severity, rule, and date filters to `GET /alerts`,
fetches `GET /alerts/{id}` for associated transfers and analyst history, and
can request `GET /customers/{customer_no}/transactions` for customer activity.
Its form calls `PATCH /alerts/{id}/status`. The server enforces the note
requirement for closing or confirming an alert and records notes even when the
analyst keeps the current status.

### Transaction analysis

The page calls `GET /transactions` with date, customer, direction, and amount
filters. It displays incoming/outgoing activity, daily transaction counts,
transfers near the active R1 threshold, and alert-linked transactions. The
account-flow diagram is hidden until an account or customer is selected. It
then loads every matching transfer for that focus (including paginated results)
and shows only links touching the selected entity; routes are grouped by
account pair and currency. Curved bands connect originating accounts, transfer
routes, and receiving accounts, with thickness indicating transfer count and
alert-linked routes highlighted. Native hover tooltips show transfer totals
and alert counts. Amount totals are grouped by currency; no exchange-rate
conversion is inferred.

### Data management

The page selects an entity type, offers a template download, accepts a CSV,
and submits it as a multipart upload. It shows accepted/rejected counts and row
errors. The last batch ID is kept in Streamlit session state; the report
lookup can fetch any entered batch ID.

### Rule management

The page fetches `GET /rules`, displays the selected rule's parameters using
rule-specific widgets, and submits them to `PUT /rules/{code}`. API validation
is still required because clients can bypass the UI.

### State and refresh behavior

Streamlit widget values are rerun-driven. `st.session_state["last_upload_id"]`
stores only the last upload ID for that browser session; the actual upload and
report live in PostgreSQL. The app does not hold the authoritative alert/rule
state in a client-side cache.

## 11. Migrations and database setup

### What Alembic is doing here

An Alembic migration is a versioned Python script that moves a database from
one known schema revision to another. `alembic_version` stores the currently
applied revision. Future schema changes should be added as new migrations
rather than editing an already-applied migration or rerunning the original SQL
file.

### Baseline migration

`0001_existing_schema_baseline` supports both expected starting conditions:

- If none of the project tables exist, it executes the original
  `database/V1__initial_schema.sql`.
- If all of the expected project tables already exist, it leaves them intact
  and records the baseline revision.
- If only some project tables exist, it stops with the names of missing tables
  instead of guessing how to repair the database.

The baseline also inserts the legacy `demo-system` row if absent. The RBAC
migration maps existing string roles to `app_role`; new request actions use
the authenticated user's ID.

This initial migration is deliberately a **baseline**, not a sequence of
fine-grained transformations from the old SQL schema. It cannot be safely
downgraded because doing so could imply deleting data. `Base.metadata` in
`alembic/env.py` is the metadata future migration/autogeneration work can
inspect.

### PostgreSQL driver normalization

The installed dependency is `psycopg2-binary`. SQLAlchemy accepts URLs such as
`postgresql://...`, but its default driver selection may choose a different
driver. `normalize_database_url` explicitly changes PostgreSQL URLs to
`postgresql+psycopg2://...`. It does not print or expose the credential values.

## 12. Configuration and dependencies

### `.env`

`DATABASE_URL` tells SQLAlchemy and Alembic which database to use.
`API_BASE_URL` tells Streamlit where FastAPI is running. `.env` is a local
secret-bearing file and should not be committed or pasted into support
messages. Set `JWT_SECRET` to a long random value; the API fails at startup if
it is missing. `.env.example` contains placeholders, not working credentials.

### Main dependencies

- **FastAPI:** route definitions, request parsing, and HTTP responses.
- **Uvicorn:** serves the ASGI FastAPI application.
- **SQLAlchemy:** maps entities and builds database queries/sessions.
- **Alembic:** applies versioned schema changes.
- **psycopg2-binary:** PostgreSQL DBAPI driver used by SQLAlchemy.
- **python-dotenv:** reads local environment settings from `.env`.
- **Streamlit:** Python-rendered interactive screens.
- **requests:** frontend-to-API HTTP calls.
- **pandas:** tables and simple chart data preparation.

There is no ORM or database connection from Streamlit directly to PostgreSQL.

## 13. Tests and how to verify changes

Run the test suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

They check:

- SQLAlchemy mapper relationships can be configured.
- Known rule values pass threshold validation.
- Invalid or ambiguous values are rejected.
- Alert candidate deduplication is stable and includes R2 account scope.
- PostgreSQL URL formats are normalized to the installed driver.
- RBAC route permissions, login audit events, identity attribution, and
  alert-scoped customer history are checked without truncating append-only
  audit/history tables.

These are **unit checks**, not proof of every database-backed workflow. A
fuller manual smoke-test sequence with a local PostgreSQL database is:

1. `alembic upgrade head`
2. Create an administrator with `python -m backend.scripts.create_admin` and
   sign in through Streamlit. Set `ENABLE_DEMO_ENDPOINTS=true` before startup
   if the smoke test should exercise demo seeding.
3. Start the API and UI.
4. Call `/health`.
5. Click the demo seed button twice. The second result should report zero
   newly created alerts.
6. Check `/dashboard/summary`, `/alerts`, and `/rules`.
7. Open an alert and inspect its related transactions.
8. Try closing an alert without a note; expect HTTP 422.
9. Close it with a note; verify the status history changes.
10. Save a valid rule setting; fetch `/rules` to see the persisted value.
11. Upload a valid CSV and one with deliberately invalid rows; inspect the
    counts and `/uploads/{batch_id}` report.

Use the API docs at `/docs` to inspect exact request shapes and responses. For
a UI issue, first check the browser page, then the API response, then backend
logs; that sequence tells you which layer is responsible.

## 14. Limits and deliberate omissions

These are important when explaining the project honestly:

- **The demo seed endpoint is disabled by default.** Set
  `ENABLE_DEMO_ENDPOINTS=true` only in a development environment; the endpoint
  still requires `upload:create`.
- **RBAC is not a production identity platform.** There is no MFA, SSO,
  password recovery, or deployment secrets-management plan.
- **Rules are basic deterministic examples.** They are not validated financial
  policy and may create false positives/negatives.
- **R2 has a simple window interpretation.** It totals all matching inbound and
  outbound transactions in the same account/currency window; it does not match
  incoming/outgoing transfers individually.
- **R3 uses the most recent N prior outgoing transactions.** It does not use a
  statistical baseline, seasonal adjustment, or a configurable time horizon.
- **R4 country codes are examples.** The demo's `TR` and `IL` settings are not
  a statement that those countries are risky.
- **No background scheduler or ML.** Rules run when a user triggers evaluation
  or after transaction upload.
- **No production upload pipeline.** There is a file/row limit and validation,
  but no malware scan, asynchronous queue, or large-file streaming import.
- **No production operations plan.** Backups, monitoring, secrets management,
  database least privilege, retention, and deployment are not implemented.
- **No committed default admin or password.** Create the first admin with
  `python -m backend.scripts.create_admin`.

## 15. Questions you should be able to answer

### “How does the dashboard know the counts?”

The UI calls `GET /dashboard/summary`. FastAPI runs database aggregate queries
with `COUNT` and `GROUP BY`, returns JSON, and Streamlit renders metrics and
charts. The dashboard does not calculate rule matches in the browser.

### “How does the app decide a transaction is suspicious?”

The rule service loads active rules and active transactions, evaluates their
threshold math, and constructs candidate alerts. It uses a unique
deduplication key when inserting, so reevaluating the same transaction set does
not create the same alert again.

### “Where does an alert's evidence come from?”

The `alert` row stores rule/customer/status/severity. The `alert_transaction`
table links it to supporting transaction rows. The detail API loads both plus
the append-only status history.

### “Why use SQLAlchemy if we already have SQL tables?”

The tables are the database schema; SQLAlchemy gives Python typed classes and
sessions to query/update those tables. It does not mean the schema disappears,
and it does not automatically migrate the database.

### “What does Alembic add?”

It records which schema version is applied and gives future changes a
repeatable, ordered migration path. The first migration adopts or creates the
existing schema without dropping an existing complete schema.

### “Why is Streamlit not connected directly to PostgreSQL?”

The API is the single place for validation and business behavior. That avoids
duplicating rule and persistence logic in the UI and makes the same behavior
available to other clients later.

### “What would change for ML?”

First keep raw transaction data, labels/review outcomes, feature definitions,
and evaluation timestamps well-structured. An ML model should be introduced as
a separate scoring component with measured precision/recall and human review,
not as an untested replacement for these transparent baseline rules. Model
training and inference are not present today.

## 16. Glossary

- **Entity/model:** a Python class mapped to a database table.
- **ORM:** object-relational mapper; translates between Python objects and
  relational database rows.
- **Session:** SQLAlchemy's unit of work for querying and committing changes.
- **Migration:** a versioned change to a database schema.
- **Foreign key:** a database constraint requiring a referenced row to exist.
- **JSONB:** PostgreSQL's queryable JSON storage type; used for rule thresholds
  and audit details.
- **Deduplication key:** a stable unique identifier for one rule finding, used
  to avoid inserting it more than once.
- **Rolling window:** an interval measured from a transaction timestamp, not
  fixed to a calendar hour.
- **Append-only history:** records are added, not updated/deleted through
  ordinary database operations; PostgreSQL triggers reject modifications.
- **ASGI:** the Python server interface used by FastAPI and Uvicorn.

## 17. Role-based access control

### Roles and permissions

Alembic revision `0002_rbac` creates the role, permission, and
`role_permission` tables and migrates `app_user.role` to `app_user.role_id`.
The seeded `admin` role has every permission. The seeded `analyst` role has
only `alert:view`, `alert:update`, and `dashboard:view`. If the old schema
contains auditor users, the migration preserves them as a legacy `auditor`
role with no seeded permissions. No user rows are deleted.

The permission codes are `user:manage`, `role:manage`, `upload:create`,
`upload:view`, `rule:view`, `rule:edit`, `customer:view`, `alert:view`,
`alert:update`, `dashboard:view`, and `audit:view`. User creation, deactivation,
and role assignment require `user:manage`; `role:manage` is reserved for role
administration and does not currently expose a role-editing endpoint.

### Authentication and route enforcement

`POST /auth/login` accepts the OAuth2 password form and returns a 30-minute
HS256 bearer token. `GET /auth/me` reloads the user, role, and permissions from
the database and returns the username, role code, and sorted permissions.
Every API request using a protected route reloads the same authorization data;
inactive users and roles are rejected. The only public routes are `POST
/auth/login` and `GET /health`.

Alerts and linked alert customer history require `alert:view`; the
alert-history route derives its customer from the alert ID and does not accept
a client-supplied customer ID. Generic transaction/customer history browsing
requires `customer:view`, which analysts do not have. Other route permissions
follow their action: rule reads use `rule:view`, edits/manual evaluation use
`rule:edit`, uploads use `upload:create`, upload reports use `upload:view`,
dashboard uses `dashboard:view`, and audit-log reads use `audit:view`.
Automatic detection after an upload is attributed to the uploading user and
does not require `rule:edit`. `ACCESS_DENIED`, `LOGIN_SUCCESS`, and
`LOGIN_FAILED` audit entries are committed in an independent transaction;
failed-login details contain the username but never the password.

The Streamlit app stores the token and permission list in session state,
attaches the bearer token to API calls, and builds navigation from permissions.
This improves the UI but is not a substitute for API enforcement.

### First administrator and existing databases

Set `JWT_SECRET` in `.env` to a long random value; the API fails at startup if
it is missing. After applying migrations, run
`python -m backend.scripts.create_admin`. The script reads
`ADMIN_USERNAME`/`ADMIN_PASSWORD` from the environment or prompts interactively.
It stores only a bcrypt hash; no default credentials are committed.

For a manually initialized database containing the complete original schema
but no Alembic revision, adopt the original baseline and apply RBAC:

```powershell
.\.venv\Scripts\alembic.exe stamp 0001_existing_schema_baseline
.\.venv\Scripts\alembic.exe upgrade head
```

Do not edit or stamp revision `0001` as the RBAC revision. The RBAC revision
is `0002_rbac`. The demo seed endpoint is disabled unless
`ENABLE_DEMO_ENDPOINTS=true` is explicitly set, and still requires
`upload:create`.
