# A-Share Workflow Runbook

## Current Workflows

项目保留两类日内自动化：

1. 09:28 竞价预测与开盘计划：根据 09:15-09:25 竞价、持仓、板块龙头/中军/补涨和最新消息，输出场景评分、事件概率、期望 R 和开盘执行权限。
2. 14:30 尾盘预测与隔夜计划：基于 collector 数据、日内结构、09:28 预测复盘和明日竞价验证条件，对观察股给出隔夜概率、期望 R 和次日验证条件。

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
python3 tools/trading_assistant.py render theme --date 2026-05-14
python3 tools/trading_assistant.py render single --date 2026-05-14
python3 tools/trading_assistant.py data-health --date 2026-05-14 --time 1430 --automation tail
python3 tools/trading_assistant.py auction-template --date 2026-05-14
python3 tools/trading_assistant.py prediction template --date 2026-05-14 --automation auction
```

Default outputs:

1. `reports/{YYYY-MM-DD}-0928-auction-run.md`
2. `reports/{YYYY-MM-DD}-1430-tail-check-run.md`
3. `reports/{YYYY-MM-DD}-theme-screening-run.md`
4. `reports/{YYYY-MM-DD}-single-stock-run.md`

Run packets are workflow inputs, not final reports.

## Data Rules

Daily reports should focus on decision-changing facts and data permission:

1. A0 account/risk status, including current position,可用数量, cost, stop lines, and risk budget.
2. A1 holdings/watchlist quote, turnover, volume ratio, VWAP, 5/10/20/60-day structure and stop lines.
3. A2 09:15-09:25 auction price, auction amount, post-09:20 cancellation, seal amount, and leader/core/follower auction ranking for 09:28.
4. B1 sector role comparison, breadth, limit-up/down, opened-board, consecutive-board height, and losing-money effect.
5. B2/B3/C data only as probability modifiers, not standalone buy/sell triggers.
6. Action plan: operation, style, trigger, stop, target R, position cap, invalidation and do-not-trade condition.

Do not fill reports with chronic missing fields. Chips, full Level-2 queue, hidden liquidity, realtime holder changes, fund/HK-connect updates and unstable individual fund-flow endpoints are Tier 3 context. Mention them only if they are supplied by Tonghuashun/screenshots/export or their absence directly blocks a conclusion.

For prediction outputs, each actionable plan must include base rate, base-rate source, base-rate sample size, positive adjustments, negative adjustments, success/failure/noise probability, expected R, and data grade. If data grade is below the plan's required permission, the plan must be downgraded automatically. If base-rate source or sample size is missing, the probability must be marked as uncalibrated.

## Collectors

Before 14:30 reports:

```bash
python3 tools/trading_assistant.py collect tail-data --date 2026-05-14 --time 1430
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
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 0928 --automation auction
```

## Prediction Logs

Predictions and outcomes are auditable artifacts:

1. `reports/predictions/{YYYY-MM-DD}-predictions.jsonl`
2. `reports/outcomes/{YYYY-MM-DD}-outcomes.jsonl`
3. `reports/behavior/{YYYY-MM-DD}-events.jsonl`

Use:

```bash
python3 tools/trading_assistant.py prediction template --date YYYY-MM-DD --automation auction
python3 tools/trading_assistant.py prediction summary --date YYYY-MM-DD
python3 tools/prediction_replay_evaluation.py --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl --behavior reports/behavior/YYYY-MM-DD-events.jsonl
```

Templates are not predictions by themselves. They are the structured rows the automation must fill with probabilities and expected R.

## Automation Limits

Weekday scheduling does not know the full China A-share holiday calendar. Each automation must verify trading-day status inside the task. If the holiday check is unavailable, mark uncertainty and avoid high-confidence execution plans.
