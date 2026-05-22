# 14:30 Tail Prediction Prompt

Generate a 14:30 A-share tail-session prediction, overnight-risk, and next-auction validation report.

This automation must not be a simple buy-score summary. It must review the 09:28 predictions, score the current market scenario, estimate overnight probabilities, calculate expected R, and define next-day 09:28 validation conditions. Use `docs/prediction_automation_system.md` as the controlling framework.

## Run Context

1. Default run time: Asia/Shanghai or Asia/Singapore 14:30.
2. Before writing the report, run `python3 tools/trading_assistant.py collect tail-data --date {YYYY-MM-DD} --time 1430` and use the generated CSV/JSON as the primary A1/B1 evidence.
3. Reference the latest 09:28 auction prediction report, `reports/predictions/{date}-predictions.jsonl` if present, and any intraday user screenshots or notes.
4. Focus on current holdings, configured watchlist, intraday user-added names, and the day's confirmed active themes. Do not expand into unrelated broad screens unless asked.
5. If collector quote/minute/daily coverage is incomplete, data grade must fall and high-confidence buy scores are forbidden.

## Data Gate

Classify data quality before conclusions:

| Grade | Required Evidence | Permission |
| --- | --- | --- |
| A | A0 account/risk + A1 collector coverage >= 80% + B1 market breadth/theme structure + relevant catalysts | May output tail buy or next-day auction priority |
| B | A0 + A1 coverage >= 60%, but B1 incomplete | May output watch/hold/reduce, not high-confidence buy |
| C | A1 coverage < 60% or stale data | Defensive checklist only |
| D | A0 missing | No position advice |

For tail buy plans, overnight gap risk and next-day auction validation must be explicit.

## Scenario Score

Score each dimension from -2 to +2:

| Dimension | Score | Evidence | Trading Meaning |
| --- | ---: | --- | --- |
| Index and turnover | | | |
| Market breadth | | | |
| Sentiment relay | | | |
| Mainline structure | | | |
| Losing-money effect | | | |

Classify regime and confidence. Tail buying is usually lower priority than morning confirmation unless a leader/core has clear close-near-high behavior, volume confirmation, and positive expected R after gap-risk penalty.

## Prediction Review

Review the 09:28 predictions when available:

| Prediction | Probability | Actual | Result | Error Type | Weight Adjustment |
| --- | ---: | --- | --- | --- | --- |

Error types: scenario misclassification, base-rate wrong, positive-factor overweight, negative-factor underweight, data missing, execution condition unclear.

## Probability Rules

For every scored holding or watchlist stock, estimate:

1. Probability of strong close: closes above VWAP/key level or near high.
2. Probability of next-day auction continuation: next 09:25 opens strong and does not immediately fail.
3. Probability of overnight failure: next day low open, open below VWAP/key level, or sector leader weak.
4. Noise probability.
5. Expected R after overnight gap-risk penalty.

Use:

```text
expected_r = success_probability × target_r - failure_probability × 1R - noise_probability × noise_cost_r - gap_risk_penalty
```

No tail buy is allowed if expected R is not positive, stop is missing, or next-day auction validation is unclear.

## Required Output

# A股 14:30 尾盘预测与隔夜计划｜{date}

## 1. 数据等级与尾盘权限

Include data grade, collector coverage, missing decision-changing data, and whether tail buy is allowed.

## 2. 09:28 预测复盘

Review morning predictions when present. If missing, state that the day cannot be used for full calibration and continue with tail prediction.

## 3. 尾盘市场场景评分

Include scenario score table, final regime, total position permission into close, and confidence.

## 4. 持仓与观察股概率表

| 股票 | 模式 | 尾盘结构 | 基准概率 | 修正因子 | 强收概率 | 次日竞价延续概率 | 隔夜失败概率 | 期望R | 评级 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |

Ratings:

1. A: Buyable if market permission and stop are clear.
2. B: Small trial or next-day auction priority.
3. C: Observe only.
4. D: Reduce/exit.
5. X: Forbidden.

## 5. 可执行尾盘计划

| 类型 | 股票/方向 | 条件 | 动作 | 仓位上限 | 1R | 目标R | 止损/失效 | 不交易条件 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |

Types: tail buy allowed, next-day auction watch, hold/reduce, remove, cancel.

## 6. 次日 09:28 验证清单

List exact next-day auction signals:

1. Which leaders must not weaken.
2. Which core anchors must confirm.
3. Which followers must be abandoned if leaders are weak.
4. Which gap-up, flat-open, or gap-down behavior confirms or cancels the plan.

## 7. 禁止动作

List only relevant prohibitions:

1. Do not tail-buy a follower just because it has not risen yet.
2. Do not chase near-limit-up after a full-day move unless leader/core status and expected R survive gap-risk penalty.
3. Do not add to short-term holdings after valid stops.
4. Do not treat low price, concept labels, or user attention as buy reasons.

## 8. 预测日志

Output JSONL-ready predictions for `reports/predictions/{date}-predictions.jsonl` and any outcomes that can be evaluated into `reports/outcomes/{date}-outcomes.jsonl`.
