# Theme Stock-Pool Screening Prompt

Use this prompt when the user wants to anchor targets under preferred A-share themes.

Run context:

1. Load `AGENTS.md` and `config/portfolio.json`.
2. Load `docs/data_sources.md` as the data-field checklist.
3. Load `docs/trading_system_upgrade.md` and apply `config.portfolio.risk_engine`.
4. Use `stock_selection_preferences`; treat `preferred_themes` only as explicit current user input if non-empty.
5. Fresh market data is mandatory for final ranking. If market data cannot be fetched, output only a provisional stock pool and mark ranking confidence as low.
6. Do not recommend any trade without stop conditions, position cap, invalidation criteria, 1R, and reward-R.

Primary objective:

Identify the day's active A-share themes from current market evidence, classify stock roles, pull recent price behavior, and rank actionable targets using the user's standards. Do not rely on any old fixed preferred-theme list.

Required process:

1. Build a stock pool for each active theme confirmed by current data:
   - Market breadth and turnover concentration
   - Sector/theme fund-flow ranking where available
   - Leader/core/catch-up feedback
   - Current holdings and user-added intraday observation names
   - Overnight external-market mapping where relevant
2. For every candidate, collect or verify:
   - Stock name and code
   - Sub-theme
   - Latest price
   - 1-day, 5-day, 10-day, and 20-day percentage change
   - Latest turnover amount
   - Turnover rate and volume ratio when available
   - Whether it recently hit limit-up, limit-down, opened after limit-up, or showed high-volume stalling
   - 5/10/20/60-day MA relationship
   - Recent catalyst, announcement, or industry-chain reason
   - Market role: leader, core anchor, catch-up, follower, or observe-only
   - Bonus factors: low price, recent IPO/new listing, low-level first launch
3. Compare the candidate with the user's current holdings:
   - Is it better than the current holding on expected value?
   - Does it reduce or increase concentration risk?
   - Is it a switch candidate or only a watchlist candidate?
4. Classify current market regime and decide whether screening can produce executable buy ideas, switch ideas, or only watchlist ideas.

Output format:

# 主题股票池与标的锚定｜{date}

## 0. 结论摘要

State the top 3-5 candidates worth watching or trading, and the top risks.

## 1. 账户约束

Summarize current position, concentration, available cash, market-regime cap, and whether the user can add risk.

## 2. 分方向股票池

For each theme:

| 股票 | 代码 | 细分方向 | 最新价 | 1日 | 5日 | 10日 | 20日 | 成交额 | 换手 | 角色 | 加分项 | 风险 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 3. 每个方向的排序

For each theme, output:

1. 龙头
2. 中军
3. 补涨
4. 低价/次新加分观察
5. 明确排除

## 4. 最终候选清单

| 优先级 | 股票 | 方向 | 入选理由 | 买点类型 | 触发条件 | 仓位上限 | 止损/失效 | 不买条件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Rules:

1. Low price and recent IPO/new listing are bonus factors, not sufficient reasons.
2. High-volume stalling, sector retreat, no-volume rebound, and unclear stop conditions must downgrade the candidate.
3. If the user is already near full position, prioritize switch candidates, reduce-risk plans, and observation triggers over new buys.
4. If material price, turnover, catalyst, or role data is missing, mark it explicitly and do not overstate confidence. Do not repeat chronic Tier 3 gaps unless they affect the ranking.
5. If the market regime is not 强进攻日 or confirmed 冰点修复日, do not rank weak followers as actionable buys.
6. New buys must state planned risk in R and target reward-R; otherwise mark as observe only.
