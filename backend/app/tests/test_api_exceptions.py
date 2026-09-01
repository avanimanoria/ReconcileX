"""Tests for the /exceptions API routes."""

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
def sample_exception_id(api_client):
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    files = {
        "payments_file": ("payments.csv", (data_dir / "payments.csv").read_bytes(), "text/csv"),
        "settlements_file": ("settlements.csv", (data_dir / "settlements.csv").read_bytes(), "text/csv"),
        "bank_credits_file": ("bank_credits.csv", (data_dir / "bank_credits.csv").read_bytes(), "text/csv"),
        "refunds_file": ("refunds.csv", (data_dir / "refunds.csv").read_bytes(), "text/csv"),
    }
    res = api_client.post("/batches", files=files)
    batch_id = res.json()["id"]

    exc_res = api_client.get(f"/batches/{batch_id}/exceptions")
    assert len(exc_res.json()["items"]) > 0
    return exc_res.json()["items"][0]["id"]


def test_get_exception_by_id_and_not_found(api_client, sample_exception_id):
    """Verify GET /exceptions/{id} returns full exception detail or 404."""
    res = api_client.get(f"/exceptions/{sample_exception_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == sample_exception_id
    assert "category" in data
    assert "priority" in data
    assert "financial_evidence" in data

    fake_id = "00000000-0000-0000-0000-000000000000"
    res_fake = api_client.get(f"/exceptions/{fake_id}")
    assert res_fake.status_code == 404


def test_patch_exception_assignment_only(api_client, sample_exception_id):
    """Verify PATCH /exceptions/{id} with assigned_to updates assignee without mutating status."""
    payload = {
        "assigned_to": "analyst_sarah",
        "actor": "lead_john",
    }
    res = api_client.patch(f"/exceptions/{sample_exception_id}", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["assigned_to"] == "analyst_sarah"
    assert data["status"] == "OPEN"  # Status remains OPEN


def test_patch_exception_lifecycle_workflow(api_client, sample_exception_id):
    """Verify valid lifecycle transitions: OPEN -> IN_REVIEW -> RESOLVED."""
    # 1. OPEN -> IN_REVIEW
    res1 = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={"status": "IN_REVIEW", "actor": "analyst_sarah"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "IN_REVIEW"

    # 2. IN_REVIEW -> RESOLVED (with mandatory resolution_reason)
    res2 = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={
            "status": "RESOLVED",
            "actor": "analyst_sarah",
            "resolution_reason": "Bank confirmed batch credit reference manual adjustment.",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "RESOLVED"
    assert data2["resolved_by"] == "analyst_sarah"
    assert data2["resolution_reason"] == "Bank confirmed batch credit reference manual adjustment."


def test_patch_exception_no_op_rejected(api_client, sample_exception_id):
    """Verify PATCH with neither status nor assigned_to is rejected with 422."""
    res = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={"actor": "analyst_sarah"},
    )
    assert res.status_code == 422


def test_patch_exception_missing_actor_rejected(api_client, sample_exception_id):
    """Verify PATCH omitting mandatory actor is rejected with 422."""
    res = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={"status": "IN_REVIEW"},
    )
    assert res.status_code == 422


def test_patch_exception_missing_resolution_reason_rejected(api_client, sample_exception_id):
    """Verify transitioning to RESOLVED or DISMISSED without resolution_reason returns 422."""
    api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={"status": "IN_REVIEW", "actor": "analyst_sarah"},
    )

    res = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={"status": "RESOLVED", "actor": "analyst_sarah"},
    )
    assert res.status_code == 422


def test_patch_exception_invalid_transition_rejected(api_client, sample_exception_id):
    """Verify invalid transition (OPEN -> RESOLVED direct) returns 409 Conflict."""
    res = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={
            "status": "RESOLVED",
            "actor": "analyst_sarah",
            "resolution_reason": "Direct resolution attempt without review",
        },
    )
    assert res.status_code == 409


def test_patch_exception_prohibited_fields_rejected(api_client, sample_exception_id):
    """Verify attempting to pass prohibited fields (e.g. priority, category) returns 422."""
    res = api_client.patch(
        f"/exceptions/{sample_exception_id}",
        json={
            "actor": "analyst_sarah",
            "status": "IN_REVIEW",
            "priority": "LOW",  # Forbidden field
        },
    )
    assert res.status_code == 422
