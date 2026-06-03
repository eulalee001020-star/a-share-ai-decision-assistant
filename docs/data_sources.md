# Data Source Requirements

Fresh A-share screening depends on accessible data. Use the best available sources in this priority order.

## Best Available Data Stack

For the current product, "best data" means the most complete data that can be acquired repeatedly and audited. Do not use one-off screenshots or unstable webpage responses as hard evidence unless they are saved into `data/manual/` or `reports/`.

| Layer | Best practical source | Use | Product rule |
| --- | --- | --- | --- |
| A0 account/risk | Broker screenshot, trade record, `config/portfolio.json` | Position, cash, cost, risk budget | Mandatory for sizing |
| A1 realtime quote/minute | Local collector from Sina/Tencent; AKShare realtime/minute when stable; licensed minute source if available | Latest price, open, VWAP, 09:35 confirmation, 14:30 tail check | Mandatory for actionable intraday output |
| Historical daily/minute | Tencent public daily bars for broad replay; AKShare/Eastmoney historical daily/minute; Tushare Pro historical minute if licensed | Backtest, threshold calibration, confirmation lift | Use public data for guardrails; use licensed minute data for 09:35 path validation |
| A2 auction | Tushare auction permission, iFinD/Tonghuashun terminal/API, Tonghuashun screenshot/manual CSV | 09:15-09:25 amount, post-09:20 cancel, seal, queue, role ranking | Only this layer can justify 09:28 early permission |
| B1 market structure | AKShare/Eastmoney limit-up/down pools, sector/concept rankings, market breadth | Market regime and losing-money effect | Missing B1 caps regime confidence |
| Sector role | Eastmoney/同花顺 concept constituents, sector leaders, manual role file, relative-strength proxy | Leader/core/catch-up/follower classification | Weak followers are default blocked |
| Message evidence | Exchange/company announcements, CNINFO, company IR, major securities news, manual notes | Catalyst, conflict, priced-in checks | Must keep source, timestamp, conflict |
| Slow structure | Fund holdings, HK Stock Connect, margin, shareholder count, chip data | Crowding and structural correction | Weak correction only; not intraday hard evidence |

Operational recommendation:

1. For free/local use, run A1/B1 collection and public historical replay every day; this is enough to keep guardrails disciplined.
2. For the best version of the application, add a licensed or terminal-export layer for historical 1-minute data and A2 auction data. Without it, do not claim 09:35 confirmation alpha or 09:28 auction alpha.
3. Cache every fetched dataset by date, code, source, and retrieval time. Reproducibility matters more than having a larger but untraceable feed.
4. If two sources conflict, keep both and lower confidence; do not silently choose the value that supports the trade.

## Provider Integration Roadmap

External discussions often mention QMT, PTrade, 掘金, 聚宽, Tushare, Sina, yfinance, and Fincep-style tools. Treat these as provider candidates, not conclusions. The local contract is in `docs/data_provider_integration_plan.md`:

1. QMT/PTrade/掘金/券商量化终端 are production-candidate sources for A1/A2/B1 only after account permission, export fields, latency, and cache format are verified.
2. 聚宽/Tushare are useful for historical replay, slow variables, and some specialty data; they do not automatically replace intraday A1 unless live fields are verified.
3. yfinance is not an A-share intraday source for this system.
4. Any new provider must first export auditable CSV/JSON into `data/vendor/` or `data/manual/`, then enter the same `data-health` gate.
5. Community comments about funding thresholds or broker access are leads for verification, not source-of-truth system rules.

For the board-capital migration view shown in external examples, use the B1 manual import:

```bash
python3 tools/trading_assistant.py sector-flow template --date YYYY-MM-DD
python3 tools/trading_assistant.py sector-flow import-csv --date YYYY-MM-DD --input data/manual/sector_flow/YYYY-MM-DD.csv --source "QMT/PTrade/JoinQuant/manual"
python3 tools/trading_assistant.py sector-flow summary --date YYYY-MM-DD
```

This can restore B1 sector-flow structure when public APIs fail, but it cannot restore A1 quote/minute/VWAP coverage.

## Stable Data Weighting

`config/decision_weights.json` is the system-level contract for data priority. The current architecture gives primary weight to data that can be collected repeatedly and audited:

1. B1 market regime and losing-money effect.
2. B1 sector resonance and stock role.
3. A1+B1 09:35 opening absorption.
4. A0+A1 risk-reward, stop distance, liquidity, and sizing.
5. A1 K-line, moving averages, volume, and relative strength.
6. C2 source-backed catalysts.

Hard-to-get layers are modifiers, not main gates. A2 auction can advance a qualified plan from 09:35 to 09:28, but cannot skip 09:35 validation. Individual fund-flow, chips, holder structure, margin, and Level-2 queue data can only adjust confidence when present; their absence should not block the stable A0/A1/B1 workflow or be repeated as daily boilerplate.

## Stock Pool Discovery

1. Exchange announcements and company公告 for verified catalysts.
2. Public concept/sector constituent pages when available, such as 东方财富、同花顺、财联社、证券时报.
3. Industry-chain research from exchange/company disclosures, Shanghai Securities News / cnstock-style public news, or company investor-relations disclosures.
4. News search for new catalysts. Rumors must be marked as unverified.

For each theme, do not stop at a single concept label. Split into sub-themes:

1. 情绪投机：最高标、连板、断板反包、次新、低价、题材情绪.
2. 国产芯片/半导体：设备、材料、封测、设计、存储、先进封装、EDA/IP、功率半导体.
3. 商业航天：卫星制造、火箭、地面设备、卫星互联网、测控、材料与元器件.
4. AI上游/电子布：AI服务器、PCB、覆铜板、玻纤布/电子布、树脂、铜箔、材料涨价.
5. 算力电力：IDC、电力设备、变压器、配电、电源、液冷、储能、绿电.

## User-Supplied Sector, Stock, And Holding Inputs

When the user provides a sector, stock, or asks about holdings, treat the input as a target-selection hint, not as market evidence. The stable workflow is:

1. Generate the combined run packet:

```bash
python3 tools/trading_assistant.py render user --date YYYY-MM-DD --themes 半导体 AI硬件 --codes 002156.SZ 603920.SH
```

2. Collect A1/B1 evidence for user-supplied stocks and the configured holdings/watchlist:

```bash
python3 tools/trading_assistant.py collect tail-data --date YYYY-MM-DD --time 1430 --codes 002156.SZ 603920.SH
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 1430 --automation user
```

3. If a single stock needs deep research, run:

```bash
python3 tools/trading_assistant.py collect stock-data --code 002156.SZ --date YYYY-MM-DD --time 1430
```

Output permissions:

| Input Type | Required Evidence | If Missing |
| --- | --- | --- |
| User sector | B1 breadth/theme structure, leader/core/catch-up comparison, catalyst source | Only direction map and manual verification list |
| User stock | A1 quote/minute/MA, liquidity, sector role, catalyst/source, stop level | No high-confidence buy/add; observe or verify only |
| Current holding | A0 cost/quantity/risk, A1 current structure, original thesis update, alternatives comparison | No add; hold/reduce/sell only by explicit trigger |
| Opening chase | A2 auction data plus A1/B1 | No 09:28 chase-strength; wait for 09:30-09:35 confirmation |

For all three input types, compare the conclusion with current portfolio risk. A new candidate should become a buy or switch candidate only when it is stronger than the relevant holding on expected value, sector role, liquidity, stop distance, and market-regime permission.

## Market Data Required

For candidate ranking, collect:

1. Latest price.
2. 1-day, 5-day, 10-day, and 20-day percentage change.
3. Latest turnover amount.
4. Turnover rate.
5. Volume ratio if available.
6. Recent limit-up, limit-down, opened-board, or failed-board behavior.
7. 5/10/20/60-day moving-average relationship.
8. Support, pressure, and invalidation level.

If any of these cannot be fetched, mark it as missing and lower ranking confidence.

## Stable Tail-Session Data Collector

The tail-session automation must not depend on ad-hoc webpage searches. Use the local collector before writing the 14:30 report:

```bash
python3 tools/trading_assistant.py collect tail-data --date YYYY-MM-DD --time 1430
```

Default outputs:

1. `reports/{YYYY-MM-DD}-1430-tail-data.csv`
2. `reports/{YYYY-MM-DD}-1430-tail-data.json`

The collector reads current holdings and the watchlist from `config/portfolio.json`; extra codes can be appended:

```bash
python3 tools/trading_assistant.py collect tail-data --date 2026-05-12 --time 1430 --codes 600183.SH 002080.SZ
```

For any single-stock deep analysis, use the same data layer with a single-code command:

```bash
python3 tools/trading_assistant.py collect stock-data --code 002428.SZ --date 2026-05-12 --time 1430
```

Default outputs:

1. `reports/{YYYY-MM-DD}-{CODE}-1430-stock-data.csv`
2. `reports/{YYYY-MM-DD}-{CODE}-1430-stock-data.json`

The single-stock JSON includes the Tier 1 quote/minute/K-line package plus market activity, sector/concept fund-flow proxies, and best-effort optional layers for individual fund-flow, shareholder structure, recent news, and Dragon-Tiger daily records. Optional-layer failures should not become daily boilerplate; carry them into the final analysis only when they materially affect the conclusion.

### Coverage Tiers

Tier 1 data is mandatory for tail-session scoring and is collected by direct Sina/Tencent quote APIs with retries:

1. Latest price, open, high, low, previous close, change percentage.
2. Turnover amount and cumulative VWAP.
3. Tencent minute snapshot at or before the requested time, such as 14:30, including minute price, cumulative turnover, and minute VWAP.
4. Turnover rate, volume ratio, market cap, and dynamic PE where Tencent exposes them.
5. Visible best bid/ask level from Sina quote fields.
6. 5/10/20/60-day moving averages, 5/10/20-day gains, and volume versus 20-day average from Tencent adjusted daily K-line.

Tier 2 data is useful but should be treated as vendor-classified proxy data:

1. Market activity from `akshare.stock_market_activity_legu`.
2.涨停池、炸板池、跌停池 from Eastmoney/AKShare.
3. Industry and concept fund-flow rankings from AKShare fund-flow endpoints.

Tier 3 data is not stable enough as a mandatory intraday input in this repository:

1. Individual-stock main-fund, super-large, large, medium, and small order flows. These endpoints often fail or lag; use them only when the collector records them successfully or when Tonghuashun screenshots/export are available.
2. Chip distribution, profit ratio, chip peak, and cost concentration. Use Tonghuashun desktop screenshots/export or paid data; public quote APIs usually do not expose reliable chip data.
3. Full Level-2 queue, sealing-order cancellation, hidden liquidity, and dark/iceberg evidence. Public APIs expose visible quote fields only; true queue and cancellation evidence requires Tonghuashun Level-2, broker Level-2, or screenshots.
4. Shareholder count, fund holdings, Hong Kong Stock Connect holdings, and margin changes. These are low-frequency structure data, suitable for post-close research rather than 14:30 timing decisions.

Tail reports must cite the generated CSV/JSON coverage line. If Tier 1 fields are missing for a stock, it cannot receive a high-confidence buy score. Missing Tier 3 data should not be repeated every day; mention it only when it blocks a claim about chips, holder structure, hidden liquidity, or true institutional intent.

## Opening Permission Data Priority

The stable product evidence for the open is not A2 alone. Use this order:

1. Market regime and losing-money effect.
2. Sector resonance: leader, core anchor, catch-up, follower, and breadth.
3. 09:30-09:35 opening confirmation from public quote/minute data.
4. Risk-reward: structural stop, 1R, target R, expected R, and position cap.
5. A2 auction fields only for earlier 09:28 permission.

The easiest high-value sample is 09:35 confirmation. Collect it with the same public collector:

```bash
python3 tools/trading_assistant.py collect tail-data --date YYYY-MM-DD --time 0935 --codes 当日核心票1 当日核心票2
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 0935 --automation auction
```

The 09:35 packet should be judged by whether the stock is above its open, above or not materially below VWAP, supported by sector core names, and still has acceptable stop distance. This is a post-open confirmation layer, not a replacement for true A2.

## 09:28 Call-Auction Data Priority

For 09:28 auction correction, use the local Tonghuashun desktop client first when available and permitted.

Collect from Tonghuashun where readable:

1. 09:15-09:25 pre-open price and auction change.
2. Auction volume and auction turnover.
3. Volume ratio, open, previous close, and early intraday high/low when available.
4. Five-level order book, visible buy/sell pressure, sealing orders, cancellations, and reseal behavior where the interface exposes them.
5. Sector ranking, concept ranking, limit-up ladder, prior limit-up feedback, failed-board or opened-board behavior, and high-recognition names.
6. Leader, core anchor, catch-up, and follower comparison for the user's preferred themes.

Fallback order:

1. User screenshots.
2. Local data interfaces such as `akshare` and `baostock`.
3. Public webpages and news feeds.

If Tonghuashun cannot be opened or read, state that explicitly. Do not infer auction strength from prior-close data alone.

### 09:28 Data Permission Rules

The 09:28 automation treats call-auction data as an early-permission input. Use the data-grade system in `docs/prediction_automation_system.md` and the permission model in `docs/opening_permission_model.md`.

1. If A2 auction data is available from Tonghuashun, screenshots, or a manual export, the report may classify auction strength and assign chase/low-buy permissions.
2. If A2 data is missing but A1 realtime quote/minute and B1 market structure are available, the report may only output 09:30-09:35 confirmation conditions. It must not say a stock is "竞价超预期".
3. If A1 is also missing, the report is a defensive checklist only.
4. Missing auction fields should be specific:竞价成交额、09:20后撤单、封单额、队列、龙头/中军/跟风排序. Do not replace them with generic boilerplate.

Recommended manual auction export path when screenshots or Tonghuashun values are supplied:

```text
data/manual/auction/{YYYY-MM-DD}.json
```

Use the local sample ledger to check whether A2 is actually usable:

```bash
python3 tools/trading_assistant.py auction-template --date YYYY-MM-DD
python3 tools/trading_assistant.py auction-csv-template --date YYYY-MM-DD --codes 当日核心票1 当日核心票2
python3 tools/trading_assistant.py auction-import-csv --date YYYY-MM-DD --input data/manual/auction/YYYY-MM-DD.csv
python3 tools/trading_assistant.py auction-samples --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python3 tools/trading_assistant.py auction-calibration --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

The critical fields for opening permission are `auction_price`, `auction_amount_cny`, `post_0920_cancel_signal`, and `role_signal`. If these are missing, the report must keep confirmation-only permission even when a screenshot or file exists.

CSV is the fastest practical path when Tonghuashun export is available or when screenshots are manually transcribed into a spreadsheet. Minimum schema:

```csv
股票代码,竞价价,竞价成交额,09:20后撤单,板块角色
002156,10.50,1.2亿,良性,中军
```

The importer also accepts English field names such as `code`, `auction_price`, `auction_amount_cny`, `post_0920_cancel_signal`, and `role_signal`. Chinese units like `万` and `亿` are converted to CNY numbers.

Initial sampling discipline:

1. First 20 trading days: holdings, watchlist, and same-day sector core names only.
2. 20-60 complete rows: compare A2-confirmed versus no-A2 predictions using `auction-calibration`.
3. Only after the comparison shows lower false-permission, lower 09:35 invalidation, and smaller expected-R error should 09:28 opening permissions be reconsidered.

## Message Evidence Layer

Announcements, news, industry-chain notes, and user-supplied articles should enter a structured evidence file before they affect stock or sector conclusions:

```bash
python3 tools/trading_assistant.py message-evidence template --date YYYY-MM-DD --codes 002156.SZ --themes 半导体
python3 tools/trading_assistant.py message-evidence summary --date YYYY-MM-DD
```

Default path:

```text
data/manual/messages/{YYYY-MM-DD}.json
```

Each evidence item must preserve source type, source name, title, publish time, URL/path, stance, freshness, rumor flag, conflict references, and confidence. Missing-source, stale, rumor, and conflicting items lower confidence and cannot become high-confidence catalysts by themselves.

Suggested structure:

```json
{
  "date": "2026-05-15",
  "scope": {
    "codes": ["002156.SZ"],
    "themes": ["半导体"]
  },
  "evidence": [
    {
      "id": "msg-001",
      "source_type": "exchange_announcement/company_disclosure/news/industry_chain/ir/transcript/manual_note",
      "source_name": "交易所公告",
      "title": "公告标题",
      "published_at": "2026-05-15 08:45",
      "url_or_path": "https://example.com/announcement",
      "code": "002156.SZ",
      "theme": "半导体",
      "summary": "一句话事实摘要，不写推断。",
      "stance": "positive/negative/neutral/conflicting",
      "freshness": "fresh/stale/unknown",
      "is_rumor": false,
      "conflicts_with": [],
      "used_for": "catalyst/thesis_update/risk/priced_in_check/background",
      "confidence": "high/medium/low"
    }
  ]
}
```

## News, Funds, And Sentiment Required

The 09:28 report must not rely only on daily K-line data. It needs a compact evidence block for news, fund behavior, market mood, and call-auction signals.

Collect where available:

1. Company news and announcements: recent stock news, exchange/company announcements, earnings, contracts, reductions, unlocks, regulatory inquiries, litigation, buybacks, placements, and risk warnings.
2. Sector and concept news: policy, industry-chain price changes, order/capex evidence, upstream/downstream changes, and overseas mapping.
3. Individual-stock fund flow: main-fund net inflow/outflow, super-large order, large order, medium order, small order, and net-inflow ratio.
4. Sector/concept fund flow: industry and concept net flow, flow ranking, leading stock, sector breadth, and whether money is concentrating or rotating.
5. Dragon-Tiger list: whether institutions, known active seats, or ordinary seats are net buying/selling; whether the stock is on the list because of strong upside, downside, high turnover, or abnormal volatility.
6. Holder structure: top shareholders, top tradable shareholders, fund holdings, Hong Kong Stock Connect holdings, recent holder-count changes, and important shareholding changes.
7. Market sentiment: hot-stock ranking, limit-up/limit-down count, consecutive-board height, prior limit-up feedback, opened-board/fail-board behavior, panic selling, and high-open selloff behavior.
8. Margin and northbound proxies where available: margin balance, financing buy/sell, Hong Kong Stock Connect flow/holdings, and their direction.

Interpretation rules:

1. "Main-fund flow" is a vendor classification, not verified real institutional intent. Use it as a short-term sentiment and pressure proxy, not as proof of accumulation or distribution.
2. Positive price action with negative main-fund flow may mean divergence, distribution, passive selling absorption, or vendor classification noise. It requires volume-price and intraday confirmation.
3. Negative price action with positive main-fund flow may mean failed support, dip buying, or trapped capital. It is not automatically bullish.
4. Holder and fund-holding data are low-frequency and often reported with delay. They are useful for structure and recognition, not for intraday timing.
5. Dragon-Tiger list is useful for active-capital identity, but it is post-trade data. Do not use it as a mechanical next-day buy signal.
6. Public A-share data usually cannot reliably expose hidden orders or true "dark" liquidity. Do not list this as a daily missing item; mention it only when the conclusion relies on hidden-liquidity or cancellation evidence.

## Market Eligibility

The user can only trade Shanghai Main Board and Shenzhen Main Board A-shares.

Exclude:

1. ChiNext / 创业板, including codes starting with `300` and `301`.
2. STAR Market / 科创板, including codes starting with `688`.
3. Beijing Stock Exchange / 北交所, including common `8xx`/`9xx` BSE codes.

When screening candidates, do not include excluded-market stocks in the final recommendation table even if they are strong.

## Ranking Rules

Rank candidates by:

1. Theme strength and catalyst freshness.
2. Role quality: leader > core anchor > high-recognition catch-up > follower.
3. Price-volume confirmation.
4. Liquidity and tradability.
5. Risk-reward from current price to invalidation level.
6. Fit with the user's current position and concentration risk.
7. Bonus only: low price, recent IPO/new listing, low-level first launch.

Low price and recent IPO/new listing never override weak role, poor liquidity, high-volume stalling, or missing stop conditions.
