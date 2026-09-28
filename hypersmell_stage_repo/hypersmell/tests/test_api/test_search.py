"""Tests for the /api/search endpoint.

Full vector search requires PostgreSQL with pgvector and the `vector_search`
SQL function defined in the migration. These tests cover auth enforcement and
parameter validation — functionality that doesn't need a real Postgres.
"""


def test_search_requires_auth(client):
    """GET /api/search without auth returns 401 or 403."""
    response = client.get("/api/search", params={"q": "bergamot"})
    assert response.status_code in (401, 403)


def test_search_limit_validation_too_low(client, auth_headers):
    """limit=0 is below the minimum (ge=1) and is rejected with 422."""
    # FastAPI validates query params before the endpoint runs,
    # so this returns 422 without ever touching the DB.
    response = client.get(
        "/api/search",
        params={"q": "vetiver", "limit": 0},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_search_limit_validation_too_high(client, auth_headers):
    """limit=101 is above the maximum (le=100) and is rejected with 422."""
    response = client.get(
        "/api/search",
        params={"q": "vetiver", "limit": 101},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_search_missing_query(client, auth_headers):
    """Missing required 'q' parameter returns 422."""
    response = client.get("/api/search", headers=auth_headers)
    assert response.status_code == 422


def test_search_response_schema():
    """SearchResponse and SearchResult have the expected fields (unit test)."""
    from hypersmell.api.search import SearchResponse, SearchResult

    result = SearchResult(
        chunk_id="abc123",
        resource_id="def456",
        content="Rose absolute from Bulgaria, rich and deep.",
        metadata={},
        source="supplier_catalog",
        score=0.92,
    )
    response = SearchResponse(
        query="rose",
        results=[result],
    )
    assert response.query == "rose"
    assert len(response.results) == 1
    assert response.results[0].score == 0.92
