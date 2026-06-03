#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Large-sample historical policy backtest for the A-share assistant.

This is a guardrail and permission-policy backtest, not a stock-picking return
backtest. It asks whether the product's conservative rules, especially "no
opening chase without A2", reduce historically observable high-risk actions.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_assistant import (
    DEFAULT_ROOT,
    http_get_text,
    is_main_board_a_share,
    load_portfolio,
    portfolio_style_code,
    read_target_codes,
    tencent_code,
)


@dataclass
class DailyBar:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    ma20: float | None = None


@dataclass
class ConfirmationRecord:
    date: str
    code: str
    price_0935: float
    vwap_0935: float
    sector_confirmed: bool | None = None
    role: str | None = None


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current / base - 1.0) * 100


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def rate(flags: list[bool]) -> float | None:
    return sum(1 for flag in flags if flag) / len(flags) if flags else None


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "confirmed", "pass", "通过", "是", "强"}:
        return True
    if text in {"0", "false", "no", "n", "failed", "fail", "不通过", "否", "弱"}:
        return False
    return None


def format_pct(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1%}"


def format_number(value: float | None, digits: int = 3) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def shift_date(date_text: str, days: int) -> str:
    parsed = dt.date.fromisoformat(date_text)
    return (parsed + dt.timedelta(days=days)).isoformat()


def first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row[name] not in ("", None):
            return row[name]
    return None


def fetch_daily_bars(code: str, start_date: str, end_date: str, max_bars: int) -> list[DailyBar]:
    raw_code = tencent_code(code)
    history_start = shift_date(start_date, -120)
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={raw_code},day,{history_start},{end_date},{max_bars},qfq"
    )
    payload = json.loads(http_get_text(url, timeout=12))
    rows = payload.get("data", {}).get(raw_code, {}).get("qfqday") or payload.get("data", {}).get(raw_code, {}).get("day") or []
    closes: list[float] = []
    bars: list[DailyBar] = []
    for row in rows:
        if len(row) < 6:
            continue
        date = str(row[0])
        if date < history_start or date > end_date:
            continue
        open_price = parse_float(row[1])
        close_price = parse_float(row[2])
        high = parse_float(row[3])
        low = parse_float(row[4])
        volume = parse_float(row[5])
        if None in (open_price, close_price, high, low, volume):
            continue
        assert close_price is not None
        closes.append(close_price)
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        if start_date <= date <= end_date:
            bars.append(
                DailyBar(
                    date=date,
                    open=open_price or 0.0,
                    close=close_price,
                    high=high or 0.0,
                    low=low or 0.0,
                    volume=volume or 0.0,
                    ma20=ma20,
                )
            )
    return bars


def load_codes(root: Path, args: argparse.Namespace) -> list[str]:
    raw_codes: list[str] = []
    if args.codes:
        raw_codes.extend(args.codes)
    if args.codes_file:
        with Path(args.codes_file).expanduser().open(encoding="utf-8-sig") as fh:
            for line in fh:
                code = line.strip().split(",", 1)[0]
                if code and not code.startswith("#"):
                    raw_codes.append(code)
    if not raw_codes:
        default_universe = root / "config" / "backtest_universe.example.csv"
        if default_universe.exists():
            with default_universe.open(encoding="utf-8-sig") as fh:
                for line in fh:
                    code = line.strip().split(",", 1)[0]
                    if code and code.lower() != "code" and not code.startswith("#"):
                        raw_codes.append(code)
    if not raw_codes:
        raw_codes.extend(read_target_codes(load_portfolio(root), []))

    codes: list[str] = []
    seen: set[str] = set()
    for raw_code in raw_codes:
        code = portfolio_style_code(raw_code)
        if not code or code in seen:
            continue
        if args.main_board_only and not is_main_board_a_share(code):
            continue
        seen.add(code)
        codes.append(code)
        if args.max_codes and len(codes) >= args.max_codes:
            break
    return codes


def load_confirmation_records(path_text: str) -> dict[tuple[str, str], ConfirmationRecord]:
    if not path_text:
        return {}
    path = Path(path_text).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"confirmation file not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rows = payload.get("records") or payload.get("confirmations") or []
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []
    else:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))

    result: dict[tuple[str, str], ConfirmationRecord] = {}
    for row in rows:
        date = str(first_present(row, ["date", "日期", "trade_date"]) or "").strip()
        code = portfolio_style_code(str(first_present(row, ["code", "股票代码", "ts_code"]) or ""))
        price = parse_float(first_present(row, ["price_0935", "confirm_price", "0935_price", "09:35价", "确认价"]))
        vwap = parse_float(first_present(row, ["vwap_0935", "confirm_vwap", "0935_vwap", "09:35_vwap", "VWAP"]))
        if not date or not code or price is None or vwap is None:
            continue
        result[(date, code)] = ConfirmationRecord(
            date=date,
            code=code,
            price_0935=price,
            vwap_0935=vwap,
            sector_confirmed=parse_bool(first_present(row, ["sector_confirmed", "板块共振", "sector_ok"])),
            role=str(first_present(row, ["role", "板块角色", "role_signal"]) or "").strip() or None,
        )
    return result


def load_role_overrides(path_text: str) -> dict[tuple[str, str], str]:
    if not path_text:
        return {}
    path = Path(path_text).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"role file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        date = str(first_present(row, ["date", "日期", "trade_date"]) or "").strip()
        code = portfolio_style_code(str(first_present(row, ["code", "股票代码", "ts_code"]) or ""))
        role = str(first_present(row, ["role", "板块角色", "role_signal"]) or "").strip()
        if code and role:
            result[(date, code)] = role
    return result


def build_market_context(daily_by_code: dict[str, list[DailyBar]]) -> dict[str, dict[str, Any]]:
    by_date: dict[str, list[dict[str, float]]] = {}
    for bars in daily_by_code.values():
        bars = sorted(bars, key=lambda item: item.date)
        for index in range(1, len(bars)):
            previous = bars[index - 1]
            current = bars[index]
            return_pct = pct_change(current.close, previous.close)
            if return_pct is None:
                continue
            by_date.setdefault(current.date, []).append(
                {
                    "return_pct": return_pct,
                    "gap_pct": pct_change(current.open, previous.close) or 0.0,
                    "close_vs_open_pct": pct_change(current.close, current.open) or 0.0,
                }
            )

    context: dict[str, dict[str, Any]] = {}
    previous_regime = "unknown"
    for date in sorted(by_date):
        rows = by_date[date]
        returns = [row["return_pct"] for row in rows]
        up_rate = rate([value > 0 for value in returns]) or 0.0
        strong_up_rate = rate([value >= 3.0 for value in returns]) or 0.0
        weak_down_rate = rate([value <= -3.0 for value in returns]) or 0.0
        mean_return = mean(returns) or 0.0
        median_return = median(returns) or 0.0
        p75_return = percentile(returns, 0.75) or median_return
        gap_up_rows = [row for row in rows if row["gap_pct"] > 0]
        gap_fade_rate = rate([row["close_vs_open_pct"] < 0 for row in gap_up_rows])

        if previous_regime == "retreat" and up_rate >= 0.55 and mean_return > 0:
            regime = "ice_point_repair_proxy"
        elif up_rate >= 0.62 and mean_return >= 0.60 and strong_up_rate >= 0.08:
            regime = "strong_attack_proxy"
        elif up_rate <= 0.38 or mean_return <= -0.60 or weak_down_rate >= 0.12:
            regime = "retreat"
        elif 0.45 <= up_rate <= 0.58 and abs(mean_return) < 0.60:
            regime = "rotation_proxy"
        else:
            regime = "chaotic_proxy"

        context[date] = {
            "regime": regime,
            "up_rate": up_rate,
            "strong_up_rate": strong_up_rate,
            "weak_down_rate": weak_down_rate,
            "mean_return_pct": mean_return,
            "median_return_pct": median_return,
            "p75_return_pct": p75_return,
            "gap_fade_rate": gap_fade_rate,
            "stock_count": len(rows),
        }
        previous_regime = regime
    return context


def classify_role_proxy(current: DailyBar, previous: DailyBar, market: dict[str, Any] | None) -> str:
    return_pct = pct_change(current.close, previous.close)
    volume_ratio = current.volume / previous.volume if previous.volume else None
    if return_pct is None:
        return "unknown_proxy"
    p75_return = market.get("p75_return_pct") if market else None
    median_return = market.get("median_return_pct") if market else None
    p75_return = p75_return if isinstance(p75_return, (int, float)) else return_pct
    median_return = median_return if isinstance(median_return, (int, float)) else return_pct
    if return_pct >= p75_return and (volume_ratio is None or volume_ratio >= 1.2) and current.close >= current.open:
        return "leader_or_core_proxy"
    if return_pct >= median_return and current.close >= current.open:
        return "trend_or_anchor_proxy"
    if current.close < current.open or return_pct < median_return:
        return "follower_or_weak_proxy"
    return "unknown_proxy"


def result_from_entry(current: DailyBar, entry_price: float, stop_loss_pct: float, target_pct: float) -> dict[str, Any]:
    stop_hit = current.low <= entry_price * (1 - stop_loss_pct / 100)
    target_hit = current.high >= entry_price * (1 + target_pct / 100)
    ambiguous = stop_hit and target_hit
    if stop_hit:
        result_r = -1.0
        outcome = "failure"
    elif target_hit:
        result_r = target_pct / stop_loss_pct
        outcome = "success"
    else:
        result_r = (current.close - entry_price) / (entry_price * stop_loss_pct / 100)
        outcome = "success" if result_r > 0 else "failure" if result_r < 0 else "noise"
    return {
        "stop_hit": stop_hit,
        "target_hit": target_hit,
        "ambiguous_intraday_order": ambiguous,
        "result_r": result_r,
        "outcome": outcome,
    }


def daily_observations(
    daily_by_code: dict[str, list[DailyBar]],
    gap_threshold_pct: float,
    strong_close_threshold_pct: float,
    stop_loss_pct: float,
    target_pct: float,
    naive_expected_r: float,
    valid_plan_r_threshold: float = 0.5,
    confirmation_by_key: dict[tuple[str, str], ConfirmationRecord] | None = None,
    role_overrides: dict[tuple[str, str], str] | None = None,
) -> dict[str, Any]:
    stock_days = 0
    opening_candidates: list[dict[str, Any]] = []
    overnight_candidates: list[dict[str, Any]] = []
    market_context = build_market_context(daily_by_code)
    confirmation_by_key = confirmation_by_key or {}
    role_overrides = role_overrides or {}

    for code, bars in daily_by_code.items():
        bars = sorted(bars, key=lambda item: item.date)
        for index in range(1, len(bars) - 1):
            previous = bars[index - 1]
            current = bars[index]
            nxt = bars[index + 1]
            if current.ma20 is None:
                continue
            stock_days += 1
            open_gap_pct = pct_change(current.open, previous.close)
            close_vs_open_pct = pct_change(current.close, current.open)
            low_from_open_pct = pct_change(current.low, current.open)
            high_from_open_pct = pct_change(current.high, current.open)
            if open_gap_pct is None or close_vs_open_pct is None or low_from_open_pct is None or high_from_open_pct is None:
                continue

            if open_gap_pct >= gap_threshold_pct and previous.close >= current.ma20:
                entry_result = result_from_entry(current, current.open, stop_loss_pct, target_pct)
                result_r = entry_result["result_r"]
                false_permission = result_r < 0 or current.close < current.open
                market = market_context.get(current.date, {})
                role = (
                    role_overrides.get((current.date, code))
                    or role_overrides.get(("", code))
                    or classify_role_proxy(current, previous, market)
                )
                confirmation = confirmation_by_key.get((current.date, code))
                confirmation_status = "unavailable"
                confirmed_result: dict[str, Any] | None = None
                if confirmation:
                    sector_ok = confirmation.sector_confirmed is not False
                    confirmed = (
                        confirmation.price_0935 >= current.open
                        and confirmation.price_0935 >= confirmation.vwap_0935
                        and sector_ok
                        and market.get("regime") != "retreat"
                    )
                    confirmation_status = "confirmed" if confirmed else "failed"
                    confirmed_result = result_from_entry(current, confirmation.price_0935, stop_loss_pct, target_pct)
                opening_candidates.append(
                    {
                        "date": current.date,
                        "code": code,
                        "market_regime": market.get("regime", "unknown"),
                        "market_up_rate": market.get("up_rate"),
                        "role": role,
                        "open_gap_pct": open_gap_pct,
                        "close_vs_open_pct": close_vs_open_pct,
                        "low_from_open_pct": low_from_open_pct,
                        "high_from_open_pct": high_from_open_pct,
                        "stop_hit": entry_result["stop_hit"],
                        "target_hit": entry_result["target_hit"],
                        "ambiguous_intraday_order": entry_result["ambiguous_intraday_order"],
                        "gap_faded_by_close": current.close < current.open,
                        "close_below_previous": current.close < previous.close,
                        "false_permission": false_permission,
                        "result_r": result_r,
                        "expected_r_error": result_r - naive_expected_r,
                        "outcome": entry_result["outcome"],
                        "potential_valid_plan_proxy": result_r >= valid_plan_r_threshold,
                        "confirmation_status": confirmation_status,
                        "confirmation_price_0935": confirmation.price_0935 if confirmation else None,
                        "confirmation_vwap_0935": confirmation.vwap_0935 if confirmation else None,
                        "confirmation_sector_confirmed": confirmation.sector_confirmed if confirmation else None,
                        "confirmation_role": confirmation.role if confirmation else None,
                        "confirmation_result_r_daily_proxy": confirmed_result["result_r"] if confirmed_result else None,
                        "confirmation_false_permission_daily_proxy": (confirmed_result["result_r"] < 0 if confirmed_result else None),
                        "confirmation_stop_hit_daily_proxy": (confirmed_result["stop_hit"] if confirmed_result else None),
                        "confirmation_result_uses_daily_range_proxy": bool(confirmed_result),
                    }
                )

            close_strength_pct = pct_change(current.close, previous.close)
            next_open_gap_pct = pct_change(nxt.open, current.close)
            if close_strength_pct is not None and next_open_gap_pct is not None and close_strength_pct >= strong_close_threshold_pct:
                overnight_candidates.append(
                    {
                        "date": current.date,
                        "code": code,
                        "close_strength_pct": close_strength_pct,
                        "next_open_gap_pct": next_open_gap_pct,
                        "bad_next_open_gap": next_open_gap_pct <= -stop_loss_pct,
                    }
                )

    return {
        "stock_days": stock_days,
        "opening_candidates": opening_candidates,
        "overnight_candidates": overnight_candidates,
        "market_context": market_context,
    }


def summarize_group(items: list[dict[str, Any]], result_key: str = "result_r") -> dict[str, Any]:
    result_rs = [item[result_key] for item in items if isinstance(item.get(result_key), (int, float))]
    false_flags = [bool(item["false_permission"]) for item in items if "false_permission" in item]
    stop_flags = [bool(item["stop_hit"]) for item in items if "stop_hit" in item]
    return {
        "count": len(items),
        "false_permission_rate": rate(false_flags),
        "stop_hit_rate": rate(stop_flags),
        "mean_result_r": mean(result_rs),
        "median_result_r": median(result_rs),
    }


def summarize_by_key(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get(key, "unknown")), []).append(item)
    return {name: summarize_group(group) for name, group in sorted(grouped.items())}


def summarize_backtest(observations: dict[str, Any], args: argparse.Namespace, codes: list[str]) -> dict[str, Any]:
    opening = observations["opening_candidates"]
    overnight = observations["overnight_candidates"]
    result_rs = [item["result_r"] for item in opening]
    expected_errors = [item["expected_r_error"] for item in opening]
    false_flags = [bool(item["false_permission"]) for item in opening]
    stop_flags = [bool(item["stop_hit"]) for item in opening]
    fade_flags = [bool(item["gap_faded_by_close"]) for item in opening]
    close_below_prev_flags = [bool(item["close_below_previous"]) for item in opening]
    bad_overnight_flags = [bool(item["bad_next_open_gap"]) for item in overnight]
    valid_plan_flags = [bool(item.get("potential_valid_plan_proxy")) for item in opening]
    confirmation_samples = [item for item in opening if item.get("confirmation_status") in {"confirmed", "failed"}]
    confirmed_samples = [item for item in opening if item.get("confirmation_status") == "confirmed"]
    failed_confirmation_samples = [item for item in opening if item.get("confirmation_status") == "failed"]
    confirmed_result_rs = [
        item["confirmation_result_r_daily_proxy"]
        for item in confirmed_samples
        if isinstance(item.get("confirmation_result_r_daily_proxy"), (int, float))
    ]
    failed_confirmation_result_rs = [
        item["confirmation_result_r_daily_proxy"]
        for item in failed_confirmation_samples
        if isinstance(item.get("confirmation_result_r_daily_proxy"), (int, float))
    ]
    confirmed_mean = mean(confirmed_result_rs)
    failed_mean = mean(failed_confirmation_result_rs)
    confirmation_lift = (
        confirmed_mean - failed_mean
        if confirmed_mean is not None and failed_mean is not None
        else None
    )

    sample_ok = (
        observations["stock_days"] >= args.min_stock_days
        and len(opening) >= args.min_opening_candidates
    )
    product_decision = (
        "Sample sufficient for public guardrail backtest; keep A2-specific calibration separate."
        if sample_ok
        else "Sample below target; do not use this run to loosen permissions."
    )
    return {
        "date_range": {"start": args.start_date, "end": args.end_date},
        "code_count": len(codes),
        "codes": codes,
        "stock_days": observations["stock_days"],
        "opening_candidate_count": len(opening),
        "overnight_candidate_count": len(overnight),
        "min_stock_days": args.min_stock_days,
        "min_opening_candidates": args.min_opening_candidates,
        "sample_sufficient": sample_ok,
        "gap_threshold_pct": args.gap_threshold_pct,
        "strong_close_threshold_pct": args.strong_close_threshold_pct,
        "stop_loss_pct": args.stop_loss_pct,
        "target_pct": args.target_pct,
        "naive_expected_r": args.naive_expected_r,
        "valid_plan_r_threshold": getattr(args, "valid_plan_r_threshold", 0.5),
        "open_chase_false_permission_rate": rate(false_flags),
        "open_chase_stop_hit_rate": rate(stop_flags),
        "open_chase_gap_fade_rate": rate(fade_flags),
        "open_chase_close_below_previous_rate": rate(close_below_prev_flags),
        "open_chase_mean_result_r": mean(result_rs),
        "open_chase_median_result_r": median(result_rs),
        "open_chase_p25_result_r": percentile(result_rs, 0.25),
        "open_chase_p75_result_r": percentile(result_rs, 0.75),
        "mean_expected_r_error": mean(expected_errors),
        "mean_abs_expected_r_error": mean([abs(value) for value in expected_errors]),
        "overnight_bad_gap_rate": rate(bad_overnight_flags),
        "current_policy_false_permission_rate_without_a2": 0.0,
        "current_policy_blocked_opening_candidates": len(opening),
        "missed_valid_plan_proxy_count": sum(1 for flag in valid_plan_flags if flag),
        "missed_valid_plan_proxy_rate": rate(valid_plan_flags),
        "confirmation_sample_count": len(confirmation_samples),
        "confirmation_confirmed_count": len(confirmed_samples),
        "confirmation_failed_count": len(failed_confirmation_samples),
        "confirmation_confirmed_mean_result_r_daily_proxy": confirmed_mean,
        "confirmation_failed_mean_result_r_daily_proxy": failed_mean,
        "confirmation_lift_mean_result_r_daily_proxy": confirmation_lift,
        "market_regime_summary": summarize_by_key(opening, "market_regime"),
        "role_summary": summarize_by_key(opening, "role"),
        "product_decision": product_decision,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Historical Policy Backtest",
        "",
        "This validates permission and guardrail effectiveness. It does not prove live return capability.",
        "",
        "## Sample",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Window | {summary['date_range']['start']} to {summary['date_range']['end']} |",
        f"| Codes | {summary['code_count']} |",
        f"| Stock-days | {summary['stock_days']} |",
        f"| Opening chase candidates | {summary['opening_candidate_count']} |",
        f"| Overnight strength candidates | {summary['overnight_candidate_count']} |",
        f"| Minimum stock-days | {summary['min_stock_days']} |",
        f"| Minimum opening candidates | {summary['min_opening_candidates']} |",
        f"| Sample sufficient | {'yes' if summary['sample_sufficient'] else 'no'} |",
        "",
        "Data source: Tencent public adjusted daily K-line, fetched through `tools/historical_policy_backtest.py`. Universe: `config/backtest_universe.example.csv` unless `--codes` or `--codes-file` is supplied.",
        "",
        "## Policy Comparison",
        "",
        "| Policy / Metric | Result | Product Meaning |",
        "| --- | ---: | --- |",
        f"| Unsafe open-chase false-permission rate | {format_pct(summary['open_chase_false_permission_rate'])} | How often gap-up chase would have become a bad permission |",
        f"| Unsafe open-chase stop-hit rate | {format_pct(summary['open_chase_stop_hit_rate'])} | Daily low breached the planned 1R stop |",
        f"| Unsafe open-chase gap-fade rate | {format_pct(summary['open_chase_gap_fade_rate'])} | Positive open faded by close |",
        f"| Unsafe close-below-previous rate | {format_pct(summary['open_chase_close_below_previous_rate'])} | Open strength fully failed by close |",
        f"| Unsafe mean result R | {format_number(summary['open_chase_mean_result_r'])} | Realized R of naive opening chase proxy |",
        f"| Unsafe median result R | {format_number(summary['open_chase_median_result_r'])} | Robust central result |",
        f"| Mean expected-R error | {format_number(summary['mean_expected_r_error'])} | Result R minus naive expected R |",
        f"| Mean abs expected-R error | {format_number(summary['mean_abs_expected_r_error'])} | Calibration error magnitude |",
        f"| Bad next-open gap after strong close | {format_pct(summary['overnight_bad_gap_rate'])} | Why tail plans still need next-day auction validation |",
        f"| Current no-A2 policy false-permission rate | {format_pct(summary['current_policy_false_permission_rate_without_a2'])} | Missing A2 blocks 09:28 chase permissions by design |",
        f"| Current no-A2 policy blocked candidates | {summary['current_policy_blocked_opening_candidates']} | Risk events withheld until 09:35 confirmation |",
        f"| Missed-valid-plan proxy rate | {format_pct(summary.get('missed_valid_plan_proxy_rate'))} | Blocked candidates that later reached at least the valid-plan R threshold by daily proxy |",
        f"| Confirmation sample count | {summary.get('confirmation_sample_count', 0)} | Rows with explicit 09:35 price and VWAP input |",
        f"| Confirmation lift mean R | {format_number(summary.get('confirmation_lift_mean_result_r_daily_proxy'))} | Confirmed group mean R minus failed-confirmation group mean R, only when 09:35 input exists |",
        "",
        "## Market-Regime Breakdown",
        "",
        "| Regime Proxy | Count | False Permission | Stop Hit | Mean R | Median R |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for regime, item in (summary.get("market_regime_summary") or {}).items():
        lines.append(
            f"| {regime} | {item['count']} | {format_pct(item['false_permission_rate'])} | "
            f"{format_pct(item['stop_hit_rate'])} | {format_number(item['mean_result_r'])} | "
            f"{format_number(item['median_result_r'])} |"
        )

    lines.extend(
        [
            "",
            "## Role Breakdown",
            "",
            "| Role / Proxy | Count | False Permission | Stop Hit | Mean R | Median R |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for role, item in (summary.get("role_summary") or {}).items():
        lines.append(
            f"| {role} | {item['count']} | {format_pct(item['false_permission_rate'])} | "
            f"{format_pct(item['stop_hit_rate'])} | {format_number(item['mean_result_r'])} | "
            f"{format_number(item['median_result_r'])} |"
        )

    lines.extend(
        [
            "",
            "## 09:35 Confirmation Layer",
            "",
            f"- Explicit 09:35 samples: {summary.get('confirmation_sample_count', 0)}.",
            f"- Confirmed: {summary.get('confirmation_confirmed_count', 0)}; failed: {summary.get('confirmation_failed_count', 0)}.",
            f"- Confirmation lift mean R: {format_number(summary.get('confirmation_lift_mean_result_r_daily_proxy'))}.",
            "- If explicit 09:35 samples are zero, the confirmation layer is implemented but not validated by this run. Do not infer independent 09:35 decision value from daily bars.",
            "- When 09:35 samples exist, the confirmation result still uses daily high/low as a coarse path proxy unless true post-09:35 minute bars are supplied.",
            "",
            "## Product Decision",
            "",
            f"- {summary['product_decision']}",
            "- If the unsafe open-chase false-permission and gap-fade rates are material, the missing-A2 no-09:28-chase rule remains justified.",
            "- Missed-valid-plan proxy must be watched together with confirmation lift; a blocked candidate that later worked by daily bar is not automatically a valid 09:28 trade.",
            "- This backtest uses public daily bars. It cannot validate true 09:15-09:25 auction amount, queue, cancellation, or sealing-order data; those still require manual or licensed A2 samples.",
            "- Missing-A2 candidates should be downgraded into 09:35 absorption confirmation, not described as auction outperformance.",
            "- Use this report together with `auction-calibration` once 20-60 true A2 rows and matched prediction/outcome rows exist.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Large-sample historical policy backtest for A-share guardrails.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Project root")
    parser.add_argument("--start-date", default="2024-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-05-27", help="YYYY-MM-DD")
    parser.add_argument("--codes", nargs="*", default=[], help="Optional explicit code list")
    parser.add_argument("--codes-file", default="", help="CSV/text file whose first column is stock code")
    parser.add_argument("--max-codes", type=int, default=0, help="Limit code count; 0 means no limit")
    parser.add_argument("--max-bars", type=int, default=900, help="Tencent daily K-line max bars")
    parser.add_argument("--main-board-only", action="store_true", default=True)
    parser.add_argument("--gap-threshold-pct", type=float, default=2.0)
    parser.add_argument("--strong-close-threshold-pct", type=float, default=3.0)
    parser.add_argument("--stop-loss-pct", type=float, default=2.5)
    parser.add_argument("--target-pct", type=float, default=5.0)
    parser.add_argument("--naive-expected-r", type=float, default=0.2)
    parser.add_argument("--valid-plan-r-threshold", type=float, default=0.5)
    parser.add_argument("--confirmation-file", default="", help="Optional CSV/JSON with date, code, price_0935, vwap_0935, sector_confirmed, role")
    parser.add_argument("--role-file", default="", help="Optional CSV with date(optional), code, role for leader/core/catch-up/follower labels")
    parser.add_argument("--min-stock-days", type=int, default=5000)
    parser.add_argument("--min-opening-candidates", type=int, default=300)
    parser.add_argument("--output", default="docs/historical_policy_backtest.md")
    parser.add_argument("--json-output", default="reports/backtests/historical_policy_backtest.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    codes = load_codes(root, args)
    if not codes:
        raise ValueError("No valid codes for backtest.")
    daily_by_code = {code: fetch_daily_bars(code, args.start_date, args.end_date, args.max_bars) for code in codes}
    daily_by_code = {code: bars for code, bars in daily_by_code.items() if bars}
    confirmation_by_key = load_confirmation_records(args.confirmation_file)
    role_overrides = load_role_overrides(args.role_file)
    observations = daily_observations(
        daily_by_code=daily_by_code,
        gap_threshold_pct=args.gap_threshold_pct,
        strong_close_threshold_pct=args.strong_close_threshold_pct,
        stop_loss_pct=args.stop_loss_pct,
        target_pct=args.target_pct,
        naive_expected_r=args.naive_expected_r,
        valid_plan_r_threshold=args.valid_plan_r_threshold,
        confirmation_by_key=confirmation_by_key,
        role_overrides=role_overrides,
    )
    summary = summarize_backtest(observations, args, sorted(daily_by_code))
    markdown = render_markdown(summary)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    if args.json_output:
        json_output = root / args.json_output
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps({"summary": summary, "observations": observations}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {output}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
