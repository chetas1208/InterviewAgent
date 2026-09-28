# CLAUDE.md

## Development Commands

- `task test` — run tests (sets up test DB, enables network blocking)
- `task test -- tests/path/to/test.py` — run specific test file
- `task lint` — check code with Ruff
- `task lint-fix` — auto-fix lint issues
- `task format` — format code with Ruff
- `task make-migration NAME="description"` — generate Alembic migration
- `task migrate` — apply migrations

Do NOT run `pytest` directly — `task test` handles database setup and
network isolation that tests depend on.

## Coding Conventions

- Write a failing test before writing implementation code
- Run `task test` and `task lint` before every commit — all tests must pass
- Line length: 100 characters
- Use `from loguru import logger` for logging
- Commit message format: `type: description` (e.g., `fix: resolve chunking
  truncation`)
- Type all function signatures — avoid `Any` or bare `dict`
- Follow existing patterns: check how similar code works before writing new code

## Architecture Notes

- Integrations subclass `Integration` base class in `integrations/base.py`
- Pipeline stages are composable: parse → chunk → embed → store
- Background tasks run through Inngest — see `tasks/events.py` for event definitions
- Settings come from environment variables via `settings.py`
