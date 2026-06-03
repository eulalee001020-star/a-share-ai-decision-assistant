# A-Share Workflow Runbook

## Current Workflows

项目保留三类日内自动化：

1. 09:28 竞价预测与开盘计划：根据市场状态、板块龙头/中军/补涨、持仓和最新消息输出场景评分、事件概率、期望 R 和开盘执行权限；真实 A2 竞价只用于提前放权。
2. 13:10 下午盘午盘信息与交易计划：收集 11:30 午盘、午间消息、13:05 下午开盘承接，输出下午盘处理计划、14:30 必看条件和次日验证条件。
3. 14:30 大盘资金流向与观察机会：工作日 14:35 执行，以 14:30 为目标分时，复核大盘资金流、板块主线、尾盘强收、可观察买入机会和次日 09:35 验证优先级。

08:55/09:10 晨报已停用。上午不再维护单独晨报，避免重复生成低置信度预案。

新自动化框架以 `docs/prediction_automation_system.md` 为准。场景决定能不能打，模式决定怎么打，概率决定值不值得打，期望 R 决定打多大。

## Local Commands

公开作品集仓库默认使用 `config/portfolio.example.json`。真实使用时复制为本地私有文件：

```bash
cp config/portfolio.example.json config/portfolio.json
```

也可以用环境变量临时指定组合配置：

```bash
TRADING_ASSISTANT_PORTFOLIO=/path/to/portfolio.json python3 tools/trading_assistant.py validate
```

```bash
python3 tools/trading_assistant.py validate
python3 tools/trading_assistant.py render auction --date 2026-05-14
python3 tools/trading_assistant.py render tail --date 2026-05-14
python3 tools/trading_assistant.py render market-flow --date 2026-05-14
python3 tools/trading_assistant.py render theme --date 2026-05-14
python3 tools/trading_assistant.py render single --date 2026-05-14
python3 tools/trading_assistant.py render user --date 2026-05-14 --themes 半导体 AI硬件 --codes 002156.SZ 603920.SH
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 1430 --automation tail
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 1430 --automation tail --json
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 1430 --automation user
python3 tools/trading_assistant.py brief --date 2026-05-14 --time 0928 --automation auction
python3 tools/trading_assistant.py collect tail-data --date 2026-05-14 --time 0935 --codes 603920.SH
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 0935 --automation auction
python3 tools/trading_assistant.py collect tail-data --date 2026-05-14 --time 1130
python3 tools/trading_assistant.py collect tail-data --date 2026-05-14 --time 1305
python3 tools/trading_assistant.py collect tail-data --date 2026-05-14 --time 1430
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 1430 --automation tail
python3 tools/trading_assistant.py auction-template --date 2026-05-14
python3 tools/trading_assistant.py auction-csv-template --date 2026-05-14 --codes 603920.SH
python3 tools/trading_assistant.py auction-import-csv --date 2026-05-14 --input data/manual/auction/2026-05-14.csv
python3 tools/trading_assistant.py auction-samples --start-date 2026-05-14 --end-date 2026-05-17
python3 tools/trading_assistant.py auction-calibration --start-date 2026-05-14 --end-date 2026-06-11
python3 tools/trading_assistant.py sector-flow template --date 2026-05-14
python3 tools/trading_assistant.py sector-flow import-csv --date 2026-05-14 --input data/manual/sector_flow/2026-05-14.csv --source "QMT/PTrade/JoinQuant/manual"
python3 tools/trading_assistant.py sector-flow summary --date 2026-05-14
python3 tools/historical_policy_backtest.py --start-date 2024-01-01 --end-date 2026-05-27
python3 tools/trading_assistant.py message-evidence template --date 2026-05-14 --codes 002156.SZ --themes 半导体
python3 tools/trading_assistant.py prediction template --date 2026-05-14 --automation auction
python3 tools/trading_assistant.py prediction outcome-template --date 2026-05-14 --automation auction
python3 tools/trading_assistant.py prediction behavior-template --date 2026-05-14 --automation auction
python3 tools/trading_assistant.py review weekly --start-date 2026-05-14 --end-date 2026-05-17
```

Default outputs:

1. `reports/{YYYY-MM-DD}-0928-auction-run.md`
2. `reports/{YYYY-MM-DD}-1430-tail-check-run.md`
3. `reports/{YYYY-MM-DD}-1430-market-flow-run.md`
4. `reports/{YYYY-MM-DD}-theme-screening-run.md`
5. `reports/{YYYY-MM-DD}-single-stock-run.md`
6. `reports/{YYYY-MM-DD}-user-request-analysis-run.md`

Run packets are workflow inputs, not final reports.

## User-Supplied Analysis

When the user provides sectors, individual stocks, or asks for holding advice, use the combined workflow instead of answering directly from memory:

```bash
python3 tools/trading_assistant.py render user --date YYYY-MM-DD --themes 板块1 板块2 --codes 002156.SZ 603920.SH
python3 tools/trading_assistant.py collect tail-data --date YYYY-MM-DD --time 1430 --codes 002156.SZ 603920.SH
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 1430 --automation user
```

The combined packet forces three analyses into one chain:

1. User-given sectors: split into sub-themes, leader/core/catch-up/follower, catalyst freshness, and relation to holdings.
2. User-given stocks: run the single-stock evidence stack before any buy/add/hold/reduce/sell conclusion.
3. Current holdings: update the original thesis, compare future expected value with new candidates, and state hold/reduce/sell/add triggers.

User attention is never evidence by itself. If A1/B1 data is missing, the answer must downgrade to a manual checklist. If A2 is missing, opening chase conclusions remain prohibited.

## Manual Sector-Flow Import

When public B1 APIs fail but a terminal, QMT/PTrade/掘金/聚宽 export, or manual screenshot provides board-capital migration data, import it before running `data-health`:

```bash
python3 tools/trading_assistant.py sector-flow template --date YYYY-MM-DD
python3 tools/trading_assistant.py sector-flow import-csv --date YYYY-MM-DD --input data/manual/sector_flow/YYYY-MM-DD.csv --source "QMT/PTrade/JoinQuant/manual"
python3 tools/trading_assistant.py sector-flow summary --date YYYY-MM-DD
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 1430 --automation tail
```

This only restores B1 sector-flow context. If A1 quote/minute/VWAP coverage is still missing, buy/add/high-confidence hold remains blocked.

## Data Rules

Daily reports should focus on decision-changing facts and data permission:

1. A0 account/risk status, including current position,可用数量, cost, stop lines, and risk budget.
2. A1 holdings/watchlist quote, turnover, volume ratio, VWAP, 5/10/20/60-day structure and stop lines.
3. B1 sector role comparison, breadth, limit-up/down, opened-board, consecutive-board height, and losing-money effect.
4. 09:30-09:35 confirmation: target price versus open, target price versus VWAP, sector core synchronization, and whether the stop distance still supports positive expected R.
5. A2 09:15-09:25 auction price, auction amount, post-09:20 cancellation, seal amount, and leader/core/follower auction ranking only when deciding whether to act before 09:35.
6. B2/B3/C data only as probability modifiers, not standalone buy/sell triggers.
7. Action plan: operation, style, trigger, stop, target R, position cap, invalidation and do-not-trade condition.

Do not fill reports with chronic missing fields. Chips, full Level-2 queue, hidden liquidity, realtime holder changes, fund/HK-connect updates and unstable individual fund-flow endpoints are Tier 3 context. Mention them only if they are supplied by Tonghuashun/screenshots/export or their absence directly blocks a conclusion.

For prediction outputs, each actionable plan must include base rate, base-rate source, base-rate sample size, positive adjustments, negative adjustments, success/failure/noise probability, expected R, and data grade. If data grade is below the plan's required permission, the plan must be downgraded automatically. If base-rate source or sample size is missing, the probability must be marked as uncalibrated.

## Collectors

Before 14:30 reports:

```bash
python3 tools/trading_assistant.py collect tail-data --date 2026-05-14 --time 1430
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 1430 --automation tail
```

For the independent 14:30 market-flow automation, use `prompts/tail_market_flow_check.md` and save the final report to:

```text
reports/{YYYY-MM-DD}-1430-market-flow-opportunity-scan.md
```

For manual single-stock research:

```bash
python3 tools/trading_assistant.py collect stock-data --code 002156.SZ --date 2026-05-14 --time 1430
```

Collector CSV/JSON files are generated artifacts. Keep only useful recent files; historical report clutter can be deleted.

Before 09:28 reports, use local Tonghuashun or user screenshots for A2 data when possible. If values are manually extracted, store them at:

```bash
data/manual/auction/YYYY-MM-DD.json
```

Then run:

```bash
python3 tools/trading_assistant.py auction-template --date YYYY-MM-DD
python3 tools/trading_assistant.py auction-csv-template --date YYYY-MM-DD --codes 当日核心票1 当日核心票2
python3 tools/trading_assistant.py auction-import-csv --date YYYY-MM-DD --input data/manual/auction/YYYY-MM-DD.csv
python3 tools/trading_assistant.py auction-samples --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 0928 --automation auction
```

`auction-samples` is the A2 calibration ledger. If it shows no usable rows or no core-complete rows, the 09:28 workflow must keep the no-chase downgrade.

If A2 is missing, switch the candidate to a first-five-minute confirmation workflow:

```bash
python3 tools/trading_assistant.py collect tail-data --date YYYY-MM-DD --time 0935 --codes 当日核心票1 当日核心票2
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 0935 --automation auction
python3 tools/trading_assistant.py brief --date YYYY-MM-DD --time 0935 --automation auction
```

The 09:35 check is the practical high-value layer for public-data operation. It can allow post-open confirmation plans when A1/B1 and risk-reward pass, but it must not be retroactively described as "竞价超预期".

Minimum CSV columns:

```csv
股票代码,竞价价,竞价成交额,09:20后撤单,板块角色
002156,10.50,1.2亿,良性,中军
```

Accepted role values include `龙头/leader`, `中军/核心/core`, `补涨/catch_up`, `跟风/follower`, and `无效/invalid`. Accepted post-09:20 cancellation values include `良性/benign`, `恶性/bad`, and `未知/unknown`.

For the first 20 trading days, sample only:

1. Current holdings.
2. Watchlist names.
3. Same-day sector core names supplied with `--codes`.

Do not expand to the whole market until the workflow has 20-60 core-complete A2 rows and matched prediction/outcome rows.

After the sample window, run:

```bash
python3 tools/trading_assistant.py auction-calibration --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

This compares A2-confirmed and no-A2 groups on false-permission rate, 09:35 invalidation rate, and expected-R error. If A2 rows or matched outcomes are below the minimum threshold, keep the no-chase downgrade.

For larger public-market validation of the permission rule, run:

```bash
python3 tools/historical_policy_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python3 tools/historical_policy_backtest.py --start-date 2026-02-28 --end-date 2026-05-27 --output docs/historical_policy_backtest_3m.md --json-output reports/backtests/historical_policy_backtest_3m.json
python3 tools/historical_policy_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --confirmation-file data/manual/opening_confirmation/YYYY-MM-DD-to-YYYY-MM-DD.csv --role-file data/manual/roles/YYYY-MM-DD-to-YYYY-MM-DD.csv
```

Default universe: `config/backtest_universe.example.csv`. The default generated report is `docs/historical_policy_backtest.md`; raw observations are written to `reports/backtests/historical_policy_backtest.json`. For rolling-window checks, write to a separate report such as `docs/historical_policy_backtest_3m.md` and summarize the product decision in `docs/reliability_backtest_3m.md`. Use `--confirmation-file` when saved 09:35 price/VWAP data exists, and `--role-file` when leader/core/catch-up/follower labels are manually or terminal-derived. Template files are `config/opening_confirmation.example.csv` and `config/role_labels.example.csv`. Without those files, the report still calculates daily guardrails and role proxies, but it must not claim 09:35 confirmation alpha. This validates risk-permission discipline, not live alpha.

## Message Evidence

Use message evidence files to keep announcements, news, industry-chain materials, and manual notes auditable:

```bash
python3 tools/trading_assistant.py message-evidence template --date YYYY-MM-DD --codes 002156.SZ --themes 半导体
python3 tools/trading_assistant.py message-evidence summary --date YYYY-MM-DD
```

Default path:

```text
data/manual/messages/YYYY-MM-DD.json
```

Missing sources, stale materials, rumors, and conflicts must be visible. A missing-source or rumor item can inform a watchlist, but cannot become a high-confidence catalyst.

## Prediction Logs

Predictions and outcomes are auditable artifacts:

1. `reports/predictions/{YYYY-MM-DD}-predictions.jsonl`
2. `reports/outcomes/{YYYY-MM-DD}-outcomes.jsonl`
3. `reports/behavior/{YYYY-MM-DD}-events.jsonl`

Use:

```bash
python3 tools/trading_assistant.py prediction template --date YYYY-MM-DD --automation auction
python3 tools/trading_assistant.py prediction outcome-template --date YYYY-MM-DD --automation auction
python3 tools/trading_assistant.py prediction behavior-template --date YYYY-MM-DD --automation auction
python3 tools/trading_assistant.py prediction summary --date YYYY-MM-DD
python3 tools/prediction_replay_evaluation.py --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl --behavior reports/behavior/YYYY-MM-DD-events.jsonl
```

Templates are not predictions, outcomes, or behavior samples by themselves. Weekly review counts them only after probabilities, actual/result/error fields, or attempted-action/rule/execution fields are filled.

## Short Brief And Weekly Review

Before long reports, generate the short permission-first view:

```bash
python3 tools/trading_assistant.py brief --date YYYY-MM-DD --time 0928 --automation auction
```

Weekly review aggregates A2 coverage, prediction/outcome matching, behavior risk events, message evidence quality, data-grade distribution, and error types:

```bash
python3 tools/trading_assistant.py review weekly --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

Use the weekly review to adjust process and factor weights. Do not upgrade base rate or loosen data gates if outcome matching, behavior logging, or A2 coverage is still weak.

## Automation Limits

Weekday scheduling does not know the full China A-share holiday calendar. Each automation must verify trading-day status inside the task. If the holiday check is unavailable, mark uncertainty and avoid high-confidence execution plans.
