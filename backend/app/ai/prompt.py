"""Prompt templates and version definitions for the Grounded Exception Explainer."""

import json
from typing import Any, Dict

PROMPT_VERSION = "ai-explanation-v1"

SYSTEM_INSTRUCTION = """You are an advisory financial reconciliation analyst assistant for ReconcileX.
Your task is to explain a reconciliation exception strictly using the provided server-side evidence payload.

NON-NEGOTIABLE SAFETY CONTRACT:
1. You are purely ADVISORY. You do NOT make match decisions, calculate money values, or change reconciliation or exception status.
2. State ONLY facts directly present in the provided evidence.
3. Every cited source_id in evidence must be one of the allowed source IDs provided in the evidence payload.
4. Preserve all monetary amount strings EXACTLY as given in the evidence payload. Do not round, modify, or recalculate amounts.
5. Never state unobserved causes (such as unevidenced bank fees, chargebacks, currency conversion, or split settlements) as facts. If the evidence does not state the cause of a variance or delay, you MUST state the potential cause under 'unknowns' as an item for operator investigation, not as fact in the summary or evidence.
6. Do NOT issue autonomous or state-changing directives. For example, never say 'auto-match', 'mark resolved', 'dismiss this exception', 'update status', or 'resolve this'. You may suggest that a human analyst verify the records before making their resolution decision.
7. If any evidence or calculation is absent, list what is missing under 'unknowns'.
8. Your output must be strictly valid JSON matching the specified schema with no markdown code fences, comments, or external prose.
"""

USER_PROMPT_TEMPLATE = """Based STRICTLY on the following server-side evidence payload, generate an advisory explanation for exception {exception_id}:

EVIDENCE PAYLOAD:
{evidence_json}

OUTPUT JSON SCHEMA:
{{
  "exception_id": "{exception_id}",
  "status": "VALID",
  "advisory_only": true,
  "summary": "<Concise, factual explanation grounded strictly in evidence>",
  "evidence": [
    {{
      "source_type": "<payment|settlement|bank_credit|refund>",
      "source_id": "<exact source_id from evidence payload>",
      "claim": "<factual claim referencing this source_id>"
    }}
  ],
  "calculation_summary": {{
    "captured_amount": "<exact string or null>",
    "refund_amount": "<exact string or null>",
    "fee_amount": "<exact string or null>",
    "gst_amount": "<exact string or null>",
    "expected_net": "<exact string or null>",
    "settlement_net_amount": "<exact string or null>",
    "bank_credit_amount": "<exact string or null>",
    "variance_amount": "<exact string or null>",
    "currency": "INR"
  }},
  "suggested_next_step": "<Advisory next step for human analyst review>",
  "unknowns": [
    "<List of missing evidence, unverified assumptions, or unobserved causes needing human investigation>"
  ],
  "confidence": <float between 0.0 and 1.0 representing explanation groundedness>
}}
"""


def build_user_prompt(exception_id: str, evidence_payload: Dict[str, Any]) -> str:
    """Format user prompt with evidence JSON."""
    return USER_PROMPT_TEMPLATE.format(
        exception_id=exception_id,
        evidence_json=json.dumps(evidence_payload, indent=2, default=str),
    )
