# A-Share AI Research & Trading Decision Assistant

一个面向高风险决策场景的 AI Native Agent MVP。项目以 A 股盘前/盘中交易辅助为场景，把实时行情、板块结构、消息证据、持仓风险和用户意图收敛成可审计的工作流：先判断数据权限，再组织事实和推理，最后输出带触发、止损、仓位、失效条件和复盘字段的行动计划。

> 本项目只做研究、计划和风险提示，不自动下单，不承诺收益，不构成投资建议。

![A 股投资辅助 Agent 工作台截图](docs/assets/demo-workbench.png)

## For Recruiters

| 30 秒问题 | 直接答案 |
| --- | --- |
| What it is | 一个高风险决策支持 Agent MVP，用交易辅助场景验证 AI 如何在数据不完整、风险高、时效强的业务中稳定输出。 |
| What I built | 数据健康门、运行包构建器、Prompt 工作流、风控引擎、prediction/outcome/behavior 日志、37 条 guardrail 评测集和静态 Demo。 |
| What it proves | AI 产品定义、Agent 架构、RAG/数据边界、模型不确定性控制、评测体系、MVP 工程落地和 ToB/SaaS 交付意识。 |
| What it does not claim | 不自动交易，不证明投资收益，不包含真实账户/持仓/截图数据，不把历史 replay 包装成长期收益能力。 |

## My Role / Ownership

这是一个个人主导的 AI 产品与工程作品。核心工作包括：

1. 产品定义：将“预测涨跌”重构为“提升决策质量、权限控制和风险纪律”的 Agent 产品问题。
2. 架构设计：拆分数据接入、数据健康门、运行包、Prompt 契约、风控引擎、日志和复盘校准。
3. 规则设计：定义 A0/A1/A2/B1 数据分层、缺数据降级、09:35 承接确认、1R 风控和反沉没成本机制。
4. 工程实现：实现本地 CLI、样例配置、运行包生成、数据健康检查、历史权限回测和验证脚本。
5. 评测与文档：设计 37 条 guardrail 用例、失败案例、验证报告、产品说明、架构说明和可互动 Demo。

开发过程中使用 AI 工具加速代码草稿、文档整理和测试迭代；产品边界、架构取舍、风控规则、验证标准和公开内容由个人审阅和定稿。

## Quick Links

- [AI Portfolio Overview](docs/ai_portfolio_submission.md): 作品集总览
- [Project Proof](docs/project_proof.md): 问题定义、用户流程、架构、评测、失败迭代和个人贡献
- Product Delivery Evidence: [PRD Excerpt](docs/prd_excerpt.md)、[Launch Metrics](docs/launch_metrics.md)、[Project Plan](docs/project_plan.md)
- [Product Case Study](docs/portfolio.md): 产品案例与取舍
- [Interactive Demo](docs/demo/index.html): Agent 工作台 Demo
- [Agent Architecture](docs/agent_architecture.md): 架构与模块边界
- [Validation Report](docs/validation_report.md): 37 条 guardrail 与回测证据
- [Workflow / Prompts / IO](docs/workflow_prompts_io.md): 工作流、Prompt 和输入输出样例

## 真实市场需求

A 股交易者每天面对三个高频痛点：

1. 信息过载：公告、题材、盘口、板块和持仓风险同时变化，容易只看单一信号。
2. 决策不可复盘：判断写成“看好/不看好”，缺少概率、触发条件和失败条件。
3. 风控滞后：先买入，后找理由；亏损后容易用沉没成本替代重新评估。

本项目的产品目标不是“预测涨跌”，而是把 AI 输出限制在可验证、可复盘、可执行的决策框架内：数据不足就降级，市场状态不允许就不新增风险，任何买入/加仓都必须有 1R、结构止损、目标 R、仓位上限和不交易条件。

## 核心能力

| 能力 | 对应文件 | 展示点 |
| --- | --- | --- |
| 交易场景识别 | `docs/prediction_automation_system.md` | 强进攻、轮动、退潮、冰点修复、混沌五类状态 |
| 风控发动机 | `config/portfolio.example.json`、`tools/trading_assistant.py` | 从止损距离倒推仓位，避免用主观信心定仓 |
| 数据权限门 | `docs/data_sources.md`、`docs/data_provider_integration_plan.md`、`config/decision_weights.json` | A0/A1/B1/09:35承接作为主证据，A2/筹码/资金流作为可选修正；`data-health` 输出结构化动作权限上限 |
| 开盘权限模型 | `docs/opening_permission_model.md` | 市场状态、板块共振、09:35承接和风险收益比是主证据；A2只用于09:28提前放权 |
| 消息面 RAG 设计 | `docs/evaluation_cases.md` | 交易所/公司公告、主流证券报新闻和行情终端数据的混合检索、引用一致性和过期拦截 |
| Agent Prompt | `prompts/*.md` | 09:28、14:30、主题筛选、单股深研、用户综合分析五类任务 |
| 用户输入综合分析 | `prompts/user_request_analysis.md`、`tools/trading_assistant.py render user` | 用户给定板块、用户给定个股、当前持仓评价和建议统一进入同一数据权限门 |
| 本地运行包 | `tools/trading_assistant.py render ...` | 自动组装上下文、配置校验、缺失数据和执行提示词 |
| 预测复盘 | `prediction template/summary` | 事件概率、期望 R、结果日志与校准闭环 |
| Agent 架构 | `docs/agent_architecture.md` | 用最小必要模块串起数据、推理、风控和复盘 |
| 可审计产物 | `examples/workflow_trace.sample.json`、`examples/run_packet.sample.md` | 证明数据包、运行包、预测日志和复盘日志如何串起来 |
| 项目证明材料 | `docs/project_proof.md` | 问题定义、原流程/新流程、产品化架构、评测用例、失败迭代、成本边界和个人贡献 |
| PRD 片段 | `docs/prd_excerpt.md` | 以 09:35 开盘承接确认为例，展示用户故事、功能范围、输入输出、异常降级、验收标准和埋点 |
| 上线指标 | `docs/launch_metrics.md` | 展示从 MVP 到试点应追踪的产品可用性、AI 质量、风险行为、成本和稳定性指标 |
| 项目推进 | `docs/project_plan.md` | 展示需求、PRD、数据、Agent、风控、验证、Demo、灰度和生产化评审的交付计划 |
| 公开验证集 | `tools/portfolio_validation.py`、`docs/validation_report.md` | 37 条离线 guardrail 用例，覆盖数据缺失、RAG、风控、用户误用、用户给定对象、开盘承接和计划完整性 |
| 历史阈值校准 | `tools/historical_threshold_calibration.py`、`docs/historical_threshold_calibration.md` | 过去一个月 20 个交易日、100 个 09:28 观察、100 个 14:30 观察，校准 A1/B1/A2 降级规则 |
| 历史权限回测 | `tools/historical_policy_backtest.py`、`docs/historical_policy_backtest.md` | 101 只主板样本股、57,558 个 stock-day、827 个开盘追强候选，验证缺 A2 禁止 09:28 追强的风险控制有效性 |
| 三个月可靠性回测 | `tools/historical_policy_backtest.py`、`docs/reliability_backtest_3m.md` | 99 只主板样本股、5,635 个 stock-day、60 个开盘追强候选，验证近期窗口未推翻缺 A2 降级规则 |
| 校准与风险证明 | `tools/prediction_replay_evaluation.py`、`docs/calibration_and_risk_proof_plan.md` | 概率分桶、Brier score、expected-R 偏差、计划外交易和无止损交易指标 |

## 快速体验

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 tools/trading_assistant.py validate
python3 tools/trading_assistant.py render user --date 2026-05-22 --themes 半导体 AI硬件 --codes 002156.SZ 603920.SH --stdout
python3 tools/portfolio_validation.py --format markdown
python3 -m unittest discover -s tests
```

如果没有本地私有配置，工具会自动读取 `config/portfolio.example.json`。真实使用时复制一份私有配置：

```bash
cp config/portfolio.example.json config/portfolio.json
```

`config/portfolio.json`、`docs/trading_assistant_state.md`、`data/manual/` 和 `reports/` 默认被 Git 忽略，避免公开账户、持仓和历史报告。

<details>
<summary>More CLI Workflows</summary>

```bash
python3 tools/trading_assistant.py render auction --date 2026-05-22 --stdout
python3 tools/trading_assistant.py data-health --date 2026-05-22 --time 0928 --automation auction --json
python3 tools/trading_assistant.py collect tail-data --date 2026-05-22 --time 0935 --codes 603920.SH
python3 tools/trading_assistant.py data-health --date 2026-05-22 --time 0935 --automation auction
python3 tools/trading_assistant.py brief --date 2026-05-22 --time 0928 --automation auction
python3 tools/trading_assistant.py prediction template --date 2026-05-22 --automation auction
python3 tools/trading_assistant.py prediction outcome-template --date 2026-05-22 --automation auction
python3 tools/trading_assistant.py prediction behavior-template --date 2026-05-22 --automation auction
python3 tools/trading_assistant.py auction-csv-template --date 2026-05-22 --codes 603920.SH
python3 tools/trading_assistant.py auction-import-csv --date 2026-05-22 --input data/manual/auction/2026-05-22.csv
python3 tools/trading_assistant.py review weekly --start-date 2026-05-22 --end-date 2026-05-22
python3 tools/historical_threshold_calibration.py --start-date 2026-04-27 --end-date 2026-05-27
python3 tools/historical_policy_backtest.py --start-date 2024-01-01 --end-date 2026-05-27
python3 tools/prediction_replay_evaluation.py --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl
```

</details>

## 工作流

```mermaid
flowchart LR
  A["User intent + private portfolio"] --> B["Data Gateway"]
  B --> C["Data Health Gate"]
  C --> D["Run Packet Builder"]
  D --> E["Reasoning Workflows"]
  E --> F["Risk Engine"]
  F --> G["Decision Plan"]
  G --> H["Prediction/Outcome Logs"]
  H --> I["Calibration Review"]
```

## 设计原则

1. 事实、推断、计划分离：价格、公告、资金代理和交易动作不混写。
2. 数据不足自动降级：关键数据缺失时只输出低权限清单，不做高置信结论。
3. 反沉没成本：持仓不因已经亏损、已经研究或已有仓位而获得继续持有特权。
4. 概率化表达：每个可执行计划必须包含成功/失败/噪音概率和期望 R。
5. 人在回路：系统不下单，只输出研究包、风控边界和复盘记录。

## 目录结构

```text
.
├── config/portfolio.example.json      # 脱敏样例组合
├── docs/
│   ├── portfolio.md                   # 产品案例说明
│   ├── project_proof.md               # 项目证明材料
│   ├── prd_excerpt.md                 # PRD 片段
│   ├── launch_metrics.md              # 上线指标与反馈闭环
│   ├── project_plan.md                # 项目推进计划
│   ├── agent_architecture.md          # 投资辅助决策 Agent 架构
│   ├── demo/index.html                # 可互动 Demo
│   ├── data_sources.md                # 数据分层与证据要求
│   ├── evaluation_cases.md            # 评测集、失败案例与消息面 RAG 方案
│   ├── calibration_and_risk_proof_plan.md
│   ├── prediction_automation_system.md
│   └── runbook.md
├── prompts/                           # Agent 工作流 Prompt
├── tests/                             # 本地校验
└── tools/trading_assistant.py          # 本地运行器
```

## 验证

```bash
python3 -m unittest discover -s tests
python3 tools/portfolio_validation.py --format markdown
```

当前公开验证集包含 37 条离线 guardrail 用例，验证数据权限、RAG 证据边界、风控完整性、用户误用拦截、用户给定板块/个股/持仓评价、开盘承接和计划可审计性。该验证不声称投资收益，只证明产品约束可以被重复检查。

历史阈值校准见 `docs/historical_threshold_calibration.md`：过去一个月公开数据支持保留 A1 80% 覆盖阈值和 B1 市场结构要求；公开历史源无法提供 A2 竞价明细，因此缺 A2 时只能输出 09:30-09:35 承接确认条件，禁止 09:28 追强。

历史权限回测见 `docs/historical_policy_backtest.md`：2024-01-01 至 2026-05-27，101 只主板样本股、57,558 个 stock-day、827 个开盘追强候选中，缺 A2 仍追强的代理策略误放行率为 61.1%，日内触发 1R 止损率为 47.5%，高开回落率为 52.5%。新增角色代理分层后，弱跟风代理组误放行率为 93.6%，龙头/核心代理组为 17.6%，趋势/中军代理组为 19.3%。该结果验证的是风险权限纪律和角色过滤价值，不声明长期收益。

过去三个月可靠性回测见 `docs/reliability_backtest_3m.md`：2026-02-28 至 2026-05-27，99 只主板样本股、5,635 个 stock-day、60 个开盘追强候选中，缺 A2 仍追强的代理策略误放行率为 55.0%，日内触发 1R 止损率为 33.3%，高开回落率为 51.7%。新增角色代理分层后，弱跟风代理组误放行率为 100.0%，龙头/核心代理组为 9.1%，趋势/中军代理组为 0.0%。该窗口支持继续保留缺 A2 降级，并把 09:35 放行范围收窄到核心/中军/趋势确认票；但样本不足以放宽权限或证明长期收益。

base rate 和风险下降证明见 `docs/calibration_and_risk_proof_plan.md`：当前不把模型概率当统计真值，而是通过 prediction/outcome logs 计算概率分桶、Brier score 和 expected-R 偏差；真实用户风险下降需要继续记录计划外交易率、无止损交易率、override 率和复盘完成率。

## 风险声明

本项目不提供确定性预测，不保证收益，不替代专业投资顾问。公开仓库中的组合、价格、概率和输出均为样例，用于展示 AI 产品设计、工作流编排、风控约束和可复盘机制。
