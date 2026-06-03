# Historical Policy Backtest

This validates permission and guardrail effectiveness. It does not prove live investment alpha.

## Sample

| Metric | Value |
| --- | ---: |
| Window | 2024-01-01 to 2026-05-27 |
| Codes | 101 |
| Stock-days | 57558 |
| Opening chase candidates | 827 |
| Overnight strength candidates | 3774 |
| Minimum stock-days | 5000 |
| Minimum opening candidates | 300 |
| Sample sufficient | yes |

Data source: Tencent public adjusted daily K-line, fetched through `tools/historical_policy_backtest.py`. Universe: `config/backtest_universe.example.csv` unless `--codes` or `--codes-file` is supplied.

## Policy Comparison

| Policy / Metric | Result | Product Meaning |
| --- | ---: | --- |
| Unsafe open-chase false-permission rate | 61.1% | How often gap-up chase would have become a bad permission |
| Unsafe open-chase stop-hit rate | 47.5% | Daily low breached the planned 1R stop |
| Unsafe open-chase gap-fade rate | 52.5% | Positive open faded by close |
| Unsafe close-below-previous rate | 13.8% | Open strength fully failed by close |
| Unsafe mean result R | -0.058 | Realized R of naive opening chase proxy |
| Unsafe median result R | -0.593 | Robust central result |
| Mean expected-R error | -0.258 | Result R minus naive expected R |
| Mean abs expected-R error | 1.051 | Calibration error magnitude |
| Bad next-open gap after strong close | 2.2% | Why tail plans still need next-day auction validation |
| Current no-A2 policy false-permission rate | 0.0% | Missing A2 blocks 09:28 chase permissions by design |
| Current no-A2 policy blocked candidates | 827 | Risk events withheld until 09:35 confirmation |
| Missed-valid-plan proxy rate | 29.0% | Blocked candidates that later reached at least the valid-plan R threshold by daily proxy |
| Confirmation sample count | 0 | Rows with explicit 09:35 price and VWAP input |
| Confirmation lift mean R | NA | Confirmed group mean R minus failed-confirmation group mean R, only when 09:35 input exists |

## Market-Regime Breakdown

| Regime Proxy | Count | False Permission | Stop Hit | Mean R | Median R |
| --- | ---: | ---: | ---: | ---: | ---: |
| chaotic_proxy | 138 | 70.3% | 45.7% | -0.207 | -0.672 |
| ice_point_repair_proxy | 84 | 48.8% | 36.9% | 0.057 | 0.000 |
| retreat | 181 | 69.6% | 56.4% | -0.238 | -1.000 |
| rotation_proxy | 89 | 61.8% | 39.3% | -0.042 | -0.516 |
| strong_attack_proxy | 335 | 55.5% | 48.4% | 0.067 | -0.405 |

## Role Breakdown

| Role / Proxy | Count | False Permission | Stop Hit | Mean R | Median R |
| --- | ---: | ---: | ---: | ---: | ---: |
| follower_or_weak_proxy | 470 | 93.6% | 69.8% | -0.682 | -1.000 |
| leader_or_core_proxy | 222 | 17.6% | 17.6% | 0.787 | 0.777 |
| trend_or_anchor_proxy | 135 | 19.3% | 19.3% | 0.724 | 0.752 |

## 09:35 Confirmation Layer

- Explicit 09:35 samples: 0.
- Confirmed: 0; failed: 0.
- Confirmation lift mean R: NA.
- If explicit 09:35 samples are zero, the confirmation layer is implemented but not validated by this run. Do not infer 09:35 alpha from daily bars.
- When 09:35 samples exist, the confirmation result still uses daily high/low as a coarse path proxy unless true post-09:35 minute bars are supplied.

## Product Decision

- Sample sufficient for public guardrail backtest; keep A2-specific calibration separate.
- If the unsafe open-chase false-permission and gap-fade rates are material, the missing-A2 no-09:28-chase rule remains justified.
- Missed-valid-plan proxy must be watched together with confirmation lift; a blocked candidate that later worked by daily bar is not automatically a valid 09:28 trade.
- This backtest uses public daily bars. It cannot validate true 09:15-09:25 auction amount, queue, cancellation, or sealing-order data; those still require manual or licensed A2 samples.
- Missing-A2 candidates should be downgraded into 09:35 absorption confirmation, not described as auction outperformance.
- Use this report together with `auction-calibration` once 20-60 true A2 rows and matched prediction/outcome rows exist.
