"""Tests for the GET /health API endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import app
from backend.app.api.deps import get_db


def test_get_health(db_conn):
    """Verify GET /health returns 200 OK and valid engine/database status."""
    app.dependency_overrides[get_db] = lambda: db_conn
    try:
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["engine_version"] == "v1.1-deterministic"
        assert data["database"] == "connected"
    finally:
        app.dependency_overrides.clear()
