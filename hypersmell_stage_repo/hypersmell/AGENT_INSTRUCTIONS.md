# Instructions for the AI Agent

To generate a robust, production-ready integration for Fragrance Formula import, please follow these explicit constraints and architectural patterns:

1. **Security & Authentication**
   - **NEVER** accept API keys or sensitive credentials via URL query parameters in FastAPI endpoints.
   - **ALWAYS** retrieve credentials securely from the `Connection` table in the database, keyed by the authenticated user's `workspace_id` and the `integration` name.

2. **Error Handling & Observability**
   - **NEVER** silently swallow exceptions (e.g., `except Exception: pass`).
   - When making external HTTP requests, use `response.raise_for_status()`. Catch `httpx.HTTPError`, log it explicitly with context using `logger.error()`, and raise an appropriate `HTTPException` so the client receives a meaningful failure reason.

3. **Data Persistence & Pipeline Integration**
   - This app relies on persisting data to the database. Fetching data and returning it to the client is insufficient.
   - Ensure the fetched formulas are either persisted directly to the newly defined `Formula` table using a SQLModel `Session`, or properly routed through the orchestrator to the `Resource` table so they can be chunked and embedded for vector search.

4. **Database Schema & Migrations**
   - Any time you add a new model to `models.py` (like the `Formula` model), you **MUST** generate the corresponding Alembic database migration script. Run `alembic revision --autogenerate` or manually create the script to ensure the schema can be applied in production.

5. **Code Architecture (Base Class)**
   - **ALWAYS** subclass `hypersmell.integrations.base.Integration` when building a new integration. Do not duplicate `httpx.Client` setup.
   - Implement `list_resources` and `fetch_resource` to integrate cleanly with the `process_resource` orchestration pipeline instead of writing raw standalone functions.
   - Adhere strictly to the project's existing patterns in `api/resources.py` for injecting dependencies like `session: Session` and `workspace_id`.
