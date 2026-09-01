"""Tests for the /audit-events API routes and read-only immutability."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import app
from backend.app.api.deps import get_db


@pytest.fixture
def api_client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def populated_batch_id(api_client):
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    files = {
        "payments_file": ("payments.csv", (data_dir / "payments.csv").read_bytes(), "text/csv"),
        "settlements_file": ("settlements.csv", (data_dir / "settlements.csv").read_bytes(), "text/csv"),
        "bank_credits_file": ("bank_credits.csv", (data_dir / "bank_credits.csv").read_bytes(), "text/csv"),
        "refunds_file": ("refunds.csv", (data_dir / "refunds.csv").read_bytes(), "text/csv"),
    }
    res = api_client.post("/batches", files=files)
    return res.json()["id"]


def test_get_audit_events_list_and_filtering(api_client, populated_batch_id):
    """Verify GET /audit-events lists audit events strictly ordered by event_sequence ASC."""
    res = api_client.get(f"/audit-events?batch_id={populated_batch_id}&limit=20&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert data["limit"] == 20

    # Verify audit ordering is explicitly defined by event_sequence ASC
    sequences = [item["event_sequence"] for item in data["items"]]
    assert len(sequences) > 0
    assert sequences == sorted(sequences)
    for i in range(len(sequences) - 1):
        assert sequences[i] < sequences[i + 1], "event_sequence must strictly increase in ascending order"


def test_audit_events_read_only_methods_return_405(api_client):
    """Verify POST, PUT, PATCH, and DELETE on /audit-events are strictly prohibited (405)."""
    assert api_client.post("/audit-events", json={"event_type": "TEST"}).status_code == 405
    assert api_client.put("/audit-events", json={"event_type": "TEST"}).status_code == 405
    assert api_client.patch("/audit-events", json={"event_type": "TEST"}).status_code == 405
    assert api_client.delete("/audit-events").status_code == 405


def test_no_delete_routes_exist_for_entities(api_client, populated_batch_id):
    """Verify DELETE is prohibited across batches and exceptions."""
    assert api_client.delete(f"/batches/{populated_batch_id}").status_code == 405
    fake_exc_id = "00000000-0000-0000-0000-000000000000"
    assert api_client.delete(f"/exceptions/{fake_exc_id}").status_code == 405
