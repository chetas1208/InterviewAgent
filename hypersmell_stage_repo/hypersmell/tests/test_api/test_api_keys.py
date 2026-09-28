"""Tests for the /api/api-keys endpoints."""
import uuid


def test_create_api_key(client, workspace):
    """POST /api/api-keys creates a key and returns the raw key in the response."""
    response = client.post(
        "/api/api-keys",
        json={"name": "My Key", "workspace_id": str(workspace.id)},
    )
    assert response.status_code == 201
    data = response.json()
    assert "key" in data
    assert data["key"].startswith("hs_")
    assert "id" in data
    assert data["workspace_id"] == str(workspace.id)
    assert data["name"] == "My Key"
    # The full key is never exposed again after creation
    assert "key_prefix" in data
    assert "key_hash" not in data


def test_create_api_key_unknown_workspace(client):
    """POST /api/api-keys with unknown workspace_id returns 404."""
    response = client.post(
        "/api/api-keys",
        json={"name": "My Key", "workspace_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_list_api_keys(client, workspace, api_key_pair):
    """GET /api/api-keys returns keys with prefix only — no raw key or hash."""
    _, api_key = api_key_pair
    response = client.get("/api/api-keys", params={"workspace_id": str(workspace.id)})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Only prefix is returned, not the full key or hash
    key_data = next(k for k in data if k["id"] == str(api_key.id))
    assert "key_prefix" in key_data
    assert "key" not in key_data
    assert "key_hash" not in key_data


def test_delete_api_key(client, workspace, api_key_pair):
    """DELETE /api/api-keys/{id} revokes the key."""
    _, api_key = api_key_pair
    response = client.delete(
        f"/api/api-keys/{api_key.id}",
        params={"workspace_id": str(workspace.id)},
    )
    assert response.status_code == 204

    # Confirm it's gone from the list
    list_response = client.get("/api/api-keys", params={"workspace_id": str(workspace.id)})
    ids = [k["id"] for k in list_response.json()]
    assert str(api_key.id) not in ids


def test_api_key_auth(client, auth_headers):
    """Requests with a valid API key succeed on auth-protected endpoints."""
    response = client.get("/api/resources", headers=auth_headers)
    assert response.status_code == 200


def test_invalid_api_key(client):
    """Requests with an invalid API key are rejected with 401."""
    response = client.get(
        "/api/resources",
        headers={"Authorization": "Bearer hs_thiskeyisnotvalid"},
    )
    assert response.status_code == 401


def test_missing_auth_header(client):
    """Requests with no Authorization header are rejected."""
    response = client.get("/api/resources")
    # FastAPI returns 403 when the security scheme is missing
    assert response.status_code in (401, 403)
