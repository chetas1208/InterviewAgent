"""Tests for the /api/resources endpoints."""
import uuid

from sqlmodel import select

from hypersmell.models import Resource


def _create_resource(session, workspace_id: uuid.UUID) -> Resource:
    """Helper: insert a resource directly into the test DB."""
    resource = Resource(
        workspace_id=workspace_id,
        integration="supplier_catalog",
        external_id="ext-001",
        title="Test Resource",
        content="Some content here.",
        status="indexed",
    )
    session.add(resource)
    session.commit()
    session.refresh(resource)
    return resource


def test_list_resources_empty(client, auth_headers):
    """GET /api/resources with auth returns empty list for a fresh workspace."""
    response = client.get("/api/resources", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_resources(client, session, workspace, auth_headers):
    """GET /api/resources returns resources belonging to the workspace."""
    resource = _create_resource(session, workspace.id)
    response = client.get("/api/resources", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(resource.id)
    assert data[0]["title"] == resource.title
    # Content is not included in the list response
    assert "content" not in data[0]


def test_get_resource(client, session, workspace, auth_headers):
    """GET /api/resources/{id} returns the full resource including content."""
    resource = _create_resource(session, workspace.id)
    response = client.get(f"/api/resources/{resource.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(resource.id)
    assert data["content"] == resource.content


def test_get_resource_not_found(client, auth_headers):
    """GET /api/resources/{id} returns 404 for unknown resource."""
    response = client.get(f"/api/resources/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_delete_resource(client, session, workspace, auth_headers):
    """DELETE /api/resources/{id} removes the resource (and any chunks)."""
    resource = _create_resource(session, workspace.id)
    response = client.delete(f"/api/resources/{resource.id}", headers=auth_headers)
    assert response.status_code == 204

    # Confirm the resource is gone
    remaining = session.exec(
        select(Resource).where(Resource.id == resource.id)
    ).first()
    assert remaining is None


def test_delete_resource_not_found(client, auth_headers):
    """DELETE /api/resources/{id} returns 404 for unknown resource."""
    response = client.delete(f"/api/resources/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_resources_require_auth(client):
    """Resource endpoints without auth return 401/403."""
    response = client.get("/api/resources")
    assert response.status_code in (401, 403)
