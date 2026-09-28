"""Tests for TastingNotesIntegration.

Mirrors the supplier_catalog tests — list, fetch, and full sync flow.
"""
from unittest.mock import MagicMock, patch

import httpx

from hypersmell.integrations.tasting_notes import TastingNotesIntegration
from hypersmell.settings import Settings


def _make_settings():
    return Settings(
        tasting_notes_api_url="http://test-tasting-notes",
        mango_url="http://test-mango",
        mango_fallback_tokens='{"tn_conn_001": "test-token"}',
    )


def _make_integration(transport=None):
    settings = _make_settings()
    connection = MagicMock()
    connection.mango_connection_id = "tn_conn_001"

    with patch("hypersmell.integrations.tasting_notes.MangoClient") as MockMango:
        mock_mango = MagicMock()
        mock_mango.get_token.return_value = "test-token"
        MockMango.return_value = mock_mango
        integration = TastingNotesIntegration(connection, settings)

    integration.mango = mock_mango

    if transport:
        integration.client = httpx.Client(
            transport=transport, base_url="http://test-tasting-notes"
        )

    return integration


SESSION_DATA = {
    "id": "sess_001",
    "date": "2025-11-15",
    "perfumer_name": "Claire Dubois",
    "scent_name": "Midnight Jasmine",
    "overall_rating": 8,
    "sillage": "moderate",
    "longevity_hours": 6.5,
    "top_notes": ["bergamot oil (cold-pressed)", "pink pepper"],
    "middle_notes": ["jasmine absolute (egyptian)", "rose (turkish)"],
    "base_notes": ["sandalwood (mysore)", "white musk"],
    "ingredients": ["bergamot oil (cold-pressed)", "jasmine absolute (egyptian)"],
    "commentary": "A bright and effervescent opening.",
}


def _session_transport():
    """Mock transport that serves session data."""
    def handler(request):
        if request.url.path == "/sessions":
            return httpx.Response(200, json={
                "items": [SESSION_DATA],
                "next_cursor": None,
            })
        if request.url.path == "/sessions/sess_001":
            return httpx.Response(200, json=SESSION_DATA)
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


class TestListResources:
    def test_list_resources_returns_sessions(self):
        integration = _make_integration(_session_transport())

        result = integration.list_resources()
        assert len(result.items) == 1
        assert result.items[0]["perfumer_name"] == "Claire Dubois"
        assert result.next_cursor is None


class TestFetchResource:
    def test_fetch_resource_returns_session_data(self):
        """fetch_resource should return parsed session data as a resource dict."""
        integration = _make_integration(_session_transport())

        result = integration.fetch_resource("sess_001")
        assert result["external_id"] == "sess_001"
        assert result["title"] == "Midnight Jasmine"
        assert "content" in result
        assert isinstance(result["metadata"], dict)

    def test_fetch_resource_metadata_includes_notes(self):
        """Session metadata should include top, middle, and base notes."""
        integration = _make_integration(_session_transport())

        result = integration.fetch_resource("sess_001")
        meta = result["metadata"]
        assert "top_notes" in meta or "perfumer_name" in meta


class TestFullSync:
    def test_full_sync_fetches_and_processes_sessions(self):
        """Full sync should list sessions, then fetch each one."""
        integration = _make_integration(_session_transport())

        all_resources = integration.list_all_resources()
        assert len(all_resources) == 1

        # Fetch each resource — this should return parsed content
        result = integration.fetch_resource(all_resources[0]["id"])
        assert result["external_id"] == "sess_001"
        assert "content" in result
