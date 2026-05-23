# A股数据接口输出示例｜2026-05-22

## 1. 请求参数

- 接口：`tail-data`
- 日期：`2026-05-22`
- 时间：`1430`
- 代码：`002156.SZ 600584.SH 600601.SH`

## 2. 本地命令

```bash
python3 tools/trading_assistant.py collect tail-data --date 2026-05-22 --time 1430 --codes 002156.SZ 600584.SH 600601.SH
python3 tools/trading_assistant.py data-health --date 2026-05-22 --time 1430 --automation tail
```

## 3. 输出文件

```text
reports/2026-05-22-1430-tail-data.csv
reports/2026-05-22-1430-tail-data.json
```

## 4. JSON 结构示意

```json
{
  "coverage": {
    "code_count": 3,
    "quote_count": 3,
    "minute_count": 3,
    "daily_metric_count": 3
  },
  "rows": [
    {
      "code": "002156.SZ",
      "price": 50.0,
      "amount": 1200000000,
      "target_vwap": 49.8,
      "ma5": 50.2,
      "ma10": 49.6,
      "ma20": 48.9,
      "data_quality": "完整"
    }
  ]
}
```
