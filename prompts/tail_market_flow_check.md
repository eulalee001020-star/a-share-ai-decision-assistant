# 14:30 Market Flow And Opportunity Scan Prompt

Generate a 14:30 A-share market-flow, sector-rotation, and observable-buy-opportunity report.

This automation is separate from the 13:10 afternoon check. The 13:10 workflow prepares the afternoon plan and 14:30 must-watch conditions; this 14:30 workflow verifies what actually happened by the tail-session node and updates next-day 09:35 validation priorities.

## Run Context

1. Recommended schedule: A-share trading days at 14:35 Asia/Shanghai, using `--time 1430` as the target minute so the 14:30 bar has time to settle.
2. Output path: `reports/{YYYY-MM-DD}-1430-market-flow-opportunity-scan.md`.
3. Prediction log path when predictions are written: `reports/predictions/{YYYY-MM-DD}-1430-market-flow-predictions.jsonl`.
4. Read, in order:
   - `AGENTS.md`
   - `config/portfolio.json`
   - `docs/trading_assistant_state.md`
   - `docs/trading_system_upgrade.md`
   - `docs/data_sources.md`
   - `docs/opening_permission_model.md`
   - `docs/prediction_automation_system.md`
   - `prompts/tail_check.md`
   - `prompts/tail_market_flow_check.md`
   - the same-day `reports/{YYYY-MM-DD}-1310-afternoon-check.md` when present
   - same-day message evidence and user intraday additions when present

## Fixed Command Order

Run these commands before writing conclusions:

```bash
python3 tools/trading_assistant.py validate
python3 tools/trading_assistant.py render tail --date {YYYY-MM-DD}
python3 tools/trading_assistant.py collect tail-data --date {YYYY-MM-DD} --time 1430
python3 tools/trading_assistant.py data-health --date {YYYY-MM-DD} --time 1430 --automation tail
python3 tools/trading_assistant.py message-evidence summary --date {YYYY-MM-DD}
```

If public market commentary or news is used for cross-checking, preserve source URL, publish time when visible, conflict, and whether it is already reflected in price. Public commentary is a cross-check only; it cannot override `data-health`, A1/B1 coverage, or portfolio risk rules.

## Data Gate

Use `data-health` as the permission gate.

| State | Permission |
| --- | --- |
| A0 + A1 >= 80% + B1 available | May output market-flow ranking, observable buy opportunities, conditional low-buy plans, hold/reduce/sell plans, and next-day validation conditions |
| A1 < 60% or B1 missing | Defensive checklist only; no high-confidence buy/add |
| A0 missing | No position sizing or action advice |
| A2 missing | No 09:28 chase-strength or "auction exceeded expectations" claims for the next day |
| C2 missing | No high-confidence catalyst claims |

## Required Analysis

### 1. 14:30 Data And Permission

Include collector coverage, `data-health` grade, stable readiness score, action ceiling, A2 state, C2 message-evidence state, and whether any buy/add plan is allowed.

### 2. Market Flow Structure

Compare 13:05 and 14:30 when both files exist:

1. Limit-up pool, opened-board pool, limit-down pool.
2. Broad ETF / index proxies in the configured watchlist.
3. Top industry and concept fund-flow proxy rankings.
4. Which sectors strengthened into 14:30, which faded, and which only had follower rotation.

Do not treat vendor-classified fund-flow proxy as true institutional intent.

### 3. Sector Priority

Rank sectors by:

1. B1 breadth and limit-up / opened-board / limit-down structure.
2. Industry and concept fund-flow proxy rank.
3. Leader/core/catch-up/follower structure.
4. Matching watchlist / holding evidence.
5. Whether the opportunity still has positive expected R after overnight gap risk.

### 4. Observable Buy Opportunities

For every candidate, classify role first:

1. Leader or core anchor.
2. Trend / core mid-cap.
3. High-recognition catch-up.
4. Follower.
5. High-volatility thermometer.

Only leaders, core anchors, and verified trend/core names can receive next-day validation priority. Weak followers, weak catch-ups, high-volatility rebounds, and no-stop names cannot receive standard tail or overnight risk.

Every candidate row must include:

1. Code and name.
2. Sector role.
3. 14:30 price versus open and VWAP.
4. Whether it is near high, mid-range, or fading.
5. Buy observation trigger.
6. Stop or invalidation condition.
7. "Do not trade if" condition.
8. Next-day 09:35 validation condition.

### 5. Holding Impact

For each current holding, state whether same-day market flow strengthened, weakened, left unchanged, or invalidated the original thesis. Do not hold or add because of sunk cost.

### 6. Risk Budget

Use regime-level normal 1R, not the hard single-trade cap:

| Market state | Normal 1R |
| --- | ---: |
| Strong attack day | 1.5% |
| Rotation day | 0.75% |
| Retreat day | 0% |
| Ice-point repair day | 0.5% |
| Chaotic day | 0.25% |

If the current total position is already above or near the regime cap, new risk must come from replacement / sell-weak-buy-strong logic, not net new exposure.

### 7. Output

Use this title:

```markdown
# A股 14:30 大盘资金流向与观察机会｜{YYYY-MM-DD}
```

Required sections:

1. 数据等级与尾盘权限
2. 14:30 大盘状态
3. 今日资金最可能流向
4. 可观察买入机会
5. 当前持仓影响
6. 明日 09:35 验证路径
7. 禁止动作
8. 预测日志 JSONL 草案

The final conclusion must clearly separate:

1. Can observe.
2. Can validate next day.
3. Can only reduce / hold.
4. Cancelled / forbidden.

Never output an automatic order instruction.
