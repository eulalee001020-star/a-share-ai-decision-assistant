# Workflow, Prompts, Inputs And Outputs

## 1. 展示目的

本页展示系统如何把用户问题转成可审计的 AI 工作流：先构造运行包，再执行 Prompt 契约，最后输出带数据权限、风险约束和复盘字段的计划。

## 2. 核心工作流

```mermaid
flowchart LR
  A["用户请求 / 持仓 / 观察池"] --> B["配置与数据校验"]
  B --> C["数据健康门"]
  C --> D["运行包生成"]
  D --> E["Prompt 工作流"]
  E --> F["风控与权限检查"]
  F --> G["交易计划草案"]
  G --> H["预测 / 结果 / 行为日志"]
```

系统的关键设计是：模型不直接决定能否买入。数据健康门和风控规则先决定输出权限，Prompt 只在这个权限范围内组织事实、推理和计划。

## 3. 任务类型

| 任务 | Prompt | 典型输入 | 输出目标 |
| --- | --- | --- | --- |
| 09:28 竞价检查 | `prompts/auction_check.md` | 日期、账户风险、持仓、观察池、竞价/开盘数据缺口 | 市场状态、允许动作、09:35 验证条件 |
| 13:10 下午盘计划 | `prompts/tail_check.md` | 上午报告、11:30 午盘、13:05 承接、持仓和观察池 | 下午盘处理、14:30 必看条件、次日 09:35 验证条件 |
| 14:30 大盘资金流 | `prompts/tail_market_flow_check.md` | 14:30 tail-data、13:10 报告、板块资金流、涨跌停/炸板/跌停、持仓和观察池 | 大盘资金流向、板块排序、观察机会、次日 09:35 验证优先级 |
| 主题筛选 | `prompts/theme_screening.md` | 用户给定主题、板块候选、催化资料 | 龙头/中军/补涨/跟风分层 |
| 单股深研 | `prompts/single_stock_research.md` | 用户给定个股、行情证据栈、资金/筹码可得性 | 买/持/减/卖/观察条件 |
| 综合请求 | `prompts/user_request_analysis.md` | 用户给定板块、个股和当前持仓 | 统一进入数据权限门后的组合建议 |

## 4. 输入包示例

运行命令：

```bash
python3 tools/trading_assistant.py render user \
  --date 2026-05-22 \
  --themes 半导体 AI硬件 \
  --codes 002156.SZ 603920.SH \
  --stdout
```

输入包会显式携带：

```json
{
  "date": "2026-05-22",
  "workflow": "user",
  "user_supplied_themes": ["半导体", "AI硬件"],
  "user_supplied_codes": ["002156.SZ", "603920.SH"],
  "portfolio_source": "config/portfolio.example.json",
  "risk_engine": {
    "max_single_stock_pct": 0.18,
    "max_short_term_pct": 0.35,
    "max_loss_per_trade_pct": 0.006
  },
  "required_checks": [
    "market_regime",
    "data_health",
    "stock_evidence_stack",
    "role_classification",
    "risk_reward",
    "do_not_trade_if"
  ]
}
```

公开样例见：

- `examples/run_packet.sample.md`
- `examples/auction_input.sample.json`
- `examples/workflow_trace.sample.json`

## 5. Prompt 契约示意

Prompt 不要求模型“预测涨跌”，而是要求它按固定顺序输出：

1. 市场状态和仓位权限。
2. 宏观、板块和主题结构。
3. 个股证据栈和角色分类。
4. 三层共振：市场、板块、个股。
5. 阶段判断。
6. 操作计划。
7. 仓位和风险控制。

每个可执行动作必须包含：

```text
操作、风格、市场状态许可、最大仓位、计划风险、买入/加仓触发、
减仓/卖出触发、止损、止盈、失效条件、不交易条件、盘中监控信号
```

如果 A2 竞价层缺失，Prompt 必须降级：

```text
不能写“竞价超预期”。
不能在 09:28 直接追强。
只能给 09:30-09:35 承接确认条件。
```

## 6. 输出效果示意

示例输出不会承诺收益，重点展示权限、证据和风险边界：

```markdown
### 数据权限

- A0 账户/风险：可用，可计算仓位。
- A1 实时行情：部分可用，个股结论最高为中置信。
- A2 竞价明细：缺失，禁止 09:28 追强。
- B1 市场宽度：可用，允许市场状态判断。

### 市场状态

判断：轮动日，新增风险权限低。

依据：
1. 指数不弱但主线持续性不足。
2. 高位强势股反馈分化。
3. 缺 A2 时不能提前确认竞价承接。

### 个股计划

操作：观察，不追强。
风格：09:35 承接确认后再低吸或放弃。
触发：站上开盘价和 VWAP，板块核心同步走强，成交不缩。
止损：跌破结构支撑或开盘承接失败。
目标：仅在确认后按 1.5R 以上计划执行。
不交易条件：市场退潮、板块核心回落、止损距离超过风险预算。
```

## 7. 复盘字段

为了避免“看对了但不可复盘”，系统会生成 prediction/outcome 日志字段：

```json
{
  "automation": "auction",
  "code": "603920.SH",
  "event": "09:35 absorption confirmation",
  "success_probability": 0.42,
  "failure_probability": 0.35,
  "noise_probability": 0.23,
  "target_r": 1.6,
  "expected_r": 0.29,
  "data_grade": "B",
  "confidence": "medium",
  "invalidation": "breaks VWAP and sector core weakens"
}
```

这些字段用于后续计算概率分桶、Brier score、expected-R 偏差、计划外交易率、无止损交易率和 override 率。

## 8. 失败案例如何处理

系统不把失败案例隐藏掉，而是纳入评测：

| 失败类型 | 处理方式 |
| --- | --- |
| 数据缺失但用户要求买入 | 降级为观察或 09:35 确认条件 |
| 用户要求确定收益 | 拒绝确定性表达，改为概率、触发和失效 |
| 资金流单独看多 | 标为 vendor-classified proxy，不能单独作为买入依据 |
| 持仓亏损想补仓 | 重新做未来期望评估，不因沉没成本加仓 |
| 弱跟风高开 | 缺 A2 时禁止 09:28 追强，弱跟风默认排除 |

完整用例见 `docs/evaluation_cases.md` 和 `docs/validation_report.md`。
