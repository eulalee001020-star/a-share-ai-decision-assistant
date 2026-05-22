#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local runner for the A-share research assistant.

This tool intentionally does not fetch or invent market data. It validates the
portfolio config and assembles auditable run packets that make missing fresh
data explicit before any trading conclusion is formed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_CONFIG_ENV = "TRADING_ASSISTANT_PORTFOLIO"

PROMPTS = {
    "auction": {
        "title": "09:28 竞价预测与开盘计划",
        "path": "prompts/auction_check.md",
        "suffix": "0928-auction-run.md",
    },
    "theme": {
        "title": "主题股票池与标的锚定",
        "path": "prompts/theme_screening.md",
        "suffix": "theme-screening-run.md",
    },
    "single": {
        "title": "单股深度研究",
        "path": "prompts/single_stock_research.md",
        "suffix": "single-stock-run.md",
    },
    "tail": {
        "title": "14:30 尾盘预测与隔夜计划",
        "path": "prompts/tail_check.md",
        "suffix": "1430-tail-check-run.md",
    },
}

CORE_CONTEXT_FILES = [
    "README.md",
    "AGENTS.md",
    "config/portfolio.json",
    "config/portfolio.example.json",
    "docs/trading_assistant_state.md",
    "docs/trading_assistant_state.example.md",
    "docs/trading_system_upgrade.md",
    "docs/data_sources.md",
    "docs/prediction_automation_system.md",
]


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]
    notes: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def read_text(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def portfolio_config_path(root: Path) -> Path:
    env_path = os.getenv(PORTFOLIO_CONFIG_ENV)
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend(
        [
            root / "config" / "portfolio.json",
            root / "config" / "portfolio.example.json",
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(str(root / "config" / "portfolio.json"))


def load_portfolio(root: Path) -> dict[str, Any]:
    with portfolio_config_path(root).open(encoding="utf-8") as fh:
        return json.load(fh)


def today_string() -> str:
    return dt.date.today().isoformat()


def normalize_code(code: str) -> str:
    return str(code).strip().upper()


def code_number(code: str) -> str:
    normalized = normalize_code(code)
    numeric = normalized.split(".", 1)[0]
    if numeric.isdigit() and len(numeric) == 6:
        return numeric
    if len(normalized) == 8 and normalized[:2].lower() in {"sh", "sz", "bj"}:
        return normalized[2:]
    return normalized


def code_exchange(code: str) -> str:
    normalized = normalize_code(code)
    numeric = code_number(normalized)
    if normalized.endswith(".SH") or normalized.lower().startswith("sh"):
        return "SH"
    if normalized.endswith(".SZ") or normalized.lower().startswith("sz"):
        return "SZ"
    if normalized.endswith(".BJ") or normalized.lower().startswith("bj"):
        return "BJ"
    if numeric.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if numeric.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZ"
    if numeric.startswith(("8", "9")):
        return "BJ"
    return ""


def sina_code(code: str) -> str:
    numeric = code_number(code)
    exchange = code_exchange(code)
    prefix = "sh" if exchange == "SH" else "sz" if exchange == "SZ" else "bj"
    return f"{prefix}{numeric}"


def tencent_code(code: str) -> str:
    return sina_code(code)


def portfolio_style_code(code: str) -> str:
    numeric = code_number(code)
    exchange = code_exchange(code)
    if exchange:
        return f"{numeric}.{exchange}"
    return numeric


def is_main_board_a_share(code: str) -> bool:
    normalized = normalize_code(code)
    numeric = normalized.split(".", 1)[0]
    if not numeric.isdigit() or len(numeric) != 6:
        return False
    if normalized.endswith(".SH"):
        return numeric.startswith(("600", "601", "603", "605"))
    if normalized.endswith(".SZ"):
        return numeric.startswith(("000", "001", "002", "003"))
    return False


def pct(value: Any) -> str:
    if value is None:
        return "缺失"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def money(value: Any) -> str:
    if value is None:
        return "缺失"
    try:
        return f"CNY {float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def risk_engine(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("risk_engine", {})
    return value if isinstance(value, dict) else {}


def estimate_position_stop_risk(item: dict[str, Any]) -> dict[str, float] | None:
    plan = item.get("risk_plan", {})
    if not isinstance(plan, dict):
        return None

    reference_price = as_float(
        plan.get("reference_price") or item.get("last_price_from_screenshot")
    )
    stop_price = as_float(plan.get("stop_price_for_sizing"))
    position_pct = as_float(item.get("current_position_pct"))
    if reference_price <= 0 or stop_price <= 0 or position_pct <= 0:
        return None
    if stop_price >= reference_price:
        return None

    stop_distance_pct = (reference_price - stop_price) / reference_price * 100
    account_loss_pct = position_pct * stop_distance_pct / 100
    return {
        "reference_price": reference_price,
        "stop_price": stop_price,
        "stop_distance_pct": stop_distance_pct,
        "account_loss_pct": account_loss_pct,
    }


def validate_portfolio(data: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    total_assets = as_float(data.get("total_assets_cny"))
    if total_assets <= 0:
        errors.append("total_assets_cny 必须大于 0。")

    required_numeric = [
        "total_market_value_cny",
        "cash_available_cny",
        "total_position_pct",
        "cash_pct",
        "short_term_total_limit_pct",
        "single_stock_limit_pct",
        "max_loss_per_trade_pct",
    ]
    for key in required_numeric:
        if key not in data:
            errors.append(f"缺少必填风控字段：{key}。")

    engine = risk_engine(data)
    if not engine:
        warnings.append("缺少 risk_engine，无法进行市场状态、动态仓位和连亏降档校验。")
    else:
        required_risk_keys = [
            "daily_stop_loss_pct",
            "weekly_stop_loss_pct",
            "max_loss_streak_before_pause",
            "market_regime_position_caps",
            "playbooks",
            "trade_journal_fields",
        ]
        for key in required_risk_keys:
            if key not in engine:
                warnings.append(f"risk_engine 缺少：{key}。")
        if as_float(engine.get("daily_stop_loss_pct")) <= 0:
            warnings.append("risk_engine.daily_stop_loss_pct 必须大于0。")
        if as_float(engine.get("weekly_stop_loss_pct")) <= 0:
            warnings.append("risk_engine.weekly_stop_loss_pct 必须大于0。")
        if not isinstance(engine.get("market_regime_position_caps"), list):
            warnings.append("risk_engine.market_regime_position_caps 必须是数组。")
        if not isinstance(engine.get("playbooks"), list):
            warnings.append("risk_engine.playbooks 必须是数组。")

    market_value = as_float(data.get("total_market_value_cny"))
    cash_available = as_float(data.get("cash_available_cny"))
    if total_assets > 0 and market_value + cash_available:
        gap = abs((market_value + cash_available) - total_assets)
        if gap > max(total_assets * 0.01, 1000):
            warnings.append(
                "total_market_value_cny + cash_available_cny 与 total_assets_cny 偏差超过 1%。"
            )

    if total_assets > 0 and "total_position_pct" in data:
        computed_position_pct = market_value / total_assets * 100
        configured_position_pct = as_float(data.get("total_position_pct"))
        if abs(computed_position_pct - configured_position_pct) > 0.2:
            warnings.append(
                f"total_position_pct 与市值口径不一致：配置 {configured_position_pct:.2f}%，"
                f"按市值计算 {computed_position_pct:.2f}%。"
            )

    positions = data.get("positions", [])
    if not isinstance(positions, list):
        errors.append("positions 必须是数组。")
        positions = []

    single_limit = as_float(data.get("single_stock_limit_pct"))
    short_limit = as_float(data.get("short_term_total_limit_pct"))
    max_loss_pct = as_float(data.get("max_loss_per_trade_pct"))
    short_position_pct = 0.0
    for item in positions:
        code = normalize_code(item.get("code", ""))
        name = item.get("name", code or "未命名")
        if not is_main_board_a_share(code):
            errors.append(f"{name} {code} 不符合沪深主板-only约束。")
        position_pct = as_float(item.get("current_position_pct"))
        if position_pct > single_limit > 0:
            warnings.append(f"{name} {code} 仓位 {position_pct:.2f}% 超过单票上限 {single_limit:.2f}%。")
        if as_float(item.get("cost")) < 0:
            warnings.append(f"{name} {code} 成本为负，需用真实成交记录校正后再判断盈亏。")
        if item.get("holding_period") == "短线":
            short_position_pct += position_pct
        if not item.get("must_answer"):
            warnings.append(f"{name} {code} 缺少 must_answer，盘前处理目标不够明确。")
        plan = item.get("risk_plan")
        if not isinstance(plan, dict):
            warnings.append(f"{name} {code} 缺少 risk_plan，无法按止损距离倒推仓位。")
        elif plan.get("stop_price_for_sizing") is None:
            warnings.append(f"{name} {code} 缺少 stop_price_for_sizing，加仓前必须补齐结构止损价。")
        metrics = estimate_position_stop_risk(item)
        if metrics:
            account_loss_pct = metrics["account_loss_pct"]
            if max_loss_pct > 0 and account_loss_pct > max_loss_pct:
                warnings.append(
                    f"{name} {code} 若打到结构止损，预计亏损 {account_loss_pct:.2f}% "
                    f"超过单笔预算 {max_loss_pct:.2f}%。"
                )
            elif max_loss_pct > 0 and account_loss_pct >= max_loss_pct * 0.8:
                notes.append(
                    f"{name} {code} 若打到结构止损，预计亏损 {account_loss_pct:.2f}%，"
                    f"接近单笔预算 {max_loss_pct:.2f}%。"
                )

    if short_limit > 0 and short_position_pct > short_limit:
        warnings.append(f"短线合计仓位 {short_position_pct:.2f}% 超过上限 {short_limit:.2f}%。")
    else:
        notes.append(f"短线合计仓位 {short_position_pct:.2f}%，上限 {short_limit:.2f}%。")

    watchlist = data.get("watchlist", [])
    if not isinstance(watchlist, list):
        errors.append("watchlist 必须是数组。")
        watchlist = []
    for item in watchlist:
        code = normalize_code(item.get("code", ""))
        name = item.get("name", code or "未命名")
        if not is_main_board_a_share(code):
            errors.append(f"观察池 {name} {code} 不符合沪深主板-only约束。")

    forbidden = set(data.get("forbidden", []))
    expected_forbidden = {"ST", "退市风险", "日成交额低于2亿", "无明确止损位的追涨"}
    missing_forbidden = sorted(expected_forbidden - forbidden)
    if missing_forbidden:
        warnings.append("forbidden 缺少：" + "、".join(missing_forbidden))

    if not data.get("preferred_themes"):
        notes.append("preferred_themes 为空：按当日市场状态、持仓风险和用户新增线索动态生成主题方向。")

    return ValidationResult(errors=errors, warnings=warnings, notes=notes)


def render_validation(result: ValidationResult, include_title: bool = True) -> str:
    lines = ["# 配置校验"] if include_title else []
    lines.append("状态：通过" if result.ok else "状态：未通过")
    if result.errors:
        lines.append("\n## 错误")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("\n## 警告")
        lines.extend(f"- {item}" for item in result.warnings)
    if result.notes:
        lines.append("\n## 备注")
        lines.extend(f"- {item}" for item in result.notes)
    return "\n".join(lines) + "\n"


def render_account_snapshot(data: dict[str, Any]) -> str:
    total_assets = as_float(data.get("total_assets_cny"))
    total_position = as_float(data.get("total_position_pct"))
    cash_pct = as_float(data.get("cash_pct"))
    short_limit = as_float(data.get("short_term_total_limit_pct"))
    single_limit = as_float(data.get("single_stock_limit_pct"))
    max_loss_pct = as_float(data.get("max_loss_per_trade_pct"))
    offensive_room = max(0.0, min(short_limit - total_position, cash_pct))
    risk_budget = total_assets * max_loss_pct / 100 if total_assets > 0 else 0.0

    positions = data.get("positions", [])
    largest = None
    if positions:
        largest = max(positions, key=lambda item: as_float(item.get("current_position_pct")))

    lines = [
        f"- 总账户资金：{money(total_assets)}",
        f"- 当前总仓位：{pct(total_position)}；现金：{pct(cash_pct)}",
        f"- 短线仓位上限：{pct(short_limit)}；理论剩余进攻仓位：{pct(offensive_room)}",
        f"- 单票上限：{pct(single_limit)}；单笔最大亏损预算：{money(risk_budget)}",
    ]
    if largest:
        lines.append(
            f"- 最大持仓：{largest.get('name')} {largest.get('code')}，"
            f"{pct(largest.get('current_position_pct'))}"
        )
    return "\n".join(lines)


def render_risk_engine_snapshot(data: dict[str, Any]) -> str:
    engine = risk_engine(data)
    if not engine:
        return "未配置 risk_engine；只能使用静态仓位上限，无法进行动态仓位和降档控制。"

    lines = [
        f"- 仓位方法：{engine.get('position_sizing_method', '缺失')}",
        f"- 1R定义：{engine.get('risk_unit', '缺失')}",
        (
            f"- 基础单笔风险：{pct(engine.get('base_risk_budget_pct'))}；"
            f"日内停手线：{pct(engine.get('daily_stop_loss_pct'))}；"
            f"周降档线：{pct(engine.get('weekly_stop_loss_pct'))}；"
            f"连续止损暂停：{engine.get('max_loss_streak_before_pause', '缺失')}笔"
        ),
        "",
        "### 持仓止损风险测算",
        "| 股票 | 仓位 | 参考价 | 结构止损价 | 止损距离 | 打到止损的账户亏损 | 状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    max_loss_pct = as_float(data.get("max_loss_per_trade_pct"))
    for item in data.get("positions", []):
        name = item.get("name", "")
        plan = item.get("risk_plan", {})
        metrics = estimate_position_stop_risk(item)
        if not metrics:
            reference = as_float(plan.get("reference_price")) if isinstance(plan, dict) else 0.0
            stop = as_float(plan.get("stop_price_for_sizing")) if isinstance(plan, dict) else 0.0
            if isinstance(plan, dict) and reference > 0 and stop > 0 and stop >= reference:
                lines.append(
                    f"| {name} | {pct(item.get('current_position_pct'))} | "
                    f"{reference:.2f} | {stop:.2f} | 已在结构线下 | 不适用 | "
                    "结构风控已触发；只按修复线/减风险处理 |"
                )
                continue

            status = "缺结构止损价；不得新增风险" if isinstance(plan, dict) else "缺risk_plan"
            reference_value = plan.get("reference_price") if isinstance(plan, dict) else None
            lines.append(
                f"| {name} | {pct(item.get('current_position_pct'))} | "
                f"{money(reference_value).replace('CNY ', '') if reference_value is not None else '缺失'} | "
                f"缺失 | 缺失 | 缺失 | {status} |"
            )
            continue

        account_loss_pct = metrics["account_loss_pct"]
        if max_loss_pct > 0 and account_loss_pct > max_loss_pct:
            status = "超过单笔预算，需降仓或上移止损"
        elif max_loss_pct > 0 and account_loss_pct >= max_loss_pct * 0.8:
            status = "接近单笔预算，只能按计划持有"
        else:
            status = "在单笔预算内，仍需竞价确认"

        lines.append(
            "| {name} | {position} | {reference:.2f} | {stop:.2f} | {distance} | {loss} | {status} |".format(
                name=name,
                position=pct(item.get("current_position_pct")),
                reference=metrics["reference_price"],
                stop=metrics["stop_price"],
                distance=pct(metrics["stop_distance_pct"]),
                loss=pct(account_loss_pct),
                status=status,
            )
        )

    regimes = engine.get("market_regime_position_caps", [])
    if isinstance(regimes, list) and regimes:
        lines.extend(
            [
                "",
                "### 市场状态仓位权限",
                "| 状态 | 总仓位上限 | 新增风险规则 | 允许打法 |",
                "| --- | ---: | --- | --- |",
            ]
        )
        for item in regimes:
            if not isinstance(item, dict):
                continue
            styles = "、".join(item.get("allowed_styles", [])) or "缺失"
            lines.append(
                "| {regime} | {cap} | {rule} | {styles} |".format(
                    regime=item.get("regime", "缺失"),
                    cap=pct(item.get("total_position_cap_pct")),
                    rule=item.get("new_position_rule", "缺失"),
                    styles=styles,
                )
            )

    return "\n".join(lines)


def render_positions(data: dict[str, Any]) -> str:
    positions = data.get("positions", [])
    if not positions:
        return "暂无持仓。"
    lines = [
        "| 股票 | 代码 | 仓位 | 持仓周期 | 主题 | 今日必须回答 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for item in positions:
        themes = "、".join(item.get("theme_tags", [])) or "缺失"
        lines.append(
            "| {name} | {code} | {position} | {period} | {themes} | {question} |".format(
                name=item.get("name", ""),
                code=item.get("code", ""),
                position=pct(item.get("current_position_pct")),
                period=item.get("holding_period", "缺失"),
                themes=themes,
                question=item.get("must_answer", "缺失"),
            )
        )
    return "\n".join(lines)


def render_watchlist(data: dict[str, Any]) -> str:
    watchlist = data.get("watchlist", [])
    if not watchlist:
        return "暂无观察池。"
    lines = [
        "| 优先级 | 股票 | 代码 | 方向 | 角色 | 状态 | 观察理由 | 必查项 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in watchlist:
        checks = "；".join(item.get("must_check", [])) or "缺失"
        lines.append(
            "| {priority} | {name} | {code} | {theme} | {role} | {status} | {reason} | {checks} |".format(
                priority=item.get("priority", "未分级"),
                name=item.get("name", ""),
                code=item.get("code", ""),
                theme=item.get("theme_bucket", "缺失"),
                role=item.get("role", "缺失"),
                status=item.get("status", "观察"),
                reason=item.get("reason", "缺失"),
                checks=checks,
            )
        )
    return "\n".join(lines)


def render_preferred_themes(data: dict[str, Any]) -> str:
    themes = data.get("preferred_themes", [])
    if not themes:
        return "无固定偏好方向；按当日市场状态、持仓风险、外盘映射、公告/产业新增信息和用户新增线索动态生成。"
    lines: list[str] = []
    for item in themes:
        lines.append(f"- {item.get('name', '未命名方向')}")
        for requirement in item.get("requirements", []):
            lines.append(f"  - {requirement}")
    return "\n".join(lines)


def render_continuity_brief(data: dict[str, Any]) -> str:
    return "\n".join(
        [
            "- 连续性文档：本地真实运行用 `docs/trading_assistant_state.md`；公开 demo 可用 `docs/trading_assistant_state.example.md`。",
            f"- 固定口径：总资金 {money(data.get('total_assets_cny'))}、主板-only、09:28 竞价校正 + 14:30 尾盘评分。",
            "- 决策纪律：贝叶斯更新、降低沉没成本、只输出研究和风控，不自动下单。",
            "- 观察池只能作为当前工作清单；主题方向必须按当天资金、板块和盘口刷新，不得静态沿用。",
        ]
    )


def render_data_gap_checklist(mode: str) -> str:
    base = [
        "数据等级：A0/A1/A2/B1/B2/B3/C 可得性，以及缺失数据禁止哪些结论",
        "A股交易日/节假日状态",
        "上证、深成指、沪深300、中证1000等主要指数与成交额",
        "涨跌家数、涨停/跌停数、连板高度、昨日涨停反馈",
        "市场状态判定：强进攻、轮动、退潮、冰点修复或混沌，并给出仓位权限",
        "账户当日/本周已实现亏损、连续止损次数、是否触发停手或降档",
        "持仓与观察池最新价、1/5/10/20日涨跌幅、成交额、换手率、量比",
        "5/10/20/60日均线位置、支撑位、压力位、结构止损位",
        "公告、政策、产业链新闻与来源时间戳",
        "行业/概念资金流排名、领涨股、净流入净流出；个股资金流只在稳定采集或截图可得时引用",
        "龙虎榜、热门股排名、连板高度、炸板/断板反馈",
    ]
    if mode == "auction":
        base.extend(
            [
                "A2核心竞价：09:15-09:25 预开价、竞价涨跌幅、竞价成交额/成交量、09:20后撤单变化、封单额、盘口队列",
                "板块龙头、中军、补涨的竞价强弱排序；缺失时禁止追强和竞价超预期结论",
                "事件预测：09:35、10:00、收盘的关键位成功/失败/噪音概率",
            ]
        )
    if mode == "theme":
        base.extend(
            [
                "每个偏好方向的候选池与主板资格",
                "龙头/中军/补涨/跟风定位的证据",
                "明确排除票及排除原因",
            ]
        )
    if mode == "single":
        base.extend(
            [
                "个股最新公告、财务指标、估值分位与产业链映射",
                "用户截图中的盘口、分时、筹码或K线信息；没有截图时不反复列长期不可得项",
            ]
        )
    if mode == "tail":
        base.extend(
            [
                "14:30 前后观察池股票实时价格、涨跌幅、成交额、换手率、量比",
                "日内均价/VWAP、分时是否收回、日内高低点回撤、尾盘是否放量承接",
                "当日主线方向的龙头、中军、补涨收盘前强弱与炸板/回封情况",
                "09:28预测复盘：实际结果、误差类型、下次权重修正",
                "观察股隔夜预测所需的结构止损、目标R、隔夜跳空风险、期望R和明日竞价验证条件",
            ]
        )
    base.append("筹码峰、股东/基金/融资/港股通、资金流等数据按 `docs/prediction_automation_system.md` 分层使用：竞价盘口是核心输入，筹码是结构概率修正，股东/基金/融资是慢变量，资金流是代理证据。")
    return "\n".join(f"- {item}" for item in base)


def render_run_packet(root: Path, mode: str, run_date: str) -> str:
    if mode not in PROMPTS:
        raise ValueError(f"unknown mode: {mode}")

    data = load_portfolio(root)
    validation = validate_portfolio(data)
    prompt_info = PROMPTS[mode]
    prompt_text = read_text(root, prompt_info["path"])

    lines = [
        f"# A股助手运行包｜{run_date}｜{prompt_info['title']}",
        "",
        "> 本文件由本地工具生成，用于组织研究流程。它不包含实时行情抓取结果；任何交易判断都必须在补齐下方数据缺口后再形成。",
        "",
        "## 1. 必读上下文",
    ]
    lines.extend(f"- `{item}`" for item in CORE_CONTEXT_FILES)
    lines.extend(
        [
            "",
            "## 2. 配置校验",
            render_validation(validation, include_title=False).strip(),
            "",
            "## 3. 账户与风控快照",
            render_account_snapshot(data),
            "",
            "## 4. 风控发动机与市场状态",
            render_risk_engine_snapshot(data),
            "",
            "## 5. 持仓逐只待处理",
            render_positions(data),
            "",
            "## 6. 观察池与重点检查",
            render_watchlist(data),
            "",
            "## 7. 动态主题方向",
            render_preferred_themes(data),
            "",
            "## 8. 运行前必须补齐的数据",
            render_data_gap_checklist(mode),
            "",
            "## 9. 当前连续性要点",
            render_continuity_brief(data),
            "",
            "## 10. 执行提示词",
            prompt_text.strip(),
            "",
            "## 11. 纪律提醒",
            "- 区分事实、推断、交易计划。",
            "- 没有实时行情、公告来源、竞价数据时，只能输出低置信度预案或清单。",
            "- 先判市场状态，再判个股；市场状态不支持时，只能降仓、观察或等待。",
            "- 每个交易计划必须先定义1R、结构止损、目标R倍数和不交易条件。",
            "- 不自动下单；不承诺收益；不因为已有浮亏、已研究或已持仓而继续投入资金。",
        ]
    )
    return "\n".join(lines) + "\n"


def output_path_for(root: Path, mode: str, run_date: str) -> Path:
    return root / "reports" / f"{run_date}-{PROMPTS[mode]['suffix']}"


def http_get_text(url: str, *, retries: int = 3, timeout: float = 10.0) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last_error}")


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def parse_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def read_target_codes(data: dict[str, Any], extra_codes: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for section in ("positions", "watchlist"):
        for item in data.get(section, []) if isinstance(data.get(section), list) else []:
            code = portfolio_style_code(str(item.get("code", "")))
            if code and code not in seen and is_main_board_a_share(code):
                seen.add(code)
                result.append(code)
    for item in extra_codes or []:
        code = portfolio_style_code(item)
        if code and code not in seen and is_main_board_a_share(code):
            seen.add(code)
            result.append(code)
    return result


def fetch_sina_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for group in chunked([sina_code(code) for code in codes], 80):
        text = http_get_text("https://hq.sinajs.cn/list=" + ",".join(group), timeout=8)
        for match in re.finditer(r'var hq_str_(\w+)="([^"]*)";', text):
            raw_code = match.group(1)
            parts = match.group(2).split(",")
            if len(parts) < 32 or not parts[0]:
                continue
            numeric = code_number(raw_code)
            exchange = code_exchange(raw_code)
            key = f"{numeric}.{exchange}"
            open_price = parse_float(parts[1])
            previous_close = parse_float(parts[2])
            current = parse_float(parts[3])
            high = parse_float(parts[4])
            low = parse_float(parts[5])
            volume_shares = parse_float(parts[8])
            amount = parse_float(parts[9])
            vwap = amount / volume_shares if amount and volume_shares else None
            output[key] = {
                "code": key,
                "name": parts[0].replace(" ", ""),
                "source_quote": "sina",
                "open": open_price,
                "previous_close": previous_close,
                "price": current,
                "high": high,
                "low": low,
                "volume_shares": volume_shares,
                "amount": amount,
                "vwap": vwap,
                "change_pct": pct_change(current, previous_close),
                "quote_date": parts[30],
                "quote_time": parts[31],
            }
            for level in range(1, 6):
                bid_volume_index = 8 + level * 2
                bid_price_index = bid_volume_index + 1
                ask_volume_index = 18 + level * 2
                ask_price_index = ask_volume_index + 1
                output[key][f"bid{level}"] = parse_float(parts[bid_price_index])
                output[key][f"bid{level}_volume_lots"] = parse_float(parts[bid_volume_index])
                output[key][f"ask{level}"] = parse_float(parts[ask_price_index])
                output[key][f"ask{level}_volume_lots"] = parse_float(parts[ask_volume_index])
    return output


def fetch_tencent_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for group in chunked([tencent_code(code) for code in codes], 80):
        text = http_get_text("https://qt.gtimg.cn/q=" + ",".join(group), timeout=8)
        for match in re.finditer(r'v_(\w+)="([^"]*)";', text):
            raw_code = match.group(1)
            parts = match.group(2).split("~")
            if len(parts) < 50:
                continue
            numeric = code_number(raw_code)
            exchange = code_exchange(raw_code)
            key = f"{numeric}.{exchange}"
            output[key] = {
                "code": key,
                "name": parts[1],
                "source_quote": "tencent",
                "price": parse_float(parts[3]),
                "previous_close": parse_float(parts[4]),
                "open": parse_float(parts[5]),
                "quote_time": parts[30],
                "change": parse_float(parts[31]),
                "change_pct": parse_float(parts[32]),
                "high": parse_float(parts[33]),
                "low": parse_float(parts[34]),
                "amount": parse_float(parts[37]) * 10000 if parse_float(parts[37]) is not None else None,
                "turnover_rate": parse_float(parts[38]),
                "pe_dynamic": parse_float(parts[39]),
                "amplitude": parse_float(parts[43]),
                "market_cap_100m": parse_float(parts[44]),
                "float_market_cap_100m": parse_float(parts[45]),
                "volume_ratio": parse_float(parts[49]),
            }
    return output


def merge_quotes(primary: dict[str, dict[str, Any]], fallback: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged = {code: dict(value) for code, value in primary.items()}
    for code, values in fallback.items():
        if code not in merged:
            merged[code] = dict(values)
            continue
        for key, value in values.items():
            if merged[code].get(key) in (None, "", 0) and value not in (None, ""):
                merged[code][key] = value
            elif key in {"turnover_rate", "volume_ratio", "pe_dynamic", "market_cap_100m", "float_market_cap_100m", "amplitude"}:
                merged[code][key] = value
    return merged


def fetch_tencent_minute(code: str, target_time: str) -> dict[str, Any]:
    raw_code = tencent_code(code)
    target = int(target_time)
    candidates = [
        f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={raw_code}",
        f"https://ifzq.gtimg.cn/appstock/app/minute/query?code={raw_code}",
    ]
    text = ""
    last_error: Exception | None = None
    for url in candidates:
        try:
            text = http_get_text(url, timeout=8)
            break
        except RuntimeError as exc:
            last_error = exc
    if not text:
        raise RuntimeError(str(last_error))
    payload = json.loads(text)
    lines = payload.get("data", {}).get(raw_code, {}).get("data", {}).get("data", [])
    selected: list[str] | None = None
    prices_until_target: list[float] = []
    for item in lines:
        parts = str(item).split()
        if len(parts) < 4:
            continue
        minute = int(parts[0])
        price = parse_float(parts[1])
        if price is not None and minute <= target:
            prices_until_target.append(price)
        if minute <= target:
            selected = parts
        else:
            break
    if not selected:
        return {"minute_source": "tencent", "minute_missing": "no minute <= target"}
    minute = selected[0]
    price = parse_float(selected[1])
    cum_volume_lots = parse_float(selected[2])
    cum_amount = parse_float(selected[3])
    return {
        "minute_source": "tencent",
        "target_time": target_time,
        "target_actual_time": minute,
        "target_price": price,
        "target_cum_volume_lots": cum_volume_lots,
        "target_amount": cum_amount,
        "target_vwap": cum_amount / (cum_volume_lots * 100) if cum_amount and cum_volume_lots else None,
        "target_minute_high": max(prices_until_target) if prices_until_target else None,
        "target_minute_low": min(prices_until_target) if prices_until_target else None,
    }


def fetch_tencent_daily_metrics(code: str) -> dict[str, Any]:
    raw_code = tencent_code(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={raw_code},day,,,90,qfq"
    payload = json.loads(http_get_text(url, timeout=10))
    data = payload.get("data", {}).get(raw_code, {})
    rows = data.get("qfqday") or data.get("day") or []
    closes = [parse_float(row[2]) for row in rows if len(row) >= 6]
    volumes = [parse_float(row[5]) for row in rows if len(row) >= 6]
    closes = [item for item in closes if item is not None]
    volumes = [item for item in volumes if item is not None]
    result: dict[str, Any] = {"daily_source": "tencent_qfq"}
    for window in (5, 10, 20, 60):
        if len(closes) >= window:
            result[f"ma{window}"] = sum(closes[-window:]) / window
    for window in (5, 10, 20):
        if len(closes) > window and closes[-1 - window]:
            result[f"pct{window}"] = pct_change(closes[-1], closes[-1 - window])
    if len(volumes) > 20:
        average = sum(volumes[-21:-1]) / 20
        result["volume_vs_20d"] = volumes[-1] / average if average else None
    return result


def limit_state(item: dict[str, Any]) -> str:
    pct_value = item.get("change_pct")
    price = item.get("price")
    high = item.get("high")
    low = item.get("low")
    if pct_value is None:
        return "缺失"
    if pct_value >= 9.8 and price == high:
        return "涨停或近似涨停"
    if pct_value >= 9.8 and high and price and price < high:
        return "触及涨停后打开"
    if pct_value <= -9.8 and price == low:
        return "跌停或近似跌停"
    return "正常交易"


def run_python_json(code: str, timeout: int) -> Any:
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("subprocess returned empty stdout")
    return json.loads(stdout.splitlines()[-1])


def enrich_quote_metrics(item: dict[str, Any]) -> dict[str, Any]:
    price = item.get("price")
    high = item.get("high")
    low = item.get("low")
    vwap = item.get("vwap")
    target_price = item.get("target_price")
    target_vwap = item.get("target_vwap")
    result = dict(item)
    result["close_vs_vwap_pct"] = pct_change(price, vwap)
    result["target_vs_vwap_pct"] = pct_change(target_price, target_vwap)
    result["drawdown_from_high_pct"] = pct_change(price, high)
    if price is not None and high is not None and low is not None and high > low:
        result["range_position_pct"] = (price - low) / (high - low) * 100
    result["limit_state"] = limit_state(result)
    missing_core = [
        key
        for key in ("price", "open", "high", "low", "amount", "turnover_rate", "volume_ratio", "target_vwap", "ma5", "ma10", "ma20", "ma60")
        if result.get(key) is None
    ]
    result["data_quality"] = "完整" if not missing_core else "部分缺失"
    result["missing_core_fields"] = "；".join(missing_core)
    return result


def fetch_market_activity(run_date: str) -> dict[str, Any]:
    activity: dict[str, Any] = {"source": "akshare+eastmoney/sina", "date": run_date}
    try:
        activity["legu_activity"] = run_python_json(
            """
import json
import akshare as ak
df = ak.stock_market_activity_legu()
values = {}
for _, row in df.iterrows():
    raw = row["value"]
    if isinstance(raw, str) and raw.endswith("%"):
        try:
            values[str(row["item"])] = float(raw.rstrip("%"))
        except Exception:
            values[str(row["item"])] = raw
    else:
        try:
            values[str(row["item"])] = float(raw)
        except Exception:
            values[str(row["item"])] = raw
print(json.dumps(values, ensure_ascii=False))
""",
            timeout=8,
        )
    except Exception as exc:  # pragma: no cover - depends on remote service
        activity["legu_error"] = repr(exc)
    for key, func_name in {
        "limit_up_pool_count": "stock_zt_pool_em",
        "opened_limit_pool_count": "stock_zt_pool_zbgc_em",
        "limit_down_pool_count": "stock_zt_pool_dtgc_em",
    }.items():
        try:
            activity[key] = run_python_json(
                f"""
import json
import akshare as ak
df = getattr(ak, {func_name!r})(date={run_date.replace("-", "")!r})
print(json.dumps(int(len(df)), ensure_ascii=False))
""",
                timeout=10,
            )
        except Exception as exc:  # pragma: no cover - depends on remote service
            activity[f"{key}_error"] = repr(exc)
    try:
        count_text = http_get_text(
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount?node=hs_a",
            timeout=8,
        )
        activity["sina_hs_a_count"] = int(json.loads(count_text))
    except Exception as exc:
        activity["sina_hs_a_count_error"] = repr(exc)
    return activity


def fetch_sector_fund_flow() -> dict[str, Any]:
    result: dict[str, Any] = {"source": "akshare data-vendor proxy"}
    try:
        result["industry_top"] = run_python_json(
            """
import json
import akshare as ak
df = ak.stock_fund_flow_industry(symbol="即时")
print(df.head(20).to_json(orient="records", force_ascii=False))
""",
            timeout=15,
        )
    except Exception as exc:  # pragma: no cover - depends on remote service
        result["industry_error"] = repr(exc)
    try:
        result["concept_top"] = run_python_json(
            """
import json
import akshare as ak
df = ak.stock_fund_flow_concept(symbol="即时")
print(df.head(30).to_json(orient="records", force_ascii=False))
""",
            timeout=20,
        )
    except Exception as exc:  # pragma: no cover - depends on remote service
        result["concept_error"] = repr(exc)
    return result


MARKET_DATA_FIELDS = [
    "code",
    "name",
    "price",
    "change_pct",
    "open",
    "previous_close",
    "high",
    "low",
    "vwap",
    "amount",
    "turnover_rate",
    "volume_ratio",
    "target_time",
    "target_actual_time",
    "target_price",
    "target_vwap",
    "target_amount",
    "target_cum_volume_lots",
    "target_minute_high",
    "target_minute_low",
    "close_vs_vwap_pct",
    "target_vs_vwap_pct",
    "drawdown_from_high_pct",
    "range_position_pct",
    "bid1",
    "bid1_volume_lots",
    "ask1",
    "ask1_volume_lots",
    "bid2",
    "bid2_volume_lots",
    "ask2",
    "ask2_volume_lots",
    "bid3",
    "bid3_volume_lots",
    "ask3",
    "ask3_volume_lots",
    "bid4",
    "bid4_volume_lots",
    "ask4",
    "ask4_volume_lots",
    "bid5",
    "bid5_volume_lots",
    "ask5",
    "ask5_volume_lots",
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "pct5",
    "pct10",
    "pct20",
    "volume_vs_20d",
    "limit_state",
    "data_quality",
    "missing_core_fields",
]


def probability(value: Any, default: float = 0.0) -> float:
    parsed = as_float(value, default)
    if parsed > 1:
        parsed = parsed / 100
    return max(0.0, min(1.0, parsed))


def calculate_expected_r(
    success_probability: Any,
    failure_probability: Any,
    target_r: Any,
    loss_r: Any = 1.0,
    noise_probability: Any = 0.0,
    noise_cost_r: Any = 0.0,
    gap_risk_penalty: Any = 0.0,
) -> float:
    success = probability(success_probability)
    failure = probability(failure_probability)
    noise = probability(noise_probability)
    return (
        success * as_float(target_r)
        - failure * as_float(loss_r, 1.0)
        - noise * as_float(noise_cost_r)
        - as_float(gap_risk_penalty)
    )


def latest_existing_path(candidates: list[Path]) -> Path | None:
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def default_coverage_path(root: Path, run_date: str, target_time: str) -> Path:
    return root / "reports" / f"{run_date}-{target_time}-tail-data.json"


def default_manual_auction_path(root: Path, run_date: str) -> Path:
    return root / "data" / "manual" / "auction" / f"{run_date}.json"


def load_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        value = json.load(fh)
    return value if isinstance(value, dict) else None


def coverage_ratios(payload: dict[str, Any] | None) -> dict[str, float]:
    coverage = (payload or {}).get("coverage", payload or {})
    code_count = as_float(coverage.get("code_count"))
    if code_count <= 0:
        return {"quote": 0.0, "minute": 0.0, "daily": 0.0, "core": 0.0}
    quote = as_float(coverage.get("quote_count")) / code_count
    minute = as_float(coverage.get("minute_count")) / code_count
    daily = as_float(coverage.get("daily_metric_count")) / code_count
    return {"quote": quote, "minute": minute, "daily": daily, "core": min(quote, minute, daily)}


def has_market_b1(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    coverage = payload.get("coverage", payload)
    activity = coverage.get("market_activity", {})
    sector = coverage.get("sector_fund_flow", {})
    return any(
        activity.get(key) is not None
        for key in ("limit_up_pool_count", "opened_limit_pool_count", "limit_down_pool_count", "sina_hs_a_count")
    ) or bool(sector.get("industry_top") or sector.get("concept_top"))


def has_manual_auction_a2(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    stocks = payload.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        return False
    for item in stocks:
        if not isinstance(item, dict):
            continue
        if item.get("auction_price") is not None or item.get("auction_change_pct") is not None:
            return True
    return False


def assess_data_health(
    root: Path,
    run_date: str,
    target_time: str,
    automation: str,
    coverage_path: Path | None = None,
    auction_path: Path | None = None,
) -> dict[str, Any]:
    data = load_portfolio(root)
    validation = validate_portfolio(data)
    a0_ok = validation.ok and as_float(data.get("total_assets_cny")) > 0

    resolved_coverage_path = coverage_path or default_coverage_path(root, run_date, target_time)
    coverage_payload = load_json_if_exists(resolved_coverage_path)
    ratios = coverage_ratios(coverage_payload)
    a1_ok = ratios["core"] >= 0.8
    a1_partial = ratios["core"] >= 0.6
    b1_ok = has_market_b1(coverage_payload)

    resolved_auction_path = auction_path or default_manual_auction_path(root, run_date)
    auction_payload = load_json_if_exists(resolved_auction_path)
    a2_ok = has_manual_auction_a2(auction_payload)

    if not a0_ok:
        grade = "D"
        permission = "A0账户/风控缺失：不能给仓位建议。"
    elif automation == "auction":
        if a1_ok and a2_ok and b1_ok:
            grade = "A"
            permission = "可输出场景概率、个股概率、期望R和仓位上限。"
        elif a1_ok and b1_ok:
            grade = "B"
            permission = "缺A2竞价：只能输出09:30-09:35确认条件，禁止追强。"
        elif a1_partial:
            grade = "C"
            permission = "A1不完整或B1缺失：只输出防守清单和手动核验表。"
        else:
            grade = "C"
            permission = "实时行情覆盖不足：只输出防守清单。"
    else:
        if a1_ok and b1_ok:
            grade = "A"
            permission = "可输出尾盘/隔夜概率、期望R和次日验证条件。"
        elif a1_partial:
            grade = "B"
            permission = "可输出观察/持有/减仓，禁止高置信买入。"
        else:
            grade = "C"
            permission = "collector覆盖不足：只输出防守清单。"

    missing: list[str] = []
    if not a0_ok:
        missing.append("A0账户/风控")
    if not a1_ok:
        missing.append("A1报价/分时/均线覆盖>=80%")
    if automation == "auction" and not a2_ok:
        missing.append("A2竞价成交/封单/撤单/队列")
    if not b1_ok:
        missing.append("B1市场广度/涨停跌停/板块结构")

    return {
        "date": run_date,
        "time": target_time,
        "automation": automation,
        "grade": grade,
        "permission": permission,
        "a0_ok": a0_ok,
        "a1_core_coverage": ratios["core"],
        "a1_ratios": ratios,
        "a2_ok": a2_ok,
        "b1_ok": b1_ok,
        "coverage_path": str(resolved_coverage_path),
        "auction_path": str(resolved_auction_path),
        "missing_decision_data": missing,
    }


def render_data_health(health: dict[str, Any]) -> str:
    lines = [
        "# 数据健康检查",
        f"- 日期/时间：{health['date']} {health['time']}",
        f"- 自动化：{health['automation']}",
        f"- 数据等级：{health['grade']}",
        f"- 输出权限：{health['permission']}",
        f"- A0账户风控：{'通过' if health['a0_ok'] else '缺失/失败'}",
        f"- A1核心覆盖：{health['a1_core_coverage']:.0%}",
        f"- A2竞价数据：{'可用' if health['a2_ok'] else '缺失'}",
        f"- B1市场结构：{'可用' if health['b1_ok'] else '缺失'}",
        f"- coverage：{health['coverage_path']}",
        f"- manual auction：{health['auction_path']}",
    ]
    if health["missing_decision_data"]:
        lines.append("\n## 会限制结论的数据缺口")
        lines.extend(f"- {item}" for item in health["missing_decision_data"])
    return "\n".join(lines) + "\n"


def prediction_paths(root: Path, run_date: str) -> tuple[Path, Path]:
    return (
        root / "reports" / "predictions" / f"{run_date}-predictions.jsonl",
        root / "reports" / "outcomes" / f"{run_date}-outcomes.jsonl",
    )


def prediction_template_rows(root: Path, run_date: str, automation: str) -> list[dict[str, Any]]:
    data = load_portfolio(root)
    rows: list[dict[str, Any]] = []
    run_time = f"{run_date} {'09:28' if automation == 'auction' else '14:30'}"
    for section, source_type in (("positions", "holding"), ("watchlist", "watchlist")):
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            code = portfolio_style_code(str(item.get("code", "")))
            if not code:
                continue
            name = item.get("name", code)
            if automation == "auction":
                events = ["09:35站回关键位", "10:00站稳VWAP", "收盘站上修复线", "触发结构止损"]
            else:
                events = ["收盘站强", "次日竞价延续", "次日低开兑现", "触发隔夜失败条件"]
            for event in events:
                rows.append(
                    {
                        "run_time": run_time,
                        "automation": automation,
                        "source_type": source_type,
                        "code": code,
                        "name": name,
                        "event": event,
                        "mode": "",
                        "base_rate": None,
                        "positive_adjustments": [],
                        "negative_adjustments": [],
                        "success_probability": None,
                        "failure_probability": None,
                        "noise_probability": None,
                        "target_r": None,
                        "loss_r": 1.0,
                        "noise_cost_r": 0.2,
                        "gap_risk_penalty": 0.0 if automation == "auction" else None,
                        "expected_r": None,
                        "action": "",
                        "data_grade": "",
                        "confidence": "",
                    }
                )
    return rows


def manual_auction_template(root: Path, run_date: str) -> dict[str, Any]:
    data = load_portfolio(root)
    stocks: list[dict[str, Any]] = []
    for section, source_type in (("positions", "holding"), ("watchlist", "watchlist")):
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            code = portfolio_style_code(str(item.get("code", "")))
            if not code:
                continue
            stocks.append(
                {
                    "code": code,
                    "name": item.get("name", code),
                    "source_type": source_type,
                    "auction_price": None,
                    "auction_change_pct": None,
                    "auction_amount_cny": None,
                    "auction_volume_lots": None,
                    "post_0920_cancel_signal": "unknown",
                    "seal_amount_cny": None,
                    "bid_queue_signal": "unknown",
                    "ask_queue_signal": "unknown",
                    "role_signal": "unknown",
                    "notes": "",
                }
            )
    return {
        "date": run_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "Tonghuashun screenshot/manual export",
        "market": {
            "index_signal": "unknown",
            "limit_up_count": None,
            "opened_limit_count": None,
            "limit_down_count": None,
            "highest_board": None,
            "yesterday_limit_feedback": "unknown",
            "losing_money_effect": "unknown",
        },
        "stocks": stocks,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_predictions(root: Path, run_date: str) -> dict[str, Any]:
    prediction_path, outcome_path = prediction_paths(root, run_date)
    predictions = read_jsonl(prediction_path)
    outcomes = read_jsonl(outcome_path)
    expected_values = [as_float(row.get("expected_r")) for row in predictions if row.get("expected_r") is not None]
    grade_counts: dict[str, int] = {}
    for row in predictions:
        grade = str(row.get("data_grade") or "missing")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
    return {
        "date": run_date,
        "prediction_path": str(prediction_path),
        "outcome_path": str(outcome_path),
        "prediction_count": len(predictions),
        "outcome_count": len(outcomes),
        "mean_expected_r": sum(expected_values) / len(expected_values) if expected_values else None,
        "data_grade_counts": grade_counts,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def collect_tail_market_data(root: Path, run_date: str, target_time: str, extra_codes: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = load_portfolio(root)
    codes = read_target_codes(data, extra_codes)
    if not codes:
        raise ValueError("没有可采集的沪深主板代码。")

    errors: dict[str, str] = {}
    try:
        sina = fetch_sina_quotes(codes)
    except Exception as exc:
        sina = {}
        errors["sina_quotes"] = repr(exc)
    try:
        tencent = fetch_tencent_quotes(codes)
    except Exception as exc:
        tencent = {}
        errors["tencent_quotes"] = repr(exc)
    quotes = merge_quotes(sina, tencent)

    rows: list[dict[str, Any]] = []
    for code in codes:
        item = dict(quotes.get(code, {"code": code, "data_quality": "报价缺失"}))
        try:
            item.update(fetch_tencent_minute(code, target_time))
        except Exception as exc:
            item["minute_error"] = repr(exc)
        try:
            item.update(fetch_tencent_daily_metrics(code))
        except Exception as exc:
            item["daily_error"] = repr(exc)
        rows.append(enrich_quote_metrics(item))

    coverage = {
        "run_date": run_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "target_time": target_time,
        "code_count": len(codes),
        "quote_count": len([row for row in rows if row.get("price") is not None]),
        "minute_count": len([row for row in rows if row.get("target_vwap") is not None]),
        "daily_metric_count": len([row for row in rows if row.get("ma20") is not None]),
        "errors": errors,
        "market_activity": fetch_market_activity(run_date),
        "sector_fund_flow": fetch_sector_fund_flow(),
        "unavailable_or_low_confidence": {
            "tier3_boundary": "Do not list chronic Tier 3 gaps in daily reports unless they are decision-critical or supplied by Tonghuashun/screenshots.",
        },
    }
    return rows, coverage


def collect_market_data_for_codes(codes: list[str], run_date: str, target_time: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized_codes = []
    seen: set[str] = set()
    for raw_code in codes:
        code = portfolio_style_code(raw_code)
        if code and code not in seen:
            seen.add(code)
            normalized_codes.append(code)
    if not normalized_codes:
        raise ValueError("没有可采集代码。")

    errors: dict[str, str] = {}
    try:
        sina = fetch_sina_quotes(normalized_codes)
    except Exception as exc:
        sina = {}
        errors["sina_quotes"] = repr(exc)
    try:
        tencent = fetch_tencent_quotes(normalized_codes)
    except Exception as exc:
        tencent = {}
        errors["tencent_quotes"] = repr(exc)
    quotes = merge_quotes(sina, tencent)

    rows: list[dict[str, Any]] = []
    for code in normalized_codes:
        item = dict(quotes.get(code, {"code": code, "data_quality": "报价缺失"}))
        item["is_main_board_eligible"] = is_main_board_a_share(code)
        try:
            item.update(fetch_tencent_minute(code, target_time))
        except Exception as exc:
            item["minute_error"] = repr(exc)
        try:
            item.update(fetch_tencent_daily_metrics(code))
        except Exception as exc:
            item["daily_error"] = repr(exc)
        rows.append(enrich_quote_metrics(item))

    coverage = {
        "run_date": run_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "target_time": target_time,
        "code_count": len(normalized_codes),
        "quote_count": len([row for row in rows if row.get("price") is not None]),
        "minute_count": len([row for row in rows if row.get("target_vwap") is not None]),
        "daily_metric_count": len([row for row in rows if row.get("ma20") is not None]),
        "errors": errors,
    }
    return rows, coverage


def fetch_single_stock_optional_layers(code: str, run_date: str) -> dict[str, Any]:
    numeric = code_number(code)
    market = "sh" if code_exchange(code) == "SH" else "sz"
    compact_date = run_date.replace("-", "")
    result: dict[str, Any] = {
        "code": portfolio_style_code(code),
        "note": "Optional layers are best-effort vendor/public data. Missing values must reduce confidence, not be inferred.",
    }
    snippets = {
        "individual_fund_flow": f"""
import json
import akshare as ak
df = ak.stock_individual_fund_flow(stock={numeric!r}, market={market!r})
print(df.tail(10).to_json(orient="records", force_ascii=False))
""",
        "shareholder_structure": f"""
import json
import akshare as ak
df = ak.stock_fund_stock_holder(symbol={numeric!r})
print(df.head(30).to_json(orient="records", force_ascii=False))
""",
        "stock_news": f"""
import json
import akshare as ak
df = ak.stock_news_em(symbol={numeric!r})
print(df.head(20).to_json(orient="records", force_ascii=False))
""",
        "dragon_tiger_daily": f"""
import json
import akshare as ak
df = ak.stock_lhb_detail_daily_sina(date={compact_date!r})
print(df[df.astype(str).apply(lambda row: row.str.contains({numeric!r}).any(), axis=1)].head(20).to_json(orient="records", force_ascii=False))
""",
    }
    timeouts = {
        "individual_fund_flow": 12,
        "shareholder_structure": 12,
        "stock_news": 12,
        "dragon_tiger_daily": 15,
    }
    for key, code_snippet in snippets.items():
        try:
            result[key] = run_python_json(code_snippet, timeout=timeouts[key])
        except Exception as exc:
            result[f"{key}_error"] = repr(exc)
    return result


def collect_single_stock_data(code: str, run_date: str, target_time: str) -> dict[str, Any]:
    rows, coverage = collect_market_data_for_codes([code], run_date, target_time)
    row = rows[0] if rows else {"code": portfolio_style_code(code)}
    return {
        "coverage": {
            **coverage,
            "market_activity": fetch_market_activity(run_date),
            "sector_fund_flow": fetch_sector_fund_flow(),
            "unavailable_or_low_confidence": {
                "tier3_boundary": "Chips, full Level-2, hidden liquidity, and low-frequency holder updates are not routine daily inputs; mention them only when decision-critical or separately supplied.",
            },
        },
        "quote": row,
        "optional_layers": fetch_single_stock_optional_layers(row.get("code", code), run_date),
    }


def command_collect_tail_data(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    target_time = args.time.replace(":", "")
    if len(target_time) != 4 or not target_time.isdigit():
        raise ValueError("--time 必须是 HHMM 或 HH:MM，例如 1430。")

    rows, coverage = collect_tail_market_data(root, run_date, target_time, args.codes or [])
    output_prefix = Path(args.output_prefix).resolve() if args.output_prefix else root / "reports" / f"{run_date}-{target_time}-tail-data"
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    write_csv(csv_path, rows, MARKET_DATA_FIELDS)
    json_path.write_text(json.dumps({"coverage": coverage, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已生成：{csv_path}")
    print(f"已生成：{json_path}")
    print(f"覆盖：报价 {coverage['quote_count']}/{coverage['code_count']}；分时 {coverage['minute_count']}/{coverage['code_count']}；均线 {coverage['daily_metric_count']}/{coverage['code_count']}")
    return 0


def command_collect_stock_data(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    target_time = args.time.replace(":", "")
    if len(target_time) != 4 or not target_time.isdigit():
        raise ValueError("--time 必须是 HHMM 或 HH:MM，例如 1430。")

    payload = collect_single_stock_data(args.code, run_date, target_time)
    code = code_number(args.code)
    output_prefix = (
        Path(args.output_prefix).resolve()
        if args.output_prefix
        else root / "reports" / f"{run_date}-{code}-{target_time}-stock-data"
    )
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    write_csv(csv_path, [payload["quote"]], MARKET_DATA_FIELDS + ["is_main_board_eligible"])
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    coverage = payload["coverage"]
    print(f"已生成：{csv_path}")
    print(f"已生成：{json_path}")
    print(f"覆盖：报价 {coverage['quote_count']}/{coverage['code_count']}；分时 {coverage['minute_count']}/{coverage['code_count']}；均线 {coverage['daily_metric_count']}/{coverage['code_count']}")
    optional = payload.get("optional_layers", {})
    errors = [key for key in optional if key.endswith("_error")]
    if errors:
        print("可选层未全部采集；仅在单股深研需要时查看 JSON。")
    return 0


def command_data_health(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    target_time = args.time.replace(":", "")
    if len(target_time) != 4 or not target_time.isdigit():
        raise ValueError("--time 必须是 HHMM 或 HH:MM，例如 1430。")
    coverage_path = Path(args.coverage_json).resolve() if args.coverage_json else None
    auction_path = Path(args.auction_json).resolve() if args.auction_json else None
    health = assess_data_health(root, run_date, target_time, args.automation, coverage_path, auction_path)
    if args.json:
        print(json.dumps(health, ensure_ascii=False, indent=2))
    else:
        print(render_data_health(health), end="")
    return 0


def command_prediction_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    rows = prediction_template_rows(root, run_date, args.automation)
    output = (
        Path(args.output).resolve()
        if args.output
        else root / "reports" / "predictions" / f"{run_date}-{args.automation}-template.jsonl"
    )
    write_jsonl(output, rows)
    print(f"已生成：{output}")
    print(f"模板行数：{len(rows)}")
    return 0


def command_auction_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    payload = manual_auction_template(root, run_date)
    output = Path(args.output).resolve() if args.output else default_manual_auction_path(root, run_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成：{output}")
    print(f"标的数量：{len(payload['stocks'])}")
    return 0


def command_prediction_summary(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    summary = summarize_predictions(root, run_date)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    data = load_portfolio(root)
    result = validate_portfolio(data)
    print(render_validation(result), end="")
    return 0 if result.ok else 1


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    packet = render_run_packet(root, args.mode, run_date)
    if args.stdout:
        print(packet, end="")
        return 0

    output_path = Path(args.output).resolve() if args.output else output_path_for(root, args.mode, run_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(packet, encoding="utf-8")
    print(f"已生成：{output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A股交易助手本地运行工具")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="项目根目录，默认自动识别")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="校验组合配置；默认读取本地私有 config/portfolio.json，缺失时使用样例配置")
    validate.set_defaults(func=command_validate)

    render = subparsers.add_parser("render", help="生成某个工作流的运行包")
    render.add_argument("mode", choices=sorted(PROMPTS), help="运行包类型")
    render.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    render.add_argument("--output", help="输出文件路径；默认写入 reports/")
    render.add_argument("--stdout", action="store_true", help="只打印，不写文件")
    render.set_defaults(func=command_render)

    collect = subparsers.add_parser("collect", help="采集可审计的市场数据")
    collect_subparsers = collect.add_subparsers(dest="collect_mode", required=True)
    tail_data = collect_subparsers.add_parser("tail-data", help="采集尾盘评分所需行情、分时、均线和市场情绪数据")
    tail_data.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    tail_data.add_argument("--time", default="1430", help="目标分时时间，默认 1430；可写 14:30")
    tail_data.add_argument("--codes", nargs="*", default=[], help="追加采集代码，例如 600183.SH 002080.SZ")
    tail_data.add_argument("--output-prefix", help="输出前缀；默认 reports/{date}-{time}-tail-data")
    tail_data.set_defaults(func=command_collect_tail_data)

    stock_data = collect_subparsers.add_parser("stock-data", help="采集单股深度分析数据包")
    stock_data.add_argument("--code", required=True, help="股票代码，例如 002428.SZ、sz002428、600584.SH")
    stock_data.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    stock_data.add_argument("--time", default="1430", help="目标分时时间，默认 1430；可写 14:30")
    stock_data.add_argument("--output-prefix", help="输出前缀；默认 reports/{date}-{code}-{time}-stock-data")
    stock_data.set_defaults(func=command_collect_stock_data)

    data_health = subparsers.add_parser("data-health", help="评估自动化数据等级和输出权限")
    data_health.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    data_health.add_argument("--time", default="1430", help="目标时间，默认 1430；可写 09:28")
    data_health.add_argument("--automation", choices=["auction", "tail"], default="tail", help="自动化类型")
    data_health.add_argument("--coverage-json", help="collector JSON 路径；默认 reports/{date}-{time}-tail-data.json")
    data_health.add_argument("--auction-json", help="手工/截图提取竞价 JSON；默认 data/manual/auction/{date}.json")
    data_health.add_argument("--json", action="store_true", help="输出 JSON")
    data_health.set_defaults(func=command_data_health)

    auction_template = subparsers.add_parser("auction-template", help="生成手工竞价数据模板，用于补齐A2数据")
    auction_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    auction_template.add_argument("--output", help="输出文件路径；默认 data/manual/auction/{date}.json")
    auction_template.set_defaults(func=command_auction_template)

    prediction = subparsers.add_parser("prediction", help="生成和汇总预测日志")
    prediction_subparsers = prediction.add_subparsers(dest="prediction_mode", required=True)
    prediction_template = prediction_subparsers.add_parser("template", help="生成预测 JSONL 模板")
    prediction_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    prediction_template.add_argument("--automation", choices=["auction", "tail"], required=True)
    prediction_template.add_argument("--output", help="输出文件路径；默认 reports/predictions/{date}-{automation}-template.jsonl")
    prediction_template.set_defaults(func=command_prediction_template)

    prediction_summary = prediction_subparsers.add_parser("summary", help="汇总某日预测和结果日志")
    prediction_summary.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    prediction_summary.set_defaults(func=command_prediction_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"缺少文件：{exc.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"JSON 解析失败：{exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
