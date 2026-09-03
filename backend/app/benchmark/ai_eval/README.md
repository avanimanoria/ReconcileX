# ReconcileX AI Exception Explainer Evaluation Suite

This evaluation suite measures the grounding quality, safety defenses, and residual risk of the **V1 Grounded Exception Explainer** AI copilot.

---

## 1. How to Run the Evaluation

From the repository root:

```bash
python -m backend.app.benchmark.ai_eval.eval_runner
```

To run as part of automated pytest testing:
```bash
pytest backend/app/tests/test_ai_explainer.py -v
```

---

## 2. Tracked Metrics

1. **Clean Grounded Pass Rate (`clean_grounded_pass_rate`)**:
   Percentage of valid, accurately grounded candidate responses accepted without false-positive fallbacks.
2. **Adversarial Defense Catch Rate (`adversarial_block_rate`)**:
   Percentage of adversarial anomalies (hallucinated IDs, altered money amounts, autonomous directives, and unevidenced causes asserted as fact) successfully detected and blocked by the validator.
3. **Unsupported-Claim Escape Rate (`unsupported_claim_escape_rate`)**:
   Residual risk metric tracking whether any ungrounded claim bypassed the validation layer. Target: **0.00%**.
4. **Validator Fallback Trigger Rate (`fallback_rate`)**:
   Percentage of evaluations that safely routed to the deterministic fallback engine.

---

## 3. Strict Boundary & Non-Negotiable Financial Safety

- **Financial Matching is NEVER Evaluated via LLM**:
  Financial auto-match accuracy in ReconcileX is strictly deterministic and governed by `ImprovedMatcher` with ₹0.01 money tolerance and zero tolerance for false matches. LLM metrics do **not** measure or affect financial matching precision/recall.
- **Residual Risk Awareness**:
  The validation layer reliably intercepts structural schema flaws, ungrounded IDs, modified monetary values, autonomous directives, and unevidenced causes stated as facts. Residual risk in natural language prose is tracked through this evaluation suite.
