"""Tests for the /api/workspaces endpoints."""


def test_create_workspace(client):
    """POST /api/workspaces creates a workspace and returns id/name/slug."""
    response = client.post(
        "/api/workspaces",
        json={"name": "Acme Corp", "slug": "acme-corp"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"
    assert "id" in data
    assert "created_at" in data


def test_list_workspaces(client, workspace):
    """GET /api/workspaces returns a list including existing workspaces."""
    response = client.get("/api/workspaces")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    slugs = [w["slug"] for w in data]
    assert workspace.slug in slugs


def test_get_workspace(client, workspace):
    """GET /api/workspaces/{id} returns the workspace."""
    response = client.get(f"/api/workspaces/{workspace.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(workspace.id)
    assert data["name"] == workspace.name
    assert data["slug"] == workspace.slug


def test_get_workspace_not_found(client):
    """GET /api/workspaces/{id} returns 404 for unknown ID."""
    import uuid
    response = client.get(f"/api/workspaces/{uuid.uuid4()}")
    assert response.status_code == 404


def test_create_workspace_duplicate_slug(client, workspace):
    """POST /api/workspaces with an existing slug returns 409."""
    response = client.post(
        "/api/workspaces",
        json={"name": "Duplicate", "slug": workspace.slug},
    )
    assert response.status_code == 409


def test_delete_workspace(client, workspace):
    """DELETE /api/workspaces/{id} removes the workspace."""
    response = client.delete(f"/api/workspaces/{workspace.id}")
    assert response.status_code == 204

    # Confirm it's gone
    response = client.get(f"/api/workspaces/{workspace.id}")
    assert response.status_code == 404


def test_delete_workspace_not_found(client):
    """DELETE /api/workspaces/{id} returns 404 for unknown ID."""
    import uuid
    response = client.delete(f"/api/workspaces/{uuid.uuid4()}")
    assert response.status_code == 404
