# Evaluation And Calibration

本项目的评估目标不是证明 AI 能预测市场，而是证明 AI 在高噪声、高风险场景里能稳定遵守数据边界、输出权限和风控纪律。

评测样本、消息面 RAG/Embedding 评测和失败案例见 [Evaluation Cases And Iteration Notes](evaluation_cases.md)。

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

建议按周复盘：

1. 概率分桶命中率：30%-40%、40%-50%、50%-60% 分别是否过度自信。
2. Brier score：衡量概率预测和实际结果的偏差。
3. 期望 R 偏差：高 expected R 的计划是否真的优于低 expected R。
4. 错误类型占比：场景误判、数据缺失、执行条件模糊、正/负因子权重错误。

## 3. 安全评估

1. 不输出保证收益、确定涨跌或内部消息式表达。
2. 不自动下单，不调用券商交易接口。
3. 不把 vendor-classified fund flow 解释为真实机构意图。
4. 不把长期不可得的 Tier 3 数据每天机械列为缺口。
5. 不在公开仓库提交真实账户、持仓截图、历史交易报告和手工竞价数据。

## 4. 演示路径

演示时优先展示数据接口和覆盖率如何约束后续报告：

1. 用“批量尾盘数据接口”展示组合和观察池的批量数据请求如何生成结构化数据包。
2. 用“单股深研数据接口”展示单个标的如何进入更细颗粒度的证据栈。
3. 用“数据健康门接口”展示覆盖率、核心字段和数据层如何决定后续报告权限。
4. 展示页面里的工作流链路：数据接口、数据健康门、运行包、约束规则、预测日志、复盘校准。
5. 打开 `examples/workflow_trace.sample.json` 和 `examples/run_packet.sample.md`，说明可审计产物如何支撑页面展示的链路。
