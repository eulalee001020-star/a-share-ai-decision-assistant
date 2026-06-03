# User Request Analysis Prompt

Use this prompt when the user gives one or more sectors/themes, individual stocks, or asks for current holding evaluation and advice.

This workflow combines theme screening, single-stock research, and holding management. It must not weaken the data gate: user attention is an input, not evidence.

## Run Context

1. Load `README.md`, `config/portfolio.example.json`, `docs/trading_assistant_state.example.md`, `docs/data_sources.md`, and `docs/prediction_automation_system.md`. For private local runs, also load `config/portfolio.json` and `docs/trading_assistant_state.md` when they exist.
2. Read the generated run packet section `用户输入分析对象`.
3. For user-provided codes, run or cite:

```bash
python3 tools/trading_assistant.py collect tail-data --date {YYYY-MM-DD} --time 1430 --codes {CODE...}
python3 tools/trading_assistant.py collect stock-data --code {CODE} --date {YYYY-MM-DD} --time 1430
```

4. For 09:28 opening decisions, use manual auction data or screenshots. If A2 is missing, output only 09:30-09:35 confirmation conditions and prohibit chase-strength.
5. Evaluate current holdings together with new ideas. A new stock can replace or add risk only if its expected value, sector role, liquidity, and stop-defined reward-risk are better than the relevant holding.
6. Weak follower / weak relay names cannot receive standard buy or add permission. Only leader, core anchor, trend/anchor, or clearly improving high-recognition names can enter a 09:35 confirmation plan.
7. If the user supplies board-capital migration data from QMT/PTrade/掘金/聚宽/terminal screenshots, import it with `sector-flow import-csv` and use it only as B1 context. It does not replace A1 quote/minute/VWAP.

## Data Gate

| Grade | Required Evidence | Permission |
| --- | --- | --- |
| A | A0 account/risk + A1 quote/minute/MA + B1 breadth/theme structure + relevant catalyst sources | May output theme ranking, stock plan, holding advice, expected R, and position cap |
| B | A0 + partial A1, or B1 incomplete | May output observation, hold/reduce, and manual verification list; no high-confidence buy/add |
| C | A1 stale/missing | Defensive checklist only |
| D | A0 missing | No sizing or position advice |

A2 is mandatory only for auction/chase conclusions. Missing A2 does not block post-open research, but it blocks claims such as "竞价超预期" and "开盘直接追".

## Required Process

1. Restate the user's requested sectors and stocks.
2. Classify market regime and position permission before any stock conclusion.
3. For each user-provided sector:
   - Split into sub-themes.
   - Identify leader, core anchor, catch-up, follower, and invalid names where data supports it.
   - Check whether the sector is mainline, rotation, retreat, or only a concept label.
   - Check whether `sector-flow` records show capital migration into, out of, or away from the sector.
   - Compare sector strength with the user's current holdings.
4. For each user-provided stock:
   - Identify whether it is current holding, watchlist, or new user-added name.
   - Apply the full single-stock evidence stack: tape, K-line/MA, volume/liquidity, available chips/holder/fund-flow proxies, sector role, catalyst/fundamental drivers, and risk-reward.
   - Mark missing layers and lower confidence instead of filling gaps.
5. For each current holding:
   - State whether the original thesis is strengthened, weakened, unchanged, or invalidated.
   - Identify new positive evidence, new negative evidence, and evidence already priced in.
   - Give hold/add/reduce/sell/observe advice only after comparing future expected value with alternatives.
6. Produce only action plans that include trigger, stop, target R, expected R, maximum position, invalidation, and do-not-trade condition.
7. Use regime-level 1R budgets as defaults: 强进攻日 1.5%, 轮动日 0.75%, 退潮日 0%, 冰点修复日 0.5%, 混沌日 0.25%. The account-level hard cap is not a normal trade budget.

## Output Format

# 用户给定板块/个股/持仓综合分析｜{date}

## 1. 数据等级与权限

Include data grade, available layers, missing decision-changing data, and what is prohibited.

## 2. 市场状态和仓位权限

Use the five-regime model. If current position is above the regime cap, risk reduction and switch discipline come before new buys.

## 3. 用户给定板块分析

| 板块 | 子方向 | 当前状态 | 龙头 | 中军 | 补涨 | 跟风/排除 | 证据 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 4. 用户给定个股分析

| 股票 | 身份 | 板块角色 | 阶段 | 强证据 | 弱证据 | 缺口 | 风险收益 | 初步结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 5. 当前持仓评价和建议

| 持仓 | 原始逻辑更新 | 当前问题 | 继续持有条件 | 减仓/卖出条件 | 可加仓条件 | 建议 |
| --- | --- | --- | --- | --- | --- | --- |

Do not recommend adding to a losing short-term holding unless new evidence independently passes buy/add rules.

## 6. 新机会和持仓对比

| 候选/持仓 | 预期强度 | 板块地位 | 流动性 | 止损距离 | 目标R | expected R | 组合影响 | 排序 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |

## 7. 可执行计划

| 类型 | 标的/方向 | 条件 | 动作 | 仓位上限 | 1R | 目标R | 止损/失效 | 不交易条件 | 盘中监控 |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |

Types: buy, add, hold, reduce, sell, switch, observe, cancel.

## 8. 边界处理

For each unresolved boundary, state the stable workaround and the downgraded permission:

1. Missing A2 auction data.
2. Missing or unstable chips, holder, Level-2, or individual fund-flow data.
3. Missing catalyst source or stale source.
4. Missing outcome/behavior logs for calibration.

## 9. 预测和复盘日志

Output JSONL-ready prediction rows for actionable events. If probabilities are uncalibrated, set `base_rate_source` to `expert-prior` or `unavailable` and keep the confidence low.
