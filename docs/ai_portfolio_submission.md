# AI Portfolio Overview｜A 股投资辅助决策 Agent

## 1. 项目介绍

A 股投资辅助决策 Agent 是一套面向盘前和盘中交易决策的 AI 工作流系统。系统不自动下单、不承诺收益，而是将市场状态、板块结构、个股证据栈、持仓风险和用户意图收敛为可审计的运行包，并用数据健康门限制模型输出权限。

核心目标是提高交易前决策质量：事实来源清楚、推理边界清楚、交易计划可执行、失败条件可复盘。

这个项目采用产品化方式组织 AI 能力：先定义用户场景和风险边界，再拆出数据接入、权限判断、Agent 推理、风控、日志、验证和复盘。它不是一个只展示界面的 Demo，而是一个可以本地运行、可以回归测试、可以继续接入外部数据源的 MVP。

当前公开版本适合作为 AI 产品作品集阅读：它展示如何在高风险场景中设计 AI Native 工作流、如何与研发讨论数据和模型边界、如何用测试与 replay 降低幻觉和越权输出风险。

## 2. 与 AI 产品岗位的能力对应

| 能力维度 | 项目体现 | 可核验证据 |
| --- | --- | --- |
| 场景理解与价值定义 | 把“预测涨跌”重构为“提升交易前决策质量和风险纪律” | `docs/product_overview.md` |
| AI Native 工作流 | 将 Agent 拆成数据健康门、运行包、Prompt 契约、风控引擎和复盘日志 | `docs/agent_architecture.md` |
| 技术边界判断 | 明确 AI 不补数据、不自动下单、不把资金流代理写成真实机构意图 | `docs/data_sources.md`、`docs/privacy_and_compliance.md` |
| MVP 快速落地 | 本地 CLI、样例配置、静态 Demo、Prompt、输入输出样例和测试用例组成最小闭环 | `tools/trading_assistant.py`、`docs/demo/index.html` |
| 评测与效果对比 | 37 条 guardrail 用例、历史权限回测、三个月可靠性回测和概率校准方案 | `docs/validation_report.md` |
| Harness 架构思维 | 用可审计输入、权限上限、结构化日志和回归测试约束模型输出 | `docs/workflow_prompts_io.md` |
| ToB/SaaS 交付意识 | 隐私隔离、外部 provider 接入路线、运行手册和可配置风险参数 | `docs/data_provider_integration_plan.md`、`docs/runbook.md` |

## 3. 交付闭环

```text
用户场景 -> 产品规则 -> 数据权限 -> Agent 工作流 -> 风控计算 -> 可执行计划 -> 复盘日志 -> 校准迭代
```

项目中的每个模块都保留了可追踪证据：需求和边界写入产品文档，关键规则写入配置和 Prompt，运行器生成可审计包，测试用例验证输出权限，历史 replay 用于检查保守规则是否仍然合理。公开版本不把这些验证包装成收益证明，只说明系统约束可以被重复检查。

完整证明材料见 [Project Proof](project_proof.md)：该页面按问题定义、用户流程、产品化架构、评测体系、失败迭代、部署边界和个人贡献展开，适合作为项目页阅读。交付型能力证据见 [PRD Excerpt](prd_excerpt.md)、[Launch Metrics](launch_metrics.md) 和 [Project Plan](project_plan.md)。

## 4. 真实问题

A 股交易者面对行情、公告、题材、盘口和持仓盈亏时，容易出现三类问题：

1. 信息过载：多个信号同时变化，容易被单一强信号牵引。
2. 决策不可复盘：结论停留在“看好/不看好”，缺少触发、止损、失效和复盘字段。
3. 风控滞后：先交易，后解释；亏损后容易用沉没成本替代重新评估。

本项目把这些问题拆成产品和系统约束，而不是让模型直接输出确定性买卖判断。

## 5. AI 方案设计

| 模块 | 作用 | 边界 |
| --- | --- | --- |
| 数据健康门 | 判断 A0/A1/A2/B1 等证据是否足够 | 数据不足时降低输出权限 |
| 运行包构建 | 汇总持仓、风险规则、用户请求和数据缺口 | 避免无关上下文淹没关键约束 |
| Prompt 工作流 | 按固定顺序组织市场、板块、个股和计划 | 不允许跳过事实/推理/计划分离 |
| 风控引擎 | 用止损距离、账户风险预算和市场状态倒推仓位 | 仓位不是模型信心表达 |
| 复盘校准 | 记录概率、expected R、结果和错误类型 | 不用单次盈亏替代样本复盘 |

AI 在系统中负责证据组织、冲突分析和自然语言计划表达；规则层负责数据权限、仓位、止损、输出降级和合规边界。

## 6. 核心能力证据

| 能力维度 | 项目证据 |
| --- | --- |
| AI 产品问题定义 | `docs/portfolio.md`、`docs/product_overview.md` |
| 完整项目证明 | `docs/project_proof.md` |
| PRD 和验收标准 | `docs/prd_excerpt.md` |
| 上线指标和反馈闭环 | `docs/launch_metrics.md` |
| 项目推进和风险管理 | `docs/project_plan.md` |
| Agent 工作流设计 | `docs/agent_architecture.md`、`docs/runbook.md` |
| Prompt 工程 | `prompts/*.md`、`docs/workflow_prompts_io.md` |
| 上下文与运行包 | `tools/trading_assistant.py render ...`、`examples/run_packet.sample.md` |
| 数据健康门 | `docs/data_sources.md`、`config/decision_weights.json` |
| 风控约束 | `config/portfolio.example.json`、`docs/opening_permission_model.md` |
| 评测与失败案例 | `docs/evaluation_cases.md`、`docs/validation_report.md` |
| 历史回测与校准 | `docs/historical_policy_backtest.md`、`docs/reliability_backtest_3m.md` |
| 隐私与合规 | `docs/privacy_and_compliance.md`、`.gitignore` |

## 7. Demo 与工程入口

静态互动 Demo：`docs/demo/index.html`

Demo 展示 Agent 工作台的核心链路：任务选择、数据健康门、数据等级、输出权限、推理链路、风险约束和复盘指标。

核心运行命令：

```bash
python3 tools/trading_assistant.py validate
python3 tools/trading_assistant.py render auction --date 2026-05-22 --stdout
python3 tools/trading_assistant.py render user --date 2026-05-22 --themes 半导体 AI硬件 --codes 002156.SZ 603920.SH --stdout
python3 tools/portfolio_validation.py --format markdown
python3 -m unittest discover -s tests
```

## 8. 验证结果

公开验证集包含 37 条 guardrail 用例，覆盖数据权限、RAG 证据边界、风控完整性、用户误用拦截、用户给定对象和开盘承接纪律。

验证结论证明的是产品约束可被重复检查，不证明投资收益。历史权限回测用于验证“缺 A2 不允许 09:28 追强”等权限纪律的必要性，而不是证明长期收益能力。

## 9. 风险边界

1. 系统只做研究、计划和风险提示，不自动下单。
2. 输出不构成投资建议，不承诺收益。
3. 公开版本使用脱敏样例配置，不包含真实账户、真实持仓、手工截图或本地报告。
4. 历史回测用于验证权限纪律和风险规则，不作为收益承诺。
