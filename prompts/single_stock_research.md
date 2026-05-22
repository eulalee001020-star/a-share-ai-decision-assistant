# Single-Stock Deep Research Prompt

Use this prompt when the user provides an A-share name/code, holding status, cost, position, time horizon, and optional screenshots.

Input template:

```text
【股票】
- 名称+代码：
- 当前身份：持仓 / 自选 / 准备买入 / 准备卖出
- 我的成本价：
- 当前仓位：占总资产比例
- 计划周期：短线几天到几周 / 中线1-3个月 / 中长期3个月以上
- 买入逻辑或关注逻辑：
- 我附上的截图：分时 / 日K / 周K / 筹码 / 盘口 / 资金 / 板块图
```

Task:

Analyze the stock using the latest available data and the user's screenshots when provided. Do not provide a static opinion without fresh-data checks. If fresh data is unavailable, mark the data gap and lower confidence.

Before writing the analysis inside this repository, run the single-stock data collector:

```bash
python3 tools/trading_assistant.py collect stock-data --code {CODE} --date {YYYY-MM-DD} --time 1430
```

Use the generated `reports/{YYYY-MM-DD}-{CODE}-1430-stock-data.csv/json` as the primary evidence for quote, intraday minute/VWAP, turnover, volume ratio, visible five-level order book, moving averages, market activity, sector/concept fund-flow proxy, optional individual fund-flow, shareholder, news, and Dragon-Tiger data. Do not repeat chronic optional-layer failures as boilerplate. State a missing optional layer only when it directly affects the conclusion, or when the user supplied a screenshot/export that conflicts with the collector.

Before any buy/add/hold conclusion:

1. Load `docs/trading_system_upgrade.md` and `config.portfolio.risk_engine`.
2. Classify the current market regime: 强进攻日、轮动日、退潮日、冰点修复日、or 混沌日.
3. Check whether the user's current total position is above the regime cap.
4. Define 1R, structural stop, target reward-R, and "do not trade if" condition.
5. If the stock has no clear structural stop, output observe/reduce only; do not recommend adding.

Mandatory evidence rule:

Do not analyze any individual stock only from price change, theme label, or a single screenshot. Every stock-level conclusion must integrate realtime tape, K-line/MA structure, volume and liquidity, available fund-flow proxies, sector role, catalyst/fundamental quality, and risk-reward. Chips, full Level-2, hidden liquidity, and realtime holder changes are optional Tier 3 layers in this repository; mention their absence only when it materially lowers confidence or blocks a buy/add/hold/reduce conclusion.

Mandatory fresh driver rule:

For every holding, buy/add idea, reduction decision, or user-requested single-stock analysis, also check the latest public information on the stock's main earnings drivers. Do not stop at quarterly revenue/profit. Identify what actually drives the next 1-2 quarters of earnings and valuation, then verify the latest marginal change from public sources where available.

Examples:

1. Upstream/cyclical materials: product prices, spreads, inventories, operating rate, effective capacity, new capacity, demand from downstream, and cash-flow/working-capital pressure.
2. Semiconductors/AI hardware: customer demand, advanced packaging or product mix, capacity ramp, utilization, capex/depreciation, gross margin, major shareholder reduction, and overseas peer/customer signal.
3. AIDC/electric-power equipment: data-center order delivery, UPS/power module/liquid-cooling progress, IDC utilization, energy-storage price competition, overseas order progress, receivables and operating cash flow.
4. Event-driven names: announcement validity, order size versus revenue base, delivery timing, profit margin, counterparty quality, and whether the market has already priced it.

Output the driver check as "latest marginal drivers": strengthened, weakened, mixed, or unverified. If current product-price, order, capacity, chip, or fund-flow data cannot be obtained, say which specific source failed and whether a public proxy was used.

## 1. 最新信息核查

Check from the previous full day to now:

1. Company announcements.
2. Earnings preview, flash report, or financial report.
3. Orders, contracts, product prices, and industry-chain changes.
4. Policy changes.
5. Regulatory inquiries, penalties, litigation.
6. Share reduction, unlock, buyback, private placement.
7. Dragon-Tiger list, block trades, investor relations.
8. Related industry, upstream/downstream, competitor, and overseas mapping.

Output:

| 时间 | 信息 | 来源 | 利好/利空/中性 | 对股价影响 | 是否已被市场反映 | 置信度 |
| --- | --- | --- | --- | --- | --- | --- |

## 2. 先分型

Classify:

1. Allocation stock, medium-term trend stock, or short-term trading stock.
2. Leader, core anchor, catch-up, or follower.
3. Cyclical growth, long-duration secular growth, cyclical, event-driven, or pure theme/emotion stock.
4. Best current style: trend hold, low-buy, chase strength, limit-up attempt, reduce on rebound, or observe only.

Explain the classification.

## 3. 宏观层

Judge:

1. Whether the market supports action.
2. Systemic risk.
3. Whether current market style fits the stock.
4. Turnover, advancers/decliners, limit-up/down count, and consecutive-board mood when available.
5. Overseas market, FX, commodities, and rates pressure/support.
6. Market-regime label and position permission based on the five-regime model.

Conclusion: 做多 / 中性 / 防守 / 回避, with market regime, position permission, and confidence.

## 4. 板块层

Judge:

1. Sector stage: launch, main rise, climax, divergence, retreat, second wave, high-low rotation, catch-up.
2. Whether the sector is a mainline.
3. Leader, core anchor, catch-up, and followers.
4. The stock's position in the sector.
5. Whether capital continues flowing into the sector.
6. Whether sector turnover share is overcrowded.
7. Whether the leader remains strong and whether there is displacement risk.

Conclusion: 主线 / 轮动 / 退潮 / 无效题材, with confidence.

## 5. 个股基本面与预期差

Analyze:

1. Revenue, profit, gross margin, net margin, ROE, and cash flow.
2. Inventory, receivables, debt, goodwill, and other risks.
3. Current valuation and historical percentile when available.
4. Potential earnings upgrade.
5. Current market focus.
6. Expectation gap.
7. Good-news-no-rise or bad-news-no-fall behavior.
8. If it is a growth stock, classify cyclical growth vs long-duration secular growth and apply the appropriate standards.

## 6. 技术面与筹码

Using screenshots and latest data, judge:

1. Daily K position: low, mid, high, box, breakout, or breakdown.
2. 5/10/20/60/120/250-day moving averages.
3. Price-volume: volume rise, shrinking decline, volume breakout, high-volume stall, shrinking rebound, heavy bearish candle.
4. MACD, KDJ, RSI, OBV when available.
5. Chip peak, profit ratio, average cost.
6. Latest shareholder count and change rate, top-holder/fund/foreign/margin holding changes, and main-holder concentration ratio when available. Treat rapid shareholder-count expansion in high-level stocks as crowding/distribution risk unless other evidence offsets it.
7. Resistance, support, liquidity, turnover, and whether it can support the user's capital size.

## 7. 主力资金意图

Choose the closest 1-2 states and provide evidence:

1. Accumulation
2. Test
3. Washout
4. Pull-up
5. Main rise
6. Acceleration
7. Sideways consolidation
8. High-level divergence
9. Distribution
10. Exit
11. Breakdown
12. Oversold rebound
13. Weak rebound trap

Evidence must include price-volume, intraday behavior, order book when available, chips, moving averages, and sector linkage.

## 8. 所处阶段判断

Use the stage library in `AGENTS.md`. Choose the closest 1-2 stages and explain why.

## 9. 三层共振与贝叶斯更新

| 层级 | 结论 | 证据 | 置信度 |
| --- | --- | --- | --- |
| 宏观 | 做多/中性/回避 | ... | 高/中/低 |
| 板块 | 主线/轮动/退潮 | ... | 高/中/低 |
| 个股 | 吸筹/洗盘/拉升/出货等 | ... | 高/中/低 |

Then perform Bayesian update:

1. Original buy/watch thesis.
2. What new evidence strengthens.
3. What new evidence weakens.
4. Whether current expected value improved.
5. Whether sunk-cost bias must be reduced.
6. Conclusion: maintain, upgrade, downgrade, or overturn the prior view.

## 10. 交易计划

| 项目 | 结论 |
| --- | --- |
| 操作方向 | 买入 / 持有 / 加仓 / 减仓 / 清仓 / 观望 |
| 操作风格 | 追涨 / 低吸 / 打板 / 趋势持有 / 反弹减仓 |
| 仓位上限 | 占总资产比例 |
| 首仓/加仓 | 具体条件 |
| 买入区间 | 具体价格或条件 |
| 止损位 | 价格/均线/结构条件 |
| 止盈位 | 第一目标、第二目标 |
| 计划风险 | 1R亏损金额/账户亏损比例 |
| 目标赔率 | 目标收益相对1R的倍数 |
| 持有周期 | 几天/几周/几个月 |
| 失效条件 | 出现什么情况说明判断错了 |
| 不交易条件 | 出现什么情况今天不买/不加/不追 |
| 盘中观察点 | 竞价、分时、板块龙头、成交量、盘口 |

Final sentence:

这只票现在最适合的打法是：____；最不能做的是：____。
