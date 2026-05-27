# 校准与风险证明方案

本文专门回答三个面试中最容易被追问的问题：

1. 数据健康门阈值到底怎么验证。
2. base rate 和 expected R 从哪里来。
3. 如何证明系统降低的是风险行为，而不是包装交易冲动。

核心原则：公开作品集只声明已经可验证的 guardrail 和校准框架，不把小样本或离线验证包装成收益证明。

## 1. 数据健康门阈值

### 当前结论

当前 `A1 >= 80%`、`缺 A2 禁止追强`、`缺 B1 市场状态降置信` 是保守产品阈值。它们的目标不是最大化交易机会，而是防止模型在关键数据缺失时越权输出。

已完成的验证：

| 证据 | 当前状态 |
| --- | --- |
| 离线 guardrail 验证 | 30 条用例，覆盖数据缺失、RAG、风控、误用和计划完整性 |
| 过去一个月公开行情 replay | 20 个交易日、100 个 09:28 开盘确认观察、100 个 14:30 尾盘观察 |
| A1 阈值 | 样本内 09:28 代理和 14:30 均达到 20/20 天覆盖 |
| B1 市场结构 | AKShare/Eastmoney 涨跌停池样本内 20/20 天可用 |
| A2 竞价层 | 公开历史接口未提供真实 09:15-09:25 竞价额、封单、撤单和队列 |

因此，专业结论不是“阈值已经充分历史验证”，而是：

> A1/B1 的公开数据健康规则已经完成过去一个月小样本校准；A2 竞价层因为公开历史数据不可得，不能被伪装成已校准，所以继续保留缺 A2 降级规则。

### 落地方案

阈值校准分三层推进：

| 阶段 | 数据 | 方法 | 产出 |
| --- | --- | --- | --- |
| P0 已完成 | 公开日线、15 分钟线、涨跌停池 | 检查 A1/B1 覆盖和缺 A2 时的开盘波动风险 | `docs/historical_threshold_calibration.md` |
| P1 待补齐 | 同花顺截图/手工导出/授权竞价数据 | 记录竞价额、封单、撤单、龙头/中军/跟风排序 | A2 样本库 |
| P2 校准 | 预测日志 + 结果日志 | 比较不同阈值下的误放行率、误拦截率和 expected-R 偏差 | 阈值版本记录 |

### 验收标准

数据健康门不是按“看起来合理”调整，而按四类指标决定是否放宽：

| 指标 | 含义 | 产品判断 |
| --- | --- | --- |
| False Permission Rate | 数据不足却放行高风险动作的比例 | 最高优先级，必须压低 |
| Missed Valid Plan Rate | 因过严规则错过后续有效计划的比例 | 只能在安全前提下优化 |
| Opening Confirmation Error | 09:28 结论到 09:35 被证伪的比例 | 用于校准 A2 权重 |
| Tail Overnight Error | 14:30 计划到次日竞价被证伪的比例 | 用于校准隔夜风险 |

缺 A2 时，不允许为了提高机会数而直接放宽追强权限。只有拿到真实 A2 样本，并证明 auction-confirmed 计划显著优于 non-confirmed 计划，才允许调整。

## 2. Base Rate 与 Expected R

### 当前结论

当前 base rate 是保守先验，不是统计真值。没有足够历史样本时，系统只能输出区间和“待校准”，不能把模型生成的概率当成真实胜率。

### Base Rate 来源分层

| 优先级 | 来源 | 使用方式 |
| --- | --- | --- |
| 1 | 同一 playbook + 同一市场状态 + 同一数据等级的历史 prediction/outcome logs | 可作为首选 base rate |
| 2 | 相近 playbook 或相近市场状态的历史样本 | 必须降权，并标注迁移来源 |
| 3 | 公开行情 replay 得到的事件发生率 | 只能作为市场背景先验 |
| 4 | 专家规则/交易经验先验 | 只能输出宽区间，标注“待校准” |
| 5 | 模型临场判断 | 不能单独作为 base rate |

### 样本量规则

| 样本量 | 输出权限 |
| ---: | --- |
| `n < 30` | 只能写“待校准”，使用宽区间，不给精确胜率 |
| `30 <= n < 100` | 可以给粗粒度区间，并展示样本数 |
| `100 <= n < 300` | 可以分场景展示概率桶，但仍需置信区间 |
| `n >= 300` | 可以作为稳定 base rate 候选，但必须继续按市场状态分层 |

### 评估指标

新增工具：

```bash
python3 tools/prediction_replay_evaluation.py \
  --predictions reports/predictions/YYYY-MM-DD-predictions.jsonl \
  --outcomes reports/outcomes/YYYY-MM-DD-outcomes.jsonl \
  --behavior reports/behavior/YYYY-MM-DD-events.jsonl
```

它会输出：

1. 概率分桶命中率：例如 30%-40%、40%-50%、50%-60% 是否校准。
2. Brier score：衡量概率预测是否过度自信。
3. Multiclass Brier：同时评估成功、失败、噪音三类概率。
4. Expected-R error：检查 `expected_r` 与实际 `result_r` 的偏差。
5. base rate 缺失和样本量不足数量：防止伪精确。

### 产品规则

任何计划如果缺少以下字段，不能写成高置信结论：

```json
{
  "base_rate": 0.42,
  "base_rate_source": "same-playbook-replay",
  "base_rate_sample_size": 45,
  "success_probability": 0.42,
  "failure_probability": 0.36,
  "noise_probability": 0.22,
  "expected_r": 0.18
}
```

如果 `base_rate_source` 或 `base_rate_sample_size` 缺失，输出必须保留“待校准”标签。

## 3. 风险下降证明

### 当前结论

当前仓库能证明的是：系统可以稳定拦截无数据、无止损、确定收益、自动下单、传闻当事实等高风险输出。它还不能证明真实用户长期风险下降。

专业解决方案不是直接宣称“用户会少亏”，而是把风险行为拆成可观测指标。

### 行为日志字段

真实使用时新增行为日志：

```json
{
  "time": "2026-05-27 09:34:18",
  "plan_id": "20260527-002156-auction-01",
  "attempted_action": "chase_strength",
  "market_regime": "rotation",
  "data_grade": "B",
  "violated_rules": ["missing_a2", "no_opening_confirmation"],
  "guardrail_action": "confirmation_only",
  "user_override": false,
  "outside_plan": false,
  "stop_present": true,
  "planned_account_loss_pct": 0.8,
  "executed": false,
  "result_r": null
}
```

### 关键指标

| 指标 | 证明什么 | 期望方向 |
| --- | --- | --- |
| No-stop attempt rate | 用户是否仍尝试无止损交易 | 下降 |
| No-stop trade rate | 无止损交易是否被真正拦下 | 下降到接近 0 |
| Outside-plan trade rate | 用户是否脱离计划冲动交易 | 下降 |
| Guarded high-risk rate | 系统是否识别并干预高风险尝试 | 上升 |
| User override rate | 用户是否绕过风控 | 下降 |
| Plan completeness rate | 每笔计划是否有触发、止损、目标、失效条件 | 上升 |
| Outcome-log completion rate | 是否能形成复盘数据 | 上升 |
| Loss-budget breach rate | 是否突破单笔/单日风险预算 | 下降 |

### 评估设计

| 阶段 | 方法 | 目的 |
| --- | --- | --- |
| Baseline | 记录 2-4 周未强制干预前的计划外交易、无止损交易和复盘完成率 | 得到个人风险行为基线 |
| Intervention | 开启数据健康门、风控确认、outside-plan 标记和冷静期 | 验证产品是否改变行为 |
| Matched Regime | 按强进攻、轮动、退潮、混沌分组比较 | 避免把市场环境变化误认为产品效果 |
| Review | 周度复盘概率校准、expected-R 偏差和行为指标 | 形成下一版规则 |

### 对外表达

可以说：

> 当前已证明系统能自动拦截高风险输出，并提供从预测到结果、从用户行为到复盘的指标闭环。

不能说：

> 已证明用户长期收益提升，或系统能稳定降低真实账户回撤。

真实风险下降必须依赖持续行为日志和交易结果日志共同验证。

## 4. 面试回答口径

### 数据健康门

> 我没有把 80% 阈值包装成充分历史验证后的最优值。当前它是保守 guardrail，已经用过去一个月公开行情做了小样本校准，支持 A1/B1 覆盖和缺 A2 降级规则作为合理的初始版本。真正要放宽 A2 权限，必须引入同花顺或授权竞价数据，再比较 auction-confirmed 与 non-confirmed 计划的误放行率和 expected-R 偏差。

### Base Rate

> base rate 不能由模型凭空生成。我把它设计成分层来源：优先使用同一 playbook、同一市场状态、同一数据等级的历史 prediction/outcome logs；样本不足时只能标注待校准并给宽区间。工具侧用 Brier score、概率分桶和 expected-R 偏差来防止伪精确。

### 风险下降

> 当前能证明的是 guardrail 能拦截风险输出，不能直接证明真实用户风险下降。我的解决方案是记录用户行为日志，看无止损交易率、计划外交易率、override 率、复盘完成率和风险预算突破率是否改善。这样证明的是决策质量和行为风险变化，而不是把收益当成唯一指标。
