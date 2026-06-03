# Historical Policy Backtest

This validates permission and guardrail effectiveness. It does not prove live investment alpha.

## Sample

| Metric | Value |
| --- | ---: |
| Window | 2026-02-28 to 2026-05-27 |
| Codes | 99 |
| Stock-days | 5635 |
| Opening chase candidates | 60 |
| Overnight strength candidates | 332 |
| Minimum stock-days | 5000 |
| Minimum opening candidates | 300 |
| Sample sufficient | no |

Data source: Tencent public adjusted daily K-line, fetched through `tools/historical_policy_backtest.py`. Universe: `config/backtest_universe.example.csv` unless `--codes` or `--codes-file` is supplied.

## Policy Comparison

| Policy / Metric | Result | Product Meaning |
| --- | ---: | --- |
| Unsafe open-chase false-permission rate | 55.0% | How often gap-up chase would have become a bad permission |
| Unsafe open-chase stop-hit rate | 33.3% | Daily low breached the planned 1R stop |
| Unsafe open-chase gap-fade rate | 51.7% | Positive open faded by close |
| Unsafe close-below-previous rate | 13.3% | Open strength fully failed by close |
| Unsafe mean result R | 0.015 | Realized R of naive opening chase proxy |
| Unsafe median result R | -0.114 | Robust central result |
| Mean expected-R error | -0.185 | Result R minus naive expected R |
| Mean abs expected-R error | 0.884 | Calibration error magnitude |
| Bad next-open gap after strong close | 3.6% | Why tail plans still need next-day auction validation |
| Current no-A2 policy false-permission rate | 0.0% | Missing A2 blocks 09:28 chase permissions by design |
| Current no-A2 policy blocked candidates | 60 | Risk events withheld until 09:35 confirmation |
| Missed-valid-plan proxy rate | 25.0% | Blocked candidates that later reached at least the valid-plan R threshold by daily proxy |
| Confirmation sample count | 0 | Rows with explicit 09:35 price and VWAP input |
| Confirmation lift mean R | NA | Confirmed group mean R minus failed-confirmation group mean R, only when 09:35 input exists |

## Market-Regime Breakdown

| Regime Proxy | Count | False Permission | Stop Hit | Mean R | Median R |
| --- | ---: | ---: | ---: | ---: | ---: |
| chaotic_proxy | 8 | 75.0% | 37.5% | -0.342 | -0.564 |
| ice_point_repair_proxy | 9 | 33.3% | 22.2% | 0.427 | 0.297 |
| retreat | 28 | 53.6% | 42.9% | 0.081 | -0.205 |
| rotation_proxy | 10 | 60.0% | 20.0% | -0.206 | -0.486 |
| strong_attack_proxy | 5 | 60.0% | 20.0% | -0.078 | -0.098 |

## Role Breakdown

| Role / Proxy | Count | False Permission | Stop Hit | Mean R | Median R |
| --- | ---: | ---: | ---: | ---: | ---: |
| follower_or_weak_proxy | 31 | 100.0% | 58.1% | -0.742 | -1.000 |
| leader_or_core_proxy | 22 | 9.1% | 9.1% | 0.725 | 0.443 |
| trend_or_anchor_proxy | 7 | 0.0% | 0.0% | 1.142 | 0.891 |

## 09:35 Confirmation Layer

- Explicit 09:35 samples: 0.
- Confirmed: 0; failed: 0.
- Confirmation lift mean R: NA.
- If explicit 09:35 samples are zero, the confirmation layer is implemented but not validated by this run. Do not infer 09:35 alpha from daily bars.
- When 09:35 samples exist, the confirmation result still uses daily high/low as a coarse path proxy unless true post-09:35 minute bars are supplied.

## Product Decision

- Sample below target; do not use this run to loosen permissions.
- If the unsafe open-chase false-permission and gap-fade rates are material, the missing-A2 no-09:28-chase rule remains justified.
- Missed-valid-plan proxy must be watched together with confirmation lift; a blocked candidate that later worked by daily bar is not automatically a valid 09:28 trade.
- This backtest uses public daily bars. It cannot validate true 09:15-09:25 auction amount, queue, cancellation, or sealing-order data; those still require manual or licensed A2 samples.
- Missing-A2 candidates should be downgraded into 09:35 absorption confirmation, not described as auction outperformance.
- Use this report together with `auction-calibration` once 20-60 true A2 rows and matched prediction/outcome rows exist.
