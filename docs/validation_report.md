# Public Validation Report

This report closes the evidence gap between "architecture is designed" and
"the portfolio can be inspected with a repeatable validation command".

The public repository does not claim live return capability. It validates the
guardrails that matter before any investment assistant can be trusted:
data permission, RAG evidence boundaries, risk completeness, user-misuse
blocking, user-supplied target handling, opening-confirmation discipline, holding-review discipline, and plan
auditability.

Historical threshold calibration is documented separately in
[Historical Threshold Calibration](historical_threshold_calibration.md). It uses
the past month of public market data to test whether the A1/B1/A2 downgrade rules
are still reasonable under recent market conditions.

Historical policy backtest is documented in
[Historical Policy Backtest](historical_policy_backtest.md). It uses a larger
public daily-bar sample to pressure-test whether the missing-A2 no-chase rule
reduces historically observable bad opening permissions.

Rolling three-month reliability replay is documented in
[过去三个月可靠性回测](reliability_backtest_3m.md). It checks whether the recent
market window still supports the same opening-permission discipline.

Probability calibration and user-risk behavior measurement are documented in
[Calibration And Risk Proof Plan](calibration_and_risk_proof_plan.md).

## 1. What Was Validated

| Area | What The Test Checks | Why It Matters |
| --- | --- | --- |
| Data gate | Missing A0/A1/A2/B1 data correctly lowers output permission | Prevents the model from inventing market facts or giving high-confidence action |
| RAG evidence | No-source, stale, rumor, conflict, and fund-flow-only cases are handled conservatively | Prevents news hallucination and one-sided catalyst summaries |
| Risk engine | Buy/add plans require stop, 1R, expected R, base rate, and invalidation | Prevents vague "看好/低吸" output |
| User misuse | Deterministic return, auto-trade, insider-style wording, and repeated override requests are blocked | Keeps the product inside research-assistance and human-confirmation boundaries |
| User-supplied inputs | User-provided sectors, stocks, and holding-review requests still pass through data gates, role checks, and anti-sunk-cost review | Prevents the assistant from treating user attention as market evidence |
| Opening permission | Missing A2 blocks 09:28 chase, while A1/B1 can still create a 09:35 absorption-confirmation workflow | Separates easier public confirmation data from hard-to-get auction queue data |
| Plan quality | Theme, single-stock, overnight, conflict, and switch-comparison cases retain source, role, next-check, and outcome requirements | Makes the workflow auditable after the market closes |
| Threshold calibration | Past-month 09:28 and 14:30 public-data replay | Checks whether A1 80%, B1 requirement, and missing-A2 downgrade remain defensible |
| Historical policy backtest | 101 main-board sample stocks, 57,558 stock-days, 827 opening-chase candidates | Tests whether opening chase without A2 creates a high false-permission risk |
| Rolling 3-month reliability replay | 99 main-board sample stocks, 5,635 stock-days, 60 opening-chase candidates | Checks whether the recent 3-month window contradicts or supports the current no-A2 downgrade |
| Replay calibration | Prediction/outcome and behavior-risk logs | Measures Brier score, expected-R error, plan-outside trading, no-stop trading, and override rate |

## 2. How To Reproduce

```bash
python3 tools/portfolio_validation.py --format markdown
python3 tools/portfolio_validation.py --format json
python3 tools/historical_policy_backtest.py --start-date 2024-01-01 --end-date 2026-05-27
python3 tools/historical_policy_backtest.py --start-date 2026-02-28 --end-date 2026-05-27 --output docs/historical_policy_backtest_3m.md --json-output reports/backtests/historical_policy_backtest_3m.json
python3 tools/prediction_replay_evaluation.py --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl
python3 -m unittest discover -s tests
```

## 3. Current Result

Latest local validation result:

| Category | Cases | Passed | Score |
| --- | ---: | ---: | ---: |
| data_gate | 8 | 8 | 16/16 |
| rag | 6 | 6 | 12/12 |
| risk | 8 | 8 | 16/16 |
| user_misuse | 6 | 6 | 12/12 |
| plan_quality | 9 | 9 | 18/18 |
| Total | 37 | 37 | 74/74 |

This is an offline guardrail regression result. It proves the product rules can
be repeatedly checked. It does not prove live profitability, live user behavior
change, or production RAG latency.

Historical policy backtest result:

| Metric | Result |
| --- | ---: |
| Window | 2024-01-01 to 2026-05-27 |
| Main-board sample stocks | 101 |
| Stock-days | 57,558 |
| Opening-chase candidates | 827 |
| Unsafe open-chase false-permission rate | 61.1% |
| Unsafe open-chase 1R stop-hit rate | 47.5% |
| Unsafe gap-fade rate | 52.5% |
| Mean expected-R error | -0.258 |
| Missed-valid-plan proxy rate | 29.0% |
| Weak-follower proxy false-permission rate | 93.6% |
| Leader/core proxy false-permission rate | 17.6% |
| Trend/anchor proxy false-permission rate | 19.3% |
| Explicit 09:35 confirmation samples | 0 |

This supports keeping the no-A2 no-chase rule. It does not validate true
auction queue, cancellation, sealing-order evidence, or the independent value
of 09:35 confirmation; those still require manual or licensed A2/minute samples. The role split
supports a stricter execution rule: weak followers stay blocked, while
leader/core/trend proxies may enter post-open confirmation.

Rolling three-month replay result:

| Metric | Result |
| --- | ---: |
| Window | 2026-02-28 to 2026-05-27 |
| Main-board sample stocks | 99 |
| Stock-days | 5,635 |
| Opening-chase candidates | 60 |
| Unsafe open-chase false-permission rate | 55.0% |
| Unsafe open-chase 1R stop-hit rate | 33.3% |
| Unsafe gap-fade rate | 51.7% |
| Mean expected-R error | -0.185 |
| Sample sufficient to loosen permission | No |
| Missed-valid-plan proxy rate | 25.0% |
| Weak-follower proxy false-permission rate | 100.0% |
| Leader/core proxy false-permission rate | 9.1% |
| Trend/anchor proxy false-permission rate | 0.0% |
| Explicit 09:35 confirmation samples | 0 |

This recent-window replay supports the conservative rule but does not have
enough opening-chase candidates to loosen 09:28 permission or recalibrate
precise base rates. It also changes the practical trading rule: missing-A2
candidates are not all thrown away; only leader/core/trend proxies may enter a
09:35 confirmation queue, while weak followers remain blocked by default.

## 4. What This Solves

Earlier portfolio wording could be challenged as "good framework, weak proof".
This validation pack adds a concrete evidence layer:

1. The evaluation set is explicit: 37 representative cases across the validation categories.
2. The acceptance rules are executable, not only written in prose.
3. The historical policy backtest adds a larger public-market sample, not only synthetic cases.
4. The result is reproducible from the public repository.
5. The scope is bounded: guardrail correctness and permission-risk reduction, not investment return.

## 5. Remaining Evidence Gap

The public daily-bar backtest reduces the evidence gap around permission
discipline, but it still does not replace true auction packets or real user
outcome logs.

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
> historical replay validation. Large-sample public data supports the conservative
> no-A2 opening-chase rule, but the system does not claim proven long-term return capability.
