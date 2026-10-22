# İşlem İzleme ve Alarm Sistemi

Transaction monitoring MVP using FastAPI, PostgreSQL,
SQLAlchemy, Alembic, and Streamlit. It includes a synthetic demo dataset, basic
deterministic R1–R4 evaluation, alert review screens, CSV uploads, and rule
parameters. Login and roles are intentionally out of scope.

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

2. Copy `.env.example` to `.env` and set `DATABASE_URL` to your local
   PostgreSQL database. Do not share or commit the local `.env` file.

3. Apply the Alembic baseline once:

   ```powershell
   .\.venv\Scripts\alembic.exe upgrade head
   ```

   For a fresh database, this creates the existing project schema. For a
   database that already has the complete original schema, it adopts that
   schema without recreating tables. Do not separately rerun
   `database\V1__initial_schema.sql` against an existing schema.

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

Click **Load demo data** to seed 10 synthetic customers, 10 accounts, and 20
transactions and run the rules. Seeding is
repeatable: it does not add the same demo records again. Import CSV data in
dependency order: customers, accounts, then transactions.

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

The schema requires a user reference for uploads and alert-history records.
`demo-system` is a technical database identity only; it does not provide login
or role-based authorization. This MVP is for synthetic data and learning, not
production risk decisions.
