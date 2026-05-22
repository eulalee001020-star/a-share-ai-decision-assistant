# Trading Assistant State Example

Last updated: 2026-05-22 Asia/Shanghai

This file is a public, synthetic continuity note. For real local usage, create a private `docs/trading_assistant_state.md`; it is ignored by Git.

## 1. Product State

The assistant keeps two daily workflows:

1. 09:28 auction check: classify the market regime, update opening permission, and generate event probabilities.
2. 14:30 tail-session check: review morning predictions, estimate overnight risk, and prepare next-day validation.

## 2. Demo Account

The public demo account is loaded from `config/portfolio.example.json`.

1. Total assets: CNY 100,000.
2. Current position: 38%.
3. Cash: 62%.
4. Max planned loss per trade: 2% of account.
5. Public data is synthetic and does not represent a real account.

## 3. Continuity Rules

1. Read `AGENTS.md`, `config/portfolio.example.json`, `docs/data_sources.md`, and `docs/prediction_automation_system.md` before producing a demo report.
2. If private `config/portfolio.json` exists, it should override the sample configuration locally.
3. Every output must separate fact, inference, plan, and risk boundary.
4. If data is missing, lower confidence and restrict allowed actions.
