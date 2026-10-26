# İşlem İzleme ve Alarm Sistemi

Transaction monitoring MVP using FastAPI, PostgreSQL,
SQLAlchemy, Alembic, and Streamlit. It includes a synthetic demo dataset, basic
deterministic R1–R4 evaluation, alert review screens, CSV uploads, and rule
parameters. The API uses bearer-token authentication and database-backed roles
and permissions.

For a detailed explanation of how the application is structured and how each
feature works, see the [Project Guide](./PROJECT_GUIDE.md).

## Requirements

- Python 3.10 or newer
- PostgreSQL

## Setup

1. Create a virtual environment and install both dependency sets:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend\requirements.txt
   python -m pip install -r frontend\requirements.txt
   ```

2. Copy `.env.example` to `.env`; set `DATABASE_URL` to your local PostgreSQL
   database and `JWT_SECRET` to a long, random secret. The API refuses to start
   without `JWT_SECRET`. Do not share or commit the local `.env` file.

3. Apply the Alembic migrations:

   ```powershell
   .\.venv\Scripts\alembic.exe upgrade head
   ```

   For a fresh database, this creates the original schema and applies RBAC.
   For an existing database with the complete original schema but no Alembic
   revision, stamp the baseline first, then apply the RBAC migration:

   ```powershell
   .\.venv\Scripts\alembic.exe stamp 0001_existing_schema_baseline
   .\.venv\Scripts\alembic.exe upgrade head
   ```

   Do not stamp revision `0002_rbac` unless the RBAC migration has already
   been applied manually. Do not rerun `database\V1__initial_schema.sql`
   against an existing schema.

4. Create the first administrator:

   ```powershell
   python -m backend.scripts.create_admin
   ```

   The script prompts for username and password. It can instead read
   `ADMIN_USERNAME` and `ADMIN_PASSWORD` from the process environment. No
   default administrator or password is included in the repository.

## Start in VS Code

Open the project root, select the `.venv` Python interpreter, and press `F5`
on **Start project (API + UI)** in **Run and Debug**. The API is at
`http://127.0.0.1:8000/docs`; Streamlit opens the UI in a browser.

## Screens and demo

Use the sidebar to switch between:

- **Detection overview:** analyzed and suspicious transaction totals, alert
  severity, 30-day detection trends, and the most frequently triggered rules.
- **Alert investigation:** filter by status, severity, rule, and date; inspect
  related transfers and customer history; record an analyst note and update
  alert status.
- **Transaction analysis:** compare incoming and outgoing transfers, review
  near-threshold activity, select a customer or account to trace only its
  incoming and outgoing links, and inspect transaction timelines.
- **Data management:** import UTF-8 CSV files for customers, accounts, or
  transactions; view row-level rejection reports and download templates.
- **Rule management:** change the active state and validated thresholds for
  R1–R4.

The demo seed endpoint is disabled by default. Set
`ENABLE_DEMO_ENDPOINTS=true` explicitly for a development environment to show
the UI action and enable `POST /demo/seed`. Seeding is repeatable. Import CSV
data in dependency order: customers, accounts, then transactions.

## Role-based access control

The `admin` role receives all seeded permissions. The `analyst` role receives
only `alert:view`, `alert:update`, and `dashboard:view`; alert detail includes
its linked customer and transactions, and alert-scoped customer history stays
limited to that alert's customer. Generic customer, account, and transaction
browsing requires `customer:view`. The API is the authorization boundary; the
Streamlit permission-based navigation is only a usability aid.

Users authenticate at `POST /auth/login` and can inspect their role and sorted
permissions at `GET /auth/me`. Tokens are signed with `JWT_SECRET` and expire
after 30 minutes. The `audit:view` permission is required for `GET /audit-log`.

Rule definitions used in this MVP:

- **R1:** group a customer's outgoing transactions by currency; flag at least
  the configured number of amounts in the near-limit range, inclusive at 90%
  of the limit and exclusive at the limit, within the configured window.
- **R2:** for an account and currency, compare incoming and outgoing totals in
  the same rolling window; flag when the outgoing/incoming ratio meets the
  configured threshold.
- **R3:** compare an outgoing amount with the configured multiple of the
  average of the customer's preceding outgoing transactions in the same
  currency; the current transaction is excluded.
- **R4:** match a configured country list when enabled. The demo seed enables
  `TR` and `IL` only as examples, not as real-world risk classifications.

The original baseline may retain a legacy `demo-system` row, but request
actions now use the authenticated user's ID for upload, rule, alert-history,
and audit attribution. This MVP is for synthetic data and learning, not
production risk decisions.
