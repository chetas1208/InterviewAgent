"""Unit tests for the Inngest sync_integration handler.

Uses mocks to avoid hitting Inngest or external APIs — verifies that
Resource rows are created (or skipped) correctly based on what the
integration returns.

Note: @client.create_function wraps the function in an inngest.Function object.
Tests call `._handler` directly to bypass the Inngest machinery.
"""
from unittest.mock import MagicMock, patch

from sqlmodel import select

from hypersmell.models import Connection, Resource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(workspace_id, integration="supplier_catalog"):
    """Build a minimal fake Inngest context."""
    ctx = MagicMock()
    ctx.event.data = {
        "workspace_id": str(workspace_id),
        "integration": integration,
    }
    return ctx


def _make_step():
    """Return a mock Inngest step that records send_event calls."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sync_creates_resources(session, workspace):
    """sync_integration creates Resource rows for each item returned by the integration."""
    connection = Connection(
        workspace_id=workspace.id,
        integration="supplier_catalog",
        status="active",
    )
    session.add(connection)
    session.commit()

    fake_resources = [
        {"id": "ing-001", "name": "Linalool"},
        {"id": "ing-002", "name": "Geraniol"},
        {"id": "ing-003", "name": "Citronellol"},
    ]

    ctx = _make_ctx(workspace.id)
    step = _make_step()

    with patch("hypersmell.tasks.handlers.Session") as MockSession, \
         patch("hypersmell.tasks.handlers.SupplierCatalogIntegration") as MockIntegration, \
         patch("hypersmell.tasks.handlers.get_settings") as mock_settings:

        MockSession.return_value.__enter__.return_value = session
        MockSession.return_value.__exit__.return_value = False

        mock_integration_instance = MagicMock()
        mock_integration_instance.list_all_resources.return_value = fake_resources
        MockIntegration.return_value = mock_integration_instance

        mock_settings.return_value = MagicMock(embedding_model="all-MiniLM-L6-v2")

        from hypersmell.tasks.handlers import sync_integration
        # Inngest wraps the function in a Function object; call the raw handler
        sync_integration._handler(ctx, step)

    resources = session.exec(
        select(Resource).where(Resource.workspace_id == workspace.id)
    ).all()

    assert len(resources) == 3
    external_ids = {r.external_id for r in resources}
    assert external_ids == {"ing-001", "ing-002", "ing-003"}

    # Each new resource should trigger a process event
    assert step.send_event.call_count == 3


def test_sync_skips_existing(session, workspace):
    """sync_integration does not create duplicate Resource rows."""
    connection = Connection(
        workspace_id=workspace.id,
        integration="supplier_catalog",
        status="active",
    )
    session.add(connection)
    session.commit()

    # Pre-create one resource that already exists
    existing = Resource(
        workspace_id=workspace.id,
        integration="supplier_catalog",
        external_id="ing-001",
        title="Linalool (existing)",
        status="ready",
    )
    session.add(existing)
    session.commit()

    fake_resources = [
        {"id": "ing-001", "name": "Linalool"},   # already in DB
        {"id": "ing-002", "name": "Geraniol"},   # new
    ]

    ctx = _make_ctx(workspace.id)
    step = _make_step()

    with patch("hypersmell.tasks.handlers.Session") as MockSession, \
         patch("hypersmell.tasks.handlers.SupplierCatalogIntegration") as MockIntegration, \
         patch("hypersmell.tasks.handlers.get_settings"):

        MockSession.return_value.__enter__.return_value = session
        MockSession.return_value.__exit__.return_value = False

        mock_integration_instance = MagicMock()
        mock_integration_instance.list_all_resources.return_value = fake_resources
        MockIntegration.return_value = mock_integration_instance

        from hypersmell.tasks.handlers import sync_integration
        sync_integration._handler(ctx, step)

    resources = session.exec(
        select(Resource).where(Resource.workspace_id == workspace.id)
    ).all()

    # Only 2 total: the pre-existing one + the new one
    assert len(resources) == 2

    # Only the new resource should trigger a process event
    assert step.send_event.call_count == 1
    sent_data = step.send_event.call_args[0][1].data
    assert sent_data["integration"] == "supplier_catalog"


def test_sync_returns_early_when_no_connection(session, workspace):
    """sync_integration exits gracefully when no Connection is found."""
    # Do NOT create a connection

    ctx = _make_ctx(workspace.id)
    step = _make_step()

    with patch("hypersmell.tasks.handlers.Session") as MockSession, \
         patch("hypersmell.tasks.handlers.get_settings"):

        MockSession.return_value.__enter__.return_value = session
        MockSession.return_value.__exit__.return_value = False

        from hypersmell.tasks.handlers import sync_integration
        sync_integration._handler(ctx, step)

    resources = session.exec(
        select(Resource).where(Resource.workspace_id == workspace.id)
    ).all()
    assert len(resources) == 0
    step.send_event.assert_not_called()


def test_sync_ignores_unknown_integration(session, workspace):
    """sync_integration returns early for unrecognised integration names."""
    connection = Connection(
        workspace_id=workspace.id,
        integration="unknown_service",
        status="active",
    )
    session.add(connection)
    session.commit()

    ctx = _make_ctx(workspace.id, integration="unknown_service")
    step = _make_step()

    with patch("hypersmell.tasks.handlers.Session") as MockSession, \
         patch("hypersmell.tasks.handlers.get_settings"):

        MockSession.return_value.__enter__.return_value = session
        MockSession.return_value.__exit__.return_value = False

        from hypersmell.tasks.handlers import sync_integration
        sync_integration._handler(ctx, step)

    resources = session.exec(
        select(Resource).where(Resource.workspace_id == workspace.id)
    ).all()
    assert len(resources) == 0
    step.send_event.assert_not_called()
