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
    "market-flow": {
        "title": "14:30 大盘资金流向与观察机会",
        "path": "prompts/tail_market_flow_check.md",
        "suffix": "1430-market-flow-run.md",
    },
    "user": {
        "title": "用户给定板块/个股/持仓综合分析",
        "path": "prompts/user_request_analysis.md",
        "suffix": "user-request-analysis-run.md",
    },
}

CORE_CONTEXT_FILES = [
    "README.md",
    "config/decision_weights.json",
    "config/portfolio.example.json",
    "docs/trading_assistant_state.example.md",
    "docs/trading_system_upgrade.md",
    "docs/data_sources.md",
    "docs/opening_permission_model.md",
    "docs/prediction_automation_system.md",
]

OPTIONAL_LOCAL_CONTEXT_FILES = [
    "config/portfolio.json",
    "docs/trading_assistant_state.md",
]


def context_files_for(root: Path) -> list[str]:
    files = list(CORE_CONTEXT_FILES)
    for item in OPTIONAL_LOCAL_CONTEXT_FILES:
        if (root / item).exists():
            files.append(item)
    return files


DEFAULT_DECISION_WEIGHTS: dict[str, Any] = {
    "version": "2026-05-28-stable-data-permission",
    "readiness_thresholds": {
        "full_plan": 75,
        "confirmation_plan": 65,
        "defensive_only_below": 40,
    },
    "primary_weights": {
        "market_regime_and_losing_money_effect": {
            "weight": 25,
            "required_layers": ["B1"],
            "description": "Market breadth, limit-up/down structure, sentiment, and losing-money effect.",
        },
        "sector_resonance_and_role": {
            "weight": 20,
            "required_layers": ["B1"],
            "description": "Leader, core anchor, catch-up, follower, and sector breadth comparison.",
        },
        "opening_absorption_0935": {
            "weight": 20,
            "required_layers": ["A1", "B1"],
            "description": "Price versus open, VWAP, first-five-minute absorption, and sector synchronization.",
        },
        "risk_reward_liquidity": {
            "weight": 20,
            "required_layers": ["A0", "A1"],
            "description": "Structural stop, stop distance, liquidity, expected R, and account risk budget.",
        },
        "kline_relative_strength": {
            "weight": 10,
            "required_layers": ["A1"],
            "description": "Daily/minute structure, moving averages, volume, and relative strength.",
        },
        "source_backed_catalyst": {
            "weight": 5,
            "required_layers": ["C2"],
            "description": "Structured announcement, news, IR, or industry-chain evidence with source and timestamp.",
        },
    },
    "optional_modifiers": {
        "a2_auction_early_permission": {
            "max_abs_delta": 8,
            "rule": "Only advances eligible action from 09:35 confirmation to 09:28 early permission.",
        },
        "fund_flow_proxy": {
            "max_abs_delta": 3,
            "rule": "Vendor-classified proxy only; never true institutional intent.",
        },
        "chips_holder_margin_structure": {
            "max_abs_delta": 5,
            "rule": "Slow structure modifier; not an intraday hard trigger.",
        },
    },
}


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


def decision_weights_path(root: Path) -> Path:
    return root / "config" / "decision_weights.json"


def load_decision_weights(root: Path) -> dict[str, Any]:
    path = decision_weights_path(root)
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            merged = json.loads(json.dumps(DEFAULT_DECISION_WEIGHTS))
            merged.update(payload)
            return merged
    return json.loads(json.dumps(DEFAULT_DECISION_WEIGHTS))


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


def is_exchange_traded_fund(code: str) -> bool:
    normalized = normalize_code(code)
    numeric = normalized.split(".", 1)[0]
    if not numeric.isdigit() or len(numeric) != 6:
        return False
    if normalized.endswith(".SH"):
        return numeric.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "560", "561", "562", "563", "588", "589"))
    if normalized.endswith(".SZ"):
        return numeric.startswith(("159", "160", "161", "162", "163", "164", "165"))
    return False


def is_allowed_portfolio_instrument(code: str) -> bool:
    return is_main_board_a_share(code) or is_exchange_traded_fund(code)


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


def parse_market_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("，", "").replace(" ", "")
    text = text.replace("人民币", "").replace("CNY", "").replace("RMB", "").replace("元", "")
    text = text.replace("%", "")
    multiplier = 1.0
    for unit, unit_multiplier in (("亿", 100000000.0), ("万", 10000.0), ("千", 1000.0)):
        if unit in text:
            multiplier = unit_multiplier
            text = text.replace(unit, "")
            break
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0)) * multiplier


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
            "regime_risk_budget_pct",
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
        if not isinstance(engine.get("regime_risk_budget_pct"), dict):
            warnings.append("risk_engine.regime_risk_budget_pct 必须是对象，用于按市场状态收缩单笔风险。")
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
        if not is_allowed_portfolio_instrument(code):
            errors.append(f"{name} {code} 不符合沪深主板股票或场内ETF约束。")
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
        if not is_allowed_portfolio_instrument(code):
            errors.append(f"观察池 {name} {code} 不符合沪深主板股票或场内ETF约束。")

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
    engine = risk_engine(data)
    base_loss_pct = as_float(engine.get("base_risk_budget_pct")) if engine else 0.0
    offensive_room = max(0.0, min(short_limit - total_position, cash_pct))
    hard_risk_budget = total_assets * max_loss_pct / 100 if total_assets > 0 else 0.0
    base_risk_budget = total_assets * base_loss_pct / 100 if total_assets > 0 and base_loss_pct > 0 else 0.0

    positions = data.get("positions", [])
    largest = None
    if positions:
        largest = max(positions, key=lambda item: as_float(item.get("current_position_pct")))

    lines = [
        f"- 总账户资金：{money(total_assets)}",
        f"- 当前总仓位：{pct(total_position)}；现金：{pct(cash_pct)}",
        f"- 短线仓位上限：{pct(short_limit)}；理论剩余进攻仓位：{pct(offensive_room)}",
        f"- 单票上限：{pct(single_limit)}；常规单笔风险预算：{money(base_risk_budget)}；单笔硬上限预算：{money(hard_risk_budget)}",
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
            f"单笔硬上限：{pct(engine.get('hard_max_loss_per_trade_pct', data.get('max_loss_per_trade_pct')))}；"
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
    regime_risk = engine.get("regime_risk_budget_pct", {})
    if isinstance(regimes, list) and regimes:
        lines.extend(
            [
                "",
                "### 市场状态仓位权限",
                "| 状态 | 总仓位上限 | 常规单笔风险 | 新增风险规则 | 允许打法 |",
                "| --- | ---: | ---: | --- | --- |",
            ]
        )
        for item in regimes:
            if not isinstance(item, dict):
                continue
            styles = "、".join(item.get("allowed_styles", [])) or "缺失"
            regime_name = str(item.get("regime", "缺失"))
            risk_pct = regime_risk.get(regime_name) if isinstance(regime_risk, dict) else None
            lines.append(
                "| {regime} | {cap} | {risk} | {rule} | {styles} |".format(
                    regime=regime_name,
                    cap=pct(item.get("total_position_cap_pct")),
                    risk=pct(risk_pct),
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


def stock_lookup(data: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    lookup: dict[str, tuple[str, dict[str, Any]]] = {}
    for section, label in (("positions", "holding"), ("watchlist", "watchlist")):
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            code = portfolio_style_code(str(item.get("code", "")))
            if code:
                lookup[code] = (label, item)
    return lookup


def normalize_requested_codes(codes: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_code in codes or []:
        code = portfolio_style_code(raw_code)
        if code and code not in seen:
            seen.add(code)
            normalized.append(code)
    return normalized


def render_user_request_context(
    data: dict[str, Any],
    run_date: str,
    requested_themes: list[str] | None = None,
    requested_codes: list[str] | None = None,
    include_holdings: bool = True,
) -> str:
    themes = [theme.strip() for theme in requested_themes or [] if theme.strip()]
    codes = normalize_requested_codes(requested_codes)
    lookup = stock_lookup(data)

    lines: list[str] = [
        "### 用户给定板块",
    ]
    if themes:
        lines.extend(
            [
                "| 板块/方向 | 必须拆分 | 必查证据 | 输出权限 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for theme in themes:
            lines.append(
                "| {theme} | 子方向、产业链位置、龙头/中军/补涨/跟风 | "
                "当日板块宽度、成交额/资金代理、涨跌停结构、最新催化、与持仓相关性 | "
                "缺B1或催化来源时只能给观察池和人工核验清单 |".format(theme=theme)
            )
    else:
        lines.append("未指定板块；按当日市场状态、持仓风险和用户临时线索动态生成。")

    lines.extend(["", "### 用户给定个股"])
    if codes:
        lines.extend(
            [
                "| 股票 | 代码 | 主板资格 | 当前身份 | 数据包命令 | 输出限制 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for code in codes:
            source_type, item = lookup.get(code, ("new", {}))
            name = item.get("name", code)
            eligible = "是" if is_main_board_a_share(code) else "否"
            identity = {"holding": "当前持仓", "watchlist": "观察池", "new": "用户新增"}[source_type]
            command = (
                f"python3 tools/trading_assistant.py collect stock-data --code {code} "
                f"--date {run_date} --time 1430"
            )
            if not is_main_board_a_share(code):
                limit = "不符合沪深主板-only；不得进入交易建议，只能做研究说明或排除"
            else:
                limit = "缺A1/B1时不得给高置信买入/加仓；缺止损只能观察/减仓"
            lines.append(f"| {name} | {code} | {eligible} | {identity} | `{command}` | {limit} |")
    else:
        lines.append("未指定个股；若用户临时给出代码，先追加到 collector，再按单股证据栈分析。")

    lines.extend(["", "### 当前持仓评价与建议队列"])
    positions = data.get("positions", []) if include_holdings else []
    if positions:
        lines.extend(
            [
                "| 股票 | 代码 | 仓位 | 可用 | 成本 | 原始逻辑更新 | 今日必须回答 |",
                "| --- | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for item in positions:
            plan = item.get("risk_plan", {}) if isinstance(item.get("risk_plan"), dict) else {}
            thesis_parts = []
            if item.get("original_thesis"):
                thesis_parts.append(str(item.get("original_thesis")).rstrip("。；; "))
            structural_condition = plan.get("structural_stop_condition")
            if structural_condition:
                thesis_parts.append(f"结构条件：{str(structural_condition).rstrip('。；; ')}")
            thesis_update = "；".join(thesis_parts) if thesis_parts else "缺失"
            lines.append(
                "| {name} | {code} | {position} | {available} | {cost} | {thesis} | {question} |".format(
                    name=item.get("name", ""),
                    code=item.get("code", ""),
                    position=pct(item.get("current_position_pct")),
                    available=item.get("available_quantity", "缺失"),
                    cost=item.get("cost", "缺失"),
                    thesis=thesis_update,
                    question=item.get("must_answer", "缺失"),
                )
            )
    else:
        lines.append("本次不纳入持仓评价；若是实盘使用，默认应纳入当前持仓，避免新机会和存量风险割裂。")

    lines.extend(
        [
            "",
            "### 边界解决机制",
            "| 边界 | 稳定解法 | 未满足时的权限 |",
            "| --- | --- | --- |",
            "| 用户给定板块过宽 | 先拆子方向，再用B1市场结构和催化来源筛选 | 只给方向地图，不给可执行买点 |",
            "| 用户给定个股缺实时数据 | 先跑单股或批量 collector，保留 coverage 路径 | 只给手动核验清单，不给高置信买入/加仓 |",
            "| 当前持仓可能受沉没成本影响 | 每只持仓重估原始逻辑增强/削弱/失效和未来期望 | 不能因为亏损、已研究、已持仓而建议继续拿 |",
            "| A2竞价数据缺失 | 用 09:30-09:35 承接确认做主证据；同花顺截图/手工 JSON 只用于提前放权 | 禁止09:28追强和竞价超预期结论 |",
            "| 筹码/股东/Level-2不稳定 | 只用截图/导出/稳定公开披露；资金流写成代理证据 | 不把缺口每天机械列出，也不据此断言主力意图 |",
            "| 长期有效性未证明 | prediction/outcome/behavior 日志持续校准 | 只能声明流程和guardrail有效，不声明长期收益提升 |",
        ]
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
                "P0主证据：市场状态、板块龙头/中军/补涨共振、亏钱效应、止损距离和expected R",
                "09:30-09:35承接确认：是否站上开盘价、是否强于VWAP、核心票是否同步、后排是否被兑现",
                "A2提前放权：09:15-09:25 预开价、竞价涨跌幅、竞价成交额/成交量、09:20后撤单变化、封单额、盘口队列",
                "板块龙头、中军、补涨的竞价强弱排序；A2缺失时禁止09:28追强和竞价超预期结论",
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
    if mode in {"tail", "market-flow"}:
        base.extend(
            [
                "14:30 前后观察池股票实时价格、涨跌幅、成交额、换手率、量比",
                "日内均价/VWAP、分时是否收回、日内高低点回撤、尾盘是否放量承接",
                "当日主线方向的龙头、中军、补涨收盘前强弱与炸板/回封情况",
                "09:28预测复盘：实际结果、误差类型、下次权重修正",
                "观察股隔夜预测所需的结构止损、目标R、隔夜跳空风险、期望R和明日竞价验证条件",
            ]
        )
    if mode == "market-flow":
        base.extend(
            [
                "13:05 到 14:30 的涨停池、炸板池、跌停池、宽基ETF和板块资金流变化",
                "资金最可能流向的板块排序，以及每个方向的龙头/中军/补涨/跟风分层",
                "次日 09:35 可观察买入机会、持仓影响、取消条件和不交易条件",
            ]
        )
    if mode == "user":
        base.extend(
            [
                "用户给定板块：子方向、板块宽度、龙头/中军/补涨/跟风、最新催化和持仓相关性",
                "用户给定个股：先生成或引用单股数据包，再补齐实时盘口、K线/均线、成交、板块角色、催化和风险收益",
                "当前持仓评价：每只持仓必须给原始逻辑增强/削弱/失效、未来期望、可卖数量、减仓/持有/加仓触发",
                "新增机会与持仓比较：只有预期强度、板块地位、流动性和风险收益明显更优，才允许换仓或新增风险",
            ]
        )
    base.append("筹码峰、股东/基金/融资/港股通、资金流等数据按 `docs/prediction_automation_system.md` 分层使用：市场状态、板块共振、09:35承接和风险收益比是主证据；A2竞价盘口只用于提前放权；筹码是结构概率修正，股东/基金/融资是慢变量，资金流是代理证据。")
    return "\n".join(f"- {item}" for item in base)


def render_run_packet(
    root: Path,
    mode: str,
    run_date: str,
    requested_themes: list[str] | None = None,
    requested_codes: list[str] | None = None,
    include_holdings: bool = True,
) -> str:
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
    lines.extend(f"- `{item}`" for item in context_files_for(root))
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
            "## 7A. 用户输入分析对象",
            render_user_request_context(
                data,
                run_date,
                requested_themes=requested_themes,
                requested_codes=requested_codes,
                include_holdings=include_holdings,
            )
            if mode == "user" or requested_themes or requested_codes
            else "本次未指定临时板块或个股；沿用持仓、观察池和动态主题流程。",
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
            if code and code not in seen and is_allowed_portfolio_instrument(code):
                seen.add(code)
                result.append(code)
    for item in extra_codes or []:
        code = portfolio_style_code(item)
        if code and code not in seen and is_allowed_portfolio_instrument(code):
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
    open_price = item.get("open")
    high = item.get("high")
    low = item.get("low")
    vwap = item.get("vwap")
    target_price = item.get("target_price")
    target_vwap = item.get("target_vwap")
    result = dict(item)
    result["close_vs_vwap_pct"] = pct_change(price, vwap)
    result["target_vs_open_pct"] = pct_change(target_price, open_price)
    result["target_vs_vwap_pct"] = pct_change(target_price, target_vwap)
    result["drawdown_from_high_pct"] = pct_change(price, high)
    if target_price is None or open_price is None or target_vwap is None:
        result["opening_confirmation_signal"] = "unknown"
    elif target_price >= open_price and target_price >= target_vwap:
        result["opening_confirmation_signal"] = "confirmed"
    elif target_price < open_price and target_price < target_vwap:
        result["opening_confirmation_signal"] = "failed"
    else:
        result["opening_confirmation_signal"] = "mixed"
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
    "target_vs_open_pct",
    "target_vs_vwap_pct",
    "opening_confirmation_signal",
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


def default_manual_sector_flow_path(root: Path, run_date: str) -> Path:
    return root / "data" / "manual" / "sector_flow" / f"{run_date}.json"


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
    manual_sector_flow = coverage.get("manual_sector_flow", {})
    manual_records = manual_sector_flow.get("records") if isinstance(manual_sector_flow, dict) else None
    return any(
        activity.get(key) is not None
        for key in ("limit_up_pool_count", "opened_limit_pool_count", "limit_down_pool_count", "sina_hs_a_count")
    ) or bool(sector.get("industry_top") or sector.get("concept_top")) or bool(manual_records)


def has_manual_sector_flow_b1(root: Path, run_date: str) -> bool:
    payload = load_json_if_exists(default_manual_sector_flow_path(root, run_date))
    records = (payload or {}).get("records")
    return isinstance(records, list) and any(isinstance(item, dict) and item.get("sector") for item in records)


def has_manual_auction_a2(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    stocks = payload.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        return False
    for item in stocks:
        if not isinstance(item, dict):
            continue
        if has_complete_auction_core(item):
            return True
    return False


def has_source_backed_message_evidence(root: Path, run_date: str) -> bool:
    payload = load_json_if_exists(default_message_evidence_path(root, run_date))
    summary = summarize_message_evidence(payload, run_date)
    evidence_count = int(summary["evidence_count"])
    if evidence_count <= 0:
        return False
    sourced_count = evidence_count - int(summary["missing_source_count"])
    fresh_count = evidence_count - int(summary["stale_count"])
    non_rumor_count = evidence_count - int(summary["rumor_count"])
    return sourced_count > 0 and fresh_count > 0 and non_rumor_count > 0


def stable_component_status(
    component_id: str,
    *,
    a0_ok: bool,
    a1_ok: bool,
    a1_partial: bool,
    b1_ok: bool,
    opening_confirmation_ok: bool,
    source_backed_catalyst_ok: bool,
) -> tuple[str, float]:
    if component_id in {"market_regime_and_losing_money_effect", "sector_resonance_and_role"}:
        return ("available", 1.0) if b1_ok else ("missing", 0.0)
    if component_id == "opening_absorption_0935":
        return ("available", 1.0) if opening_confirmation_ok else ("missing", 0.0)
    if component_id == "risk_reward_liquidity":
        if a0_ok and a1_ok:
            return "available", 1.0
        if a0_ok and a1_partial:
            return "partial", 0.5
        return "missing", 0.0
    if component_id == "kline_relative_strength":
        if a1_ok:
            return "available", 1.0
        if a1_partial:
            return "partial", 0.5
        return "missing", 0.0
    if component_id == "source_backed_catalyst":
        return ("available", 1.0) if source_backed_catalyst_ok else ("missing", 0.0)
    return "not_assessed", 0.0


def assess_stable_data_readiness(
    root: Path,
    run_date: str,
    *,
    a0_ok: bool,
    a1_ok: bool,
    a1_partial: bool,
    b1_ok: bool,
    opening_confirmation_ok: bool,
) -> dict[str, Any]:
    weights = load_decision_weights(root)
    primary = weights.get("primary_weights", {})
    source_backed_catalyst_ok = has_source_backed_message_evidence(root, run_date)
    components: list[dict[str, Any]] = []
    score = 0.0
    max_score = 0.0
    if isinstance(primary, dict):
        for component_id, config in primary.items():
            if not isinstance(config, dict):
                continue
            weight = as_float(config.get("weight"))
            status, multiplier = stable_component_status(
                str(component_id),
                a0_ok=a0_ok,
                a1_ok=a1_ok,
                a1_partial=a1_partial,
                b1_ok=b1_ok,
                opening_confirmation_ok=opening_confirmation_ok,
                source_backed_catalyst_ok=source_backed_catalyst_ok,
            )
            earned = weight * multiplier
            score += earned
            max_score += weight
            components.append(
                {
                    "id": component_id,
                    "weight": weight,
                    "earned": earned,
                    "status": status,
                    "required_layers": config.get("required_layers", []),
                    "description": config.get("description", ""),
                }
            )
    return {
        "version": weights.get("version", "unknown"),
        "score": round(score, 2),
        "max_score": round(max_score, 2),
        "score_pct": round(score / max_score, 4) if max_score > 0 else 0.0,
        "thresholds": weights.get("readiness_thresholds", {}),
        "components": components,
        "optional_modifiers": weights.get("optional_modifiers", {}),
        "message_evidence_path": str(default_message_evidence_path(root, run_date)),
        "source_backed_catalyst_ok": source_backed_catalyst_ok,
    }


def action_permission_ceiling(
    automation: str,
    *,
    a0_ok: bool,
    a1_ok: bool,
    a1_partial: bool,
    a2_ok: bool,
    b1_ok: bool,
    opening_confirmation_ok: bool,
    early_chase_ok: bool,
) -> dict[str, Any]:
    if not a0_ok:
        return {
            "code": "research_only_no_sizing",
            "max_action": "research_and_manual_verify",
            "summary": "A0缺失：只能研究和补数，不能给仓位或买卖动作。",
            "allowed_actions": ["research", "observe", "manual_verify"],
            "blocked_actions": ["buy", "add", "reduce", "sell", "chase_strength", "limit_up_attempt"],
            "required_before_upgrade": ["补齐账户总资产、持仓、现金、成本、风险预算"],
        }

    if automation == "auction":
        if early_chase_ok:
            return {
                "code": "auction_early_plan_with_0935_validation",
                "max_action": "early_core_plan",
                "summary": "A0+A1+A2+B1可用：可输出09:28提前计划，但必须接受09:35承接验证。",
                "allowed_actions": [
                    "observe",
                    "hold",
                    "reduce",
                    "sell",
                    "core_low_buy",
                    "core_chase_strength_with_stop",
                    "limit_up_attempt_core_only",
                ],
                "blocked_actions": ["skip_0935_validation", "weak_follower_chase", "no_stop_trade"],
                "required_before_upgrade": ["09:35不低于开盘价", "不弱于VWAP", "板块核心同步", "止损距离合格"],
            }
        if opening_confirmation_ok:
            return {
                "code": "opening_confirmation_only",
                "max_action": "post_0935_confirmed_plan",
                "summary": "缺A2但A1+B1可用：只能等待09:35承接确认，确认前禁止追强。",
                "allowed_actions": [
                    "observe",
                    "hold",
                    "reduce",
                    "sell",
                    "post_0935_core_low_buy",
                    "post_0935_core_or_anchor_buy",
                ],
                "blocked_actions": [
                    "09:28_chase_strength",
                    "auction_outperformance_claim",
                    "limit_up_attempt_before_0935",
                    "weak_follower_standard_size",
                ],
                "required_before_upgrade": ["补A2竞价核心字段，或等09:35价格/VWAP/板块共振通过"],
            }
        if a1_partial:
            return {
                "code": "auction_defensive_manual_check",
                "max_action": "defensive_management",
                "summary": "A1不完整或B1缺失：只允许防守处理和人工核验。",
                "allowed_actions": ["observe", "hold", "reduce_on_trigger", "manual_verify"],
                "blocked_actions": ["buy", "add", "chase_strength", "limit_up_attempt"],
                "required_before_upgrade": ["A1覆盖>=80%", "B1市场结构可用"],
            }
        return {
            "code": "auction_defensive_only",
            "max_action": "defensive_checklist",
            "summary": "实时行情覆盖不足：只输出防守清单。",
            "allowed_actions": ["risk_check", "manual_verify"],
            "blocked_actions": ["buy", "add", "chase_strength", "limit_up_attempt", "high_confidence_hold"],
            "required_before_upgrade": ["运行collector或导入可审计实时行情包"],
        }

    if automation == "tail":
        if a1_ok and b1_ok:
            return {
                "code": "tail_full_plan",
                "max_action": "tail_plan_with_next_open_validation",
                "summary": "A1+B1可用：可输出尾盘/隔夜计划，但隔夜动作仍要次日开盘验证。",
                "allowed_actions": ["observe", "hold", "reduce", "sell", "conditional_low_buy_plan", "next_day_validation_plan"],
                "blocked_actions": ["guaranteed_next_day_claim", "overnight_no_stop_trade"],
                "required_before_upgrade": ["次日09:35承接或A2提前放权"],
            }
        if a1_partial:
            return {
                "code": "tail_low_confidence",
                "max_action": "observe_hold_reduce",
                "summary": "A1部分可用：允许观察、持有和减仓触发，禁止高置信买入。",
                "allowed_actions": ["observe", "hold", "reduce_on_trigger"],
                "blocked_actions": ["high_confidence_buy", "add", "overnight_chase"],
                "required_before_upgrade": ["A1覆盖>=80%", "B1市场结构可用"],
            }
        return {
            "code": "tail_defensive_only",
            "max_action": "defensive_checklist",
            "summary": "collector覆盖不足：只输出防守清单。",
            "allowed_actions": ["risk_check", "manual_verify"],
            "blocked_actions": ["buy", "add", "high_confidence_hold", "overnight_plan"],
            "required_before_upgrade": ["运行collector或导入可审计实时行情包"],
        }

    if a1_ok and b1_ok:
        return {
            "code": "user_or_research_full_plan",
            "max_action": "conditional_plan_with_sizing",
            "summary": "A1+B1可用：可输出综合分析、持仓建议、期望R和仓位上限；开盘追强仍需A2。",
            "allowed_actions": ["observe", "hold", "reduce", "sell", "conditional_buy", "conditional_switch"],
            "blocked_actions": ["09:28_chase_without_a2", "no_stop_trade", "weak_follower_standard_size"],
            "required_before_upgrade": ["结构止损", "市场状态权限", "板块角色", "expected_R>0"],
        }
    if a1_partial:
        return {
            "code": "user_or_research_low_confidence",
            "max_action": "observe_hold_reduce",
            "summary": "A1部分可用：可输出低置信观察、持有/减仓和人工补数清单。",
            "allowed_actions": ["observe", "hold", "reduce_on_trigger", "manual_verify"],
            "blocked_actions": ["high_confidence_buy", "add", "switch_to_new_risk"],
            "required_before_upgrade": ["A1覆盖>=80%", "B1市场结构可用"],
        }
    return {
        "code": "user_or_research_defensive_only",
        "max_action": "defensive_checklist",
        "summary": "实时行情或市场结构覆盖不足：只输出防守清单和手动核验表。",
        "allowed_actions": ["risk_check", "manual_verify"],
        "blocked_actions": ["buy", "add", "high_confidence_hold", "switch"],
        "required_before_upgrade": ["运行collector或导入A1/B1数据包"],
    }


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
    manual_sector_flow_path = default_manual_sector_flow_path(root, run_date)
    manual_sector_flow_ok = has_manual_sector_flow_b1(root, run_date)
    b1_ok = has_market_b1(coverage_payload) or manual_sector_flow_ok

    resolved_auction_path = auction_path or default_manual_auction_path(root, run_date)
    auction_payload = load_json_if_exists(resolved_auction_path)
    a2_ok = has_manual_auction_a2(auction_payload)
    opening_confirmation_ok = a1_ok and b1_ok
    early_chase_ok = a1_ok and a2_ok and b1_ok
    stable_readiness = assess_stable_data_readiness(
        root,
        run_date,
        a0_ok=a0_ok,
        a1_ok=a1_ok,
        a1_partial=a1_partial,
        b1_ok=b1_ok,
        opening_confirmation_ok=opening_confirmation_ok,
    )
    permission_ceiling = action_permission_ceiling(
        automation,
        a0_ok=a0_ok,
        a1_ok=a1_ok,
        a1_partial=a1_partial,
        a2_ok=a2_ok,
        b1_ok=b1_ok,
        opening_confirmation_ok=opening_confirmation_ok,
        early_chase_ok=early_chase_ok,
    )

    if not a0_ok:
        grade = "D"
        permission = "A0账户/风控缺失：不能给仓位建议。"
    elif automation == "auction":
        if early_chase_ok:
            grade = "A"
            permission = "A2提前放权和主证据层可用：可输出09:28计划，但仍需09:35承接验证。"
        elif opening_confirmation_ok:
            grade = "B"
            permission = "主证据层可用但缺A2：只给09:30-09:35承接确认；确认前禁止追强。"
        elif a1_partial:
            grade = "C"
            permission = "A1不完整或B1缺失：只输出防守清单和手动核验表。"
        else:
            grade = "C"
            permission = "实时行情覆盖不足：只输出防守清单。"
    elif automation == "tail":
        if a1_ok and b1_ok:
            grade = "A"
            permission = "可输出尾盘/隔夜概率、期望R和次日验证条件。"
        elif a1_partial:
            grade = "B"
            permission = "可输出观察/持有/减仓，禁止高置信买入。"
        else:
            grade = "C"
            permission = "collector覆盖不足：只输出防守清单。"
    else:
        if a1_ok and b1_ok:
            grade = "A"
            permission = "可输出用户给定板块/个股/持仓评价、期望R和仓位上限；新买仍需止损与市场权限。"
        elif a1_partial:
            grade = "B"
            permission = "可输出低置信观察、持有/减仓和人工补数清单；禁止高置信买入/加仓。"
        else:
            grade = "C"
            permission = "实时行情或市场结构覆盖不足：只输出防守清单和手动核验表。"

    missing: list[str] = []
    if not a0_ok:
        missing.append("A0账户/风控")
    if not a1_ok:
        missing.append("A1报价/分时/均线覆盖>=80%")
    if automation == "auction" and not a2_ok:
        missing.append("A2提前放权字段：竞价成交额/09:20后撤单/封单/队列/板块角色")
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
        "opening_confirmation_ok": opening_confirmation_ok,
        "early_chase_ok": early_chase_ok,
        "action_permission_ceiling": permission_ceiling,
        "stable_data_readiness": stable_readiness,
        "decision_weights_path": str(decision_weights_path(root)),
        "coverage_path": str(resolved_coverage_path),
        "auction_path": str(resolved_auction_path),
        "sector_flow_path": str(manual_sector_flow_path),
        "manual_sector_flow_ok": manual_sector_flow_ok,
        "missing_decision_data": missing,
    }


def render_data_health(health: dict[str, Any]) -> str:
    readiness = health["stable_data_readiness"]
    ceiling = health["action_permission_ceiling"]
    lines = [
        "# 数据健康检查",
        f"- 日期/时间：{health['date']} {health['time']}",
        f"- 自动化：{health['automation']}",
        f"- 数据等级：{health['grade']}",
        f"- 输出权限：{health['permission']}",
        f"- 动作权限上限：{ceiling['max_action']}（{ceiling['code']}）",
        f"- 稳定数据就绪分：{readiness['score']:.0f}/{readiness['max_score']:.0f}",
        f"- 权重配置：{health['decision_weights_path']}（{readiness['version']}）",
        f"- A0账户风控：{'通过' if health['a0_ok'] else '缺失/失败'}",
        f"- A1核心覆盖：{health['a1_core_coverage']:.0%}",
        f"- A2提前放权数据：{'可用' if health['a2_ok'] else '缺失'}",
        f"- B1市场结构：{'可用' if health['b1_ok'] else '缺失'}",
        f"- 09:35承接确认能力：{'可评估' if health['opening_confirmation_ok'] else '不足'}",
        f"- 09:28提前追强权限：{'允许' if health['early_chase_ok'] else '禁止'}",
        f"- coverage：{health['coverage_path']}",
        f"- manual auction：{health['auction_path']}",
        f"- manual sector flow：{health['sector_flow_path']}（{'可用' if health.get('manual_sector_flow_ok') else '缺失'}）",
    ]
    if health["missing_decision_data"]:
        lines.append("\n## 会限制结论的数据缺口")
        lines.extend(f"- {item}" for item in health["missing_decision_data"])
    lines.extend(
        [
            "",
            "## 动作权限上限",
            f"- 结论：{ceiling['summary']}",
            f"- 允许：{', '.join(ceiling['allowed_actions'])}",
            f"- 禁止：{', '.join(ceiling['blocked_actions'])}",
            f"- 升级前置：{', '.join(ceiling['required_before_upgrade'])}",
            "",
            "## 稳定数据权重",
            "| 组件 | 权重 | 得分 | 状态 |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for component in readiness["components"]:
        lines.append(
            "| {id} | {weight:.0f} | {earned:.0f} | {status} |".format(
                id=component["id"],
                weight=component["weight"],
                earned=component["earned"],
                status=component["status"],
            )
        )
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
            for event_index, event in enumerate(events, start=1):
                rows.append(
                    {
                        "plan_id": f"{run_date}-{automation}-{code}-{event_index:02d}",
                        "run_time": run_time,
                        "automation": automation,
                        "source_type": source_type,
                        "code": code,
                        "name": name,
                        "event": event,
                        "mode": "",
                        "base_rate": None,
                        "base_rate_source": "",
                        "base_rate_sample_size": 0,
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


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def iter_dates(start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError("--end-date 不能早于 --start-date。")
    days = (end - start).days
    return [(start + dt.timedelta(days=index)).isoformat() for index in range(days + 1)]


def is_filled(value: Any, unknown_values: set[str] | None = None, *, zero_is_missing: bool = False) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in (unknown_values or {"unknown", "缺失", "na", "n/a"}):
            return False
        if zero_is_missing:
            try:
                return float(stripped) != 0
            except ValueError:
                return True
    if zero_is_missing and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return True


AUCTION_STOCK_FIELDS = [
    "auction_price",
    "auction_change_pct",
    "auction_amount_cny",
    "auction_volume_lots",
    "post_0920_cancel_signal",
    "seal_amount_cny",
    "bid_queue_signal",
    "ask_queue_signal",
    "role_signal",
]
AUCTION_CORE_FIELDS = ["auction_price", "auction_amount_cny", "post_0920_cancel_signal", "role_signal"]
AUCTION_POSITIVE_NUMERIC_FIELDS = {"auction_price", "auction_amount_cny", "auction_volume_lots"}
AUCTION_CSV_ALIASES = {
    "code": {"code", "股票代码", "证券代码", "代码"},
    "name": {"name", "股票名称", "证券名称", "名称"},
    "auction_price": {"auction_price", "竞价价", "竞价价格", "集合竞价价", "开盘价"},
    "auction_change_pct": {"auction_change_pct", "竞价涨幅", "竞价涨跌幅", "涨跌幅", "涨幅"},
    "auction_amount_cny": {"auction_amount_cny", "竞价额", "竞价金额", "竞价成交额", "成交额"},
    "auction_volume_lots": {"auction_volume_lots", "竞价量", "竞价成交量", "成交量"},
    "post_0920_cancel_signal": {"post_0920_cancel_signal", "09:20后撤单", "0920后撤单", "撤单信号"},
    "seal_amount_cny": {"seal_amount_cny", "封单额", "封单金额"},
    "bid_queue_signal": {"bid_queue_signal", "买队列", "买盘队列", "买方队列"},
    "ask_queue_signal": {"ask_queue_signal", "卖队列", "卖盘队列", "卖方队列"},
    "role_signal": {"role_signal", "角色", "板块角色", "竞价角色"},
    "source_type": {"source_type", "来源类型"},
    "notes": {"notes", "备注", "说明"},
}
AUCTION_NUMERIC_FIELDS = {
    "auction_price",
    "auction_change_pct",
    "auction_amount_cny",
    "auction_volume_lots",
    "seal_amount_cny",
}
POST_0920_SIGNAL_MAP = {
    "良性": "benign",
    "正常": "benign",
    "稳定": "benign",
    "无明显撤单": "benign",
    "恶性": "bad",
    "大撤单": "bad",
    "撤单": "bad",
    "未知": "unknown",
    "缺失": "unknown",
}
ROLE_SIGNAL_MAP = {
    "龙头": "leader",
    "领涨": "leader",
    "核心": "core",
    "中军": "core",
    "补涨": "catch_up",
    "后排": "follower",
    "跟风": "follower",
    "无效": "invalid",
    "失效": "invalid",
    "未知": "unknown",
}


def is_auction_field_filled(item: dict[str, Any], field: str) -> bool:
    return is_filled(item.get(field), zero_is_missing=field in AUCTION_POSITIVE_NUMERIC_FIELDS)


def has_complete_auction_core(item: dict[str, Any]) -> bool:
    return all(is_auction_field_filled(item, field) for field in AUCTION_CORE_FIELDS)


def normalized_auction_csv_header(header: str) -> str | None:
    normalized = header.strip().replace(" ", "").replace("_", "").lower()
    for field, aliases in AUCTION_CSV_ALIASES.items():
        for alias in aliases:
            alias_key = alias.strip().replace(" ", "").replace("_", "").lower()
            if normalized == alias_key:
                return field
    return None


def normalize_auction_signal(field: str, value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"unknown", "benign", "bad", "leader", "core", "catch_up", "follower", "invalid"}:
        return lowered
    if field == "post_0920_cancel_signal":
        return POST_0920_SIGNAL_MAP.get(text, text)
    if field == "role_signal":
        return ROLE_SIGNAL_MAP.get(text, text)
    return text


def auction_payload_from_csv(root: Path, run_date: str, input_path: Path, source: str) -> dict[str, Any]:
    lookup = stock_lookup(load_portfolio(root))
    stocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    with input_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV 缺少表头。")
        header_map = {
            header: normalized
            for header in reader.fieldnames
            if (normalized := normalized_auction_csv_header(header))
        }
        if "code" not in set(header_map.values()):
            raise ValueError("CSV 必须包含 code/股票代码/证券代码 字段。")
        for row_number, row in enumerate(reader, start=2):
            item: dict[str, Any] = {
                "code": "",
                "name": "",
                "source_type": "manual_csv",
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
            for header, field in header_map.items():
                raw_value = row.get(header)
                if field in AUCTION_NUMERIC_FIELDS:
                    item[field] = parse_market_number(raw_value)
                elif field in {"post_0920_cancel_signal", "role_signal"}:
                    item[field] = normalize_auction_signal(field, raw_value)
                else:
                    normalized_value = normalize_auction_signal(field, raw_value)
                    item[field] = normalized_value if normalized_value is not None else item.get(field)
            code = portfolio_style_code(str(item.get("code") or ""))
            if not code:
                warnings.append(f"第{row_number}行缺少有效股票代码，已跳过。")
                continue
            source_type, portfolio_item = lookup.get(code, (str(item.get("source_type") or "manual_csv"), {}))
            item["code"] = code
            if not item.get("name"):
                item["name"] = portfolio_item.get("name", code)
            if item.get("source_type") == "manual_csv" and source_type in {"holding", "watchlist"}:
                item["source_type"] = source_type
            stocks.append(item)
    return {
        "date": run_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "input_path": str(input_path),
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
        "import_warnings": warnings,
    }


AUCTION_CSV_TEMPLATE_FIELDS = [
    "股票代码",
    "股票名称",
    "来源类型",
    "竞价价",
    "竞价涨跌幅",
    "竞价成交额",
    "竞价量",
    "09:20后撤单",
    "封单额",
    "买队列",
    "卖队列",
    "板块角色",
    "备注",
]


def auction_csv_template_rows(root: Path, run_date: str, extra_codes: list[str] | None = None) -> list[dict[str, Any]]:
    data = load_portfolio(root)
    lookup = stock_lookup(data)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_row(code: str, name: str, source_type: str) -> None:
        normalized = portfolio_style_code(code)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        rows.append(
            {
                "股票代码": normalized,
                "股票名称": name or normalized,
                "来源类型": source_type,
                "竞价价": "",
                "竞价涨跌幅": "",
                "竞价成交额": "",
                "竞价量": "",
                "09:20后撤单": "unknown",
                "封单额": "",
                "买队列": "unknown",
                "卖队列": "unknown",
                "板块角色": "unknown",
                "备注": f"{run_date} A2 sample",
            }
        )

    for section, source_type in (("positions", "holding"), ("watchlist", "watchlist")):
        items = data.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            append_row(str(item.get("code", "")), str(item.get("name", "")), source_type)

    for code in normalize_requested_codes(extra_codes):
        _, item = lookup.get(code, ("sector_core", {}))
        append_row(code, str(item.get("name", code)), "sector_core")
    return rows


def summarize_auction_samples(
    root: Path,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    sample_dir = root / "data" / "manual" / "auction"
    paths = sorted(sample_dir.glob("*.json")) if sample_dir.exists() else []
    if start_date or end_date:
        start = parse_date(start_date or "0001-01-01")
        end = parse_date(end_date or "9999-12-31")
        filtered_paths: list[Path] = []
        for path in paths:
            try:
                if path.stem.count("-") == 2 and start <= parse_date(path.stem) <= end:
                    filtered_paths.append(path)
            except ValueError:
                continue
        paths = filtered_paths

    field_counts = {field: 0 for field in AUCTION_STOCK_FIELDS}
    sample_summaries: list[dict[str, Any]] = []
    stock_rows = 0
    usable_rows = 0
    complete_core_rows = 0
    errors: list[dict[str, str]] = []

    for path in paths:
        try:
            payload = load_json_if_exists(path) or {}
        except Exception as exc:
            errors.append({"path": str(path), "error": repr(exc)})
            continue
        stocks = payload.get("stocks", [])
        if not isinstance(stocks, list):
            errors.append({"path": str(path), "error": "stocks is not a list"})
            continue
        file_stock_rows = 0
        file_usable_rows = 0
        file_complete_core_rows = 0
        for item in stocks:
            if not isinstance(item, dict):
                continue
            file_stock_rows += 1
            stock_rows += 1
            for field in AUCTION_STOCK_FIELDS:
                if is_auction_field_filled(item, field):
                    field_counts[field] += 1
            if has_manual_auction_a2({"stocks": [item]}):
                usable_rows += 1
                file_usable_rows += 1
            if has_complete_auction_core(item):
                complete_core_rows += 1
                file_complete_core_rows += 1
        sample_summaries.append(
            {
                "date": payload.get("date") or path.stem,
                "path": str(path),
                "stock_rows": file_stock_rows,
                "usable_rows": file_usable_rows,
                "complete_core_rows": file_complete_core_rows,
                "source": payload.get("source", ""),
            }
        )

    return {
        "sample_dir": str(sample_dir),
        "sample_file_count": len(sample_summaries),
        "stock_row_count": stock_rows,
        "usable_a2_row_count": usable_rows,
        "complete_core_row_count": complete_core_rows,
        "field_coverage": {
            field: {
                "filled": count,
                "total": stock_rows,
                "coverage": count / stock_rows if stock_rows else 0.0,
            }
            for field, count in field_counts.items()
        },
        "samples": sample_summaries,
        "errors": errors,
    }


def render_auction_sample_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# A2竞价样本覆盖统计",
        f"- 样本目录：{summary['sample_dir']}",
        f"- 样本文件：{summary['sample_file_count']}",
        f"- 个股样本行：{summary['stock_row_count']}",
        f"- A2可用行：{summary['usable_a2_row_count']}",
        f"- 核心字段完整行：{summary['complete_core_row_count']}",
        "",
        "## 字段覆盖",
        "| 字段 | 已填 | 总数 | 覆盖率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for field, data in summary["field_coverage"].items():
        lines.append(f"| {field} | {data['filled']} | {data['total']} | {data['coverage']:.0%} |")
    lines.extend(["", "## 样本文件", "| 日期 | 个股行 | A2可用行 | 核心完整行 | 来源 |", "| --- | ---: | ---: | ---: | --- |"])
    for item in summary["samples"]:
        lines.append(
            f"| {item['date']} | {item['stock_rows']} | {item['usable_rows']} | "
            f"{item['complete_core_rows']} | {item['source'] or '缺失'} |"
        )
    if not summary["samples"]:
        lines.append("| NA | 0 | 0 | 0 | 缺失 |")
    if summary["errors"]:
        lines.append("\n## 读取错误")
        lines.extend(f"- {item['path']}: {item['error']}" for item in summary["errors"])
    lines.extend(
        [
            "",
            "## 产品判断",
            "- A2样本不是行情替代品；它用于校准竞价权限和开盘确认规则。",
            "- 核心字段不完整时，09:28仍应降级为确认清单，不能输出追强结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def outcome_template_rows(root: Path, run_date: str, automation: str) -> list[dict[str, Any]]:
    prediction_path, _ = prediction_paths(root, run_date)
    predictions = read_jsonl(prediction_path)
    if not predictions:
        predictions = prediction_template_rows(root, run_date, automation)
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        if automation and prediction.get("automation") not in {automation, ""}:
            continue
        rows.append(
            {
                "plan_id": prediction.get("plan_id", ""),
                "run_time": prediction.get("run_time", ""),
                "automation": prediction.get("automation", automation),
                "code": prediction.get("code", ""),
                "name": prediction.get("name", ""),
                "event": prediction.get("event", ""),
                "actual": "",
                "actual_time": "",
                "result_r": None,
                "error_type": "",
                "false_permission": False,
                "invalidated_at_0935": False,
                "evidence": "",
                "next_weight_adjustment": "",
                "notes": "",
            }
        )
    return rows


def behavior_template_rows(root: Path, run_date: str, automation: str | None = None) -> list[dict[str, Any]]:
    prediction_path, _ = prediction_paths(root, run_date)
    predictions = read_jsonl(prediction_path)
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        if automation and prediction.get("automation") != automation:
            continue
        rows.append(
            {
                "time": f"{run_date} 09:30",
                "plan_id": prediction.get("plan_id", ""),
                "attempted_action": "",
                "market_regime": "",
                "data_grade": prediction.get("data_grade", ""),
                "violated_rules": [],
                "guardrail_action": "",
                "outside_plan": False,
                "stop_present": True,
                "planned_account_loss_pct": None,
                "executed": False,
                "user_override": False,
                "notes": "",
            }
        )
    if not rows:
        rows.append(
            {
                "time": f"{run_date} 09:30",
                "plan_id": "",
                "attempted_action": "",
                "market_regime": "",
                "data_grade": "",
                "violated_rules": [],
                "guardrail_action": "",
                "outside_plan": False,
                "stop_present": True,
                "planned_account_loss_pct": None,
                "executed": False,
                "user_override": False,
                "notes": "",
            }
        )
    return rows


def message_evidence_template(run_date: str, codes: list[str] | None = None, themes: list[str] | None = None) -> dict[str, Any]:
    return {
        "date": run_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "codes": normalize_requested_codes(codes),
            "themes": [theme.strip() for theme in themes or [] if theme.strip()],
        },
        "evidence": [
            {
                "id": "",
                "source_type": "exchange_announcement/company_disclosure/news/industry_chain/ir/transcript/manual_note",
                "source_name": "",
                "title": "",
                "published_at": "",
                "url_or_path": "",
                "code": "",
                "theme": "",
                "summary": "",
                "stance": "positive/negative/neutral/conflicting",
                "freshness": "fresh/stale/unknown",
                "is_rumor": False,
                "conflicts_with": [],
                "used_for": "catalyst/thesis_update/risk/priced_in_check/background",
                "confidence": "high/medium/low",
                "notes": "",
            }
        ],
    }


def summarize_message_evidence(payload: dict[str, Any] | None, run_date: str) -> dict[str, Any]:
    rows = (payload or {}).get("evidence", [])
    if not isinstance(rows, list):
        rows = []
    stale_count = 0
    missing_source_count = 0
    rumor_count = 0
    conflict_count = 0
    stance_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        stance = str(row.get("stance") or "missing")
        source_type = str(row.get("source_type") or "missing")
        stance_counts[stance] = stance_counts.get(stance, 0) + 1
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        if not row.get("source_name") and not row.get("url_or_path"):
            missing_source_count += 1
        if row.get("freshness") == "stale":
            stale_count += 1
        elif row.get("published_at"):
            try:
                published = parse_date(str(row["published_at"])[:10])
                if (parse_date(run_date) - published).days > 30:
                    stale_count += 1
            except ValueError:
                pass
        rumor_count += int(bool(row.get("is_rumor")))
        conflict_count += int(bool(row.get("conflicts_with")))
    return {
        "evidence_count": len([row for row in rows if isinstance(row, dict)]),
        "missing_source_count": missing_source_count,
        "stale_count": stale_count,
        "rumor_count": rumor_count,
        "conflict_count": conflict_count,
        "stance_counts": stance_counts,
        "source_type_counts": source_type_counts,
    }


def render_message_evidence_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# 消息证据层统计",
        f"- 证据条数：{summary['evidence_count']}",
        f"- 缺来源：{summary['missing_source_count']}",
        f"- 过期材料：{summary['stale_count']}",
        f"- 传闻：{summary['rumor_count']}",
        f"- 冲突材料：{summary['conflict_count']}",
        "",
        "## 立场分布",
        "| 立场 | 数量 |",
        "| --- | ---: |",
    ]
    for key, value in sorted(summary["stance_counts"].items()):
        lines.append(f"| {key} | {value} |")
    if not summary["stance_counts"]:
        lines.append("| NA | 0 |")
    lines.extend(["", "## 来源类型", "| 来源类型 | 数量 |", "| --- | ---: |"])
    for key, value in sorted(summary["source_type_counts"].items()):
        lines.append(f"| {key} | {value} |")
    if not summary["source_type_counts"]:
        lines.append("| NA | 0 |")
    lines.extend(
        [
            "",
            "## 产品判断",
            "- 缺来源、过期或传闻材料不得作为高置信催化。",
            "- 冲突材料必须保留，不应合成为单边结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def default_message_evidence_path(root: Path, run_date: str) -> Path:
    return root / "data" / "manual" / "messages" / f"{run_date}.json"


def behavior_path_for(root: Path, run_date: str) -> Path:
    return root / "reports" / "behavior" / f"{run_date}-events.jsonl"


def outcome_paths_for(root: Path, run_date: str) -> list[Path]:
    _, canonical_path = prediction_paths(root, run_date)
    template_paths = sorted((root / "reports" / "outcomes").glob(f"{run_date}-*-outcome-template.jsonl"))
    return [canonical_path, *[path for path in template_paths if path != canonical_path]]


def behavior_paths_for(root: Path, run_date: str) -> list[Path]:
    canonical_path = behavior_path_for(root, run_date)
    template_path = root / "reports" / "behavior" / f"{run_date}-behavior-template.jsonl"
    return [canonical_path, template_path] if template_path != canonical_path else [canonical_path]


def unique_rows_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        for row in read_jsonl(path):
            key = json.dumps(row, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def is_completed_outcome(row: dict[str, Any]) -> bool:
    if not is_filled(row.get("plan_id")):
        return False
    return (
        is_filled(row.get("actual"))
        or row.get("result_r") is not None
        or is_filled(row.get("error_type"))
        or is_filled(row.get("evidence"))
    )


def is_completed_behavior(row: dict[str, Any]) -> bool:
    violated_rules = row.get("violated_rules")
    return (
        is_filled(row.get("attempted_action"))
        or is_filled(row.get("guardrail_action"))
        or bool(violated_rules)
        or str(row.get("executed")).lower() in {"true", "1", "yes", "y"}
        or str(row.get("outside_plan")).lower() in {"true", "1", "yes", "y"}
        or str(row.get("user_override")).lower() in {"true", "1", "yes", "y"}
        or str(row.get("stop_present")).lower() == "false"
        or is_filled(row.get("notes"))
    )


def completed_outcome_rows(root: Path, run_date: str) -> list[dict[str, Any]]:
    return [row for row in unique_rows_from_paths(outcome_paths_for(root, run_date)) if is_completed_outcome(row)]


def completed_behavior_rows(root: Path, run_date: str) -> list[dict[str, Any]]:
    return [row for row in unique_rows_from_paths(behavior_paths_for(root, run_date)) if is_completed_behavior(row)]


def boolish(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y", "是"}


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def log_row_key(row: dict[str, Any]) -> str:
    if row.get("plan_id"):
        return str(row["plan_id"])
    return "|".join(str(row.get(field, "")) for field in ("run_time", "automation", "code", "event"))


def auction_core_codes_by_date(root: Path, start_date: str, end_date: str) -> dict[str, set[str]]:
    codes_by_date = {run_date: set() for run_date in iter_dates(start_date, end_date)}
    sample_dir = root / "data" / "manual" / "auction"
    for run_date in codes_by_date:
        payload = load_json_if_exists(sample_dir / f"{run_date}.json") or {}
        stocks = payload.get("stocks", [])
        if not isinstance(stocks, list):
            continue
        for item in stocks:
            if not isinstance(item, dict) or not has_complete_auction_core(item):
                continue
            code = portfolio_style_code(str(item.get("code", "")))
            if code:
                codes_by_date[run_date].add(code)
    return codes_by_date


def is_opening_permission_prediction(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(field, ""))
        for field in ("action", "mode", "style", "event", "notes")
    ).lower()
    permission_terms = {
        "buy",
        "add",
        "chase",
        "limit-up",
        "limit_up",
        "买",
        "加",
        "追",
        "打板",
        "半路",
        "开仓",
    }
    return any(term in text for term in permission_terms)


def outcome_marks_false_permission(row: dict[str, Any]) -> bool:
    error_type = str(row.get("error_type", "")).lower()
    return boolish(row.get("false_permission")) or error_type in {"false_permission", "permission_error", "overpermission"}


def outcome_invalidated_at_0935(row: dict[str, Any]) -> bool:
    if boolish(row.get("invalidated_at_0935")):
        return True
    text = " ".join(str(row.get(field, "")) for field in ("actual", "actual_time", "event", "error_type", "evidence", "notes"))
    return "09:35" in text and any(term in text.lower() for term in ("failure", "failed", "stop", "证伪", "失败", "跌破", "未站回"))


def empty_auction_calibration_bucket() -> dict[str, Any]:
    return {
        "matched_count": 0,
        "permission_count": 0,
        "false_permission_count": 0,
        "invalidated_0935_count": 0,
        "expected_r_errors": [],
        "abs_expected_r_errors": [],
    }


def auction_calibration_summary(root: Path, start_date: str, end_date: str, min_a2_rows: int = 20) -> dict[str, Any]:
    dates = iter_dates(start_date, end_date)
    a2_codes_by_date = auction_core_codes_by_date(root, start_date, end_date)
    groups = {
        "a2_confirmed": empty_auction_calibration_bucket(),
        "no_a2": empty_auction_calibration_bucket(),
    }
    prediction_count = 0
    outcome_count = 0
    matched_count = 0

    for run_date in dates:
        prediction_path, _ = prediction_paths(root, run_date)
        predictions = [row for row in read_jsonl(prediction_path) if row.get("automation") in {"auction", ""}]
        outcomes = completed_outcome_rows(root, run_date)
        outcome_by_key = {log_row_key(row): row for row in outcomes}
        prediction_count += len(predictions)
        outcome_count += len(outcomes)
        for prediction in predictions:
            outcome = outcome_by_key.get(log_row_key(prediction))
            if not outcome:
                continue
            matched_count += 1
            code = portfolio_style_code(str(prediction.get("code", "")))
            group_name = "a2_confirmed" if code in a2_codes_by_date.get(run_date, set()) else "no_a2"
            group = groups[group_name]
            group["matched_count"] += 1
            if is_opening_permission_prediction(prediction):
                group["permission_count"] += 1
            if outcome_marks_false_permission(outcome):
                group["false_permission_count"] += 1
            if outcome_invalidated_at_0935(outcome):
                group["invalidated_0935_count"] += 1
            expected_r = optional_float(prediction.get("expected_r"))
            result_r = optional_float(outcome.get("result_r"))
            if expected_r is not None and result_r is not None:
                error = result_r - expected_r
                group["expected_r_errors"].append(error)
                group["abs_expected_r_errors"].append(abs(error))

    def finalize(group: dict[str, Any]) -> dict[str, Any]:
        matched = group["matched_count"]
        permission = group["permission_count"]
        errors = group.pop("expected_r_errors")
        abs_errors = group.pop("abs_expected_r_errors")
        return {
            **group,
            "false_permission_rate": group["false_permission_count"] / permission if permission else None,
            "invalidated_0935_rate": group["invalidated_0935_count"] / matched if matched else None,
            "mean_expected_r_error": sum(errors) / len(errors) if errors else None,
            "mean_abs_expected_r_error": sum(abs_errors) / len(abs_errors) if abs_errors else None,
        }

    auction_summary = summarize_auction_samples(root, start_date, end_date)
    finalized_groups = {name: finalize(group) for name, group in groups.items()}
    complete_rows = auction_summary["complete_core_row_count"]
    recommendations: list[str] = []
    if complete_rows < min_a2_rows:
        recommendations.append(f"A2核心完整行只有{complete_rows}，少于{min_a2_rows}；不得放宽09:28追强权限。")
    if matched_count < min_a2_rows:
        recommendations.append(f"prediction/outcome匹配样本只有{matched_count}，不足以调整base rate或权限阈值。")
    if not recommendations:
        recommendations.append("样本量达到最低复盘门槛；可以比较A2确认组与非A2组，但仍需按市场状态分层。")
    return {
        "start_date": start_date,
        "end_date": end_date,
        "date_count": len(dates),
        "min_a2_rows": min_a2_rows,
        "a2_complete_core_rows": complete_rows,
        "prediction_count": prediction_count,
        "outcome_count": outcome_count,
        "matched_count": matched_count,
        "groups": finalized_groups,
        "recommendations": recommendations,
    }


def render_auction_calibration(summary: dict[str, Any]) -> str:
    lines = [
        "# A2竞价校准比较",
        f"- 时间：{summary['start_date']} 至 {summary['end_date']}（{summary['date_count']}天）",
        f"- A2核心完整行：{summary['a2_complete_core_rows']}；最低门槛：{summary['min_a2_rows']}",
        f"- Prediction：{summary['prediction_count']}；Outcome：{summary['outcome_count']}；匹配：{summary['matched_count']}",
        "",
        "| 分组 | 匹配样本 | 放行动作 | 误放行 | 误放行率 | 09:35证伪 | 09:35证伪率 | Mean expected-R error | Mean abs expected-R error |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, group in summary["groups"].items():
        label = "A2确认组" if name == "a2_confirmed" else "非A2组"
        lines.append(
            "| {label} | {matched} | {permission} | {false_count} | {false_rate} | {invalid_count} | {invalid_rate} | {mean_error} | {mean_abs_error} |".format(
                label=label,
                matched=group["matched_count"],
                permission=group["permission_count"],
                false_count=group["false_permission_count"],
                false_rate=pct(group["false_permission_rate"] * 100) if group["false_permission_rate"] is not None else "缺失",
                invalid_count=group["invalidated_0935_count"],
                invalid_rate=pct(group["invalidated_0935_rate"] * 100) if group["invalidated_0935_rate"] is not None else "缺失",
                mean_error=f"{group['mean_expected_r_error']:.3f}" if group["mean_expected_r_error"] is not None else "缺失",
                mean_abs_error=f"{group['mean_abs_expected_r_error']:.3f}" if group["mean_abs_expected_r_error"] is not None else "缺失",
            )
        )
    lines.extend(["", "## 结论边界"])
    lines.extend(f"- {item}" for item in summary["recommendations"])
    lines.append("- 该比较只用于校准数据权限和开盘确认规则，不证明长期收益。")
    return "\n".join(lines) + "\n"


def weekly_review_summary(root: Path, start_date: str, end_date: str) -> dict[str, Any]:
    dates = iter_dates(start_date, end_date)
    prediction_count = 0
    outcome_count = 0
    behavior_count = 0
    matched_count = 0
    data_grade_counts: dict[str, int] = {}
    error_type_counts: dict[str, int] = {}
    outside_plan_executed = 0
    no_stop_executed = 0
    override_count = 0
    executed_count = 0
    message_evidence_count = 0
    missing_source_count = 0

    for run_date in dates:
        prediction_path, _ = prediction_paths(root, run_date)
        predictions = read_jsonl(prediction_path)
        outcomes = completed_outcome_rows(root, run_date)
        behaviors = completed_behavior_rows(root, run_date)
        prediction_count += len(predictions)
        outcome_count += len(outcomes)
        behavior_count += len(behaviors)
        outcome_keys = {str(row.get("plan_id") or "") for row in outcomes}
        matched_count += len([row for row in predictions if str(row.get("plan_id") or "") in outcome_keys])
        for row in predictions:
            grade = str(row.get("data_grade") or "missing")
            data_grade_counts[grade] = data_grade_counts.get(grade, 0) + 1
        for row in outcomes:
            error_type = str(row.get("error_type") or "missing")
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
        for row in behaviors:
            executed = str(row.get("executed")).lower() in {"true", "1", "yes", "y"}
            outside_plan = str(row.get("outside_plan")).lower() in {"true", "1", "yes", "y"}
            no_stop = str(row.get("stop_present")).lower() == "false"
            user_override = str(row.get("user_override")).lower() in {"true", "1", "yes", "y"}
            executed_count += int(executed)
            outside_plan_executed += int(outside_plan and executed)
            no_stop_executed += int(no_stop and executed)
            override_count += int(user_override)
        message_summary = summarize_message_evidence(load_json_if_exists(default_message_evidence_path(root, run_date)), run_date)
        message_evidence_count += message_summary["evidence_count"]
        missing_source_count += message_summary["missing_source_count"]

    auction_summary = summarize_auction_samples(root, start_date, end_date)
    recommendations: list[str] = []
    if auction_summary["sample_file_count"] == 0 or auction_summary["complete_core_row_count"] == 0:
        recommendations.append("继续补A2竞价样本；没有核心完整行时，09:28追强权限不能放宽。")
    if prediction_count and matched_count / prediction_count < 0.8:
        recommendations.append("补齐outcome日志；prediction无法匹配结果时，base rate不能升级。")
    if behavior_count == 0:
        recommendations.append("开始记录behavior日志；否则无法证明计划外/无止损/override行为是否下降。")
    if message_evidence_count and missing_source_count / message_evidence_count > 0.1:
        recommendations.append("收紧消息证据来源字段；缺来源材料不得进入高置信催化。")
    if not recommendations:
        recommendations.append("样本闭环完整度可接受；下周重点看概率校准误差和高风险行为是否下降。")

    return {
        "start_date": start_date,
        "end_date": end_date,
        "date_count": len(dates),
        "prediction_count": prediction_count,
        "outcome_count": outcome_count,
        "matched_count": matched_count,
        "behavior_count": behavior_count,
        "executed_count": executed_count,
        "outside_plan_executed": outside_plan_executed,
        "no_stop_executed": no_stop_executed,
        "override_count": override_count,
        "message_evidence_count": message_evidence_count,
        "missing_source_count": missing_source_count,
        "data_grade_counts": data_grade_counts,
        "error_type_counts": error_type_counts,
        "auction": auction_summary,
        "recommendations": recommendations,
    }


def render_weekly_review(summary: dict[str, Any]) -> str:
    prediction_count = summary["prediction_count"]
    matched_rate = summary["matched_count"] / prediction_count if prediction_count else None
    executed_count = summary["executed_count"]
    outside_rate = summary["outside_plan_executed"] / executed_count if executed_count else None
    no_stop_rate = summary["no_stop_executed"] / executed_count if executed_count else None
    lines = [
        "# 周度复盘摘要",
        f"- 时间：{summary['start_date']} 至 {summary['end_date']}（{summary['date_count']}天）",
        f"- Prediction：{summary['prediction_count']}；Outcome：{summary['outcome_count']}；匹配率：{pct(matched_rate * 100) if matched_rate is not None else '缺失'}",
        f"- Behavior事件：{summary['behavior_count']}；执行动作：{summary['executed_count']}",
        f"- 计划外执行率：{pct(outside_rate * 100) if outside_rate is not None else '缺失'}；无止损执行率：{pct(no_stop_rate * 100) if no_stop_rate is not None else '缺失'}；override：{summary['override_count']}",
        f"- A2样本文件：{summary['auction']['sample_file_count']}；核心完整行：{summary['auction']['complete_core_row_count']}",
        f"- 消息证据：{summary['message_evidence_count']}；缺来源：{summary['missing_source_count']}",
        "",
        "## 数据等级分布",
        "| 数据等级 | 数量 |",
        "| --- | ---: |",
    ]
    for key, value in sorted(summary["data_grade_counts"].items()):
        lines.append(f"| {key} | {value} |")
    if not summary["data_grade_counts"]:
        lines.append("| NA | 0 |")
    lines.extend(["", "## 错误类型", "| 错误类型 | 数量 |", "| --- | ---: |"])
    for key, value in sorted(summary["error_type_counts"].items()):
        lines.append(f"| {key} | {value} |")
    if not summary["error_type_counts"]:
        lines.append("| NA | 0 |")
    lines.extend(["", "## 下周动作"])
    lines.extend(f"- {item}" for item in summary["recommendations"])
    return "\n".join(lines) + "\n"


def render_decision_brief(
    root: Path,
    run_date: str,
    target_time: str,
    automation: str,
    coverage_path: Path | None = None,
    auction_path: Path | None = None,
) -> str:
    data = load_portfolio(root)
    health = assess_data_health(root, run_date, target_time, automation, coverage_path, auction_path)
    validation = validate_portfolio(data)
    ceiling = health["action_permission_ceiling"]
    readiness = health["stable_data_readiness"]
    lines = [
        "# 决策简报",
        f"- 时间：{run_date} {target_time}",
        f"- 工作流：{automation}",
        f"- 数据等级：{health['grade']}",
        f"- 输出权限：{health['permission']}",
        f"- 动作权限上限：{ceiling['max_action']}（{ceiling['code']}）",
        f"- 稳定数据就绪分：{readiness['score']:.0f}/{readiness['max_score']:.0f}",
        f"- 账户配置：{'通过' if validation.ok else '未通过'}",
        f"- 当前仓位：{pct(data.get('total_position_pct'))}；现金：{pct(data.get('cash_pct'))}",
        f"- 单笔最大亏损预算：{pct(data.get('max_loss_per_trade_pct'))}",
    ]
    if health["missing_decision_data"]:
        lines.append("\n## 先解决的数据缺口")
        lines.extend(f"- {item}" for item in health["missing_decision_data"])
    lines.extend(
        [
            "",
            "## 当前动作权限",
            f"- 允许：{', '.join(ceiling['allowed_actions'])}",
            f"- 禁止：{', '.join(ceiling['blocked_actions'])}",
            f"- 升级前置：{', '.join(ceiling['required_before_upgrade'])}",
            "",
            "## 最小下一步",
        ]
    )
    if automation == "auction" and health["opening_confirmation_ok"] and not health["a2_ok"]:
        lines.append("- 先等待或引用09:30-09:35承接确认；只有想提前到09:28行动时，才补A2竞价截图/手工JSON。")
        lines.append("- 把候选改为first-five-minute confirmation，不写竞价超预期，不给开盘直接追。")
    elif automation == "auction" and not health["a2_ok"]:
        lines.append("- A2缺失会禁止09:28追强；当前还缺A1/B1主证据时，先补实时行情和市场结构，再谈09:35确认。")
    if not health["b1_ok"]:
        lines.append("- 补市场宽度、涨跌停、板块角色和亏钱效应。")
    if health["a1_core_coverage"] < 0.8:
        lines.append("- 运行collector或导入实时行情数据包。")
    if not health["missing_decision_data"]:
        lines.append("- 进入对应工作流，输出完整计划并写入prediction/outcome/behavior日志。")
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


SECTOR_FLOW_FIELDS = [
    "date",
    "window",
    "sector",
    "direction",
    "net_amount_cny",
    "score",
    "sector_change_pct",
    "breadth_pct",
    "leader",
    "core_anchor",
    "momentum_label",
    "source",
    "source_time",
    "confidence",
    "notes",
]

SECTOR_FLOW_CSV_ALIASES = {
    "date": ["date", "日期"],
    "window": ["window", "周期", "区间"],
    "sector": ["sector", "板块", "行业", "概念"],
    "direction": ["direction", "方向", "资金方向", "流向"],
    "net_amount_cny": ["net_amount_cny", "net_amount", "净流入", "净流出", "净额", "金额"],
    "score": ["score", "评分", "承接分", "强度分"],
    "sector_change_pct": ["sector_change_pct", "涨跌幅", "板块涨跌幅"],
    "breadth_pct": ["breadth_pct", "宽度", "上涨占比", "板块宽度"],
    "leader": ["leader", "龙头", "领涨股"],
    "core_anchor": ["core_anchor", "中军", "核心中军"],
    "momentum_label": ["momentum_label", "状态", "标签", "承接状态"],
    "source": ["source", "来源", "数据源"],
    "source_time": ["source_time", "来源时间", "更新时间", "采集时间"],
    "confidence": ["confidence", "置信度", "可信度"],
    "notes": ["notes", "备注", "说明"],
}


def normalized_sector_flow_csv_header(header: str) -> str | None:
    normalized = header.strip().replace(" ", "").replace("_", "").lower()
    for field, aliases in SECTOR_FLOW_CSV_ALIASES.items():
        for alias in aliases:
            alias_key = alias.strip().replace(" ", "").replace("_", "").lower()
            if normalized == alias_key:
                return field
    return None


def normalize_sector_flow_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"inflow", "承接", "流入", "净流入", "买入"}:
        return "inflow"
    if text in {"outflow", "退潮", "流出", "净流出", "卖出"}:
        return "outflow"
    if text in {"mixed", "分歧", "观察", "震荡"}:
        return "mixed"
    return text or "unknown"


def sector_flow_payload_from_csv(run_date: str, input_path: Path, source: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    with input_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV 缺少表头。")
        header_map = {
            header: normalized
            for header in reader.fieldnames
            if (normalized := normalized_sector_flow_csv_header(header))
        }
        if "sector" not in set(header_map.values()):
            raise ValueError("CSV 必须包含 sector/板块/行业/概念 字段。")
        for row_number, row in enumerate(reader, start=2):
            item: dict[str, Any] = {field: "" for field in SECTOR_FLOW_FIELDS}
            item["date"] = run_date
            item["window"] = "today"
            item["source"] = source
            item["confidence"] = "manual"
            for header, field in header_map.items():
                raw_value = row.get(header)
                if field in {"net_amount_cny", "score", "sector_change_pct", "breadth_pct"}:
                    item[field] = parse_market_number(raw_value)
                elif field == "direction":
                    item[field] = normalize_sector_flow_direction(raw_value)
                else:
                    item[field] = str(raw_value or "").strip()
            if not item.get("sector"):
                warnings.append(f"第{row_number}行缺少板块名称，已跳过。")
                continue
            records.append(item)
    return {
        "date": run_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "input_path": str(input_path),
        "records": records,
        "warnings": warnings,
        "permission_note": "Manual sector-flow data can satisfy B1 sector-flow structure, but it does not replace A1 quote/minute/VWAP coverage.",
    }


def sector_flow_template_rows(run_date: str) -> list[dict[str, Any]]:
    return [
        {
            "date": run_date,
            "window": "today",
            "sector": "有色金属",
            "direction": "inflow",
            "net_amount_cny": "52.27亿",
            "score": 67,
            "sector_change_pct": "",
            "breadth_pct": "",
            "leader": "",
            "core_anchor": "",
            "momentum_label": "观察",
            "source": "manual/QMT/PTrade/JoinQuant/Tushare/terminal",
            "source_time": f"{run_date} 14:30",
            "confidence": "manual",
            "notes": "示例行，填写真实来源后再导入。",
        },
        {
            "date": run_date,
            "window": "today",
            "sector": "电子",
            "direction": "outflow",
            "net_amount_cny": "-391.80亿",
            "score": "",
            "sector_change_pct": "",
            "breadth_pct": "",
            "leader": "",
            "core_anchor": "",
            "momentum_label": "退潮",
            "source": "manual/QMT/PTrade/JoinQuant/Tushare/terminal",
            "source_time": f"{run_date} 14:30",
            "confidence": "manual",
            "notes": "示例行，填写真实来源后再导入。",
        },
    ]


def summarize_sector_flow(payload: dict[str, Any] | None, run_date: str) -> dict[str, Any]:
    records = (payload or {}).get("records")
    if not isinstance(records, list):
        records = []
    inflow: list[dict[str, Any]] = []
    outflow: list[dict[str, Any]] = []
    mixed: list[dict[str, Any]] = []
    missing_source = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        direction = normalize_sector_flow_direction(raw.get("direction"))
        if not raw.get("source") or not raw.get("source_time"):
            missing_source += 1
        if direction == "inflow":
            inflow.append(raw)
        elif direction == "outflow":
            outflow.append(raw)
        else:
            mixed.append(raw)
    sort_key = lambda item: as_float(item.get("score")) or abs(as_float(item.get("net_amount_cny")))
    return {
        "date": run_date,
        "record_count": len(records),
        "inflow_count": len(inflow),
        "outflow_count": len(outflow),
        "mixed_count": len(mixed),
        "missing_source_count": missing_source,
        "top_inflow": sorted(inflow, key=sort_key, reverse=True)[:5],
        "top_outflow": sorted(outflow, key=sort_key, reverse=True)[:5],
    }


def render_sector_flow_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# 板块资金迁移摘要",
        f"- 日期：{summary['date']}",
        f"- 记录数：{summary['record_count']}",
        f"- 承接/流入：{summary['inflow_count']}；退潮/流出：{summary['outflow_count']}；分歧/未知：{summary['mixed_count']}",
        f"- 缺来源或来源时间：{summary['missing_source_count']}",
        "",
        "## 承接/流入 Top",
        "| 板块 | 净额 | 评分 | 状态 | 来源 |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for item in summary["top_inflow"]:
        lines.append(f"| {item.get('sector', '')} | {money(item.get('net_amount_cny'))} | {item.get('score', '')} | {item.get('momentum_label', '')} | {item.get('source', '')} {item.get('source_time', '')} |")
    if not summary["top_inflow"]:
        lines.append("| NA | NA | NA | NA | NA |")
    lines.extend(["", "## 退潮/流出 Top", "| 板块 | 净额 | 评分 | 状态 | 来源 |", "| --- | ---: | ---: | --- | --- |"])
    for item in summary["top_outflow"]:
        lines.append(f"| {item.get('sector', '')} | {money(item.get('net_amount_cny'))} | {item.get('score', '')} | {item.get('momentum_label', '')} | {item.get('source', '')} {item.get('source_time', '')} |")
    if not summary["top_outflow"]:
        lines.append("| NA | NA | NA | NA | NA |")
    lines.extend(
        [
            "",
            "## 使用边界",
            "- 该文件只补 B1 板块资金迁移结构，不能替代 A1 个股报价、分时、VWAP 和均线。",
            "- 缺来源或来源时间的板块数据只能作为低置信线索，不能单独触发买入。",
        ]
    )
    return "\n".join(lines) + "\n"


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
        "manual_sector_flow": load_json_if_exists(default_manual_sector_flow_path(root, run_date)) or {},
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


def command_sector_flow_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    output_path = Path(args.output).resolve() if args.output else root / "data" / "manual" / "sector_flow" / f"{run_date}.csv"
    write_csv(output_path, sector_flow_template_rows(run_date), SECTOR_FLOW_FIELDS)
    print(f"已生成：{output_path}")
    print("填写真实板块资金迁移数据后，运行 sector-flow import-csv 导入为 JSON。")
    return 0


def command_sector_flow_import_csv(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else default_manual_sector_flow_path(root, run_date)
    payload = sector_flow_payload_from_csv(run_date, input_path, args.source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = summarize_sector_flow(payload, run_date)
    print(f"已生成：{output_path}")
    print(f"记录：{summary['record_count']}；承接/流入：{summary['inflow_count']}；退潮/流出：{summary['outflow_count']}")
    if payload.get("warnings"):
        print("警告：" + "；".join(payload["warnings"]))
    return 0


def command_sector_flow_summary(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    input_path = Path(args.input).resolve() if args.input else default_manual_sector_flow_path(root, run_date)
    payload = load_json_if_exists(input_path)
    summary = summarize_sector_flow(payload, run_date)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_sector_flow_summary(summary), end="")
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


def command_decision_brief(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    target_time = args.time.replace(":", "")
    coverage_path = Path(args.coverage_json).resolve() if args.coverage_json else None
    auction_path = Path(args.auction_json).resolve() if args.auction_json else None
    print(render_decision_brief(root, run_date, target_time, args.automation, coverage_path, auction_path), end="")
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


def command_outcome_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    rows = outcome_template_rows(root, run_date, args.automation)
    output = (
        Path(args.output).resolve()
        if args.output
        else root / "reports" / "outcomes" / f"{run_date}-{args.automation}-outcome-template.jsonl"
    )
    write_jsonl(output, rows)
    print(f"已生成：{output}")
    print(f"模板行数：{len(rows)}")
    return 0


def command_behavior_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    rows = behavior_template_rows(root, run_date, args.automation)
    output = (
        Path(args.output).resolve()
        if args.output
        else root / "reports" / "behavior" / f"{run_date}-behavior-template.jsonl"
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


def command_auction_import_csv(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    input_path = Path(args.input).resolve()
    payload = auction_payload_from_csv(root, run_date, input_path, args.source)
    output = Path(args.output).resolve() if args.output else default_manual_auction_path(root, run_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    complete_core_rows = sum(1 for item in payload["stocks"] if has_complete_auction_core(item))
    print(f"已生成：{output}")
    print(f"导入行数：{len(payload['stocks'])}")
    print(f"核心完整行：{complete_core_rows}")
    print(f"A2可用行：{complete_core_rows}")
    if payload.get("import_warnings"):
        print("导入警告：")
        for warning in payload["import_warnings"]:
            print(f"- {warning}")
    return 0


def command_auction_csv_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    rows = auction_csv_template_rows(root, run_date, args.codes or [])
    output = Path(args.output).resolve() if args.output else root / "data" / "manual" / "auction" / f"{run_date}.csv"
    write_csv(output, rows, AUCTION_CSV_TEMPLATE_FIELDS)
    print(f"已生成：{output}")
    print(f"模板行数：{len(rows)}")
    return 0


def command_auction_samples_summary(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    summary = summarize_auction_samples(root, args.start_date, args.end_date)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_auction_sample_summary(summary), end="")
    return 0


def command_auction_calibration(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    summary = auction_calibration_summary(root, args.start_date, args.end_date, args.min_a2_rows)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_auction_calibration(summary), end="")
    return 0


def command_message_template(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    payload = message_evidence_template(run_date, args.codes or [], args.themes or [])
    output = Path(args.output).resolve() if args.output else default_message_evidence_path(root, run_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成：{output}")
    return 0


def command_message_summary(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_date = args.date or today_string()
    path = Path(args.input).resolve() if args.input else default_message_evidence_path(root, run_date)
    payload = load_json_if_exists(path)
    summary = summarize_message_evidence(payload, run_date)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_message_evidence_summary(summary), end="")
    return 0


def command_weekly_review(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    summary = weekly_review_summary(root, args.start_date, args.end_date)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_weekly_review(summary), end="")
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
    packet = render_run_packet(
        root,
        args.mode,
        run_date,
        requested_themes=args.themes,
        requested_codes=args.codes,
        include_holdings=not args.no_holdings,
    )
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
    render.add_argument("--themes", nargs="*", default=[], help="用户临时给定板块/方向，例如 半导体 AI硬件")
    render.add_argument("--codes", nargs="*", default=[], help="用户临时给定个股代码，例如 002156.SZ 603920.SH")
    render.add_argument("--no-holdings", action="store_true", help="不把当前持仓纳入本次综合分析队列")
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

    sector_flow = subparsers.add_parser("sector-flow", help="生成、导入和汇总手工/外部板块资金迁移数据")
    sector_flow_subparsers = sector_flow.add_subparsers(dest="sector_flow_mode", required=True)
    sector_flow_template = sector_flow_subparsers.add_parser("template", help="生成板块资金迁移 CSV 模板")
    sector_flow_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    sector_flow_template.add_argument("--output", help="输出路径；默认 data/manual/sector_flow/{date}.csv")
    sector_flow_template.set_defaults(func=command_sector_flow_template)

    sector_flow_import = sector_flow_subparsers.add_parser("import-csv", help="把QMT/PTrade/掘金/聚宽/截图抄录的板块资金CSV导入JSON")
    sector_flow_import.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    sector_flow_import.add_argument("--input", required=True, help="CSV 路径")
    sector_flow_import.add_argument("--source", default="manual sector-flow CSV", help="样本来源说明")
    sector_flow_import.add_argument("--output", help="输出路径；默认 data/manual/sector_flow/{date}.json")
    sector_flow_import.set_defaults(func=command_sector_flow_import_csv)

    sector_flow_summary = sector_flow_subparsers.add_parser("summary", help="汇总板块资金迁移数据")
    sector_flow_summary.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    sector_flow_summary.add_argument("--input", help="输入 JSON 路径；默认 data/manual/sector_flow/{date}.json")
    sector_flow_summary.add_argument("--json", action="store_true", help="输出 JSON")
    sector_flow_summary.set_defaults(func=command_sector_flow_summary)

    data_health = subparsers.add_parser("data-health", help="评估自动化数据等级和输出权限")
    data_health.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    data_health.add_argument("--time", default="1430", help="目标时间，默认 1430；可写 09:28")
    data_health.add_argument("--automation", choices=["auction", "tail", "theme", "single", "user"], default="tail", help="自动化类型")
    data_health.add_argument("--coverage-json", help="collector JSON 路径；默认 reports/{date}-{time}-tail-data.json")
    data_health.add_argument("--auction-json", help="手工/截图提取竞价 JSON；默认 data/manual/auction/{date}.json")
    data_health.add_argument("--json", action="store_true", help="输出 JSON")
    data_health.set_defaults(func=command_data_health)

    brief = subparsers.add_parser("brief", help="生成短版决策简报，先给权限、风险和最小下一步")
    brief.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    brief.add_argument("--time", default="1430", help="目标时间，默认 1430；可写 09:28")
    brief.add_argument("--automation", choices=["auction", "tail", "theme", "single", "user"], default="tail")
    brief.add_argument("--coverage-json", help="collector JSON 路径")
    brief.add_argument("--auction-json", help="手工/截图提取竞价 JSON")
    brief.set_defaults(func=command_decision_brief)

    auction_template = subparsers.add_parser("auction-template", help="生成手工竞价数据模板，用于补齐A2数据")
    auction_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    auction_template.add_argument("--output", help="输出文件路径；默认 data/manual/auction/{date}.json")
    auction_template.set_defaults(func=command_auction_template)

    auction_csv_template = subparsers.add_parser("auction-csv-template", help="生成A2采样CSV模板：持仓+观察池+当日核心票")
    auction_csv_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    auction_csv_template.add_argument("--codes", nargs="*", default=[], help="当日板块核心票代码，例如 002156.SZ 603920.SH")
    auction_csv_template.add_argument("--output", help="输出文件路径；默认 data/manual/auction/{date}.csv")
    auction_csv_template.set_defaults(func=command_auction_csv_template)

    auction_import_csv = subparsers.add_parser("auction-import-csv", help="把同花顺/手工竞价CSV导入为A2样本JSON")
    auction_import_csv.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    auction_import_csv.add_argument("--input", required=True, help="CSV 路径")
    auction_import_csv.add_argument("--source", default="Tonghuashun/manual CSV", help="样本来源说明")
    auction_import_csv.add_argument("--output", help="输出文件路径；默认 data/manual/auction/{date}.json")
    auction_import_csv.set_defaults(func=command_auction_import_csv)

    auction_samples = subparsers.add_parser("auction-samples", help="统计手工A2竞价样本覆盖")
    auction_samples.add_argument("--start-date", help="开始日期，格式 YYYY-MM-DD")
    auction_samples.add_argument("--end-date", help="结束日期，格式 YYYY-MM-DD")
    auction_samples.add_argument("--json", action="store_true", help="输出 JSON")
    auction_samples.set_defaults(func=command_auction_samples_summary)

    auction_calibration = subparsers.add_parser("auction-calibration", help="比较A2确认组和非A2组的开盘校准指标")
    auction_calibration.add_argument("--start-date", required=True, help="开始日期，格式 YYYY-MM-DD")
    auction_calibration.add_argument("--end-date", required=True, help="结束日期，格式 YYYY-MM-DD")
    auction_calibration.add_argument("--min-a2-rows", type=int, default=20, help="最低A2核心完整行门槛，默认20")
    auction_calibration.add_argument("--json", action="store_true", help="输出 JSON")
    auction_calibration.set_defaults(func=command_auction_calibration)

    message = subparsers.add_parser("message-evidence", help="生成或统计消息证据层数据")
    message_subparsers = message.add_subparsers(dest="message_mode", required=True)
    message_template = message_subparsers.add_parser("template", help="生成消息证据 JSON 模板")
    message_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    message_template.add_argument("--codes", nargs="*", default=[], help="关联代码")
    message_template.add_argument("--themes", nargs="*", default=[], help="关联板块/方向")
    message_template.add_argument("--output", help="输出路径；默认 data/manual/messages/{date}.json")
    message_template.set_defaults(func=command_message_template)

    message_summary = message_subparsers.add_parser("summary", help="统计消息证据来源、时效和冲突")
    message_summary.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    message_summary.add_argument("--input", help="消息证据 JSON 路径；默认 data/manual/messages/{date}.json")
    message_summary.add_argument("--json", action="store_true", help="输出 JSON")
    message_summary.set_defaults(func=command_message_summary)

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

    outcome_template = prediction_subparsers.add_parser("outcome-template", help="根据prediction生成outcome JSONL模板")
    outcome_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    outcome_template.add_argument("--automation", choices=["auction", "tail"], required=True)
    outcome_template.add_argument("--output", help="输出文件路径；默认 reports/outcomes/{date}-{automation}-outcome-template.jsonl")
    outcome_template.set_defaults(func=command_outcome_template)

    behavior_template = prediction_subparsers.add_parser("behavior-template", help="生成behavior风险事件JSONL模板")
    behavior_template.add_argument("--date", help="运行日期，格式 YYYY-MM-DD；默认今天")
    behavior_template.add_argument("--automation", choices=["auction", "tail"], help="只为某个自动化生成关联模板")
    behavior_template.add_argument("--output", help="输出文件路径；默认 reports/behavior/{date}-behavior-template.jsonl")
    behavior_template.set_defaults(func=command_behavior_template)

    review = subparsers.add_parser("review", help="复盘汇总")
    review_subparsers = review.add_subparsers(dest="review_mode", required=True)
    weekly = review_subparsers.add_parser("weekly", help="按日期区间生成周度复盘摘要")
    weekly.add_argument("--start-date", required=True, help="开始日期，格式 YYYY-MM-DD")
    weekly.add_argument("--end-date", required=True, help="结束日期，格式 YYYY-MM-DD")
    weekly.add_argument("--json", action="store_true", help="输出 JSON")
    weekly.set_defaults(func=command_weekly_review)
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
