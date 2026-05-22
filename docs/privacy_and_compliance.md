# Privacy, Compliance, And Public Repo Boundary

## 1. 公开仓库只保留什么

公开仓库保留：

1. 脱敏样例组合：`config/portfolio.example.json`
2. 工作流 Prompt：`prompts/*.md`
3. 数据和风控规则：`docs/*.md`
4. 本地运行器：`tools/trading_assistant.py`
5. 静态互动 Demo：`docs/demo/index.html`
6. 单元测试和 CI 配置

## 2. 默认不提交什么

`.gitignore` 默认排除：

1. `config/portfolio.json`
2. `docs/trading_assistant_state.md`
3. `data/manual/`
4. `reports/`

这些文件可能包含真实账户、持仓、交易时间、截图提取数据、历史判断和个人策略偏好。它们适合本地使用，不适合作品集公开。

## 3. 合规边界

1. 系统只做研究和风控提示，不自动下单。
2. 输出不构成投资建议，不承诺收益。
3. 所有结论必须区分事实、推断和计划。
4. 无实时数据时必须降低置信度或取消高风险动作。
5. 资金流、龙虎榜、筹码、股东户数等数据只能作为证据或概率修正，不能被描述为确定性主力意图。

## 4. 上传前检查清单

```bash
git status --short
git check-ignore -v config/portfolio.json docs/trading_assistant_state.md
python3 -m unittest discover -s tests
```

上传前应确认 `git status --short` 中没有真实报告、真实账户配置或截图数据。
