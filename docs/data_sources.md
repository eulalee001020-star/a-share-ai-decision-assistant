# Data Source Requirements

Fresh A-share screening depends on accessible data. Use the best available sources in this priority order.

## Stock Pool Discovery

1. Exchange announcements and company公告 for verified catalysts.
2. Public concept/sector constituent pages when available, such as 东方财富、同花顺、财联社、证券时报、券商研报摘要.
3. Industry-chain research from public reports or company investor-relations disclosures.
4. News search for new catalysts. Rumors must be marked as unverified.

For each theme, do not stop at a single concept label. Split into sub-themes:

1. 情绪投机：最高标、连板、断板反包、次新、低价、题材情绪.
2. 国产芯片/半导体：设备、材料、封测、设计、存储、先进封装、EDA/IP、功率半导体.
3. 商业航天：卫星制造、火箭、地面设备、卫星互联网、测控、材料与元器件.
4. AI上游/电子布：AI服务器、PCB、覆铜板、玻纤布/电子布、树脂、铜箔、材料涨价.
5. 算力电力：IDC、电力设备、变压器、配电、电源、液冷、储能、绿电.

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

The 09:28 automation now treats call-auction data as a core input, not an optional enhancement. Use the data-grade system in `docs/prediction_automation_system.md`.

1. If A2 auction data is available from Tonghuashun, screenshots, or a manual export, the report may classify auction strength and assign chase/low-buy permissions.
2. If A2 data is missing but A1 realtime quote/minute data is available, the report may only output 09:30-09:35 confirmation conditions. It must not say a stock is "竞价超预期".
3. If A1 is also missing, the report is a defensive checklist only.
4. Missing auction fields should be specific:竞价成交额、09:20后撤单、封单额、队列、龙头/中军/跟风排序. Do not replace them with generic boilerplate.

Recommended manual auction export path when screenshots or Tonghuashun values are supplied:

```text
data/manual/auction/{YYYY-MM-DD}.json
```

Suggested structure:

```json
{
  "generated_at": "2026-05-15 09:27:30",
  "source": "Tonghuashun screenshot/manual export",
  "market": {
    "index_signal": "弱/中/强",
    "limit_up_count": 0,
    "limit_down_count": 0,
    "highest_board": 0
  },
  "stocks": [
    {
      "code": "002156.SZ",
      "name": "通富微电",
      "auction_price": 0,
      "auction_change_pct": 0,
      "auction_amount_cny": 0,
      "post_0920_cancel_signal": "unknown/benign/bad",
      "seal_amount_cny": 0,
      "role_signal": "leader/core/catch_up/follower/invalid"
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
