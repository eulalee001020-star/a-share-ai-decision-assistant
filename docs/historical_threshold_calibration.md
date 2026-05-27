# Historical Threshold Calibration

- Window: 2026-04-27 to 2026-05-27
- Trading-day samples: 20
- Public demo stocks: 002156.SZ, 600584.SH, 600601.SH, 600206.SH, 002886.SZ
- Market data source: Tencent public daily qfq K-line and 15-minute K-line
- B1 source: AKShare/Eastmoney limit-up and limit-down pools, best effort
- A2 auction source: not available from the public historical APIs used here

## Summary

| Metric | Result | Product Decision |
| --- | ---: | --- |
| A1 >= 80% at 09:28 confirmation proxy | 20/20 days | Keep 80% as high-confidence threshold |
| A1 >= 80% at 14:30 | 20/20 days | Keep 80% as high-confidence threshold |
| B1 market structure available | 20/20 days | Missing B1 still caps regime confidence at medium |
| A2 historical auction available | 0/20 days | Keep missing-A2 downgrade; requires Tonghuashun/manual export |
| Avg abs open gap | 1.69% | Opening risk is non-trivial, no chase without A2 |
| Avg first-15m range | 3.77% | Use 09:30-09:45 confirmation when A2 missing |
| Gap-up faded by 09:45 | 20.00% | Positive open alone is insufficient |
| Avg 14:30-to-close absolute move | 0.69% | Tail plans need close confirmation and stop |
| Avg next-open absolute gap | 1.69% | Overnight plans need next-day auction validation |

## 09:28 Samples

| Date | A1 Coverage | A2 | B1 | Limit Up | Limit Down | Avg Open Gap | First-15m Range | Fade Rate | Permission |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-04-27 | 100.0% | no | yes | 0 | 0 | NA% | 2.41% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-04-28 | 100.0% | no | yes | 0 | 0 | 0.86% | 3.45% | 20.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-04-29 | 100.0% | no | yes | 0 | 0 | 1.29% | 2.50% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-04-30 | 100.0% | no | yes | 0 | 0 | 1.66% | 2.97% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-06 | 100.0% | no | yes | 0 | 0 | 4.16% | 2.33% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-07 | 100.0% | no | yes | 100 | 4 | 2.13% | 3.08% | 60.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-08 | 100.0% | no | yes | 98 | 2 | 1.47% | 2.73% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-11 | 100.0% | no | yes | 95 | 3 | 3.46% | 4.26% | 20.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-12 | 100.0% | no | yes | 58 | 7 | 1.15% | 4.47% | 20.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-13 | 100.0% | no | yes | 113 | 2 | 1.93% | 2.39% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-14 | 100.0% | no | yes | 55 | 17 | 0.36% | 4.29% | 60.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-15 | 100.0% | no | yes | 54 | 15 | 0.96% | 4.35% | 20.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-18 | 100.0% | no | yes | 82 | 18 | 0.98% | 4.52% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-19 | 100.0% | no | yes | 90 | 8 | 1.44% | 3.31% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-20 | 100.0% | no | yes | 61 | 22 | 0.83% | 4.14% | 0.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-21 | 100.0% | no | yes | 34 | 25 | 1.54% | 3.77% | 40.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-22 | 100.0% | no | yes | 115 | 5 | 0.62% | 3.71% | 40.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-25 | 100.0% | no | yes | 103 | 15 | 1.67% | 5.23% | 20.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-26 | 100.0% | no | yes | 46 | 16 | 2.07% | 4.33% | 40.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |
| 2026-05-27 | 100.0% | no | yes | 47 | 22 | 3.54% | 7.24% | 40.00% | 缺 A2：只允许 09:30-09:45 确认，禁止追强。 |

## 14:30 Samples

| Date | A1 Coverage | B1 | Limit Up | Limit Down | Tail-to-close Move | Next-open Gap | Permission |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 2026-04-27 | 100.0% | yes | 0 | 0 | 0.20% | 0.86% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-04-28 | 100.0% | yes | 0 | 0 | 0.27% | 1.29% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-04-29 | 100.0% | yes | 0 | 0 | 0.23% | 1.66% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-04-30 | 100.0% | yes | 0 | 0 | 0.28% | 4.16% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-06 | 100.0% | yes | 0 | 0 | 0.11% | 2.13% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-07 | 100.0% | yes | 100 | 4 | 0.24% | 1.47% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-08 | 100.0% | yes | 98 | 2 | 1.02% | 3.46% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-11 | 100.0% | yes | 95 | 3 | 0.13% | 1.15% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-12 | 100.0% | yes | 58 | 7 | 0.34% | 1.93% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-13 | 100.0% | yes | 113 | 2 | 0.37% | 0.36% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-14 | 100.0% | yes | 55 | 17 | 1.86% | 0.96% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-15 | 100.0% | yes | 54 | 15 | 1.13% | 0.98% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-18 | 100.0% | yes | 82 | 18 | 0.30% | 1.44% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-19 | 100.0% | yes | 90 | 8 | 0.44% | 0.83% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-20 | 100.0% | yes | 61 | 22 | 0.19% | 1.54% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-21 | 100.0% | yes | 34 | 25 | 0.89% | 0.62% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-22 | 100.0% | yes | 115 | 5 | 0.30% | 1.67% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-25 | 100.0% | yes | 103 | 15 | 0.71% | 2.07% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-26 | 100.0% | yes | 46 | 16 | 1.80% | 3.54% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |
| 2026-05-27 | 100.0% | yes | 47 | 22 | 2.96% | NA% | A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。 |

## Calibrated Answers

1. A1 80% threshold is retained. In this replay, A1 daily/MA/15-minute coverage reached the threshold on the sampled days. Lower coverage should still downgrade output because cross-stock comparison and VWAP/MA checks become incomplete.
2. Missing A2 auction data is not treated as a small warning. Public historical sources did not expose 09:15-09:25 auction amount, post-09:20 cancel behavior, seal amount, or queue data. The replay shows opening gaps and first-15-minute ranges are material enough that the system should keep the rule: no chase, only 09:30-09:45 confirmation.
3. B1 remains a required regime input. Limit-up and limit-down counts changed materially across the month, so a stock-only view is not enough to classify strong attack, rotation, or retreat with high confidence.
4. Tail-session plans still need next-day auction validation. The 14:30-to-close and next-open gap statistics show that tail strength is not equivalent to next-day executable confirmation.

## Boundary

This is a historical data-health and guardrail calibration. It does not prove live alpha, and it does not replace a full prediction/outcome replay with Brier score and expected-R error. The missing A2 conclusion is especially important: historical public APIs were insufficient, so production use still requires Tonghuashun/manual auction export or another licensed auction source.
