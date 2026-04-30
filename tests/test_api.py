import pytest
from fastapi.testclient import TestClient

from app import app
from iacs.utils import get_id


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_view_requirement(client):
    """Test that we can call the API to view the requirements
    component for the active registry.
    """

    # Make the call to the API
    resp = client.get("/api/view/requirement")
    assert resp.status_code == 200
    data = resp.json()

    # Check that the foundational requirement for iacs is in the requirements view
    filepath = "builtins/iacs.yaml"
    path = "iacs.be_a_powerful_tool_for_solutions_architecture"
    test_entity_id = get_id(filepath, path)
    for record in data:

        if record["entity_id"] != test_entity_id:
            continue

        assert record["requirement.value"] == "functional"
        assert record["requirement.priority"] == 0.5


def test_view_multiple_component_types(client):
    """Test that slash-separated component types are inner-joined by entity_id."""
    resp = client.get("/api/view/description/requirement")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) > 0
    record = data[0]
    assert "description.value" in record
    assert "requirement.value" in record


def test_view_specific_field(client):
    """Test that individual dotted fields can be requested via the API."""
    resp = client.get("/api/view/requirement.priority")
    assert resp.status_code == 200
    data = resp.json()

    filepath = "builtins/iacs.yaml"
    path = "iacs.be_a_powerful_tool_for_solutions_architecture"
    test_entity_id = get_id(filepath, path)
    for record in data:

        if record["entity_id"] != test_entity_id:
            continue

        assert record["requirement.priority"] == 0.5
        assert "requirement.value" not in record
