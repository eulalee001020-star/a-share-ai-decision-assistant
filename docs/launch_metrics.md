# Launch Metrics｜验收、上线指标与反馈闭环

## 1. 定位

本文档说明 A 股投资辅助决策 Agent 从本地 MVP 走向生产化试点时应如何验收、监控和迭代。当前公开仓库已经提供可运行 CLI、静态 Demo、37 条 guardrail 验证和历史权限回测；这里不声明真实金融生产上线，也不声明投资收益能力。

上线指标的目标是回答三个问题：

1. 系统是否稳定遵守数据边界和风险边界。
2. AI 输出是否可用、可解释、可复盘。
3. 用户是否因为系统约束而减少无计划、无止损和越权行为。

## 2. MVP 验收门槛

| 类别 | 必须满足的门槛 | 当前公开证据 |
| --- | --- | --- |
| 数据边界 | 缺 A0/A1/A2/B1 时动作权限自动降级 | `tools/portfolio_validation.py` |
| 风控完整性 | 买入/加仓计划必须包含触发、止损、目标 R、仓位上限和失效条件 | `prompts/*.md`、`docs/validation_report.md` |
| 用户误用拦截 | 自动下单、确定收益、满仓诱导必须被拒绝 | 37 条 guardrail 用例 |
| RAG 证据边界 | 无来源、过期、传闻和冲突消息不得写成确定事实 | `docs/evaluation_cases.md` |
| 隐私边界 | 真实账户、持仓、截图和报告不得进入公开仓库 | `.gitignore`、`docs/privacy_and_compliance.md` |
| 复盘闭环 | 计划必须能映射到 prediction/outcome/behavior 日志 | `docs/calibration_and_risk_proof_plan.md` |

## 3. 上线后指标体系

### 产品可用性

| 指标 | 定义 | 目标解释 |
| --- | --- | --- |
| workflow_completion_rate | 工作流成功生成可读计划的比例 | 衡量用户是否能完成盘前/盘中任务 |
| average_review_time | 用户从输入到完成计划阅读的时间 | 衡量效率，不用于证明收益 |
| plan_completeness_rate | 计划包含触发、止损、目标 R、失效和不交易条件的比例 | 低于阈值说明输出契约失效 |
| manual_edit_rate | 用户对 AI 计划进行编辑的比例 | 高编辑率可能说明语言或证据组织不够可用 |
| repeat_usage_rate | 同一用户在多个交易日继续使用的比例 | 衡量产品是否有持续使用价值 |

### AI 质量与证据边界

| 指标 | 定义 | 风险信号 |
| --- | --- | --- |
| unsupported_fact_rate | 输出中无法被输入或引用支撑的事实比例 | 必须接近 0 |
| stale_source_rate | 使用过期消息作为关键依据的比例 | 高于阈值需要加强 freshness gate |
| conflict_retention_rate | 正反证据同时存在时保留冲突的比例 | 低说明模型在强行单边总结 |
| source_citation_coverage | 消息面结论带来源和时间的比例 | 低说明 RAG 输出不可审计 |
| overconfidence_rate | 低证据场景输出高置信动作的比例 | 高说明 guardrail 或 Prompt contract 失效 |

### 风险与行为

| 指标 | 定义 | 目标解释 |
| --- | --- | --- |
| unsupported_action_block_rate | 缺证据动作被阻断的比例 | 衡量 guardrail 是否发挥作用 |
| no_stop_plan_rate | 没有止损的可执行计划比例 | 必须为 0 |
| user_override_rate | 用户无视风险提示继续请求高风险动作的比例 | 用于优化提示、确认成本和教育反馈 |
| plan_outside_trade_rate | 用户执行了计划外交易的比例 | 衡量行为风险是否下降 |
| outcome_log_completion_rate | 计划结果被记录的比例 | 没有 outcome 就无法校准 |
| expected_r_error | 实际结果 R 与计划 expected R 的偏差 | 衡量概率和风险收益表达是否校准 |

### 成本与稳定性

| 指标 | 定义 | 生产化意义 |
| --- | --- | --- |
| average_generation_latency | 单次计划平均生成时间 | 决定盘中可用性 |
| p95_generation_latency | 95 分位生成时间 | 防止少数慢请求影响开盘体验 |
| model_calls_per_workflow | 单个工作流模型调用次数 | 控制成本和失败点 |
| model_cost_per_run | 单次运行模型成本 | 判断 SaaS 化价格边界 |
| cache_hit_rate | 新闻、公告和行情包缓存命中率 | 降低重复检索和延迟 |
| data_timeout_rate | 数据源超时比例 | 判断是否需要多供应商 fallback |

## 4. 反馈闭环

上线后每个计划应支持用户或评审者标记问题类型：

| 反馈标签 | 说明 | 迭代方向 |
| --- | --- | --- |
| data_missing | 缺关键数据，计划不可执行 | 补数据源或强化降级提示 |
| too_confident | 输出语气过强 | 调整概率、证据和不确定性表达 |
| too_conservative | 系统过度阻断 | 用 outcome 样本检查是否规则过严 |
| weak_evidence | 证据链不足 | 强化 RAG 引用、冲突保留和结构化字段 |
| risk_unclear | 止损、仓位或失效条件不清 | 强化风控字段和计划模板 |
| not_actionable | 计划不能转成实际核验动作 | 改写触发条件和人工确认清单 |

## 5. 指标看板字段

```text
run_id
workflow_type
trade_date
time_window
data_health_level
action_permission_ceiling
missing_fields
model_calls
latency_ms
plan_completeness
blocked_actions
manual_edits
user_override
prediction_event_id
outcome_log_id
behavior_log_id
feedback_tags
```

这些字段的作用是把一次 AI 输出从“看起来合理的文本”转化为可追踪的产品事件。没有这些字段，系统无法判断问题来自数据、模型、风控规则还是用户行为。

## 6. 当前结论与边界

当前公开仓库已经能证明：

1. Guardrail 验证可重复执行，37 条用例全部通过。
2. 缺 A2 不追强规则有大样本公开日线压力测试支持。
3. Prompt、CLI、Demo、日志模板和验证报告已经形成 MVP 交付闭环。

仍需生产化补齐：

1. 真实用户行为指标。
2. 真实 prediction/outcome 长期匹配样本。
3. 模型调用成本、延迟和失败重试数据。
4. 授权实时数据源和生产级 RAG 引用一致性评测。
5. 灰度、监控、告警、审计和权限体系。
