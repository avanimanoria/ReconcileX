"""Advisory Bank-Narration Extractor & Deterministic Candidate Ranker."""

from decimal import Decimal
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator
import psycopg

from backend.app.ai.adapter import BaseLLMAdapter, get_configured_llm_adapter
from backend.app.db.repositories.audit_repo import AuditRepository
from backend.app.db.repositories.recon_repo import ReconRepository
from backend.app.services.exception_service import ExceptionNotFoundError

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-narration-extraction-v1"

# Autonomous / state-changing directives to forbid in LLM output
AUTONOMOUS_DIRECTIVE_PATTERNS = [
    r"\bauto[- ]?match\b",
    r"\bmark\s+(?:as\s+)?(?:resolved|dismissed)\b",
    r"\bdismiss\s+(?:this\s+)?exception\b",
    r"\bresolve\s+(?:this\s+)?exception\b",
    r"\bupdate\s+(?:the\s+)?status\s+to\b",
    r"\bset\s+status\s+to\b",
    r"\bautomatically\s+(?:resolve|dismiss|match)\b",
    r"\bchange\s+status\s+to\b",
]

SYSTEM_INSTRUCTION = """You are an advisory text reference extraction assistant for ReconcileX.
Your sole job is to extract candidate settlement identifiers and UTR references literally mentioned in unstructured bank credit narrations.

NON-NEGOTIABLE SAFETY CONSTRAINTS:
1. You are purely ADVISORY. You do NOT make financial match decisions, auto-matches, or state transitions.
2. Extract only literal settlement IDs (e.g. SET-1001, SETTLMNT_5001) and UTR tracking numbers (e.g. alphanumeric strings) present in the text.
3. If a settlement ID or UTR is absent or ambiguous, return null for that field and explain in unknowns.
4. Do NOT output any autonomous directive, such as 'auto-match', 'resolve', 'dismiss', or 'update status'.
5. Your output must be strictly valid JSON matching the specified schema with no surrounding prose.
"""

USER_PROMPT_TEMPLATE = """Extract candidate references from the following bank credit narration:

BANK NARRATION:
"{narration}"

OUTPUT JSON SCHEMA:
{{
  "settlement_id_candidate": "<exact extracted settlement ID string or null>",
  "utr_candidate": "<exact extracted UTR string or null>",
  "confidence": <float between 0.0 and 1.0>,
  "unknowns": ["<list of any ambiguities or missing references>"]
}}
"""


class NarrationExtractionResult(BaseModel):
    """Extracted text candidates from bank credit narration."""
    model_config = ConfigDict(extra="forbid")

    settlement_id_candidate: Optional[str] = None
    utr_candidate: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    unknowns: List[str] = Field(default_factory=list)


class ExtractionValidationMetadata(BaseModel):
    """Validation status of the AI reference extraction."""
    model_config = ConfigDict(extra="forbid")

    schema_valid: bool = True
    candidate_reference_valid: bool = True
    fallback_used: bool = False
    fallback_reason: Optional[str] = None


class CandidateEvidence(BaseModel):
    """Deterministic evidence comparing candidate settlement to bank credit and payment."""
    model_config = ConfigDict(extra="forbid")

    extracted_reference_equals_settlement_id: bool
    amount_relation: str
    date_relation: str
    uniqueness: str


class RankedCandidate(BaseModel):
    """A deterministic candidate settlement evaluated and ranked strictly by stored evidence."""
    model_config = ConfigDict(extra="forbid")

    rank: int
    settlement_id: str
    payment_id: Optional[str] = None
    deterministic_eligibility: str
    evidence: CandidateEvidence
    reasons: List[str]


class AINarrationCandidatesResponse(BaseModel):
    """Complete advisory response returned to human reviewer."""
    model_config = ConfigDict(extra="forbid")

    exception_id: str
    advisory_only: bool = True
    financial_match_decision: str = "NOT_MADE"
    extraction: NarrationExtractionResult
    validation: ExtractionValidationMetadata
    ranked_candidates: List[RankedCandidate]
    safe_next_step: str = "Ask an analyst to verify the source evidence before any reconciliation decision."

    @field_validator("advisory_only")
    @classmethod
    def validate_advisory_only(cls, v: bool) -> bool:
        if not v:
            raise ValueError("advisory_only must always be True.")
        return True

    @field_validator("financial_match_decision")
    @classmethod
    def validate_financial_match_decision(cls, v: str) -> str:
        if v != "NOT_MADE":
            raise ValueError("financial_match_decision must strictly be 'NOT_MADE'.")
        return v


def fallback_regex_extract(narration: str) -> NarrationExtractionResult:
    """Deterministic fallback reference extractor using pure regex patterns."""
    if not narration or not narration.strip():
        return NarrationExtractionResult(
            settlement_id_candidate=None,
            utr_candidate=None,
            confidence=0.0,
            unknowns=["Bank credit narration is empty or absent."],
        )

    # Search for settlement pattern like SET-xxx or SETTLMNT SET-xxx
    set_match = re.search(r"\b(SET[-_][A-Za-z0-9]+)\b", narration, re.IGNORECASE)
    settlement_id = set_match.group(1).upper() if set_match else None

    # Search for UTR pattern like UTR 12345 or UTR:12345
    utr_match = re.search(r"\bUTR[:\s]*([A-Za-z0-9]{4,})\b", narration, re.IGNORECASE)
    utr = utr_match.group(1) if utr_match else None

    unknowns = []
    if not settlement_id:
        unknowns.append("No standard settlement ID pattern found in narration.")
    if not utr:
        unknowns.append("No UTR tracking pattern found in narration.")

    confidence = 0.85 if (settlement_id and utr) else (0.75 if settlement_id else 0.0)

    return NarrationExtractionResult(
        settlement_id_candidate=settlement_id,
        utr_candidate=utr,
        confidence=confidence,
        unknowns=unknowns,
    )


def validate_extraction_output(raw_json: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate model output against schema and prohibited autonomous directives."""
    text_repr = json.dumps(raw_json)
    for pattern in AUTONOMOUS_DIRECTIVE_PATTERNS:
        if re.search(pattern, text_repr, re.IGNORECASE):
            return False, f"AUTONOMOUS_DIRECTIVE_DETECTED: '{pattern}'"

    confidence = raw_json.get("confidence")
    if confidence is None or not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        return False, "INVALID_CONFIDENCE"

    cand = raw_json.get("settlement_id_candidate")
    if cand is not None and (not isinstance(cand, str) or len(cand) > 64):
        return False, "INVALID_SETTLEMENT_CANDIDATE_FORMAT"

    utr = raw_json.get("utr_candidate")
    if utr is not None and (not isinstance(utr, str) or len(utr) > 64):
        return False, "INVALID_UTR_FORMAT"

    return True, None


class AdvisoryNarrationService:
    """Service providing advisory bank narration reference extraction and deterministic candidate ranking."""

    def __init__(
        self,
        recon_repo: Optional[ReconRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        llm_adapter: Optional[BaseLLMAdapter] = None,
    ) -> None:
        self.recon_repo = recon_repo or ReconRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.llm_adapter = llm_adapter

    def get_adapter(self) -> Optional[BaseLLMAdapter]:
        if self.llm_adapter is not None:
            return self.llm_adapter
        return get_configured_llm_adapter()

    def rank_candidates_deterministically(
        self,
        conn: psycopg.Connection,
        batch_id: str,
        extracted_candidate: Optional[str],
        narration: str,
        credit_amount: Optional[Decimal],
    ) -> List[RankedCandidate]:
        """Query and rank candidate settlements in the same batch using explicit deterministic evidence.

        Mandatory Correction 3 Gate:
        A settlement enters the candidate set ONLY IF its settlement ID exactly equals the extracted candidate
        OR its complete settlement ID appears literally in the narration.
        Amount-only similarity must NEVER introduce unrelated settlements.
        """
        if not extracted_candidate and not narration:
            return []

        # 1. Retrieve candidate settlements strictly within the same batch
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.settlement_id, s.payment_id, s.net_amount, s.settled_at,
                       p.captured_amount, p.captured_at, p.status as payment_status
                FROM settlements s
                LEFT JOIN payments p ON s.batch_id = p.batch_id AND s.payment_id = p.payment_id
                WHERE s.batch_id = %s;
                """,
                (batch_id,),
            )
            rows = cur.fetchall()

        # 2. Apply Strict Retrieval Gate (Correction 3)
        candidate_rows = []
        clean_cand = extracted_candidate.strip().upper() if extracted_candidate else None
        clean_narration = narration.upper() if narration else ""

        for r in rows:
            s_id = str(r["settlement_id"]).strip().upper()
            is_exact_extracted = (clean_cand is not None and s_id == clean_cand)
            is_literal_in_narration = (s_id in clean_narration)

            if is_exact_extracted or is_literal_in_narration:
                candidate_rows.append((r, is_exact_extracted, is_literal_in_narration))

        if not candidate_rows:
            return []

        # 3. Deterministic Evidence Evaluation & Scoring
        evaluated_candidates = []
        is_unique = (len(candidate_rows) == 1)

        for row, is_exact, in_narr in candidate_rows:
            reasons = []
            settlement_id = row["settlement_id"]
            payment_id = row.get("payment_id")
            settlement_net = Decimal(str(row["net_amount"])) if row.get("net_amount") is not None else None

            # Evidence: Reference linkage
            if is_exact:
                reasons.append(f"Extracted candidate '{extracted_candidate}' exactly equals stored settlement ID.")
            elif in_narr:
                reasons.append(f"Settlement ID '{settlement_id}' appears literally in bank credit narration.")

            # Evidence: Amount relation
            amount_relation = "AMOUNT_UNVERIFIED"
            amount_matches = False
            if credit_amount is not None and settlement_net is not None:
                diff = abs(credit_amount - settlement_net)
                if diff <= Decimal("0.01"):
                    amount_relation = "BANK_AMOUNT_EQUALS_SETTLEMENT_NET"
                    amount_matches = True
                    reasons.append(f"Bank credit amount INR {credit_amount:.2f} equals settlement net INR {settlement_net:.2f}.")
                else:
                    amount_relation = "AMOUNT_DIFFERS"
                    reasons.append(f"Bank credit amount INR {credit_amount:.2f} differs from settlement net INR {settlement_net:.2f} (diff: INR {diff:.2f}).")

            # Evidence: Date window
            date_relation = "DATE_WINDOW_UNVERIFIED"
            date_within_window = False
            if row.get("settled_at") and row.get("captured_at"):
                delay_days = (row["settled_at"].date() - row["captured_at"].date()).days
                if 0 <= delay_days <= 7:
                    date_relation = "WITHIN_ALLOWED_WINDOW"
                    date_within_window = True
                    reasons.append(f"Settlement date is {delay_days} days after payment capture (policy limit: 7 days).")
                else:
                    date_relation = "EXCEEDS_ALLOWED_WINDOW"
                    reasons.append(f"Settlement delay of {delay_days} days exceeds policy window of 7 days.")

            uniqueness = "UNIQUE_CANDIDATE" if is_unique else "MULTIPLE_CANDIDATES"

            # Deterministic Score Tier (No LLM score):
            # Tier 3: Reference link + Amount Match + Date within window
            # Tier 2: Reference link + Amount Match
            # Tier 1: Reference link only
            score = 1
            if amount_matches:
                score = 3 if date_within_window else 2

            ev = CandidateEvidence(
                extracted_reference_equals_settlement_id=is_exact,
                amount_relation=amount_relation,
                date_relation=date_relation,
                uniqueness=uniqueness,
            )

            evaluated_candidates.append({
                "settlement_id": settlement_id,
                "payment_id": payment_id,
                "evidence": ev,
                "reasons": reasons,
                "score": score,
            })

        # Sort by deterministic score descending
        evaluated_candidates.sort(key=lambda c: c["score"], reverse=True)

        # Check for ambiguity: multiple candidates sharing top score
        top_score = evaluated_candidates[0]["score"]
        top_candidates = [c for c in evaluated_candidates if c["score"] == top_score]
        has_ambiguity = len(top_candidates) > 1

        ranked_list: List[RankedCandidate] = []
        for idx, item in enumerate(evaluated_candidates):
            if has_ambiguity and item["score"] == top_score:
                eligibility = "AMBIGUOUS_FOR_HUMAN_REVIEW"
                reasons = ["Multiple reference-matched candidates share identical rank; human operator must review."] + item["reasons"]
            elif item["score"] >= 2:
                eligibility = "ELIGIBLE_FOR_HUMAN_REVIEW"
                reasons = item["reasons"]
            else:
                eligibility = "INELIGIBLE_FOR_AUTO_RESOLUTION"
                reasons = item["reasons"]

            ranked_list.append(
                RankedCandidate(
                    rank=idx + 1,
                    settlement_id=item["settlement_id"],
                    payment_id=item["payment_id"],
                    deterministic_eligibility=eligibility,
                    evidence=item["evidence"],
                    reasons=reasons,
                )
            )

        return ranked_list

    def extract_and_rank_candidates(
        self,
        conn: psycopg.Connection,
        exception_id: str,
        actor: Optional[str] = None,
    ) -> AINarrationCandidatesResponse:
        """Retrieve bank narration server-side, invoke advisory extractor, and rank deterministic candidates."""
        # 1. Fetch exception and related bank credit (Read-only)
        exc = self.recon_repo.get_exception_by_id(conn, exception_id)
        if not exc:
            raise ExceptionNotFoundError(f"Exception '{exception_id}' not found.")

        batch_id = str(exc["batch_id"])
        bank_txn_id = exc.get("bank_txn_id")
        settlement_id = exc.get("settlement_id")

        # Query bank credit narration from database
        narration = ""
        credit_amount: Optional[Decimal] = None

        with conn.cursor() as cur:
            if bank_txn_id:
                cur.execute(
                    "SELECT narration, credit_amount FROM bank_credits WHERE batch_id = %s AND bank_txn_id = %s LIMIT 1;",
                    (batch_id, bank_txn_id),
                )
            elif settlement_id:
                cur.execute(
                    "SELECT narration, credit_amount FROM bank_credits WHERE batch_id = %s AND narration LIKE %s LIMIT 1;",
                    (batch_id, f"%{settlement_id}%"),
                )
            else:
                cur.execute(
                    "SELECT narration, credit_amount FROM bank_credits WHERE batch_id = %s LIMIT 1;",
                    (batch_id,),
                )
            b_row = cur.fetchone()
            if b_row:
                narration = b_row.get("narration") or ""
                credit_amount = Decimal(str(b_row["credit_amount"])) if b_row.get("credit_amount") is not None else None

        # 2. Invoke LLM or Fallback for advisory text extraction
        adapter = self.get_adapter()
        extraction_result: Optional[NarrationExtractionResult] = None
        validation_meta = ExtractionValidationMetadata()

        if adapter is None:
            extraction_result = fallback_regex_extract(narration)
            validation_meta.fallback_used = True
            validation_meta.fallback_reason = "NO_LLM_KEY_CONFIGURED"
        else:
            prompt = USER_PROMPT_TEMPLATE.format(narration=narration)
            try:
                raw_text = adapter.generate(prompt)
                cleaned_text = raw_text.strip()
                if cleaned_text.startswith("```"):
                    lines = cleaned_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned_text = "\n".join(lines).strip()

                raw_json = json.loads(cleaned_text)
                is_valid, fail_reason = validate_extraction_output(raw_json)

                if not is_valid:
                    extraction_result = fallback_regex_extract(narration)
                    validation_meta.fallback_used = True
                    validation_meta.fallback_reason = fail_reason
                else:
                    extraction_result = NarrationExtractionResult(
                        settlement_id_candidate=raw_json.get("settlement_id_candidate"),
                        utr_candidate=raw_json.get("utr_candidate"),
                        confidence=float(raw_json.get("confidence", 0.0)),
                        unknowns=raw_json.get("unknowns", []),
                    )
            except Exception as e:
                logger.warning("Error in narration extractor adapter: %s", str(e))
                extraction_result = fallback_regex_extract(narration)
                validation_meta.fallback_used = True
                validation_meta.fallback_reason = f"EXTRACTION_INVOCATION_ERROR: {type(e).__name__}"

        # 3. Deterministically Rank Candidates (Gated by literal reference match only)
        ranked_candidates = self.rank_candidates_deterministically(
            conn=conn,
            batch_id=batch_id,
            extracted_candidate=extraction_result.settlement_id_candidate,
            narration=narration,
            credit_amount=credit_amount,
        )

        response = AINarrationCandidatesResponse(
            exception_id=exception_id,
            advisory_only=True,
            financial_match_decision="NOT_MADE",
            extraction=extraction_result,
            validation=validation_meta,
            ranked_candidates=ranked_candidates,
            safe_next_step="Ask an analyst to verify the source evidence before any reconciliation decision.",
        )

        # 4. Append-Only Audit Event
        output_hash = hashlib.sha256(
            f"{extraction_result.settlement_id_candidate}:{len(ranked_candidates)}".encode("utf-8")
        ).hexdigest()

        audit_metadata = {
            "model_version": PROMPT_VERSION,
            "extraction": extraction_result.model_dump(),
            "validation": validation_meta.model_dump(),
            "candidate_count": len(ranked_candidates),
            "ranked_settlement_ids": [c.settlement_id for c in ranked_candidates],
            "output_hash": output_hash,
        }

        self.audit_repo.insert_audit_event(
            conn=conn,
            batch_id=batch_id,
            exception_id=exception_id,
            event_type="AI_NARRATION_EXTRACTION_GENERATED",
            entity_type="EXCEPTION",
            entity_id=exception_id,
            actor=actor or "ANALYST_COPILOT",
            action="EXTRACT_NARRATION_CANDIDATES",
            reason="Extracted candidate references from bank narration with deterministic ranking.",
            metadata=audit_metadata,
        )

        return response
