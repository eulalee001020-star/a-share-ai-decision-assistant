# 09:28 Auction Prediction Prompt

Generate a 09:28 A-share call-auction prediction and opening execution report.

This automation is no longer a market-summary report. It must produce scenario classification, event probabilities, expected-R calculations, and execution permissions. Use `docs/prediction_automation_system.md` as the controlling framework.

## Run Context

1. Default run time: Asia/Shanghai or Asia/Singapore 09:28, after 09:15-09:25 call auction has ended.
2. Use `config/portfolio.json`, `docs/trading_assistant_state.md`, `docs/trading_system_upgrade.md`, `docs/data_sources.md`, `docs/prediction_automation_system.md`, the 09:28 run packet, user screenshots, local Tonghuashun-readable information, and collector output when available.
3. Do not read or wait for 08:55 or 09:10 morning reports.
4. If A2 auction data is missing, do not infer auction strength from prior close. Downgrade output to a 09:30-09:35 confirmation checklist and explicitly prohibit chase-strength plans.
5. All conclusions must separate facts, inference, probabilities, and trading plan.

## Data Gate

Before any trading conclusion, classify data quality:

| Grade | Required Evidence | Permission |
| --- | --- | --- |
| A | A0 account/risk + A1 realtime quote/minute/MA + A2 auction/queue + B1 breadth/theme structure | May output probabilities, expected R, and position caps |
| B | A0 + A1 + B1, but A2 incomplete | May output opening confirmation conditions; no chase-strength |
| C | A0 plus stale or partial market data | Defensive checklist only |
| D | A0 missing | No position advice |

Report which fields are missing only if they change today's decision. Chronic Tier 3 missing data must not become boilerplate.

## Scenario Score

Score each dimension from -2 to +2 and show the evidence:

| Dimension | Score | Evidence | Trading Meaning |
| --- | ---: | --- | --- |
| Index and turnover | | | |
| Market breadth | | | |
| Sentiment relay | | | |
| Mainline structure | | | |
| Losing-money effect | | | |

Map the total score to 强进攻日、轮动日、退潮日、冰点修复日、混沌日, with confidence. Ice-point repair requires separate evidence: panic released, limit-down pressure easing, and high-recognition names stabilizing.

## Probability Rules

Every actionable stock or sector plan must include:

1. Trading mode: 龙头延续、中军趋势确认、核心回踩低吸、补涨分歧、弱票反弹、新仓失败处理, or invalid.
2. Base rate range and why that mode fits the current scenario.
3. Positive adjustments with numeric deltas.
4. Negative adjustments with numeric deltas.
5. Success probability, failure probability, noise probability.
6. Expected R:

```text
expected_r = success_probability × target_r - failure_probability × 1R - noise_probability × noise_cost_r
```

If probabilities cannot be supported by data, mark the plan as untradeable rather than inventing precision.

## Required Output

# A股 09:28 竞价预测与开盘计划｜{date}

## 1. 数据等级与输出权限

Include:

1. Data grade: A/B/C/D.
2. Available A0/A1/A2/B1/B2/B3/C data.
3. Missing decision-changing data.
4. What the missing data prohibits today.

## 2. 市场场景评分

Include the scenario score table, final regime, confidence, and total position permission. If current position exceeds the regime cap, risk reduction takes priority over new trades.

## 3. 持仓事件预测

| 股票 | 模式 | 基准概率 | 修正因子 | 09:35事件概率 | 10:00事件概率 | 收盘事件概率 | 失败概率 | 期望R | 下注资格 |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |

For each holding, define exact events. Example: "09:35站回59.40", "10:00站稳VWAP", "收盘站上60.80". Include structural stop, 1R, target R, and do-not-trade condition.

## 4. 板块与候选预测

| 板块 | 龙头证据 | 中军证据 | 补涨证据 | 场景含义 | 可交易模式 | 概率结论 |
| --- | --- | --- | --- | --- | --- | --- |

If leaders and core anchors are weaker than followers, follower strength is unreliable and must be downgraded.

## 5. 开盘执行表

| 类型 | 标的/方向 | 触发条件 | 动作 | 仓位上限 | 1R | 目标R | 取消条件 | 不交易条件 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |

Types: open-executable, first-five-minute confirmation, low-buy only, reduce/exit, observe, cancel.

Do not allow a buy/add plan unless expected R is positive, data permission allows it, and stop distance is defined.

## 6. 禁止动作

List only today's relevant prohibitions, such as:

1. Missing A2 data means no chase-strength.
2. Do not add to any short-term holding after structural stop fires.
3. Do not trade a follower if leader/core auction is weak.
4. Do not trade solely from a concept label or good-news high open.

## 7. 预测日志

Output a compact JSONL-ready block containing every prediction that should be recorded in `reports/predictions/{date}-predictions.jsonl`. Each row must include automation, code or sector, event, probability fields, expected_r, data_grade, and action.
