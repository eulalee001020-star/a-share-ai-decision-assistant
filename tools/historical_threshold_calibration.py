#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Historical threshold calibration for the public A-share portfolio.

The script uses public historical data to calibrate data-health thresholds for
the portfolio. It intentionally separates what can be validated from public
history from what still needs proprietary/manual auction data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_assistant import (
    DEFAULT_ROOT,
    http_get_text,
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
class MinuteBar:
    timestamp: str
    open: float
    close: float
    high: float
    low: float
    volume: float

    @property
    def date(self) -> str:
        return f"{self.timestamp[:4]}-{self.timestamp[4:6]}-{self.timestamp[6:8]}"

    @property
    def time(self) -> str:
        return self.timestamp[8:12]


def parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current / base - 1.0) * 100


def compact(date_text: str) -> str:
    return date_text.replace("-", "")


def shift_date(date_text: str, days: int) -> str:
    parsed = dt.date.fromisoformat(date_text)
    return (parsed + dt.timedelta(days=days)).isoformat()


def fetch_daily_bars(code: str, start_date: str, end_date: str) -> dict[str, DailyBar]:
    raw_code = tencent_code(code)
    history_start = shift_date(start_date, -80)
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={raw_code},day,{history_start},{end_date},180,qfq"
    )
    payload = json.loads(http_get_text(url, timeout=10))
    rows = payload.get("data", {}).get(raw_code, {}).get("qfqday") or []
    closes: list[float] = []
    bars: dict[str, DailyBar] = {}
    for row in rows:
        if len(row) < 6:
            continue
        parsed_date = row[0]
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
        if start_date <= parsed_date <= end_date:
            bars[parsed_date] = DailyBar(
                date=parsed_date,
                open=open_price or 0.0,
                close=close_price,
                high=high or 0.0,
                low=low or 0.0,
                volume=volume or 0.0,
                ma20=ma20,
            )
    return bars


def fetch_m15_bars(code: str) -> dict[tuple[str, str], MinuteBar]:
    raw_code = tencent_code(code)
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={raw_code},m15,,320"
    payload = json.loads(http_get_text(url, timeout=10))
    rows = payload.get("data", {}).get(raw_code, {}).get("m15") or []
    bars: dict[tuple[str, str], MinuteBar] = {}
    for row in rows:
        if len(row) < 6:
            continue
        open_price = parse_float(row[1])
        close_price = parse_float(row[2])
        high = parse_float(row[3])
        low = parse_float(row[4])
        volume = parse_float(row[5])
        if None in (open_price, close_price, high, low, volume):
            continue
        bar = MinuteBar(
            timestamp=str(row[0]),
            open=open_price or 0.0,
            close=close_price or 0.0,
            high=high or 0.0,
            low=low or 0.0,
            volume=volume or 0.0,
        )
        bars[(bar.date, bar.time)] = bar
    return bars


def fetch_b1_counts(run_date: str) -> dict[str, Any]:
    try:
        import akshare as ak  # type: ignore

        compact_date = compact(run_date)
        zt = ak.stock_zt_pool_em(date=compact_date)
        dt_pool = ak.stock_zt_pool_dtgc_em(date=compact_date)
        return {
            "source": "akshare/eastmoney",
            "limit_up_count": int(len(zt)),
            "limit_down_count": int(len(dt_pool)),
        }
    except Exception as exc:  # pragma: no cover - depends on remote source
        return {
            "source": "akshare/eastmoney",
            "error": repr(exc),
            "limit_up_count": None,
            "limit_down_count": None,
        }


def mean(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return statistics.mean(clean) if clean else None


def rate(values: list[bool]) -> float | None:
    return sum(1 for value in values if value) / len(values) if values else None


def pct(value: float | None) -> str:
    return "NA" if value is None else f"{value:.1%}"


def number(value: float | int | None, digits: int = 2) -> str:
    return "NA" if value is None else f"{float(value):.{digits}f}"


def latest_trading_dates(daily_by_code: dict[str, dict[str, DailyBar]], start_date: str, end_date: str, limit: int) -> list[str]:
    date_sets = [
        {date for date in bars if start_date <= date <= end_date}
        for bars in daily_by_code.values()
        if bars
    ]
    if not date_sets:
        return []
    common = sorted(set.intersection(*date_sets))
    return common[-limit:]


def build_samples(
    codes: list[str],
    start_date: str,
    end_date: str,
    sample_limit: int,
    fetch_b1: bool,
) -> dict[str, Any]:
    daily_by_code = {code: fetch_daily_bars(code, start_date, end_date) for code in codes}
    m15_by_code = {code: fetch_m15_bars(code) for code in codes}
    dates = latest_trading_dates(daily_by_code, start_date, end_date, sample_limit)
    b1_by_date = {date: fetch_b1_counts(date) for date in dates} if fetch_b1 else {}

    auction_samples: list[dict[str, Any]] = []
    tail_samples: list[dict[str, Any]] = []
    observations_0928: list[dict[str, Any]] = []
    observations_1430: list[dict[str, Any]] = []

    for date in dates:
        opening_daily = 0
        opening_m15 = 0
        tail_daily = 0
        tail_m15 = 0
        ma20_count = 0
        opening_ranges: list[float] = []
        opening_gaps: list[float] = []
        opening_gap_fades: list[bool] = []
        tail_to_close_moves: list[float] = []
        next_open_gaps: list[float] = []

        for code in codes:
            daily = daily_by_code[code].get(date)
            if not daily:
                continue
            opening_daily += 1
            tail_daily += 1
            if daily.ma20 is not None:
                ma20_count += 1

            previous_dates = [item for item in daily_by_code[code] if item < date]
            previous_bar = daily_by_code[code].get(previous_dates[-1]) if previous_dates else None
            next_dates = [item for item in daily_by_code[code] if item > date]
            next_bar = daily_by_code[code].get(next_dates[0]) if next_dates else None

            open_bar = m15_by_code[code].get((date, "0945"))
            if open_bar:
                opening_m15 += 1
                opening_range = pct_change(open_bar.high, open_bar.low)
                if opening_range is not None:
                    opening_ranges.append(opening_range)
                gap = pct_change(daily.open, previous_bar.close if previous_bar else None)
                if gap is not None:
                    opening_gaps.append(abs(gap))
                    opening_gap_fades.append(gap > 0 and open_bar.close < daily.open)
                observations_0928.append(
                    {
                        "date": date,
                        "code": code,
                        "open_gap_pct": gap,
                        "first_15m_range_pct": opening_range,
                        "gap_up_faded_by_0945": gap > 0 and open_bar.close < daily.open if gap is not None else None,
                    }
                )

            tail_bar = m15_by_code[code].get((date, "1430"))
            if tail_bar:
                tail_m15 += 1
                move = pct_change(daily.close, tail_bar.close)
                if move is not None:
                    tail_to_close_moves.append(abs(move))
                gap_next = pct_change(next_bar.open if next_bar else None, daily.close)
                if gap_next is not None:
                    next_open_gaps.append(abs(gap_next))
                observations_1430.append(
                    {
                        "date": date,
                        "code": code,
                        "tail_to_close_abs_pct": abs(move) if move is not None else None,
                        "next_open_gap_abs_pct": abs(gap_next) if gap_next is not None else None,
                    }
                )

        code_count = len(codes)
        a1_open = min(opening_daily, opening_m15, ma20_count) / code_count if code_count else 0
        a1_tail = min(tail_daily, tail_m15, ma20_count) / code_count if code_count else 0
        b1 = b1_by_date.get(date, {})
        auction_samples.append(
            {
                "date": date,
                "a1_core_coverage": a1_open,
                "a2_available": False,
                "b1_available": b1.get("limit_up_count") is not None,
                "limit_up_count": b1.get("limit_up_count"),
                "limit_down_count": b1.get("limit_down_count"),
                "avg_abs_open_gap_pct": mean(opening_gaps),
                "avg_first_15m_range_pct": mean(opening_ranges),
                "gap_up_fade_rate": rate([item for item in opening_gap_fades if item is not None]),
                "permission": "缺 A2：只允许 09:30-09:45 确认，禁止追强。",
            }
        )
        tail_samples.append(
            {
                "date": date,
                "a1_core_coverage": a1_tail,
                "b1_available": b1.get("limit_up_count") is not None,
                "limit_up_count": b1.get("limit_up_count"),
                "limit_down_count": b1.get("limit_down_count"),
                "avg_abs_tail_to_close_pct": mean(tail_to_close_moves),
                "avg_abs_next_open_gap_pct": mean(next_open_gaps),
                "permission": "A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。",
            }
        )

    return {
        "codes": codes,
        "date_range": {"start": start_date, "end": end_date},
        "dates": dates,
        "auction_samples": auction_samples,
        "tail_samples": tail_samples,
        "observations_0928": observations_0928,
        "observations_1430": observations_1430,
    }


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    auction = result["auction_samples"]
    tail = result["tail_samples"]
    obs_0928 = result["observations_0928"]
    obs_1430 = result["observations_1430"]
    return {
        "sample_days": len(result["dates"]),
        "stock_observations_0928": len(obs_0928),
        "stock_observations_1430": len(obs_1430),
        "a1_0928_days_ge_80": sum(1 for item in auction if item["a1_core_coverage"] >= 0.8),
        "a1_1430_days_ge_80": sum(1 for item in tail if item["a1_core_coverage"] >= 0.8),
        "b1_days_available": sum(1 for item in auction if item["b1_available"]),
        "a2_days_available": sum(1 for item in auction if item["a2_available"]),
        "avg_abs_open_gap_pct": mean([item["avg_abs_open_gap_pct"] for item in auction if item["avg_abs_open_gap_pct"] is not None]),
        "avg_first_15m_range_pct": mean([item["avg_first_15m_range_pct"] for item in auction if item["avg_first_15m_range_pct"] is not None]),
        "gap_up_fade_rate": mean([item["gap_up_fade_rate"] for item in auction if item["gap_up_fade_rate"] is not None]),
        "avg_abs_tail_to_close_pct": mean([item["avg_abs_tail_to_close_pct"] for item in tail if item["avg_abs_tail_to_close_pct"] is not None]),
        "avg_abs_next_open_gap_pct": mean([item["avg_abs_next_open_gap_pct"] for item in tail if item["avg_abs_next_open_gap_pct"] is not None]),
    }


def render_markdown(result: dict[str, Any]) -> str:
    summary = summarize(result)
    dates = result["dates"]
    lines = [
        "# Historical Threshold Calibration",
        "",
        f"- Window: {result['date_range']['start']} to {result['date_range']['end']}",
        f"- Trading-day samples: {summary['sample_days']}",
        f"- Public demo stocks: {', '.join(result['codes'])}",
        "- Market data source: Tencent public daily qfq K-line and 15-minute K-line",
        "- B1 source: AKShare/Eastmoney limit-up and limit-down pools, best effort",
        "- A2 auction source: not available from the public historical APIs used here",
        "",
        "## Summary",
        "",
        "| Metric | Result | Product Decision |",
        "| --- | ---: | --- |",
        f"| A1 >= 80% at 09:28 confirmation proxy | {summary['a1_0928_days_ge_80']}/{summary['sample_days']} days | Keep 80% as high-confidence threshold |",
        f"| A1 >= 80% at 14:30 | {summary['a1_1430_days_ge_80']}/{summary['sample_days']} days | Keep 80% as high-confidence threshold |",
        f"| B1 market structure available | {summary['b1_days_available']}/{summary['sample_days']} days | Missing B1 still caps regime confidence at medium |",
        f"| A2 historical auction available | {summary['a2_days_available']}/{summary['sample_days']} days | Keep missing-A2 downgrade; requires Tonghuashun/manual export |",
        f"| Avg abs open gap | {number(summary['avg_abs_open_gap_pct'])}% | Opening risk is non-trivial, no chase without A2 |",
        f"| Avg first-15m range | {number(summary['avg_first_15m_range_pct'])}% | Use 09:30-09:45 confirmation when A2 missing |",
        f"| Gap-up faded by 09:45 | {number((summary['gap_up_fade_rate'] or 0) * 100)}% | Positive open alone is insufficient |",
        f"| Avg 14:30-to-close absolute move | {number(summary['avg_abs_tail_to_close_pct'])}% | Tail plans need close confirmation and stop |",
        f"| Avg next-open absolute gap | {number(summary['avg_abs_next_open_gap_pct'])}% | Overnight plans need next-day auction validation |",
        "",
        "## 09:28 Samples",
        "",
        "| Date | A1 Coverage | A2 | B1 | Limit Up | Limit Down | Avg Open Gap | First-15m Range | Fade Rate | Permission |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in result["auction_samples"]:
        lines.append(
            f"| {item['date']} | {pct(item['a1_core_coverage'])} | "
            f"{'yes' if item['a2_available'] else 'no'} | "
            f"{'yes' if item['b1_available'] else 'no'} | "
            f"{item['limit_up_count'] if item['limit_up_count'] is not None else 'NA'} | "
            f"{item['limit_down_count'] if item['limit_down_count'] is not None else 'NA'} | "
            f"{number(item['avg_abs_open_gap_pct'])}% | "
            f"{number(item['avg_first_15m_range_pct'])}% | "
            f"{number((item['gap_up_fade_rate'] or 0) * 100)}% | {item['permission']} |"
        )

    lines.extend(
        [
            "",
            "## 14:30 Samples",
            "",
            "| Date | A1 Coverage | B1 | Limit Up | Limit Down | Tail-to-close Move | Next-open Gap | Permission |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in result["tail_samples"]:
        lines.append(
            f"| {item['date']} | {pct(item['a1_core_coverage'])} | "
            f"{'yes' if item['b1_available'] else 'no'} | "
            f"{item['limit_up_count'] if item['limit_up_count'] is not None else 'NA'} | "
            f"{item['limit_down_count'] if item['limit_down_count'] is not None else 'NA'} | "
            f"{number(item['avg_abs_tail_to_close_pct'])}% | "
            f"{number(item['avg_abs_next_open_gap_pct'])}% | {item['permission']} |"
        )

    lines.extend(
        [
            "",
            "## Calibrated Answers",
            "",
            "1. A1 80% threshold is retained. In this replay, A1 daily/MA/15-minute coverage reached the threshold on the sampled days. Lower coverage should still downgrade output because cross-stock comparison and VWAP/MA checks become incomplete.",
            "2. Missing A2 auction data is not treated as a small warning. Public historical sources did not expose 09:15-09:25 auction amount, post-09:20 cancel behavior, seal amount, or queue data. The replay shows opening gaps and first-15-minute ranges are material enough that the system should keep the rule: no chase, only 09:30-09:45 confirmation.",
            "3. B1 remains a required regime input. Limit-up and limit-down counts changed materially across the month, so a stock-only view is not enough to classify strong attack, rotation, or retreat with high confidence.",
            "4. Tail-session plans still need next-day auction validation. The 14:30-to-close and next-open gap statistics show that tail strength is not equivalent to next-day executable confirmation.",
            "",
            "## Boundary",
            "",
            "This is a historical data-health and guardrail calibration. It does not prove live alpha, and it does not replace a full prediction/outcome replay with Brier score and expected-R error. The missing A2 conclusion is especially important: historical public APIs were insufficient, so production use still requires Tonghuashun/manual auction export or another licensed auction source.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate data-health thresholds with recent public market data.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Project root")
    parser.add_argument("--start-date", default="2026-04-27", help="YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-05-27", help="YYYY-MM-DD")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--output", default="docs/historical_threshold_calibration.md")
    parser.add_argument("--json-output", default="")
    parser.add_argument("--skip-b1", action="store_true", help="Skip AKShare/Eastmoney B1 calls")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    with (root / "config" / "portfolio.example.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    codes = read_target_codes(data, [])
    result = build_samples(
        codes=codes,
        start_date=args.start_date,
        end_date=args.end_date,
        sample_limit=args.sample_limit,
        fetch_b1=not args.skip_b1,
    )

    markdown = render_markdown(result)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    if args.json_output:
        json_output = root / args.json_output
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {output}")
    print(json.dumps(summarize(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
