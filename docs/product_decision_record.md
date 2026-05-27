# Product Decision Record

This document records the main product decisions behind the A-share investment
decision-support agent. It is written as an audit trail for product review:
why AI is used, where it is not used, how uncertainty is controlled, and what
evidence is still missing.

## 1. Why Agent Instead Of Rules Only

Rules are used where the judgment is deterministic: data permission, stop-loss
requirements, position caps, action blocking, and compliance boundaries.

The Agent layer is used where the task requires evidence composition:
market regime, sector structure, stock role, catalyst quality, conflicting
evidence, and conversion of messy context into a plan.

The product choice is therefore not "Agent replaces rules". It is:

```text
structured data + fixed rules + bounded reasoning workflow + human confirmation
```

If the system only used rules and templates, it would be cheaper but would miss
cross-source reasoning such as "positive company news exists, but same-day price
action already faded and sector breadth is weak". If it only used a model, it
would be unsafe because the model could invent market facts or overrule risk
limits. The current architecture keeps the high-risk decisions outside the model.

## 2. Data Health Gate Thresholds

Current thresholds are conservative product defaults. They now have one month of
public-data replay as an initial calibration baseline; they are still not a
claim of live investment alpha.

| Rule | Current Default | Rationale | Future Calibration |
| --- | --- | --- | --- |
| A1 quote/minute/MA coverage | >= 80% for high-confidence stock-level output | Below this, cross-stock comparison becomes unreliable | Replay historical run packets and compare downgrade decisions |
| Missing A2 auction data | No chase; only 09:30-09:35 confirmation | Opening strength cannot be inferred from prior close | Compare auction-confirmed vs non-confirmed plans |
| Missing B1 market structure | Market regime confidence capped at medium | Individual stock signals degrade when breadth and limit-up feedback are unknown | Calibrate by regime-error rate |
| Missing A0 account/risk | No sizing | Position size requires account and stop-distance context | Non-negotiable rule |

Initial historical calibration:

- Window: 2026-04-27 to 2026-05-27.
- Public demo stocks: 002156.SZ, 600584.SH, 600601.SH, 600206.SH, 002886.SZ.
- Samples: 20 trading days, 100 opening-confirmation observations, 100 tail-session observations.
- Result: A1 reached >=80% coverage on 20/20 sampled days for both 09:28 confirmation proxy and 14:30.
- A2 result: 0/20 public historical auction samples had true 09:15-09:25 auction amount, seal amount, post-09:20 cancellation, or queue data.

See [Historical Threshold Calibration](historical_threshold_calibration.md) and
[Calibration And Risk Proof Plan](calibration_and_risk_proof_plan.md).

The important product point is that thresholds are visible and adjustable by
validation, not hidden inside a prompt. The rule for future threshold changes is
also explicit: do not optimize for "more trade opportunities" first. Optimize
for lower false-permission rate first, then evaluate whether the rule is too
strict.

The most important limitation remains A2: public historical data can support the
"do not chase without A2" rule through opening-gap and first-15-minute volatility,
but it cannot fully calibrate auction-specific fields. Production use still needs
Tonghuashun/manual export or a licensed auction data source.

## 3. Model Vs Risk Engine Arbitration

The risk engine has veto power.

If the model says "opportunity is strong" but the market regime or data grade
does not allow the action, the final output must downgrade to observe,
confirmation-only, reduce, or no-trade. This is because model confidence is not
capital protection. The system treats the model as a reasoning assistant and the
risk engine as a permission system.

```text
facts -> model reasoning -> candidate plan -> risk gate -> final allowed output
```

No candidate plan can skip the risk gate.

## 4. What RAG/Embedding Actually Solves

RAG is used only for the message-evidence layer. It does not fetch realtime
quotes, calculate VWAP, decide position size, or replace the risk engine.

RAG solves four problems that keyword search alone handles poorly:

1. Different wording: the same catalyst may appear as policy, price increase,
   capacity, order, earnings, or supply-chain language.
2. Source ranking: exchange/company announcements should outrank unsourced news.
3. Freshness: stale materials must be retrieved but downgraded.
4. Conflict preservation: positive company news and negative risk disclosure
   must both remain visible.

Current public scope:

| Component | Current Portfolio Claim |
| --- | --- |
| Source types | Exchange/company announcements, company disclosures, Shanghai Securities News / cnstock-style public news, and market terminal data |
| Retrieval design | Hybrid keyword + embedding retrieval with metadata filters |
| Current repo proof | Product design, evaluation cases, and guardrail validation |
| Not claimed | Production vector database, low-latency realtime RAG service, or complete paid-data integration |

## 5. How "Priced In" Is Assessed

A catalyst is not accepted as tradable evidence just because it is positive.
The system requires a second-stage price-action check.

| Evidence | Interpretation Rule |
| --- | --- |
| News positive + stock already gapped and faded | Treat as possible priced-in or failed-confirmation |
| News positive + sector breadth weak | Lower confidence; no broad-theme conclusion |
| News positive + volume confirms + leader/mid-cap anchor both hold | Can enter candidate plan, still needs stop and invalidation |
| News stale | Background only; cannot be current catalyst |

This is intentionally not a pure model judgment. The model can explain the
relationship, but the confirmation depends on structured market data.

## 6. Base Rate And Expected R

Before enough historical samples exist, base rates are conservative priors, not
precise probabilities. The portfolio should not present 42% as a discovered
truth. It should present it as a prior to be calibrated.

Current rule:

1. Every probability must have base rate, positive adjustments, negative
   adjustments, noise probability, and data grade.
2. If no historical base rate exists, the output must say "待校准" and use a
   broad interval instead of pseudo-precision.
3. Predictions without outcome logs cannot be used to claim win rate.

Implementation rule:

1. `base_rate_source` must explain whether the prior comes from same-playbook
   replay, adjacent-playbook replay, public-market context, or expert prior.
2. `base_rate_sample_size` controls output precision. Fewer than 30 samples
   means "待校准"; 30-99 samples means rough interval; 100+ samples can be
   bucketed by regime and data grade.
3. `tools/prediction_replay_evaluation.py` computes probability buckets,
   Brier score, multiclass Brier, expected-R error, and missing base-rate
   fields from prediction/outcome logs.

The product value is not "we know the exact probability today". It is "we force
probability claims into a log structure that can be audited later".

## 7. Repeated User Override

If a user repeatedly ignores no-trade guidance, the product should not simply
show another warning. The next product step is increasing friction:

1. Show the exact violated rule.
2. Require the user to restate the stop, maximum loss, and invalidation.
3. Mark the action as "outside plan" in the outcome log.
4. Cool down new high-risk suggestions after repeated overrides.

This turns risk control from a passive disclaimer into a behavior loop.

## 8. Competitive Difference

| Alternative | Strength | Gap This Project Targets |
| --- | --- | --- |
| Tonghuashun / Eastmoney | Strong market data and terminal workflows | They expose information; they do not force a personal risk and evidence contract |
| Snowball / social feeds | Fast sentiment discovery | High noise, hard to audit, easy to reinforce bias |
| Broker advisory | Compliance and human expertise | Less personalized to intraday decision discipline and personal risk rules |
| TradingView | Strong charting and alerts | Less connected to A-share limit-up structure and Chinese market microstructure |
| Generic AI agent | Flexible reasoning | Unsafe without data gates, risk veto, source checks, and audit logs |

The differentiation is not data ownership. It is the decision-quality layer:
source discipline, permission control, expected-R framing, and calibration logs.

## 9. How To Prove Risk Reduction

The right business metric is not "AI recommended stocks went up". That would
turn the product into a disguised stock-picking claim.

Better metrics:

| Metric | Why It Is Safer |
| --- | --- |
| Plan completeness rate | Measures whether every action has trigger, stop, target, invalidation, and no-trade condition |
| Unsupported-action block rate | Measures whether the product prevents actions when data is missing |
| Plan-outside-trade rate | Measures whether users still violate their own plan |
| No-stop trade rate | Measures whether high-risk trades still happen without a stop |
| User override rate | Measures whether users bypass guardrails after warnings |
| Average review time | Measures productivity without claiming alpha |
| Outcome-log completion rate | Measures whether the system creates learning data |
| Probability calibration error | Measures overconfidence rather than raw return |

Only after these are stable should a private historical replay compare risk and
return outcomes. Public portfolio wording should avoid claiming long-term profit.

Behavior-risk logs should be stored separately from prediction logs:

```text
reports/behavior/{YYYY-MM-DD}-events.jsonl
```

The minimum fields are `plan_id`, `attempted_action`, `violated_rules`,
`guardrail_action`, `outside_plan`, `stop_present`, `executed`, and
`user_override`. This allows the product to prove whether it reduced
unplanned/no-stop/override behavior before making any claim about account-level
outcomes.

## 10. Compliance Boundary

The product remains research assistance when it:

1. Shows facts, inferences, and plans separately.
2. Requires user confirmation.
3. Avoids guaranteed return or deterministic language.
4. Does not place orders.
5. Explains data gaps and source limits.

It moves toward investment-advice risk when it:

1. Gives a direct buy/sell instruction without personal suitability context.
2. Presents probability as certainty.
3. Uses insider-style or undisclosed-source language.
4. Ignores risk capacity, stop, and invalidation.
5. Automates execution.

Product controls:

| Layer | Control |
| --- | --- |
| Product copy | "decision-support", not "stock recommendation" |
| Workflow | human confirmation before any action |
| Prompt | deterministic return and auto-trade refusal |
| Risk engine | no stop / no data / no A0 means no actionable plan |
| Public repo | sample data only; private account and reports ignored |
