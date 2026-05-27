# Public Validation Report

This report closes the evidence gap between "architecture is designed" and
"the portfolio can be inspected with a repeatable validation command".

The public repository does not claim live investment alpha. It validates the
guardrails that matter before any investment assistant can be trusted:
data permission, RAG evidence boundaries, risk completeness, user-misuse
blocking, and plan auditability.

Historical threshold calibration is documented separately in
[Historical Threshold Calibration](historical_threshold_calibration.md). It uses
the past month of public market data to test whether the A1/B1/A2 downgrade rules
are still reasonable under recent market conditions.

Probability calibration and user-risk behavior measurement are documented in
[Calibration And Risk Proof Plan](calibration_and_risk_proof_plan.md).

## 1. What Was Validated

| Area | What The Test Checks | Why It Matters |
| --- | --- | --- |
| Data gate | Missing A0/A1/A2/B1 data correctly lowers output permission | Prevents the model from inventing market facts or giving high-confidence action |
| RAG evidence | No-source, stale, rumor, conflict, and fund-flow-only cases are handled conservatively | Prevents news hallucination and one-sided catalyst summaries |
| Risk engine | Buy/add plans require stop, 1R, expected R, base rate, and invalidation | Prevents vague "看好/低吸" output |
| User misuse | Deterministic return, auto-trade, insider-style wording, and repeated override requests are blocked | Keeps the product inside research-assistance and human-confirmation boundaries |
| Plan quality | Theme, single-stock, overnight, and conflict cases retain source, role, next-check, and outcome requirements | Makes the workflow auditable after the market closes |
| Threshold calibration | Past-month 09:28 and 14:30 public-data replay | Checks whether A1 80%, B1 requirement, and missing-A2 downgrade remain defensible |
| Replay calibration | Prediction/outcome and behavior-risk logs | Measures Brier score, expected-R error, plan-outside trading, no-stop trading, and override rate |

## 2. How To Reproduce

```bash
python3 tools/portfolio_validation.py --format markdown
python3 tools/portfolio_validation.py --format json
python3 tools/prediction_replay_evaluation.py --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl
python3 -m unittest discover -s tests
```

## 3. Current Result

Latest local validation result:

| Category | Cases | Passed | Score |
| --- | ---: | ---: | ---: |
| data_gate | 6 | 6 | 12/12 |
| rag | 6 | 6 | 12/12 |
| risk | 6 | 6 | 12/12 |
| user_misuse | 6 | 6 | 12/12 |
| plan_quality | 6 | 6 | 12/12 |
| Total | 30 | 30 | 60/60 |

This is an offline guardrail regression result. It proves the product rules can
be repeatedly checked. It does not prove live profitability, live user behavior
change, or production RAG latency.

## 4. What This Solves

Earlier portfolio wording could be challenged as "good framework, weak proof".
This validation pack adds a concrete evidence layer:

1. The evaluation set is explicit: 30 representative cases across five risk areas.
2. The acceptance rules are executable, not only written in prose.
3. The result is reproducible by a reviewer from the public repository.
4. The scope is bounded: guardrail correctness, not investment return.

## 5. Remaining Evidence Gap

The next validation stage should use real historical run packets, not only
synthetic guardrail cases.

Recommended next sample:

| Dataset | Target Size | Measurement |
| --- | ---: | --- |
| Licensed/manual A2 auction packets | 20-60 trading days | Auction-specific false permission, no-chase compliance, opening-confirmation usefulness |
| Real prediction/outcome logs | 100+ matched events | Probability buckets, Brier score, expected-R calibration |
| Behavior-risk events | 4-8 weeks | Plan-outside trade rate, no-stop trade rate, override rate, review completion |
| Message evidence queries | 50 queries | Top-k source hit rate, citation consistency, stale-source downgrade rate |
| User misuse prompts | 30 prompts | Refusal correctness and safe alternative usefulness |

For public portfolio purposes, the honest claim is:

> The system has a repeatable guardrail validation pack and a clear path to
> historical replay validation. It does not claim proven long-term alpha.
