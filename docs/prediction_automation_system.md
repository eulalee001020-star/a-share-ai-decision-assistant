# 预测型自动化系统设计

Last updated: 2026-05-28 Asia/Shanghai

本文定义 09:28 集合竞价自动化、13:10 下午盘计划自动化和 14:30 尾盘资金流自动化的新框架。目标不是制造确定性预测，而是把每个交易判断变成可审计、可复盘、可校准的概率下注。

## 1. 核心原则

1. 先判场景，再判模式，再给概率，最后计算期望 R。
2. 不输出无法验证的预测。预测必须绑定具体事件、时间窗口、价格/结构条件和结果判定。
3. 数据等级决定输出权限。数据不够时自动降级，不靠文字提醒。
4. 仓位不是信心表达，而是止损距离、成功概率、失败概率、期望 R 和市场状态的函数。
5. 不把资金行为代理说成真实主力意图。只能说“可观察资金行为显示承接/兑现/分歧”。

## 2. 数据等级

| 等级 | 数据 | 自动化地位 | 缺失时的限制 |
| --- | --- | --- | --- |
| A0 | 当前持仓、可用数量、成本、账户总资产、止损线、风险预算 | 必须有 | 不能给仓位建议，只能给观察清单 |
| A1 | 个股实时价、开高低、成交额、VWAP、量比、5/10/20/60 日线、涨跌幅 | 必须有 | 不能给高置信个股计划 |
| A2 | 09:15-09:25 竞价成交、竞价额、09:20 后撤单、封单额、盘口队列、龙头/中军/跟风竞价排序 | 09:28 提前放权输入 | 禁止 09:28 追强、禁止说“竞价超预期”，只能给 09:30-09:35 确认条件 |
| B1 | 板块龙头/中军/补涨同步，涨停、跌停、炸板、连板高度，强股反馈 | 场景判断核心输入 | 市场状态置信度不得高于中 |
| B2 | 筹码峰、成本分布、压力/支撑区 | 概率修正输入 | 可以交易，但突破/回踩概率必须降置信 |
| B3 | 大单、资金流、龙虎榜、融资、港股通 | 资金行为代理 | 不可单独定性为吸筹/出货 |
| C1 | 股东户数、基金持仓、机构调研 | 慢变量和拥挤度 | 只影响中线质量，不触发日内买卖 |
| C2 | 公告、产业链新闻、政策、价格/订单/产能变化 | 催化与预期修正 | 没有来源不能作为高置信买点 |

## 2A. 开盘权限模型

09:28 不是唯一决策点。系统把开盘权限拆成主证据层和提前放权层，具体以 `docs/opening_permission_model.md` 为准。

| 证据层 | 组成 | 作用 |
| --- | --- | --- |
| 主证据层 | 市场状态、亏钱效应、板块共振、个股 09:30-09:35 承接、成交额/换手/量比、止损距离和 expected R | 决定能不能交易、交易什么、仓位多大 |
| 提前放权层 | 真实 A2 竞价额、09:20 后撤单、封单、队列和竞价角色 | 只决定能不能把动作提前到 09:28 |

缺 A2 时，不是完全不能研究，也不是永远不能交易；它只禁止 09:28 追强和“竞价超预期”结论。若 A1+B1 可用，候选必须降级为 09:30-09:35 承接确认：站上开盘价、强于 VWAP、板块核心票同步、止损距离仍合格，才允许进入后续计划。

## 2B. 稳定数据权重

稳定、可重复、可审计的数据优先于难以连续获得的数据。权重配置固化在 `config/decision_weights.json`，并由 `data-health` 输出 `stable_data_readiness` 和 `action_permission_ceiling`，供后续工作流直接读取。

| 主证据组件 | 权重 | 主要数据层 | 权限含义 |
| --- | ---: | --- | --- |
| 市场状态和亏钱效应 | 25 | B1 | 决定当天能否承担新增风险 |
| 板块共振和角色 | 20 | B1 | 决定只做核心/中军还是观察 |
| 09:35 开盘承接 | 20 | A1+B1 | 缺 A2 时的主要执行确认 |
| 风险收益比和流动性 | 20 | A0+A1 | 决定仓位上限和是否值得做 |
| K 线和相对强弱 | 10 | A1 | 定义阶段、压力、支撑和失效条件 |
| 有来源的催化 | 5 | C2 | 修正逻辑强弱，不单独触发日内买入 |

可选修正不进入主证据硬门槛：真实 A2 竞价最多只提前放权，资金流只能作为 vendor-classified proxy，筹码/股东/融资/港股通只能修正结构和拥挤度。任何买入或加仓仍必须经过市场状态、板块共振、09:35/VWAP 承接、结构止损和 expected R。

## 3. 场景评分

每天先对市场场景打分，每项 -2 到 +2。

| 维度 | 证据 | 权重含义 |
| --- | --- | --- |
| 指数与成交 | 指数涨跌、成交额放大/缩小、权重拖累/支撑 | 系统风险偏好 |
| 市场广度 | 涨跌家数、涨跌超 5%、涨停/跌停 | 赚钱效应扩散度 |
| 情绪接力 | 连板高度、昨日涨停反馈、炸板率、核按钮 | 短线资金是否愿意接力 |
| 主线结构 | 龙头、中军、补涨、低位扩散是否同步 | 是否有可下注方向 |
| 亏钱效应 | 高标断板、A 杀、强股补跌、跌停扩散 | 错误惩罚强度 |

场景映射：

| 总分 | 场景 | 默认权限 |
| ---: | --- | --- |
| +7 到 +10 | 强进攻日 | 只做龙头、核心中军、验证强趋势 |
| +3 到 +6 | 轮动日 / 修复日 | 低吸核心、强换弱、小仓试错 |
| -2 到 +2 | 混沌日 | 降仓、观察、等待确认 |
| -6 到 -3 | 退潮日 | 不开新仓，优先处理持仓 |
| -10 到 -7 | 强退潮日 | 降低总仓位，只做风控 |

冰点修复日单独判断：前期恐慌充分释放，跌停和核按钮减少，高辨识度开始止跌或反包，但主线确认不足。此时分数未必高，只允许核心反包和低位首启，小仓快撤。

## 4. 交易模式库

| 模式 | 典型场景 | 基准概率起点 | 关键修正因子 |
| --- | --- | ---: | --- |
| 龙头延续 | 强进攻/修复确认 | 50%-60% | 竞价成交、封单稳定、中军同步、开盘 VWAP 承接 |
| 中军趋势确认 | 强进攻/轮动 | 45%-55% | 成交额、MA 多头、板块净流入、回踩不破 VWAP |
| 核心回踩低吸 | 轮动/修复 | 40%-50% | 缩量回踩、筹码支撑、龙头未破、止损短 |
| 补涨分歧 | 强进攻尾段/轮动 | 30%-45% | 龙头位置、补涨辨识度、换手是否过热 |
| 弱票反弹 | 退潮/混沌 | 20%-35% | 只能减亏，默认不加仓 |
| 新仓失败处理 | 任意场景 | 失败概率优先 | 跌破成本/结构线、低于 VWAP、板块不支持 |

基准概率必须保守，后续用预测日志校准。没有历史样本前，只使用区间而非伪精确数字。

## 5. 概率解释公式

每个可执行计划必须写明：

```text
最终成功概率 = 基准概率 + 正向修正 - 负向修正
期望R = 成功概率 × 目标R - 失败概率 × 1R - 噪音概率 × 噪音成本R
```

至少输出三类概率：

| 概率 | 定义 | 用途 |
| --- | --- | --- |
| 成功概率 | 到达目标 R、站上关键位、收盘确认或次日竞价延续 | 决定是否值得下注 |
| 失败概率 | 跌破结构止损、跌回 VWAP、开盘承接失败 | 决定止损和仓位 |
| 噪音概率 | 震荡、不触发买卖、机会成本增加 | 修正期望 R |

## 6. 三个日内自动化的分工

### 09:28 竞价预测

回答三个问题：

1. 今天能不能打？
2. 哪类结构有下注资格？
3. 开盘 5-30 分钟错了怎么撤？

必须输出：

1. 数据等级和缺失限制。
2. 场景评分和市场状态概率。
3. 持仓 09:35 / 10:00 / 收盘事件预测。
4. 板块龙头、中军、补涨的竞价强弱和同步性。
5. 期望 R、仓位上限、取消条件。

### 13:10 下午盘午盘信息与交易计划

回答三个问题：

1. 上午盘判断哪里被强化或证伪？
2. 下午盘持仓怎么处理，哪些观察池需要 14:30 再验证？
3. 哪些尾盘/隔夜想法必须先取消？

必须输出：

1. 数据等级、11:30 与 13:05 承接对比。
2. 上午盘预测复盘和市场状态更新。
3. 持仓处理、观察池排序、14:30 必看条件。
4. 尾盘/隔夜候选、取消清单、1R、结构止损、目标R和不交易条件。
5. 次日 09:35 验证条件。

### 14:30 尾盘资金流与观察机会

回答三个问题：

1. 09:28 预测哪里对、哪里错？
2. 今天资金最终更可能流向哪些板块？
3. 哪些核心/中军有次日 09:35 可观察买入机会？

必须输出：

1. 14:30 数据等级、动作权限和缺失限制。
2. 13:05 到 14:30 的涨停、炸板、跌停、宽基和板块资金流变化。
3. 资金最可能流向的板块排序，以及龙头/中军/补涨/跟风分层。
4. 可观察买入机会、持仓影响、期望 R、隔夜风险和不交易条件。
5. 次日 09:35 验证清单。

### 用户给定板块/个股/持仓综合分析

This is an on-demand workflow, not a scheduled automation. It answers three user-driven questions in one data-permission chain:

1. 用户给出的板块是否是真主线、轮动方向、退潮方向，还是仅是概念标签。
2. 用户给出的个股在证据栈、板块角色、催化和风险收益上是否有交易资格。
3. 当前持仓的原始逻辑是否 strengthened, weakened, unchanged, or invalidated, and whether new candidates are better than existing exposure.

Required safeguards:

1. User attention is not evidence. It only defines the target list.
2. Missing A1/B1 downgrades the output to observation and manual verification.
3. Missing A2 blocks only auction/chase conclusions, not post-open research.
4. Holding advice must include thesis update, positive/negative evidence, priced-in evidence, reduce/sell triggers, and add conditions.
5. Switch advice requires comparing expected value, sector role, liquidity, stop distance, and concentration risk.

## 7. 输出权限

| 数据状态 | 允许输出 |
| --- | --- |
| A0 + A1 + A2 + B1 可用 | 可以输出09:28提前计划、场景概率、个股概率、下注资格和仓位；仍需09:35承接验证 |
| A0 + A1 + B1 可用，但 A2 缺失 | 只能输出09:30-09:35承接确认条件，确认前禁止追强 |
| A0 + A1 + B1 可用，用户给定板块/个股/持仓 | 可以输出综合分析、持仓建议、期望R和仓位上限；开盘追强仍需A2 |
| 只有 A0 和昨日数据 | 只能输出防守清单和手动核验表 |
| A0 缺失 | 不能给仓位，不能给买卖动作 |

## 8. 复盘闭环

预测日志保存到：

```text
reports/predictions/{YYYY-MM-DD}-predictions.jsonl
reports/outcomes/{YYYY-MM-DD}-outcomes.jsonl
```

预测字段至少包括：

```json
{
  "run_time": "2026-05-15 09:28",
  "automation": "auction",
  "code": "002156.SZ",
  "event": "09:35站回59.40",
  "base_rate": 0.30,
  "base_rate_source": "expert-prior",
  "base_rate_sample_size": 0,
  "positive_adjustments": [{"factor": "板块龙头竞价强", "delta": 0.08}],
  "negative_adjustments": [{"factor": "昨日低于VWAP", "delta": -0.08}],
  "success_probability": 0.30,
  "failure_probability": 0.45,
  "noise_probability": 0.25,
  "target_r": 1.5,
  "loss_r": 1.0,
  "noise_cost_r": 0.2,
  "expected_r": 0.10,
  "action": "观察，不加仓",
  "data_grade": "B",
  "confidence": "中"
}
```

收盘或次日必须记录 actual、result_r、error_type 和修正结论。没有复盘的预测不允许进入后续胜率统计。

可先用 prediction 自动生成 outcome 模板，避免复盘漏行：

```bash
python3 tools/trading_assistant.py prediction outcome-template --date YYYY-MM-DD --automation auction
```

09:28 A2 校准还需要额外标记 `false_permission` 和 `invalidated_at_0935`。前者用于衡量数据权限是否误放行，后者用于衡量竞价判断到 09:35 是否被开盘承接证伪。

20-60 个真实 A2 样本后，使用：

```bash
python3 tools/trading_assistant.py auction-calibration --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

校准 replay 使用：

```bash
python3 tools/prediction_replay_evaluation.py \
  --predictions reports/predictions/{YYYY-MM-DD}-predictions.jsonl \
  --outcomes reports/outcomes/{YYYY-MM-DD}-outcomes.jsonl \
  --behavior reports/behavior/{YYYY-MM-DD}-events.jsonl
```

若 `base_rate_source` 或 `base_rate_sample_size` 缺失，概率只能标注为待校准；不能用模型临场判断替代统计来源。

用户行为日志保存到：

```text
reports/behavior/{YYYY-MM-DD}-events.jsonl
```

最小字段包括 `plan_id`、`attempted_action`、`violated_rules`、`guardrail_action`、`outside_plan`、`stop_present`、`executed` 和 `user_override`。这些字段用于证明系统是否减少计划外交易、无止损交易和绕过风控，而不是用于声明收益。

行为日志模板和周度复盘入口：

```bash
python3 tools/trading_assistant.py prediction behavior-template --date YYYY-MM-DD --automation auction
python3 tools/trading_assistant.py review weekly --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```
