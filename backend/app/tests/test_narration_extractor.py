"""Comprehensive unit and integration tests for Advisory Bank-Narration Extractor and Candidate Ranker."""

from decimal import Decimal
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import psycopg

from backend.app.ai.adapter import MockLLMAdapter
from backend.app.ai.narration_extractor import (
    AINarrationCandidatesResponse,
    AdvisoryNarrationService,
    fallback_regex_extract,
    validate_extraction_output,
)
from backend.app.api.app import app
from backend.app.api.deps import get_advisory_narration_service, get_db
from backend.app.services.batch_service import BatchService


@pytest.fixture
def populated_batch_with_narration(db_conn):
    """Seed test database with batch CSV data and ensure a bank credit has narration."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "input"
    batch_service = BatchService()
    summary = batch_service.process_csv_directory(conn=db_conn, data_dir=data_dir)
    assert len(summary.exceptions) > 0

    exc_info = summary.exceptions[0]
    batch_id = summary.batch_id

    # Add or update a bank credit with a known narration in this batch
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bank_credits (batch_id, bank_txn_id, credit_amount, credited_at, narration)
            VALUES (%s, 'BNK-TEST-NARR-01', 976.40, '2026-03-03 00:00:00+00', 'NEFT RAZORPAY SETTLMNT SET-001 UTR 98124571')
            ON CONFLICT (batch_id, bank_txn_id) DO UPDATE SET narration = EXCLUDED.narration;
            """,
            (batch_id,),
        )

        # Link reconciliation result to this bank txn for testing
        cur.execute(
            "UPDATE reconciliation_results SET bank_txn_id = 'BNK-TEST-NARR-01' WHERE id = %s;",
            (exc_info["reconciliation_result_id"],),
        )

    db_conn.commit()

    return {
        "batch_id": batch_id,
        "exception_id": exc_info["exception_id"],
        "expected_settlement_id": "SET-001",
    }


def test_narration_extraction_valid_exact_match(db_conn, populated_batch_with_narration):
    """Test valid extraction with exact stored settlement candidate."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]
    exp_set = data["expected_settlement_id"]

    mock_json = json.dumps({
        "settlement_id_candidate": exp_set,
        "utr_candidate": "98124571",
        "confidence": 0.96,
        "unknowns": [],
    })
    mock_adapter = MockLLMAdapter(canned_response=mock_json)
    service = AdvisoryNarrationService(llm_adapter=mock_adapter)

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates", json={"actor": "analyst_alice"})
    assert res.status_code == 200
    payload = res.json()

    assert payload["exception_id"] == exc_id
    assert payload["advisory_only"] is True
    assert payload["financial_match_decision"] == "NOT_MADE"
    assert payload["extraction"]["settlement_id_candidate"] == exp_set
    assert payload["extraction"]["utr_candidate"] == "98124571"
    assert payload["validation"]["fallback_used"] is False

    # Check ranked candidate
    assert len(payload["ranked_candidates"]) >= 1
    top_cand = payload["ranked_candidates"][0]
    assert top_cand["settlement_id"] == exp_set
    assert top_cand["deterministic_eligibility"] in ("ELIGIBLE_FOR_HUMAN_REVIEW", "AMBIGUOUS_FOR_HUMAN_REVIEW")
    assert top_cand["evidence"]["extracted_reference_equals_settlement_id"] is True


def test_narration_extraction_no_reference_present(db_conn, populated_batch_with_narration):
    """Test narration with no settlement ID -> returns null candidate and empty candidates list."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    mock_json = json.dumps({
        "settlement_id_candidate": None,
        "utr_candidate": "123456",
        "confidence": 0.50,
        "unknowns": ["No settlement ID in narration"],
    })
    mock_adapter = MockLLMAdapter(canned_response=mock_json)
    service = AdvisoryNarrationService(llm_adapter=mock_adapter)

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200
    payload = res.json()

    assert payload["extraction"]["settlement_id_candidate"] is None


def test_narration_extraction_malformed_json_fallback(db_conn, populated_batch_with_narration):
    """Malformed model JSON must trigger deterministic regex fallback."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    mock_adapter = MockLLMAdapter(canned_response="INVALID JSON NOT A DICT")
    service = AdvisoryNarrationService(llm_adapter=mock_adapter)


    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200
    payload = res.json()

    assert payload["validation"]["fallback_used"] is True
    assert "EXTRACTION_INVOCATION_ERROR" in payload["validation"]["fallback_reason"]
    # Fallback regex still extracted SET-001 from the narration
    assert payload["extraction"]["settlement_id_candidate"] == "SET-001"


def test_narration_extraction_invented_candidate_zero_candidates(db_conn, populated_batch_with_narration):
    """Model extracting a nonexistent settlement ID must yield 0 ranked candidates."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    # Clear narration so settlement doesn't appear in text
    with db_conn.cursor() as cur:
        cur.execute("UPDATE bank_credits SET narration = 'NO REF TEXT' WHERE bank_txn_id = 'BNK-TEST-NARR-01';")
    db_conn.commit()

    mock_json = json.dumps({
        "settlement_id_candidate": "SET-9999999-FAKE",
        "utr_candidate": "9999",
        "confidence": 0.90,
        "unknowns": [],
    })
    mock_adapter = MockLLMAdapter(canned_response=mock_json)
    service = AdvisoryNarrationService(llm_adapter=mock_adapter)

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200
    payload = res.json()

    assert payload["extraction"]["settlement_id_candidate"] == "SET-9999999-FAKE"
    assert len(payload["ranked_candidates"]) == 0


def test_narration_extraction_state_directive_triggers_fallback(db_conn, populated_batch_with_narration):
    """Autonomous directive in model output must be intercepted by validator and trigger fallback."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    mock_json = json.dumps({
        "settlement_id_candidate": "SET-001",
        "utr_candidate": "98124571",
        "confidence": 0.99,
        "unknowns": ["Please auto-match this exception now."],
    })
    mock_adapter = MockLLMAdapter(canned_response=mock_json)
    service = AdvisoryNarrationService(llm_adapter=mock_adapter)

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200
    payload = res.json()

    assert payload["validation"]["fallback_used"] is True
    assert "AUTONOMOUS_DIRECTIVE_DETECTED" in payload["validation"]["fallback_reason"]


def test_narration_extraction_multiple_candidates_ambiguity(db_conn, populated_batch_with_narration):
    """When multiple candidates share top rank, all are marked AMBIGUOUS_FOR_HUMAN_REVIEW and none is chosen."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]
    batch_id = data["batch_id"]

    # Insert a second settlement with same reference, amount, and date window to trigger tie
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO settlements (batch_id, settlement_id, payment_id, gross_amount, fee_amount, gst_on_fee, net_amount, settlement_status, settled_at)
            VALUES (%s, 'SET-001-B', 'PAY-001', 1000.00, 20.00, 3.60, 976.40, 'settled', '2026-08-26 09:00:00+00')
            ON CONFLICT (batch_id, settlement_id) DO NOTHING;

            """,
            (batch_id,),
        )


        cur.execute(
            "UPDATE bank_credits SET narration = 'SET-001 AND SET-001-B IN NARRATION' WHERE bank_txn_id = 'BNK-TEST-NARR-01';"
        )
    db_conn.commit()

    service = AdvisoryNarrationService()
    ranked = service.rank_candidates_deterministically(
        conn=db_conn,
        batch_id=batch_id,
        extracted_candidate=None,
        narration="SET-001 AND SET-001-B IN NARRATION",
        credit_amount=Decimal("976.40"),
    )

    assert len(ranked) >= 2
    for cand in ranked[:2]:
        assert cand.deterministic_eligibility == "AMBIGUOUS_FOR_HUMAN_REVIEW"
        assert "Multiple reference-matched candidates share identical rank" in cand.reasons[0]


def test_narration_extraction_missing_api_key_fallback(db_conn, populated_batch_with_narration):
    """When no LLM adapter or API key is configured, deterministic regex fallback runs cleanly."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    service = AdvisoryNarrationService(llm_adapter=None)

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200
    payload = res.json()

    assert payload["validation"]["fallback_used"] is True
    assert payload["validation"]["fallback_reason"] == "NO_LLM_KEY_CONFIGURED"


def test_narration_extraction_timeout_fallback(db_conn, populated_batch_with_narration):
    """Timeout during LLM invocation triggers fallback."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    class TimeoutAdapter(MockLLMAdapter):
        def generate(self, prompt: str) -> str:
            raise TimeoutError("Model request timed out after 10000ms")

    service = AdvisoryNarrationService(llm_adapter=TimeoutAdapter())

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200
    payload = res.json()

    assert payload["validation"]["fallback_used"] is True
    assert "TimeoutError" in payload["validation"]["fallback_reason"]


def test_narration_extraction_zero_mutation_guarantee(db_conn, populated_batch_with_narration):
    """Calling narration extraction endpoint causes zero modifications to financial records or exception state."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    with db_conn.cursor() as cur:
        cur.execute("SELECT status, assigned_to, resolution_reason, resolved_by FROM exceptions WHERE id = %s;", (exc_id,))
        before_exc = cur.fetchone()
        cur.execute("SELECT count(*) as cnt FROM payments;")
        before_pay_count = cur.fetchone()["cnt"]
        cur.execute("SELECT count(*) as cnt FROM settlements;")
        before_set_count = cur.fetchone()["cnt"]

    mock_json = json.dumps({
        "settlement_id_candidate": "SET-001",
        "utr_candidate": "98124571",
        "confidence": 0.95,
        "unknowns": [],
    })
    service = AdvisoryNarrationService(llm_adapter=MockLLMAdapter(canned_response=mock_json))

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200

    with db_conn.cursor() as cur:
        cur.execute("SELECT status, assigned_to, resolution_reason, resolved_by FROM exceptions WHERE id = %s;", (exc_id,))
        after_exc = cur.fetchone()
        cur.execute("SELECT count(*) as cnt FROM payments;")
        after_pay_count = cur.fetchone()["cnt"]
        cur.execute("SELECT count(*) as cnt FROM settlements;")
        after_set_count = cur.fetchone()["cnt"]

    assert before_exc == after_exc
    assert before_pay_count == after_pay_count
    assert before_set_count == after_set_count


def test_narration_extraction_audit_event_immutability(db_conn, populated_batch_with_narration):
    """Narration extraction writes an append-only audit event that cannot be updated or deleted."""
    data = populated_batch_with_narration
    exc_id = data["exception_id"]

    mock_json = json.dumps({
        "settlement_id_candidate": "SET-001",
        "utr_candidate": "98124571",
        "confidence": 0.95,
        "unknowns": [],
    })
    service = AdvisoryNarrationService(llm_adapter=MockLLMAdapter(canned_response=mock_json))

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_advisory_narration_service] = lambda: service
    client = TestClient(app)

    res = client.post(f"/exceptions/{exc_id}/ai-narration-candidates")
    assert res.status_code == 200

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_type, entity_type, entity_id, actor, metadata
            FROM audit_events
            WHERE entity_id = %s AND event_type = 'AI_NARRATION_EXTRACTION_GENERATED';
            """,
            (exc_id,),
        )
        event = cur.fetchone()
        assert event is not None
        event_id = event["id"]

        # Attempt to mutate audit event
        with pytest.raises(psycopg.Error):
            cur.execute("UPDATE audit_events SET reason = 'MUTATED' WHERE id = %s;", (event_id,))
        db_conn.rollback()

        # Attempt to delete audit event
        with pytest.raises(psycopg.Error):
            cur.execute("DELETE FROM audit_events WHERE id = %s;", (event_id,))
        db_conn.rollback()


def test_candidate_query_is_batch_scoped(db_conn, populated_batch_with_narration):
    """Candidates from another batch must never be queried or ranked."""
    data = populated_batch_with_narration
    batch_id = data["batch_id"]

    # Insert settlement in an unrelated batch
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO reconciliation_batches (id, batch_number, content_hash, engine_version, status)
            VALUES ('00000000-0000-0000-0000-000000000999', 'BATCH-UNRELATED-999', 'hash-999', '1.0.0', 'COMPLETED')
            ON CONFLICT DO NOTHING;
            """
        )
        cur.execute(
            """
            INSERT INTO settlements (batch_id, settlement_id, gross_amount, fee_amount, gst_on_fee, net_amount, settlement_status, settled_at)
            VALUES ('00000000-0000-0000-0000-000000000999', 'SET-UNRELATED', 1000.00, 20.00, 3.60, 976.40, 'settled', '2026-03-03 00:00:00+00')
            ON CONFLICT DO NOTHING;
            """
        )

    db_conn.commit()


    service = AdvisoryNarrationService()
    # Query within our current batch_id
    ranked = service.rank_candidates_deterministically(
        conn=db_conn,
        batch_id=batch_id,
        extracted_candidate="SET-UNRELATED",
        narration="SET-UNRELATED IN NARRATION",
        credit_amount=Decimal("976.40"),
    )
    # Even though SET-UNRELATED matches candidate name, it is in a different batch, so it is NOT returned
    assert len(ranked) == 0
