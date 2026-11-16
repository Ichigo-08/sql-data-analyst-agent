# Architecture notes

## Dependency direction

`ui` -> application/service modules -> `database` / `sql_engine` / `analytics`
`visualization` is called by UI pages and consumes prepared data.

Lower-level modules must not import Streamlit. This keeps core logic testable
without a browser session.

## Phase 2–4 service boundaries

- Connection manager: owns SQLAlchemy engine lifecycle and connection testing.
- Schema inspector: returns normalized table, column, key, and relationship metadata.
- SQL validator: parses a single statement, allows only SELECT and safe read-only CTEs,
  and rejects modifying or administrative statements.
- Query executor: accepts only validated statements, applies row/time limits, and
  returns structured results and execution metadata.

## Phase 9 provider boundary

A future provider interface may accept a user request plus normalized schema metadata
and return a proposed SQL string. The SQL validator and query executor remain
mandatory and cannot be bypassed by a provider.
