import pytest
from fastapi.testclient import TestClient
from app import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_get_tree_200(client):
    resp = client.get("/api/tree")
    assert resp.status_code == 200
    assert "name" in resp.json()

def test_get_tree_custom_ancestor(client):
    resp = client.get("/api/tree?ancestor_key=be_a_powerful_tool_for_solutions_architecture")
    assert resp.status_code == 200
    assert resp.json()["name"] == "be_a_powerful_tool_for_solutions_architecture"

def test_get_tree_bad_ancestor_404(client):
    resp = client.get("/api/tree?ancestor_key=nonexistent_key_xyz")
    assert resp.status_code == 404

def test_get_files_returns_list(client):
    resp = client.get("/api/files")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0

def test_get_file_content(client):
    resp = client.get("/api/files/iacs.yaml")
    assert resp.status_code == 200
    assert len(resp.text) > 0
