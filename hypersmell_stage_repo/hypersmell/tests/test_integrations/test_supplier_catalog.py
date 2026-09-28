"""Tests for SupplierCatalogIntegration.

All HTTP calls are mocked via httpx.MockTransport — no real network access.
"""

import httpx
import pytest

from hypersmell.integrations.base import PaginatedResult
from hypersmell.integrations.supplier_catalog import SupplierCatalogIntegration
from hypersmell.settings import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> Settings:
    """Return a Settings instance with a predictable supplier catalog URL."""
    return Settings(
        supplier_catalog_api_url="http://test-catalog",
        **overrides,
    )


class _MockTransport(httpx.BaseTransport):
    """Simple mock transport that dispatches requests to registered handlers."""

    def __init__(self, handlers: dict):
        # handlers maps (method, path) -> (status_code, body_dict | None)
        self._handlers = handlers

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key not in self._handlers:
            return httpx.Response(404, json={"detail": "not found"})
        status, body = self._handlers[key]
        return httpx.Response(status, json=body)


def _make_integration(transport: httpx.BaseTransport) -> SupplierCatalogIntegration:
    """Build a SupplierCatalogIntegration with a mocked HTTP client."""
    settings = _make_settings()
    integration = SupplierCatalogIntegration(connection=None, settings=settings)
    # Replace the real httpx.Client with one using our mock transport
    integration.client = httpx.Client(transport=transport, base_url="http://test-catalog")
    return integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


INGREDIENT_LINALOOL = {
    "id": "ing-001",
    "name": "Linalool",
    "description": "A naturally occurring terpene alcohol with a floral scent.",
    "cas_number": "78-70-6",
    "scent_family": "floral",
    "supplier": "Givaudan",
    "price_per_kg": 12.50,
    "origin_country": "France",
    "synonyms": ["3,7-dimethyl-1,6-octadien-3-ol", "licareol"],
    "safety_notes": "IFRA compliant up to 4.5% in leave-on products.",
}

INGREDIENT_VETIVER = {
    "id": "ing-002",
    "name": "Vetiver",
    "description": "Earthy, smoky root extract from Chrysopogon zizanioides.",
    "cas_number": "8016-96-4",
    "scent_family": "woody",
    "supplier": "Firmenich",
    "price_per_kg": 280.00,
    "origin_country": "Haiti",
    "synonyms": [],
    "safety_notes": "IFRA compliant, no restrictions.",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListResources:
    def test_list_resources_returns_paginated_result(self):
        page = {
            "items": [INGREDIENT_LINALOOL, INGREDIENT_VETIVER],
            "next_cursor": None,
        }
        transport = _MockTransport({("GET", "/ingredients"): (200, page)})
        integration = _make_integration(transport)

        result = integration.list_resources()

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 2
        assert result.items[0]["id"] == "ing-001"
        assert result.items[1]["id"] == "ing-002"
        assert result.next_cursor is None

    def test_list_resources_passes_cursor_param(self):
        """Cursor is forwarded as a query parameter."""
        page = {
            "items": [INGREDIENT_VETIVER],
            "next_cursor": None,
        }

        captured_params: list[str] = []

        class CapturingTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                captured_params.append(str(request.url.params))
                return httpx.Response(200, json=page)

        integration = _make_integration(CapturingTransport())
        integration.list_resources(cursor="cursor-abc")

        assert "cursor=cursor-abc" in captured_params[0]

    def test_list_resources_with_next_cursor(self):
        page = {
            "items": [INGREDIENT_LINALOOL],
            "next_cursor": "cursor-xyz",
        }
        transport = _MockTransport({("GET", "/ingredients"): (200, page)})
        integration = _make_integration(transport)

        result = integration.list_resources()

        assert result.next_cursor == "cursor-xyz"


class TestListAllResources:
    def test_collects_all_pages(self):
        """list_all_resources iterates until next_cursor is None."""
        call_count = 0

        class PaginatingTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                nonlocal call_count
                call_count += 1
                cursor = request.url.params.get("cursor")
                if cursor is None:
                    body = {"items": [INGREDIENT_LINALOOL], "next_cursor": "page-2"}
                elif cursor == "page-2":
                    body = {"items": [INGREDIENT_VETIVER], "next_cursor": None}
                else:
                    body = {"items": [], "next_cursor": None}
                return httpx.Response(200, json=body)

        integration = _make_integration(PaginatingTransport())
        all_items = integration.list_all_resources()

        # Sort by id to avoid flakiness if pagination order is non-deterministic
        sorted_items = sorted(all_items, key=lambda x: x["id"])
        assert len(sorted_items) == 2
        assert sorted_items[0]["id"] == "ing-001"
        assert sorted_items[1]["id"] == "ing-002"
        assert call_count == 2

    def test_single_page_stops_immediately(self):
        page = {"items": [INGREDIENT_LINALOOL], "next_cursor": None}
        transport = _MockTransport({("GET", "/ingredients"): (200, page)})
        integration = _make_integration(transport)

        all_items = integration.list_all_resources()

        assert len(all_items) == 1


class TestFetchResource:
    def test_fetch_resource_returns_normalized_dict(self):
        transport = _MockTransport({
            ("GET", "/ingredients/ing-001"): (200, INGREDIENT_LINALOOL),
        })
        integration = _make_integration(transport)

        result = integration.fetch_resource("ing-001")

        assert result["external_id"] == "ing-001"
        assert result["title"] == "Linalool"
        assert "content" in result
        assert isinstance(result["metadata"], dict)

    def test_fetch_resource_metadata_fields(self):
        transport = _MockTransport({
            ("GET", "/ingredients/ing-001"): (200, INGREDIENT_LINALOOL),
        })
        integration = _make_integration(transport)

        result = integration.fetch_resource("ing-001")
        meta = result["metadata"]

        assert meta["cas_number"] == "78-70-6"
        assert meta["scent_family"] == "floral"
        assert meta["supplier"] == "Givaudan"
        assert meta["price_per_kg"] == 12.50
        assert meta["origin_country"] == "France"
        assert meta["synonyms"] == ["3,7-dimethyl-1,6-octadien-3-ol", "licareol"]

    def test_fetch_resource_missing_optional_fields_default_to_none(self):
        """Optional fields absent from the API response produce None in metadata."""
        minimal = {"id": "ing-003", "name": "Oakmoss"}
        transport = _MockTransport({
            ("GET", "/ingredients/ing-003"): (200, minimal),
        })
        integration = _make_integration(transport)

        result = integration.fetch_resource("ing-003")
        meta = result["metadata"]

        assert meta["cas_number"] is None
        assert meta["scent_family"] is None
        assert meta["synonyms"] == []

    def test_fetch_resource_not_found_raises(self):
        transport = _MockTransport({})  # 404 for everything
        integration = _make_integration(transport)

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            integration.fetch_resource("ing-missing")

        assert exc_info.value.response.status_code == 404


class TestBuildContent:
    def _get_integration(self) -> SupplierCatalogIntegration:
        settings = _make_settings()
        return SupplierCatalogIntegration(connection=None, settings=settings)

    def test_build_content_includes_name_and_description(self):
        integration = self._get_integration()
        content = integration._build_content(INGREDIENT_LINALOOL)

        assert "Linalool" in content
        assert "floral scent" in content

    def test_build_content_includes_safety_notes(self):
        integration = self._get_integration()
        content = integration._build_content(INGREDIENT_LINALOOL)

        assert "Safety:" in content
        assert "IFRA compliant" in content

    def test_build_content_includes_synonyms_when_present(self):
        integration = self._get_integration()
        content = integration._build_content(INGREDIENT_LINALOOL)

        assert "Also known as:" in content
        assert "licareol" in content

    def test_build_content_omits_synonyms_line_when_empty(self):
        integration = self._get_integration()
        content = integration._build_content(INGREDIENT_VETIVER)

        assert "Also known as:" not in content

    def test_build_content_handles_missing_description_gracefully(self):
        integration = self._get_integration()
        minimal = {"name": "Mystery Musk", "id": "x"}
        content = integration._build_content(minimal)

        assert "Mystery Musk" in content
        # Should not blow up, empty description is filtered out
        assert content.startswith("Mystery Musk")
