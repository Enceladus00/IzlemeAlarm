# Project Guide: Understand the Transaction Monitoring MVP

This guide is meant to help you explain how the project works—not just how to
start it. It follows a request from the screen, through the API and business
logic, down to PostgreSQL, and back. It also explains the important trade-offs
and what the current version does **not** do.

> **Scope:** This is a learning/demo MVP. It uses synthetic data and simple,
> deterministic rules. It does not provide login, roles, production fraud
> decisions, or machine learning.

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
| `frontend/app.py` | Streamlit navigation and the shared demo-data action. |
| `frontend/app_pages/` | Detection overview, alert investigation, transaction analysis, data management, and rule management pages. |
| `frontend/components/` | Shared page headers, metric layouts, and transaction tables. |
| `frontend/utils/api.py` | Shared HTTP client and user-facing API errors. |
| `backend/main.py` | FastAPI application factory and router composition. |
| `backend/api/routes/` | Thin HTTP adapters grouped by analysis, alerts, rules, transactions, and uploads. |
| `backend/api/dependencies.py` | Constructs application services from the request-scoped database session. |
| `backend/api_schemas.py` | Pydantic request/response data shapes for a few API payloads. |
| `backend/database.py` | Lazily creates the SQLAlchemy engine/session factory and provides a session to each request. |
| `backend/db_url.py` | Normalizes PostgreSQL connection URLs to the installed `psycopg2` driver. |
| `backend/models.py` | SQLAlchemy entity definitions mapped to PostgreSQL tables. |
| `backend/services/` | Application workflows for analysis, alerts, demo seeding, detection, rules, transactions, and uploads. |
| `backend/repositories/` | SQLAlchemy data-access implementations injected into services. |
| `backend/detection/` | Detection engine contracts and independent R1–R4 strategy implementations. |
| `backend/rules.py` | Backward-compatible exports for the detection service and deduplication helper. |
| `backend/demo.py` | Creates a small, repeatable set of synthetic data and rule defaults. |
| `database/V1__initial_schema.sql` | Original PostgreSQL schema, constraints, indexes, triggers, and initial rule rows. |
| `alembic.ini`, `alembic/` | Alembic configuration and the initial schema-baseline migration. |
| `tests/test_application.py` | Fast unit checks for model mapping, threshold validation, deduplication, and URL normalization. |
| `.vscode/launch.json` | VS Code launch buttons for the API, UI, or both together. |
| `.env.example` | Template for local configuration. Copy this to `.env` and set your own database URL. |
| `backend/requirements.txt` | Backend dependencies, including FastAPI, SQLAlchemy, and Alembic. |
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

- **AppUser:** exists because the original schema requires a user foreign key
  for some actions. This MVP creates a technical `demo-system` row; it is not
  a login account.
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
- Alert status/severity and user role values are constrained.
- Closing or confirming an alert requires a nonblank note.
- Alert deduplication keys are unique.
- SQL triggers reject UPDATE/DELETE on the three append-only history tables.

Indexes help common lookups such as transactions by account/time, alerts by
status/time, alerts by customer, and upload errors by batch.

## 6. The API, route by route

The route implementations are in `backend/main.py`; the interactive reference
is available at `/docs` while the API is running.

| Method and route | Purpose | Important behavior |
| --- | --- | --- |
| `GET /health` | Check database connectivity. | Runs `SELECT 1`; returns 503 when the database cannot be reached. |
| `GET /dashboard/summary` | Return record totals, severity/rule distributions, and recent detection trends. | Uses SQL `COUNT` and `GROUP BY`; it does not load all transactions into Python. |
| `GET /alerts` | List/filter alerts. | Supports status, severity, rule code, date range, offset, and bounded page size. |
| `GET /alerts/{alert_id}` | Show one alert, its linked transactions, and status history. | Returns 404 if no alert has that ID. |
| `PATCH /alerts/{alert_id}/status` | Change status or record analyst reasoning. | Allowed status values are fixed; closing/confirming requires a note; writes history and audit rows. |
| `GET /transactions` | Filter and inspect account-to-account transfers. | Supports date, customer, direction, and amount filters; returns linked-alert indicators. |
| `GET /customers/{customer_no}/transactions` | Show a customer's transaction history. | Includes incoming and outgoing transfers for active customer accounts. |
| `GET /rules` | Read rule descriptions, active flags, and thresholds. | Rules are returned ordered by code. |
| `PUT /rules/{rule_code}` | Save a rule's active flag and thresholds. | Rejects unknown/missing threshold keys and invalid values with 422. |
| `POST /rules/evaluate` | Evaluate active rules against stored transactions. | Returns how many new deduplicated alerts were inserted. |
| `POST /demo/seed` | Seed the demo data and evaluate it. | Repeat calls don't recreate demo transactions or duplicate existing alerts. |
| `POST /uploads?entity=...` | Upload customer/account/transaction CSV. | Enforces CSV, UTF-8, 5 MB, 5000-row, header, and row-level validation. |
| `GET /uploads/{batch_id}` | Retrieve one upload report. | Includes summary counts and stored row errors; returns 404 for an unknown batch. |

### Why the frontend calls the API

The Streamlit UI is a client of the API, rather than a direct database client.
That keeps SQL and business logic in one place and means API validation also
applies when someone calls an endpoint outside the UI. At the current MVP
stage, this is an architectural boundary, not an authentication boundary:
there is no login or authorization.

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
- A technical `demo-system` record when needed for the existing user foreign
  keys.

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

It also inserts `demo-system` if absent, because the current database schema
requires user IDs in upload/history records.

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
messages. `.env.example` contains a placeholder, not working credentials.

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

Run the unit tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

They check:

- SQLAlchemy mapper relationships can be configured.
- Known rule values pass threshold validation.
- Invalid or ambiguous values are rejected.
- Alert candidate deduplication is stable and includes R2 account scope.
- PostgreSQL URL formats are normalized to the installed driver.

These are **unit checks**, not proof of every database-backed workflow. A
fuller manual smoke-test sequence with a local PostgreSQL database is:

1. `alembic upgrade head`
2. Start the API and UI.
3. Call `/health`.
4. Click the demo seed button twice. The second result should report zero
   newly created alerts.
5. Check `/dashboard/summary`, `/alerts`, and `/rules`.
6. Open an alert and inspect its related transactions.
7. Try closing an alert without a note; expect HTTP 422.
8. Close it with a note; verify the status history changes.
9. Save a valid rule setting; fetch `/rules` to see the persisted value.
10. Upload a valid CSV and one with deliberately invalid rows; inspect the
    counts and `/uploads/{batch_id}` report.

Use the API docs at `/docs` to inspect exact request shapes and responses. For
a UI issue, first check the browser page, then the API response, then backend
logs; that sequence tells you which layer is responsible.

## 14. Limits and deliberate omissions

These are important when explaining the project honestly:

- **No login, roles, or authorization.** Anyone able to reach the API can call
  its routes. The screens are not access control.
- **`demo-system` is not authentication.** The existing schema requires user
  foreign keys; the technical record only satisfies those references.
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
- **No committed default admin or password.** There is also no login flow to
  create one.

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
