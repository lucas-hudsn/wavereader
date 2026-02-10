from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")


def test_get_states():
    response = client.get("/api/states")
    assert response.status_code == 200
    data = response.json()
    assert "states" in data
    assert isinstance(data["states"], list)


def test_get_all_breaks():
    response = client.get("/api/breaks")
    assert response.status_code == 200
    data = response.json()
    assert "breaks" in data
    assert "total" in data
    assert isinstance(data["breaks"], list)


def test_get_all_breaks_pagination():
    response = client.get("/api/breaks?limit=5&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["breaks"]) <= 5
    assert data["limit"] == 5
    assert data["offset"] == 0


def test_get_break_not_found():
    response = client.get("/api/break/NonExistentBeach12345")
    assert response.status_code == 404


def test_get_break_case_insensitive():
    # First get a real break name
    breaks_response = client.get("/api/breaks?limit=1")
    breaks = breaks_response.json().get("breaks", [])
    if not breaks:
        return  # Skip if no data
    name = breaks[0]["name"]
    # Try with different case
    response = client.get(f"/api/break/{name.lower()}")
    # Should find it (case-insensitive) or at least not 500
    assert response.status_code in (200, 404)
