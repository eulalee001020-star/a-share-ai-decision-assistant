# Evaluation And Calibration

本项目的评估目标不是证明 AI 能预测市场，而是证明 AI 在高噪声、高风险场景里能稳定遵守数据边界、输出权限和风控纪律。

评测样本、消息面 RAG/Embedding 评测和失败案例见 [Evaluation Cases And Iteration Notes](evaluation_cases.md)。公开 guardrail 验证结果见 [Public Validation Report](validation_report.md)。base rate、expected R 和用户行为风险证明方案见 [Calibration And Risk Proof Plan](calibration_and_risk_proof_plan.md)。

## 1. 输出质量指标

| 指标 | 合格标准 | 失败示例 |
| --- | --- | --- |
| 数据权限一致性 | 数据等级和动作权限一致 | 数据不足却输出高权限动作 |
| 可执行性 | 每个动作都有触发、止损、目标、取消、不交易条件 | 只写“看好，逢低买入” |
| 风险可计算 | 买入/加仓能从止损距离倒推仓位 | 只给固定仓位，不解释亏多少算错 |
| 事实可追溯 | 行情、公告、资金代理有来源或标缺失 | 编造价格、涨跌幅、资金流 |
| 沉没成本控制 | 持仓重新按未来期望评估 | 因为亏损而建议继续持有 |

## 2. 预测校准指标

预测日志写入 `reports/predictions/{date}-predictions.jsonl`，结果日志写入 `reports/outcomes/{date}-outcomes.jsonl`。

核心字段：

```json
{
  "event": "09:35站回关键位",
  "success_probability": 0.42,
  "failure_probability": 0.34,
  "noise_probability": 0.24,
  "target_r": 1.8,
  "expected_r": 0.37,
  "actual": "success",
  "result_r": 0.8,
  "error_type": "positive-factor-overweight"
}
```

公开仓库提供一组可运行的离线 guardrail 验证：

```bash
python3 tools/portfolio_validation.py --format markdown
```

这组验证检查数据权限、RAG 证据边界、风控完整性、用户误用拦截和计划可审计性，不用于证明投资收益。

建议按周复盘：

1. 概率分桶命中率：30%-40%、40%-50%、50%-60% 分别是否过度自信。
2. Brier score：衡量概率预测和实际结果的偏差。
3. 期望 R 偏差：高 expected R 的计划是否真的优于低 expected R。
4. 错误类型占比：场景误判、数据缺失、执行条件模糊、正/负因子权重错误。

可运行的 replay 评估命令：

```bash
python3 tools/prediction_replay_evaluation.py \
  --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl \
  --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl \
  --behavior reports/behavior/YYYY-MM-DD-events.jsonl
```

该工具输出概率分桶、Brier score、multiclass Brier、expected-R 偏差、base rate 缺失数量，以及计划外交易、无止损交易、override 和高风险干预指标。它用于判断校准质量和行为风险变化，不用于声明投资收益。

## 3. 用户行为风险指标

真实使用时需要记录 `reports/behavior/{YYYY-MM-DD}-events.jsonl`。核心字段：

```json
{
  "plan_id": "20260527-002156-auction-01",
  "attempted_action": "chase_strength",
  "violated_rules": ["missing_a2"],
  "guardrail_action": "confirmation_only",
  "outside_plan": false,
  "stop_present": true,
  "executed": false,
  "user_override": false
}
```

必须区分三类证据：

| 证据 | 当前可证明程度 |
| --- | --- |
| guardrail 能拦截风险输出 | 已由离线验证覆盖 |
| 概率和 expected R 是否校准 | 需要 prediction/outcome replay |
| 用户真实风险行为是否下降 | 需要持续行为日志 |

## 4. 安全评估

1. 不输出保证收益、确定涨跌或内部消息式表达。
2. 不自动下单，不调用券商交易接口。
3. 不把 vendor-classified fund flow 解释为真实机构意图。
4. 不把长期不可得的 Tier 3 数据每天机械列为缺口。
5. 不在公开仓库提交真实账户、持仓截图、历史交易报告和手工竞价数据。

## 5. 演示路径

演示时优先展示数据接口和覆盖率如何约束后续报告：

1. 用“批量尾盘数据接口”展示组合和观察池的批量数据请求如何生成结构化数据包。
2. 用“单股深研数据接口”展示单个标的如何进入更细颗粒度的证据栈。
3. 用“数据健康门接口”展示覆盖率、核心字段和数据层如何决定后续报告权限。
4. 展示页面里的工作流链路：数据接口、数据健康门、运行包、约束规则、预测日志、复盘校准。
5. 打开 `examples/workflow_trace.sample.json` 和 `examples/run_packet.sample.md`，说明可审计产物如何支撑页面展示的链路。
