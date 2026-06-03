# Data Provider Integration Plan

本文把外部讨论里提到的数据方案收敛成可执行的数据接入路线。核心判断不变：策略和 Prompt 不是第一关，数据覆盖、来源审计和实时性才是第一关。

## 1. 设计目标

1. 数据源先落成统一文件或 API，再进入 Agent。
2. 不让模型直接“相信某个平台”；只相信已缓存、可追溯、字段完整的数据包。
3. 回测数据、实时行情、竞价盘口、板块资金迁移分开评估，不能混用。
4. 如果数据源不可用，Agent 必须降级为防守清单或人工补数，而不是补故事。

## 2. 来源分层

| 来源 | 适合层级 | 主要价值 | 主要风险 | 当前处理 |
| --- | --- | --- | --- | --- |
| Sina/Tencent public quote | A1 | 免费、低门槛、可缓存 | DNS/限流/字段不完整；不保证长期稳定 | 继续作为免费默认源 |
| AKShare/Eastmoney | B1/Tier2 | 涨跌停、市场活跃、行业/概念资金代理 | 接口容易变动；资金流只是 vendor proxy | 保留，失败不编造 |
| QMT / PTrade / 掘金 / 券商量化终端 | A1/A2/B1 | 更适合实盘分钟线、盘口、账户附近数据 | 账号、权限、资金门槛和券商差异需要实测；社区说法不能当事实 | 作为生产增强层，先导出 CSV/JSON 接入 |
| JoinQuant / 聚宽 | 历史回测 / B1 | 历史数据和研究环境较成熟 | 实时实盘权限、费用和延迟需单独核验 | 先用于回测和板块迁移样本，不直接替代实盘 A1 |
| Tushare / Tushare Pro | 历史/慢变量/A2可能层 | 财务、日线、部分特色字段 | 免费层不够；分钟/竞价权限需验证 | 作为可选增强源 |
| yfinance | 海外行情 | 美股/海外资产方便 | A 股实时与微观结构不合适 | 不作为 A 股实盘主源 |
| Fincep / 其他新工具 | 待验证 | 可能减少数据工程成本 | 来源、稳定性、字段、合规边界未知 | 进入候选清单，先做小样本字段审计 |
| 手工截图/导出 | A2/B1/C2补数 | 最快补关键缺口 | 易错、样本小、不可自动化 | 必须保留来源、时间、字段和人工置信度 |

## 3. 统一接入契约

任何外部源接入前，先回答四个问题：

1. 能不能稳定拿到目标字段，而不是只在截图里看到。
2. 能不能保存原始返回、日期、代码、来源、抓取时间。
3. 能不能把字段映射到 A0/A1/A2/B1/C2。
4. 与现有数据冲突时，能不能并存而不是覆盖。

建议统一目录：

```text
data/vendor/{provider}/{YYYY-MM-DD}/raw/
data/manual/auction/{YYYY-MM-DD}.json
data/manual/sector_flow/{YYYY-MM-DD}.json
data/manual/messages/{YYYY-MM-DD}.json
reports/{YYYY-MM-DD}-{time}-tail-data.json
```

## 4. 板块资金迁移监控

截图里的“板块资金迁移监控”对应本系统的 B1 层：市场主线、资金流入/流出、退潮和承接。它不能替代个股 A1，但能决定是否允许把某只票从观察升级。

新增本地入口：

```bash
python3 tools/trading_assistant.py sector-flow template --date YYYY-MM-DD
python3 tools/trading_assistant.py sector-flow import-csv --date YYYY-MM-DD --input data/manual/sector_flow/YYYY-MM-DD.csv --source "QMT/PTrade/JoinQuant/manual"
python3 tools/trading_assistant.py sector-flow summary --date YYYY-MM-DD
python3 tools/trading_assistant.py data-health --date YYYY-MM-DD --time 1430 --automation tail
```

CSV 最小字段：

```csv
板块,方向,净流入,评分,涨跌幅,宽度,龙头,中军,状态,来源,更新时间,备注
有色金属,承接,52.27亿,67,,, , ,观察,QMT截图,2026-06-02 14:30,
电子,退潮,-391.80亿,,,,, ,退潮,PTrade导出,2026-06-02 14:30,
```

使用边界：

1. 有 `sector_flow` 只说明 B1 板块迁移可用。
2. 若 A1 个股报价/分时/VWAP 缺失，仍不能高置信买入。
3. 来源和更新时间缺失时，只能当低置信线索。
4. 资金流是平台分类代理，不等同真实机构买卖。

## 5. 接入优先级

| 优先级 | 动作 | 验收标准 |
| --- | --- | --- |
| P0 | 做好外部 B1 板块资金迁移导入 | `data-health` 能识别手工/外部 `sector_flow`，并仍受 A1 权限约束 |
| P1 | 选一个实盘 A1 数据源做最小适配 | 6 只持仓/观察股在 09:35、11:30、13:05、14:30 覆盖 >=80% |
| P2 | 加 A2 竞价导入或截图 OCR 流程 | 20 个交易日核心字段完整率可统计 |
| P3 | 建历史分钟/板块迁移回测样本 | 能比较板块流入/流出对次日延续的校准价值 |
| P4 | 再考虑 Coze/网页产品化 | 后端仍使用本地数据健康门和风险引擎 |

## 6. 不做的事

1. 不因为某工具“看起来可用”就绕过 data-health。
2. 不把回测漂亮当实盘有效。
3. 不把没有来源时间的社区截图当高置信数据。
4. 不把 yfinance 这类海外友好库硬套到 A 股实时交易。
5. 不接自动下单；本项目仍是研究和交易计划辅助。
