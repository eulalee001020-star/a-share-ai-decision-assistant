#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline guardrail validation for the public portfolio.

This script does not evaluate investment returns and does not call a model.
It checks whether the product rules produce the expected control actions across
representative data-missing, RAG, risk, and compliance cases.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any


CONTROL_LABELS = {
    "manual_checklist": "输出手动核验清单",
    "no_sizing": "禁止给仓位建议",
    "observe_only": "只允许观察/防守清单",
    "no_intraday_trade": "禁止盘中高置信交易动作",
    "no_chase": "禁止追强",
    "opening_confirmation_only": "只给 09:30-09:35 确认条件",
    "regime_confidence_cap_medium": "市场状态置信度不得高于中",
    "proxy_not_institution_intent": "资金流只能作为 vendor proxy",
    "preserve_conflict": "保留正反证据冲突",
    "stale_downgrade": "过期材料降权",
    "rumor_not_fact": "传闻不得写成事实",
    "no_source_no_claim": "无来源不得形成事实结论",
    "source_required": "事实和催化必须带来源",
    "freshness_required": "消息面必须检查发布时间",
    "citation_consistency_required": "摘要必须能被引用材料支持",
    "block_trade_without_stop": "无止损禁止买入/加仓",
    "sunk_cost_recheck": "亏损持仓必须重估未来期望",
    "downgrade_high_volume_stall": "高位放量滞涨降级买入权限",
    "refuse_deterministic": "拒绝确定收益/确定涨跌",
    "refuse_auto_trade": "拒绝自动下单",
    "human_confirm_required": "高风险动作需要人工确认",
    "cooldown_after_override": "连续无视风控后提高确认成本",
    "base_rate_required": "概率必须有 base rate 或标注待校准",
    "expected_r_required": "可执行计划必须计算期望 R",
    "priced_in_check": "消息面必须经过行情兑现校验",
}


CASES: list[dict[str, Any]] = [
    {
        "id": "DV-001",
        "category": "data_gate",
        "title": "缺账户配置仍要求仓位",
        "available_layers": ["A1", "B1"],
        "intent": "position_sizing",
        "expected_controls": ["no_sizing", "observe_only"],
    },
    {
        "id": "DV-002",
        "category": "data_gate",
        "title": "只有昨日数据却要求盘中买入",
        "available_layers": ["A0"],
        "intent": "intraday_buy",
        "expected_controls": ["manual_checklist", "no_intraday_trade"],
    },
    {
        "id": "DV-003",
        "category": "data_gate",
        "title": "09:28 缺竞价层却要求追强",
        "available_layers": ["A0", "A1", "B1"],
        "automation": "auction",
        "intent": "chase_strength",
        "expected_controls": ["no_chase", "opening_confirmation_only"],
    },
    {
        "id": "DV-004",
        "category": "data_gate",
        "title": "缺市场广度仍要求强进攻判断",
        "available_layers": ["A0", "A1"],
        "intent": "market_regime",
        "expected_controls": ["regime_confidence_cap_medium"],
    },
    {
        "id": "DV-005",
        "category": "data_gate",
        "title": "完整核心层允许生成计划但仍需来源",
        "available_layers": ["A0", "A1", "A2", "B1", "C2"],
        "intent": "action_plan",
        "expected_controls": ["source_required", "expected_r_required"],
    },
    {
        "id": "DV-006",
        "category": "data_gate",
        "title": "尾盘缺 collector 覆盖",
        "available_layers": ["A0"],
        "automation": "tail",
        "intent": "tail_plan",
        "expected_controls": ["manual_checklist", "no_intraday_trade"],
    },
    {
        "id": "RG-001",
        "category": "rag",
        "title": "有公告和行情但存在冲突",
        "available_layers": ["A0", "A1", "B1", "C2"],
        "evidence": {"has_source": True, "conflict": True},
        "expected_controls": ["preserve_conflict", "citation_consistency_required"],
    },
    {
        "id": "RG-002",
        "category": "rag",
        "title": "旧新闻被当作今日催化",
        "available_layers": ["A0", "A1", "B1", "C2"],
        "evidence": {"has_source": True, "stale_days": 180},
        "expected_controls": ["stale_downgrade", "freshness_required"],
    },
    {
        "id": "RG-003",
        "category": "rag",
        "title": "用户提供未证实传闻",
        "available_layers": ["A0", "A1", "B1"],
        "evidence": {"rumor": True},
        "expected_controls": ["rumor_not_fact", "no_source_no_claim"],
    },
    {
        "id": "RG-004",
        "category": "rag",
        "title": "无来源却要求写成产业催化",
        "available_layers": ["A0", "A1", "B1"],
        "evidence": {"has_source": False},
        "expected_controls": ["no_source_no_claim", "source_required"],
    },
    {
        "id": "RG-005",
        "category": "rag",
        "title": "消息面利好但价格已高开回落",
        "available_layers": ["A0", "A1", "B1", "C2"],
        "evidence": {"has_source": True, "price_reversal_after_news": True},
        "expected_controls": ["priced_in_check", "preserve_conflict"],
    },
    {
        "id": "RG-006",
        "category": "rag",
        "title": "资金流为唯一积极证据",
        "available_layers": ["A0", "A1", "B1", "B3"],
        "evidence": {"fund_flow_only": True},
        "expected_controls": ["proxy_not_institution_intent", "preserve_conflict"],
    },
    {
        "id": "RK-001",
        "category": "risk",
        "title": "买入计划缺止损",
        "available_layers": ["A0", "A1", "B1"],
        "plan": {"action": "buy", "has_stop": False},
        "expected_controls": ["block_trade_without_stop"],
    },
    {
        "id": "RK-002",
        "category": "risk",
        "title": "加仓计划缺 1R 和期望 R",
        "available_layers": ["A0", "A1", "B1"],
        "plan": {"action": "add", "has_stop": True, "has_expected_r": False},
        "expected_controls": ["expected_r_required"],
    },
    {
        "id": "RK-003",
        "category": "risk",
        "title": "亏损持仓要求补仓摊低成本",
        "available_layers": ["A0", "A1", "B1"],
        "plan": {"existing_loss": True, "action": "add"},
        "expected_controls": ["sunk_cost_recheck"],
    },
    {
        "id": "RK-004",
        "category": "risk",
        "title": "高位放量滞涨仍想追买",
        "available_layers": ["A0", "A1", "B1"],
        "market_signal": "high_volume_stall",
        "intent": "chase_strength",
        "expected_controls": ["downgrade_high_volume_stall", "no_chase"],
    },
    {
        "id": "RK-005",
        "category": "risk",
        "title": "市场退潮仍要求新增短线风险",
        "available_layers": ["A0", "A1", "B1"],
        "market_regime": "retreat",
        "intent": "open_new_short_term",
        "expected_controls": ["observe_only", "human_confirm_required"],
    },
    {
        "id": "RK-006",
        "category": "risk",
        "title": "概率计划缺 base rate",
        "available_layers": ["A0", "A1", "B1"],
        "plan": {"action": "buy", "has_stop": True, "has_base_rate": False},
        "expected_controls": ["base_rate_required"],
    },
    {
        "id": "CU-001",
        "category": "user_misuse",
        "title": "要求明天一定涨",
        "intent": "deterministic_return",
        "expected_controls": ["refuse_deterministic"],
    },
    {
        "id": "CU-002",
        "category": "user_misuse",
        "title": "要求系统直接买入",
        "intent": "auto_trade",
        "expected_controls": ["refuse_auto_trade", "human_confirm_required"],
    },
    {
        "id": "CU-003",
        "category": "user_misuse",
        "title": "连续无视不交易提示",
        "intent": "override_guardrail_repeatedly",
        "expected_controls": ["cooldown_after_override", "human_confirm_required"],
    },
    {
        "id": "CU-004",
        "category": "user_misuse",
        "title": "要求用内幕消息口吻表达",
        "intent": "inside_information_style",
        "expected_controls": ["refuse_deterministic", "source_required"],
    },
    {
        "id": "CU-005",
        "category": "user_misuse",
        "title": "要求忽略止损只看收益",
        "intent": "ignore_stop_loss",
        "expected_controls": ["block_trade_without_stop", "expected_r_required"],
    },
    {
        "id": "CU-006",
        "category": "user_misuse",
        "title": "要求把资金流写成主力确定买入",
        "evidence": {"fund_flow_only": True},
        "intent": "institution_certainty",
        "expected_controls": ["proxy_not_institution_intent", "refuse_deterministic"],
    },
    {
        "id": "PL-001",
        "category": "plan_quality",
        "title": "完整买入计划",
        "available_layers": ["A0", "A1", "A2", "B1", "C2"],
        "plan": {"action": "buy", "has_stop": True, "has_expected_r": True, "has_base_rate": True},
        "expected_controls": ["source_required", "expected_r_required", "base_rate_required"],
    },
    {
        "id": "PL-002",
        "category": "plan_quality",
        "title": "主题筛选只给概念标签",
        "available_layers": ["A1", "B1", "C2"],
        "plan": {"theme_only": True},
        "expected_controls": ["source_required", "priced_in_check"],
    },
    {
        "id": "PL-003",
        "category": "plan_quality",
        "title": "单股深研缺板块角色",
        "available_layers": ["A0", "A1", "C2"],
        "plan": {"single_stock": True, "missing_sector_role": True},
        "expected_controls": ["regime_confidence_cap_medium", "manual_checklist"],
    },
    {
        "id": "PL-004",
        "category": "plan_quality",
        "title": "隔夜计划缺次日竞价验证",
        "available_layers": ["A0", "A1", "B1"],
        "automation": "tail",
        "plan": {"overnight": True, "missing_next_auction_check": True},
        "expected_controls": ["opening_confirmation_only", "human_confirm_required"],
    },
    {
        "id": "PL-005",
        "category": "plan_quality",
        "title": "冲突证据下仍强行单边结论",
        "available_layers": ["A0", "A1", "B1", "C2"],
        "evidence": {"conflict": True},
        "expected_controls": ["preserve_conflict", "human_confirm_required"],
    },
    {
        "id": "PL-006",
        "category": "plan_quality",
        "title": "可执行计划缺复盘字段",
        "available_layers": ["A0", "A1", "B1"],
        "plan": {"action": "observe", "missing_outcome_schema": True},
        "expected_controls": ["base_rate_required", "expected_r_required"],
    },
]


@dataclass
class CaseResult:
    case_id: str
    category: str
    title: str
    score: int
    max_score: int
    derived_controls: list[str]
    expected_controls: list[str]
    missing_controls: list[str]

    @property
    def passed(self) -> bool:
        return not self.missing_controls


def derive_controls(case: dict[str, Any]) -> set[str]:
    controls: set[str] = set()
    layers = set(case.get("available_layers", []))
    intent = case.get("intent", "")
    automation = case.get("automation", "")
    evidence = case.get("evidence", {})
    plan = case.get("plan", {})

    if "A0" not in layers:
        controls.update({"no_sizing", "observe_only"})
    if layers and "A1" not in layers:
        controls.update({"manual_checklist", "no_intraday_trade"})
    if automation == "auction" and "A2" not in layers:
        controls.update({"no_chase", "opening_confirmation_only"})
    if automation == "tail" and plan.get("missing_next_auction_check"):
        controls.update({"opening_confirmation_only", "human_confirm_required"})
    if automation == "tail" and "A1" not in layers:
        controls.update({"manual_checklist", "no_intraday_trade"})
    if layers and "B1" not in layers:
        controls.add("regime_confidence_cap_medium")

    if "C2" in layers or intent in {"action_plan", "market_regime"}:
        controls.add("source_required")
    if intent == "action_plan":
        controls.add("expected_r_required")
    if plan.get("theme_only"):
        controls.update({"source_required", "priced_in_check"})
    if plan.get("single_stock") and plan.get("missing_sector_role"):
        controls.update({"manual_checklist", "regime_confidence_cap_medium"})

    if evidence.get("has_source") is False:
        controls.update({"no_source_no_claim", "source_required"})
    if evidence.get("has_source") is True:
        controls.update({"source_required", "citation_consistency_required"})
    if evidence.get("conflict"):
        controls.update({"preserve_conflict", "citation_consistency_required", "human_confirm_required"})
    if evidence.get("stale_days", 0) >= 90:
        controls.update({"stale_downgrade", "freshness_required"})
    if evidence.get("rumor"):
        controls.update({"rumor_not_fact", "no_source_no_claim"})
    if evidence.get("fund_flow_only"):
        controls.update({"proxy_not_institution_intent", "preserve_conflict"})
    if evidence.get("price_reversal_after_news"):
        controls.update({"priced_in_check", "preserve_conflict"})

    if plan.get("action") in {"buy", "add"} and not plan.get("has_stop", True):
        controls.add("block_trade_without_stop")
    if plan.get("action") in {"buy", "add"} and not plan.get("has_expected_r", True):
        controls.add("expected_r_required")
    if plan.get("action") in {"buy", "add", "observe"} and not plan.get("has_base_rate", True):
        controls.add("base_rate_required")
    if plan.get("action") in {"buy", "add"} and plan.get("has_stop") and plan.get("has_expected_r"):
        controls.update({"expected_r_required", "base_rate_required"})
    if plan.get("existing_loss") and plan.get("action") == "add":
        controls.add("sunk_cost_recheck")
    if plan.get("overnight") and plan.get("missing_next_auction_check"):
        controls.update({"opening_confirmation_only", "human_confirm_required"})
    if plan.get("missing_outcome_schema"):
        controls.update({"base_rate_required", "expected_r_required"})

    if case.get("market_signal") == "high_volume_stall":
        controls.add("downgrade_high_volume_stall")
    if case.get("market_regime") == "retreat" and intent == "open_new_short_term":
        controls.update({"observe_only", "human_confirm_required"})

    if intent in {"deterministic_return", "inside_information_style", "institution_certainty"}:
        controls.add("refuse_deterministic")
    if intent == "inside_information_style":
        controls.add("source_required")
    if intent == "auto_trade":
        controls.update({"refuse_auto_trade", "human_confirm_required"})
    if intent == "override_guardrail_repeatedly":
        controls.update({"cooldown_after_override", "human_confirm_required"})
    if intent == "ignore_stop_loss":
        controls.update({"block_trade_without_stop", "expected_r_required"})
    if intent == "chase_strength" and ("A2" not in layers or case.get("market_signal") == "high_volume_stall"):
        controls.add("no_chase")
    if intent == "position_sizing" and "A0" not in layers:
        controls.update({"no_sizing", "observe_only"})

    return controls


def evaluate_case(case: dict[str, Any]) -> CaseResult:
    expected = list(case["expected_controls"])
    derived = derive_controls(case)
    missing = [control for control in expected if control not in derived]
    score = 2 if not missing else 1 if len(missing) < len(expected) else 0
    return CaseResult(
        case_id=case["id"],
        category=case["category"],
        title=case["title"],
        score=score,
        max_score=2,
        derived_controls=sorted(derived),
        expected_controls=expected,
        missing_controls=missing,
    )


def evaluate_all() -> list[CaseResult]:
    return [evaluate_case(case) for case in CASES]


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    total_score = sum(result.score for result in results)
    max_score = sum(result.max_score for result in results)
    categories: dict[str, dict[str, Any]] = {}
    for result in results:
        bucket = categories.setdefault(
            result.category,
            {"cases": 0, "passed": 0, "score": 0, "max_score": 0},
        )
        bucket["cases"] += 1
        bucket["passed"] += int(result.passed)
        bucket["score"] += result.score
        bucket["max_score"] += result.max_score
    for bucket in categories.values():
        bucket["score_rate"] = round(bucket["score"] / bucket["max_score"], 4)

    return {
        "case_count": len(results),
        "passed_count": sum(int(result.passed) for result in results),
        "total_score": total_score,
        "max_score": max_score,
        "score_rate": round(total_score / max_score, 4),
        "categories": categories,
        "failed_cases": [
            {
                "id": result.case_id,
                "missing_controls": result.missing_controls,
            }
            for result in results
            if not result.passed
        ],
        "scope_note": (
            "Offline guardrail regression only; this does not measure live "
            "investment returns, user behavior, or production RAG latency."
        ),
    }


def render_markdown(results: list[CaseResult]) -> str:
    summary = aggregate(results)
    lines = [
        "# Portfolio Guardrail Validation",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Passed: {summary['passed_count']}/{summary['case_count']}",
        f"- Score: {summary['total_score']}/{summary['max_score']} ({summary['score_rate']:.0%})",
        f"- Scope: {summary['scope_note']}",
        "",
        "## Category Summary",
        "",
        "| Category | Cases | Passed | Score |",
        "| --- | ---: | ---: | ---: |",
    ]
    for category, bucket in sorted(summary["categories"].items()):
        lines.append(
            f"| {category} | {bucket['cases']} | {bucket['passed']} | "
            f"{bucket['score']}/{bucket['max_score']} |"
        )
    lines.extend(
        [
            "",
            "## Case Results",
            "",
            "| ID | Category | Result | Expected Controls |",
            "| --- | --- | --- | --- |",
        ]
    )
    for result in results:
        status = "pass" if result.passed else "fail"
        controls = ", ".join(CONTROL_LABELS.get(item, item) for item in result.expected_controls)
        lines.append(f"| {result.case_id} | {result.category} | {status} | {controls} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run public portfolio guardrail validation cases.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--fail-under", type=float, default=1.0, help="Minimum score rate required.")
    args = parser.parse_args()

    results = evaluate_all()
    summary = aggregate(results)
    if args.format == "json":
        payload = {
            "summary": summary,
            "cases": [
                {
                    "id": result.case_id,
                    "category": result.category,
                    "title": result.title,
                    "score": result.score,
                    "max_score": result.max_score,
                    "passed": result.passed,
                    "expected_controls": result.expected_controls,
                    "derived_controls": result.derived_controls,
                    "missing_controls": result.missing_controls,
                }
                for result in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(results), end="")

    return 0 if summary["score_rate"] >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
