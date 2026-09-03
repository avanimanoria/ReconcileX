"""Comprehensive unit and integration tests for the Grounded Exception Explainer AI module."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.ai.adapter import MockLLMAdapter
from backend.app.ai.service import GroundedExceptionExplainerService
from backend.app.api.app import app
from backend.app.api.deps import get_ai_explainer_service, get_db
from backend.app.services.batch_service import BatchService


@pytest.fixture
def populated_batch_exception(db_conn):
    """Seed test database with fixture data and return first exception ID and details."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    batch_service = BatchService()
    summary = batch_service.process_csv_directory(conn=db_conn, data_dir=data_dir)
    assert len(summary.exceptions) > 0

    exc_info = summary.exceptions[0]
    return exc_info["exception_id"]


def test_ai_explanation_valid_grounded_response(db_conn, populated_batch_exception):
    """Verify that a valid, grounded model response is accepted and returned as HTTP 200."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    # First fetch exception to get valid grounded IDs
    exc_res = client.get(f"/exceptions/{exc_id}")
    assert exc_res.status_code == 200
    exc_data = exc_res.json()
    valid_payment_id = exc_data.get("payment_id") or "PAY-001"
    valid_settlement_id = exc_data.get("settlement_id") or "SET-001"

    valid_ai_json = json.dumps({
        "exception_id": exc_id,
        "status": "VALID",
        "advisory_only": True,
        "summary": f"Payment {valid_payment_id} and settlement {valid_settlement_id} have a deterministic variance.",
        "evidence": [
            {
                "source_type": "payment",
                "source_id": valid_payment_id,
                "claim": f"Payment recorded under {valid_payment_id}",
            },
            {
                "source_type": "settlement",
                "source_id": valid_settlement_id,
                "claim": f"Settlement recorded under {valid_settlement_id}",
            },
        ],
        "calculation_summary": {
            "captured_amount": None,
            "refund_amount": None,
            "fee_amount": None,
            "gst_amount": None,
            "expected_net": None,
            "settlement_net_amount": None,
            "bank_credit_amount": None,
            "variance_amount": None,
            "currency": "INR",
        },
        "suggested_next_step": "Ask an analyst to verify supporting documents before taking any action.",
        "unknowns": ["Root cause of variance is not present in batch data."],
        "confidence": 0.88,
    })

    mock_adapter = MockLLMAdapter(canned_response=valid_ai_json)
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation", json={"actor": "tester_alice"})
        assert res.status_code == 200
        data = res.json()
        assert data["exception_id"] == exc_id
        assert data["advisory_only"] is True
        assert data["confidence"] == 0.88
        assert data["validation"]["schema_valid"] is True
        assert data["validation"]["grounding_valid"] is True
        assert data["validation"]["fallback_used"] is False
        assert len(data["evidence"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_malformed_json_fallback(db_conn, populated_batch_exception):
    """Verify that malformed JSON returned by LLM triggers safe deterministic fallback."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    mock_adapter = MockLLMAdapter(canned_response="{ not valid json: bad syntax ")
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert data["validation"]["fallback_reason"] == "MALFORMED_JSON_RETURNED"
        assert data["advisory_only"] is True
        assert data["model"]["provider"] == "deterministic_fallback"
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_unsupported_evidence_id_fallback(db_conn, populated_batch_exception):
    """Verify that LLM inventing an unsupported source ID triggers fallback."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    hallucinated_json = json.dumps({
        "exception_id": exc_id,
        "status": "VALID",
        "advisory_only": True,
        "summary": "Fabricated analysis.",
        "evidence": [
            {
                "source_type": "payment",
                "source_id": "PAY-HALLUCINATED-9999",
                "claim": "Non-existent payment claimed.",
            }
        ],
        "calculation_summary": {},
        "suggested_next_step": "Investigate.",
        "unknowns": [],
        "confidence": 0.9,
    })

    mock_adapter = MockLLMAdapter(canned_response=hallucinated_json)
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert "UNGROUNDED_SOURCE_ID" in data["validation"]["fallback_reason"]
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_wrong_amount_fallback(db_conn, populated_batch_exception):
    """Verify that LLM altering a calculated amount triggers fallback."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    # First fetch exception to get valid IDs
    exc_res = client.get(f"/exceptions/{exc_id}")
    exc_data = exc_res.json()
    valid_payment_id = exc_data.get("payment_id") or "PAY-001"

    altered_amount_json = json.dumps({
        "exception_id": exc_id,
        "status": "VALID",
        "advisory_only": True,
        "summary": "Summary with fabricated amount.",
        "evidence": [
            {
                "source_type": "payment",
                "source_id": valid_payment_id,
                "claim": "Valid payment ID with invalid amount",
            }
        ],
        "calculation_summary": {
            "captured_amount": "999999.99",  # Completely wrong amount
        },
        "suggested_next_step": "Investigate.",
        "unknowns": [],
        "confidence": 0.9,
    })

    mock_adapter = MockLLMAdapter(canned_response=altered_amount_json)
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert "AMOUNT_MISMATCH" in data["validation"]["fallback_reason"]
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_banned_autonomous_directive_fallback(db_conn, populated_batch_exception):
    """Verify that model issuing autonomous/state-changing directives is blocked."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    exc_res = client.get(f"/exceptions/{exc_id}")
    valid_payment_id = exc_res.json().get("payment_id") or "PAY-001"

    directive_json = json.dumps({
        "exception_id": exc_id,
        "status": "VALID",
        "advisory_only": True,
        "summary": "This match looks clean so the system should auto-match it now.",
        "evidence": [
            {"source_type": "payment", "source_id": valid_payment_id, "claim": "Payment found."}
        ],
        "calculation_summary": {},
        "suggested_next_step": "Mark resolved immediately.",
        "unknowns": [],
        "confidence": 0.9,
    })

    mock_adapter = MockLLMAdapter(canned_response=directive_json)
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert "AUTONOMOUS_DIRECTIVE_DETECTED" in data["validation"]["fallback_reason"]
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_unobserved_cause_as_fact_fallback(db_conn, populated_batch_exception):
    """Verify that model asserting an unobserved cause (e.g. unevidenced bank fee) as fact triggers fallback."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    exc_res = client.get(f"/exceptions/{exc_id}")
    valid_payment_id = exc_res.json().get("payment_id") or "PAY-001"

    unobserved_cause_json = json.dumps({
        "exception_id": exc_id,
        "status": "VALID",
        "advisory_only": True,
        "summary": "The amount difference was caused by a bank fee that was deducted.",
        "evidence": [
            {"source_type": "payment", "source_id": valid_payment_id, "claim": "Payment found."}
        ],
        "calculation_summary": {},
        "suggested_next_step": "Inquire with operations.",
        "unknowns": [],
        "confidence": 0.9,
    })

    mock_adapter = MockLLMAdapter(canned_response=unobserved_cause_json)
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert "UNOBSERVED_CAUSE_ASSERTED_AS_FACT" in data["validation"]["fallback_reason"]
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_missing_api_key_deterministic_fallback(db_conn, populated_batch_exception):
    """Verify that when no LLM adapter is configured, deterministic fallback is returned cleanly."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    # Explicitly pass None adapter
    ai_service = GroundedExceptionExplainerService(llm_adapter=None)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert data["validation"]["fallback_reason"] == "NO_LLM_KEY_CONFIGURED"
        assert data["model"]["provider"] == "deterministic_fallback"
        assert len(data["summary"]) > 10
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_timeout_returns_fallback(db_conn, populated_batch_exception):
    """Verify that adapter timeout triggers safe deterministic fallback."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    mock_adapter = MockLLMAdapter(should_timeout=True)
    ai_service = GroundedExceptionExplainerService(llm_adapter=mock_adapter)
    app.dependency_overrides[get_ai_explainer_service] = lambda: ai_service

    try:
        res = client.post(f"/exceptions/{exc_id}/ai-explanation")
        assert res.status_code == 200
        data = res.json()
        assert data["validation"]["fallback_used"] is True
        assert "MODEL_TIMEOUT" in data["validation"]["fallback_reason"]
    finally:
        app.dependency_overrides.clear()


def test_ai_explanation_zero_mutation_guarantee(db_conn, populated_batch_exception):
    """Verify calling POST /exceptions/{id}/ai-explanation makes zero mutations to exception or results."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    # Query initial state of exception
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM exceptions WHERE id = %s;", (exc_id,))
        before_exc = dict(cur.fetchone())

        cur.execute("SELECT COUNT(*) as cnt FROM reconciliation_results;")
        before_result_count = cur.fetchone()["cnt"]

    # Call AI explanation endpoint
    res = client.post(f"/exceptions/{exc_id}/ai-explanation")
    assert res.status_code == 200

    # Query state after call
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM exceptions WHERE id = %s;", (exc_id,))
        after_exc = dict(cur.fetchone())

        cur.execute("SELECT COUNT(*) as cnt FROM reconciliation_results;")
        after_result_count = cur.fetchone()["cnt"]

    # Assert 100% identity of exception fields
    assert before_exc["status"] == after_exc["status"]
    assert before_exc["assigned_to"] == after_exc["assigned_to"]
    assert before_exc["resolution_reason"] == after_exc["resolution_reason"]
    assert before_exc["resolved_by"] == after_exc["resolved_by"]
    assert before_exc["resolved_at"] == after_exc["resolved_at"]
    assert before_exc["updated_at"] == after_exc["updated_at"]
    assert before_result_count == after_result_count


def test_ai_explanation_creates_audit_event_with_immutable_protection(db_conn, populated_batch_exception):
    """Verify that calling AI explanation creates append-only audit event and audit triggers remain intact."""
    app.dependency_overrides[get_db] = lambda: db_conn
    client = TestClient(app)
    exc_id = populated_batch_exception

    res = client.post(f"/exceptions/{exc_id}/ai-explanation", json={"actor": "audited_operator"})
    assert res.status_code == 200

    # Verify audit event in database
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM audit_events WHERE exception_id = %s AND event_type = 'AI_EXPLANATION_GENERATED';",
            (exc_id,),
        )
        events = cur.fetchall()
        assert len(events) >= 1
        ev = dict(events[-1])
        assert ev["actor"] == "audited_operator"
        assert ev["action"] == "GENERATE_AI_EXPLANATION"
        assert "output_hash" in ev["metadata"]
        assert "model" in ev["metadata"]

        # Attempt to mutate audit event to prove PostgreSQL immutable trigger protection
        with pytest.raises(Exception, match="audit_events is append-only"):
            cur.execute("UPDATE audit_events SET reason = 'Tampered' WHERE id = %s;", (ev["id"],))

        with pytest.raises(Exception, match="audit_events is append-only"):
            cur.execute("DELETE FROM audit_events WHERE id = %s;", (ev["id"],))
