"""Strict schema and grounding validator for AI-generated explanations."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from backend.app.ai.schemas import AIExplanationResponse

# Autonomous / state-changing directives to block (case-insensitive regex patterns)
AUTONOMOUS_DIRECTIVE_PATTERNS = [
    r"\bauto[- ]?match\b",
    r"\bmark\s+(?:as\s+)?(?:resolved|dismissed)\b",
    r"\bdismiss\s+(?:this\s+)?exception\b",
    r"\bresolve\s+(?:this\s+)?exception\b",
    r"\bupdate\s+(?:the\s+)?status\s+to\b",
    r"\bset\s+status\s+to\b",
    r"\bautomatically\s+(?:resolve|dismiss|match)\b",
    r"\bchange\s+status\s+to\b",
    r"\bclose\s+(?:this\s+)?exception\b",
]

# Patterns where unobserved causes are asserted as factual statements in summary or evidence claims
UNOBSERVED_CAUSE_FACT_PATTERNS = [
    r"\b(?:caused by|due to|result of|because of)\s+(?:an?\s+)?(?:unrecorded|unobserved|hidden|additional|internal)?\s*(?:bank fee|bank charge|split settlement|withholding|chargeback|adjustment)\b",
    r"\bbank\s+(?:deducted|charged|retained)\s+(?:a|an)?\s*(?:fee|charge|amount)\b",
]


class GroundingValidationError(Exception):
    """Raised when an AI explanation output fails grounding or schema validation."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def validate_grounding(
    raw_response: Dict[str, Any],
    allowed_source_ids: Set[str],
    server_calculations: Dict[str, Optional[str]],
) -> Tuple[bool, Optional[str]]:
    """Validate AI response against schema, citations, exact monetary amounts, and safety constraints.

    Returns:
        (is_valid, failure_reason)
    """
    # 1. Autonomous / state-changing directive checks
    summary_text = raw_response.get("summary", "")
    suggested_step = raw_response.get("suggested_next_step", "")
    full_text_to_check = f"{summary_text} {suggested_step}"

    for pattern in AUTONOMOUS_DIRECTIVE_PATTERNS:
        if re.search(pattern, full_text_to_check, re.IGNORECASE):
            return False, f"AUTONOMOUS_DIRECTIVE_DETECTED: text matched pattern '{pattern}'"

    # 2. Check evidence source IDs
    evidence_items = raw_response.get("evidence", [])
    for item in evidence_items:
        src_id = item.get("source_id")
        if not src_id or src_id not in allowed_source_ids:
            return False, f"UNGROUNDED_SOURCE_ID: cited ID '{src_id}' is not in retrieved server evidence set"

        # Check evidence claim for unobserved causes stated as fact
        claim_text = item.get("claim", "")
        for pattern in UNOBSERVED_CAUSE_FACT_PATTERNS:
            if re.search(pattern, claim_text, re.IGNORECASE):
                return False, f"UNOBSERVED_CAUSE_ASSERTED_AS_FACT: claim asserted unevidenced cause '{pattern}'"

    # Check summary for unobserved causes stated as fact
    for pattern in UNOBSERVED_CAUSE_FACT_PATTERNS:
        if re.search(pattern, summary_text, re.IGNORECASE):
            return False, f"UNOBSERVED_CAUSE_ASSERTED_AS_FACT: summary asserted unevidenced cause '{pattern}'"

    # 3. Check calculation summary exactness
    calc_summary = raw_response.get("calculation_summary", {})
    for key, expected_val in server_calculations.items():
        if key in calc_summary and calc_summary[key] is not None:
            actual_val = str(calc_summary[key]).strip()
            if expected_val is not None:
                if actual_val != expected_val.strip():
                    return False, f"AMOUNT_MISMATCH: {key} actual '{actual_val}' != server-side expected '{expected_val}'"
            elif actual_val:
                # Value was provided when server had null/no calculation
                return False, f"AMOUNT_FABRICATION: {key} actual '{actual_val}' but server has no calculated value"

    # 4. Check confidence bounds
    confidence = raw_response.get("confidence")
    if confidence is None or not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        return False, f"INVALID_CONFIDENCE: confidence '{confidence}' must be a float between 0.0 and 1.0"

    # 5. Check advisory_only is True
    if raw_response.get("advisory_only") is not True:
        return False, "ADVISORY_ONLY_VIOLATION: advisory_only must be strictly True"

    return True, None
