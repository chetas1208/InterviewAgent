"""Pytest configuration and shared fixtures.

Uses SQLite in-memory with a shared pool for fast, isolated tests.
Each test gets its own engine to avoid cross-test state contamination.

The Chunk model uses pgvector's Vector(384) column which is not supported
by SQLite — tests that exercise chunk storage mock the session directly.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from hypersmell.database import get_session
from hypersmell.main import app
from hypersmell.models import ApiKey, Workspace

# ---------------------------------------------------------------------------
# Engine and session — function-scoped so each test is fully isolated
# ---------------------------------------------------------------------------


@pytest.fixture(name="engine")
def engine_fixture():
    """SQLite in-memory engine, fresh for each test.

    Uses StaticPool so the same in-memory connection is shared across threads
    (necessary because FastAPI's TestClient runs sync routes in a threadpool).

    Only creates the tables that don't require Postgres-only types. The
    chunks table is excluded because pgvector's Vector column is not
    supported by SQLite — chunk-related tests mock the session instead.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create tables whose SQLModel models are SQLite-compatible.
    # The chunks table uses pgvector's Vector column which SQLite can't handle,
    # so we create a simplified chunks table manually (TEXT for the embedding).
    tables = [
        SQLModel.metadata.tables[name]
        for name in ["workspaces", "api_keys", "connections", "resources"]
        if name in SQLModel.metadata.tables
    ]
    SQLModel.metadata.create_all(engine, tables=tables)

    # Manually create the chunks table with a TEXT embedding column for SQLite
    with engine.begin() as conn:
        conn.execute(
            __import__("sqlalchemy").text("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    resource_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT,
                    chunk_index INTEGER NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (resource_id, chunk_index)
                )
            """)
        )

    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="workspace")
def workspace_fixture(session):
    """Pre-created workspace available to every test that requests it."""
    workspace = Workspace(
        name="Test Workspace",
        slug="test-workspace",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


@pytest.fixture(name="api_key_pair")
def api_key_pair_fixture(session, workspace):
    """Creates an API key; returns (raw_key, db_record) tuple."""
    raw_key = "hs_testkey123456789"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = ApiKey(
        workspace_id=workspace.id,
        key_hash=key_hash,
        key_prefix=raw_key[:8],
        name="Test Key",
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return raw_key, api_key


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(api_key_pair):
    raw_key, _ = api_key_pair
    return {"Authorization": f"Bearer {raw_key}"}
