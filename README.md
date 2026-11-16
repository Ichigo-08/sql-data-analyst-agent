# SQL Data Analyst Platform — Phase 1

A modular, AI-free SQL analytics platform. Phase 1 establishes the architecture,
dependency baseline, configuration conventions, and project skeleton. Application
features are intentionally implemented in later phases.

## Requirements

- Python 3.11
- pip
- A local SQLite database for initial development
- PostgreSQL or MySQL server only when testing those connectors

## Setup

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Planned launch command

The Streamlit entry point will be `app.py` in a later phase:

```bash
streamlit run app.py
```

## Architecture

- `config/`: application settings and environment configuration
- `database/`: database connections, schema inspection, query execution and imports
- `sql_engine/`: deterministic SQL generation, validation, templates and history
- `analytics/`: metric calculations, aggregations and rule-based observations
- `visualization/`: Plotly chart and dashboard composition
- `ui/`: Streamlit pages and navigation
- `tests/`: automated tests
- `data/`: local development databases and sample data (database files are git-ignored)

## Design principles

1. No AI SDKs, model downloads, API keys, or paid services in Phase 1.
2. Keep UI, database access, SQL safety, analytics, and visualization separate.
3. Default to read-only query execution.
4. Use SQLAlchemy dialect metadata and SQLGlot rather than assuming one SQL dialect.
5. Do not infer business meaning from arbitrary column names; dashboard metrics will be configured by users.
6. Keep credentials out of source code and logs.

## Development phases

1. Architecture and dependencies — current
2. Database connection manager
3. Database explorer and schema inspection
4. SQL validator and read-only query executor
5. Visual query builder
6. Analytics dashboard and visualizations
7. CSV and Excel import
8. Testing, bug fixing and documentation
9. Optional AI provider interface

## Known limitations at this stage

This is a Phase 1 scaffold, not a runnable analytics application yet. The entry point,
database adapters, UI pages, query execution, dashboards, and tests will be implemented
in their respective phases. PostgreSQL and MySQL require reachable servers and valid
credentials to test end-to-end.


## Phase 4 — SQL Workspace

The SQL Workspace provides SQLGlot-based validation and read-only query execution.
It permits one SELECT statement or read-only SELECT CTE, rejects modifying and
administrative statements, supports bound parameters, applies result-row limits,
tracks execution time, and exports displayed results to CSV and Excel.

SQLite connections use `PRAGMA query_only` during query execution. PostgreSQL
transactions are marked read-only and use `statement_timeout`. For MySQL, use a
dedicated read-only database account and configure server-side execution limits;
timeout enforcement differs by MySQL server/version. Application-level validation
is not a substitute for least-privilege database credentials.


## Phase 5 — Visual SQL Query Builder

The Visual Query Builder creates parameterized SELECT statements from selected
tables, columns, filters, optional joins, aggregations, grouping, sorting and a
row limit. Generated SQL is passed through the Phase 4 read-only validator and
query executor. Filter values are bound as parameters rather than interpolated
into SQL. One additional table can be joined at a time; declared foreign keys
are detected automatically, and manual join keys are available when no FK exists.

The builder currently supports one optional joined table per generated query.
If no foreign-key relationship is declared, the user selects the join-key
columns manually. Up to five filter rows are available; untouched rows are
ignored. Joined output columns are qualified by table name to prevent
ambiguous column references.

## Phase 6 — Analytics Dashboard and Visualisations

The Analytics Dashboard provides schema-driven KPIs, interactive Plotly charts,
optional categorical/date/numeric filters, bounded data previews, CSV/Excel exports,
and simple rule-based observations derived from the selected result data. It works
against the active SQLite, PostgreSQL or MySQL SQLAlchemy connection and does not
assume fixed business table or column names.

Dashboard aggregates and chart queries use SQLAlchemy Core reflected identifiers and
bound filter values. The dashboard does not accept user-authored SQL and performs
read-only SELECT/aggregate operations. Chart and preview result sets are bounded.

To use it, connect a database, open **Analytics Dashboard**, choose a table or view,
configure KPI cards and a chart, and optionally enable a filter. Export buttons download
the displayed chart data or preview as CSV or Excel.

### Included sample database

Run `python seed_sample_db.py` from the project root to generate a local sample
SQLite database at `data/sample.db`. The script recreates its four sample tables
(customers, products, orders and order_items), so rerunning it replaces those sample
tables. Connect to `data/sample.db` from Database Connections to explore the platform.

## Phase 7 — CSV and Excel import

The **Import CSV / Excel** page allows a connected database user to load `.csv` and `.xlsx` files into the active SQLite, PostgreSQL or MySQL database.

- Shows a preview and row/column/file-size summary before import.
- Supports selecting a worksheet in Excel workbooks.
- Uses a 50 MB file limit and a 250,000-row import limit.
- Requires destination table names to use portable letters, numbers and underscores.
- Defaults to refusing an existing table. Append requires matching column names; replacing an existing table requires explicit confirmation.
- Imports use SQLAlchemy transactions and Pandas `to_sql`; uploaded values are not concatenated into SQL statements.
- Imported tables become available to Database Explorer, SQL Workspace and Analytics Dashboard after refresh/reconnection if needed.

Run the tests with `python -m pytest -q`. The importer-specific tests can be run with `python -m pytest -q tests/test_data_importer.py`.
