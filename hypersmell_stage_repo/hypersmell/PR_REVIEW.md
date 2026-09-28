# PR Review: Fragrance Formula Import

## What I would approve
- **Domain Modeling**: The `Formula` SQLModel nicely captures the domain requirements (accords, concentration, structured scent profile). The use of `JSONB` for structured fields like `ingredients` and `scent_profile` is a smart choice for Postgres.
- **Parsing Logic**: The `_parse_formula_notation` string parsing logic cleanly converts unstructured top/middle/base notes into structured dictionaries. It handles the format perfectly and correctly extracts percentages.
- **Pagination Logic**: The `while True` loop and `len(formulas) < PAGE_SIZE` break condition is a standard, solid approach to API pagination.

## What I would request changes on
1. **Critical Security Vulnerability (API Keys in Query Params)**: In `api/formula_import.py`, `api_key_param` is passed directly as a query parameter. The API key must be securely retrieved from the database's `Connection` table.
2. **Architectural Violation (Ignoring Base Class)**: The code ignores the `Integration` base class (`hypersmell/integrations/base.py`). It explicitly duplicates `httpx.Client` setup (even leaving a comment: `# Duplicates the client setup from supplier_catalog`) instead of inheriting it. It implements raw `list_formulas` and `fetch_formula` functions rather than overriding `list_resources` and `fetch_resource`.
3. **Silently Swallowing Exceptions**: In `integrations/formula_import.py`, both functions wrap HTTP calls in `except Exception: pass`. This silently fails on invalid keys or rate limits. The `Integration` base class already provides a `@retry` decorator for transient failures; we should use that and let real errors propagate.
4. **Incomplete Feature (No Database Persistence)**: `import_all_formulas` never saves the data to the database. By not subclassing `Integration`, it completely bypasses the `process_resource` orchestration pipeline.
5. **Missing Tests**: There are zero tests included in the PR to verify the complex formula parsing logic or the API endpoints.
6. **Missing Alembic Migration**: The PR adds a new `Formula` table but doesn't include an `alembic` migration script to create it in production.
