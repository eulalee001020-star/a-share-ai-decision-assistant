# A股助手运行包｜2026-05-22｜14:30 尾盘预测与隔夜计划

> This is a shortened public sample. Real run packets are generated locally and ignored by Git.

## 1. Data Health

| Layer | Coverage | Status | Effect |
| --- | ---: | --- | --- |
| A0 account/risk | 100% | available | Position sizing can be calculated |
| A1 quote/minute/MA | 88% | available | Stock-level evidence can be used |
| B1 market breadth/theme | available | available | Market regime can be classified |
| Optional proxies | partial | modifier only | Cannot prove true institutional intent |

## 2. Context Packet

- Portfolio config: `config/portfolio.example.json`
- Data rules: `docs/data_sources.md`
- Prediction framework: `docs/prediction_automation_system.md`
- Prompt contract: `prompts/tail_check.md`

## 3. Output Contract

The model must separate:

1. Facts: sourced quote, turnover, VWAP, MA, breadth, and catalyst fields.
2. Inferences: market regime, sector role, probability adjustments.
3. Plans: trigger, stop, target-R, invalidation, and do-not-trade condition.
4. Logs: JSONL rows for prediction and outcome calibration.

## 4. JSONL Row Sample

```json
{
  "automation": "tail",
  "code": "002156.SZ",
  "event": "next auction holds above validation level",
  "success_probability": 0.46,
  "failure_probability": 0.31,
  "noise_probability": 0.23,
  "target_r": 1.8,
  "expected_r": 0.47,
  "data_grade": "A",
  "confidence": "medium"
}
```
