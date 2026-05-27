"""Evaluate prediction/outcome logs and behavior-risk logs.

The goal is not to prove trading alpha. This tool checks whether probability
claims, expected-R estimates, and user-risk interventions are measurable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "1", "yes", "y"}


def row_key(row: dict[str, Any]) -> str:
    plan_id = row.get("plan_id")
    if plan_id:
        return str(plan_id)
    return "|".join(
        str(row.get(field, ""))
        for field in ("run_time", "automation", "code", "event")
    )


def outcome_label(row: dict[str, Any]) -> str | None:
    actual = str(row.get("actual", "")).strip().lower()
    if actual in {"success", "hit", "true", "1"}:
        return "success"
    if actual in {"failure", "failed", "stop", "false", "0"}:
        return "failure"
    if actual in {"noise", "neutral", "not_triggered", "none"}:
        return "noise"
    return None


def bucket_label(probability: float) -> str:
    lower = int(max(0, min(0.999999, probability)) * 10) * 10
    return f"{lower}-{lower + 10}%"


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def evaluate_predictions(
    predictions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    outcome_by_key = {row_key(row): row for row in outcomes}
    matched: list[dict[str, Any]] = []
    brier_values: list[float] = []
    multiclass_brier_values: list[float] = []
    expected_errors: list[float] = []
    expected_abs_errors: list[float] = []
    result_values: list[float] = []
    expected_values: list[float] = []
    buckets: dict[str, dict[str, Any]] = {}

    missing_base_rate = 0
    missing_base_rate_source = 0
    uncalibrated_base_rate = 0

    for prediction in predictions:
        if as_float(prediction.get("base_rate")) is None:
            missing_base_rate += 1
        if not prediction.get("base_rate_source"):
            missing_base_rate_source += 1
        sample_size = as_float(prediction.get("base_rate_sample_size"))
        if sample_size is None or sample_size < 30:
            uncalibrated_base_rate += 1

        outcome = outcome_by_key.get(row_key(prediction))
        label = outcome_label(outcome or {})
        success_probability = as_float(prediction.get("success_probability"))
        if outcome is None or label is None or success_probability is None:
            continue

        matched.append(prediction)
        actual_success = 1.0 if label == "success" else 0.0
        brier = (success_probability - actual_success) ** 2
        brier_values.append(brier)

        failure_probability = as_float(prediction.get("failure_probability"))
        noise_probability = as_float(prediction.get("noise_probability"))
        if failure_probability is not None and noise_probability is not None:
            y_success = 1.0 if label == "success" else 0.0
            y_failure = 1.0 if label == "failure" else 0.0
            y_noise = 1.0 if label == "noise" else 0.0
            multiclass_brier_values.append(
                (success_probability - y_success) ** 2
                + (failure_probability - y_failure) ** 2
                + (noise_probability - y_noise) ** 2
            )

        label_key = bucket_label(success_probability)
        bucket = buckets.setdefault(
            label_key,
            {
                "count": 0,
                "probabilities": [],
                "actual_successes": 0,
                "brier_values": [],
            },
        )
        bucket["count"] += 1
        bucket["probabilities"].append(success_probability)
        bucket["actual_successes"] += int(actual_success)
        bucket["brier_values"].append(brier)

        expected_r = as_float(prediction.get("expected_r"))
        result_r = as_float(outcome.get("result_r"))
        if expected_r is not None and result_r is not None:
            expected_values.append(expected_r)
            result_values.append(result_r)
            error = result_r - expected_r
            expected_errors.append(error)
            expected_abs_errors.append(abs(error))

    rendered_buckets = []
    for label, data in sorted(buckets.items()):
        count = data["count"]
        rendered_buckets.append(
            {
                "bucket": label,
                "count": count,
                "avg_probability": mean(data["probabilities"]),
                "success_rate": data["actual_successes"] / count if count else None,
                "brier": mean(data["brier_values"]),
            }
        )

    return {
        "prediction_count": len(predictions),
        "outcome_count": len(outcomes),
        "matched_count": len(matched),
        "missing_base_rate_count": missing_base_rate,
        "missing_base_rate_source_count": missing_base_rate_source,
        "uncalibrated_base_rate_count": uncalibrated_base_rate,
        "binary_success_brier": mean(brier_values),
        "multiclass_brier": mean(multiclass_brier_values),
        "mean_expected_r": mean(expected_values),
        "mean_result_r": mean(result_values),
        "mean_expected_r_error": mean(expected_errors),
        "mean_abs_expected_r_error": mean(expected_abs_errors),
        "buckets": rendered_buckets,
    }


def evaluate_behavior(rows: list[dict[str, Any]]) -> dict[str, Any]:
    executed_count = 0
    high_risk_attempts = 0
    guarded_high_risk = 0
    outside_plan_attempts = 0
    outside_plan_executed = 0
    no_stop_attempts = 0
    no_stop_executed = 0
    override_count = 0

    for row in rows:
        executed = as_bool(row.get("executed"))
        outside_plan = as_bool(row.get("outside_plan"))
        stop_present = row.get("stop_present")
        no_stop = stop_present is False or str(stop_present).lower() == "false"
        violated_rules = row.get("violated_rules") or []
        if isinstance(violated_rules, str):
            violated_rules = [violated_rules] if violated_rules else []
        guardrail_action = str(row.get("guardrail_action", "")).lower()
        guarded = guardrail_action in {"block", "downgrade", "confirmation_only", "require_confirm"}
        high_risk = bool(violated_rules) or str(row.get("risk_level", "")).lower() == "high"

        executed_count += int(executed)
        high_risk_attempts += int(high_risk)
        guarded_high_risk += int(high_risk and guarded)
        outside_plan_attempts += int(outside_plan)
        outside_plan_executed += int(outside_plan and executed)
        no_stop_attempts += int(no_stop)
        no_stop_executed += int(no_stop and executed)
        override_count += int(as_bool(row.get("user_override")) or (outside_plan and executed))

    return {
        "behavior_event_count": len(rows),
        "executed_count": executed_count,
        "high_risk_attempt_count": high_risk_attempts,
        "guarded_high_risk_count": guarded_high_risk,
        "guarded_high_risk_rate": guarded_high_risk / high_risk_attempts if high_risk_attempts else None,
        "outside_plan_attempt_count": outside_plan_attempts,
        "outside_plan_executed_count": outside_plan_executed,
        "plan_adherence_rate": 1 - outside_plan_executed / executed_count if executed_count else None,
        "no_stop_attempt_count": no_stop_attempts,
        "no_stop_executed_count": no_stop_executed,
        "no_stop_trade_rate": no_stop_executed / executed_count if executed_count else None,
        "override_count": override_count,
    }


def format_percent(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value * 100:.1f}%"


def format_number(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.3f}"


def render_markdown(result: dict[str, Any]) -> str:
    prediction = result["prediction"]
    behavior = result["behavior"]
    lines = [
        "# Prediction Replay Evaluation",
        "",
        "This report measures calibration readiness and risk-control behavior. It does not prove live investment returns.",
        "",
        "## Probability And Expected-R Calibration",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Predictions | {prediction['prediction_count']} |",
        f"| Outcomes | {prediction['outcome_count']} |",
        f"| Matched prediction/outcome rows | {prediction['matched_count']} |",
        f"| Missing base rate | {prediction['missing_base_rate_count']} |",
        f"| Missing base-rate source | {prediction['missing_base_rate_source_count']} |",
        f"| Uncalibrated base-rate sample size | {prediction['uncalibrated_base_rate_count']} |",
        f"| Binary success Brier | {format_number(prediction['binary_success_brier'])} |",
        f"| Multiclass Brier | {format_number(prediction['multiclass_brier'])} |",
        f"| Mean expected R | {format_number(prediction['mean_expected_r'])} |",
        f"| Mean result R | {format_number(prediction['mean_result_r'])} |",
        f"| Mean expected-R error | {format_number(prediction['mean_expected_r_error'])} |",
        f"| Mean absolute expected-R error | {format_number(prediction['mean_abs_expected_r_error'])} |",
        "",
        "## Probability Buckets",
        "",
        "| Bucket | Count | Avg probability | Success rate | Brier |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for bucket in prediction["buckets"]:
        lines.append(
            "| {bucket} | {count} | {avg_probability} | {success_rate} | {brier} |".format(
                bucket=bucket["bucket"],
                count=bucket["count"],
                avg_probability=format_percent(bucket["avg_probability"]),
                success_rate=format_percent(bucket["success_rate"]),
                brier=format_number(bucket["brier"]),
            )
        )
    if not prediction["buckets"]:
        lines.append("| NA | 0 | NA | NA | NA |")

    lines.extend(
        [
            "",
            "## Behavior-Risk Metrics",
            "",
            "| Metric | Result |",
            "| --- | ---: |",
            f"| Behavior events | {behavior['behavior_event_count']} |",
            f"| Executed actions | {behavior['executed_count']} |",
            f"| High-risk attempts | {behavior['high_risk_attempt_count']} |",
            f"| Guarded high-risk attempts | {behavior['guarded_high_risk_count']} |",
            f"| Guarded high-risk rate | {format_percent(behavior['guarded_high_risk_rate'])} |",
            f"| Outside-plan attempts | {behavior['outside_plan_attempt_count']} |",
            f"| Outside-plan executed actions | {behavior['outside_plan_executed_count']} |",
            f"| Plan adherence rate | {format_percent(behavior['plan_adherence_rate'])} |",
            f"| No-stop attempts | {behavior['no_stop_attempt_count']} |",
            f"| No-stop executed actions | {behavior['no_stop_executed_count']} |",
            f"| No-stop trade rate | {format_percent(behavior['no_stop_trade_rate'])} |",
            f"| User overrides | {behavior['override_count']} |",
            "",
            "## Product Reading",
            "",
            "1. If base-rate source or sample size is missing, probability output must be marked as uncalibrated.",
            "2. Brier score and expected-R error measure overconfidence and payoff estimation error, not stock-picking skill by themselves.",
            "3. Behavior-risk metrics are the right way to prove reduced risk-taking: fewer no-stop trades, fewer outside-plan trades, and fewer guardrail overrides.",
        ]
    )
    return "\n".join(lines) + "\n"


def evaluate(
    prediction_path: Path,
    outcome_path: Path,
    behavior_path: Path | None,
) -> dict[str, Any]:
    predictions = read_jsonl(prediction_path)
    outcomes = read_jsonl(outcome_path)
    behavior_rows = read_jsonl(behavior_path) if behavior_path else []
    return {
        "prediction": evaluate_predictions(predictions, outcomes),
        "behavior": evaluate_behavior(behavior_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate prediction replay and behavior-risk logs.")
    parser.add_argument("--predictions", required=True, help="Prediction JSONL path.")
    parser.add_argument("--outcomes", required=True, help="Outcome JSONL path.")
    parser.add_argument("--behavior", help="Optional behavior-risk JSONL path.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    result = evaluate(
        Path(args.predictions),
        Path(args.outcomes),
        Path(args.behavior) if args.behavior else None,
    )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
