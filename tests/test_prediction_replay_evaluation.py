import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "prediction_replay_evaluation.py"
SPEC = importlib.util.spec_from_file_location("prediction_replay_evaluation", MODULE_PATH)
prediction_replay_evaluation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = prediction_replay_evaluation
SPEC.loader.exec_module(prediction_replay_evaluation)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class PredictionReplayEvaluationTests(unittest.TestCase):
    def test_prediction_metrics_include_brier_and_expected_r_error(self):
        predictions = [
            {
                "plan_id": "p1",
                "base_rate": 0.40,
                "base_rate_source": "same-playbook-replay",
                "base_rate_sample_size": 45,
                "success_probability": 0.60,
                "failure_probability": 0.25,
                "noise_probability": 0.15,
                "expected_r": 0.70,
            },
            {
                "plan_id": "p2",
                "base_rate": 0.35,
                "base_rate_source": "same-playbook-replay",
                "base_rate_sample_size": 45,
                "success_probability": 0.30,
                "failure_probability": 0.50,
                "noise_probability": 0.20,
                "expected_r": -0.15,
            },
            {
                "plan_id": "p3",
                "base_rate": None,
                "success_probability": None,
            },
        ]
        outcomes = [
            {"plan_id": "p1", "actual": "success", "result_r": 1.2},
            {"plan_id": "p2", "actual": "failure", "result_r": -1.0},
        ]
        result = prediction_replay_evaluation.evaluate_predictions(predictions, outcomes)

        self.assertEqual(3, result["prediction_count"])
        self.assertEqual(2, result["matched_count"])
        self.assertEqual(1, result["missing_base_rate_count"])
        self.assertEqual(1, result["missing_base_rate_source_count"])
        self.assertEqual(1, result["uncalibrated_base_rate_count"])
        self.assertAlmostEqual(0.125, result["binary_success_brier"])
        self.assertAlmostEqual(-0.175, result["mean_expected_r_error"])
        self.assertEqual(2, len(result["buckets"]))

    def test_behavior_metrics_track_guardrails_and_overrides(self):
        rows = [
            {
                "risk_level": "high",
                "violated_rules": ["missing_a2"],
                "guardrail_action": "confirmation_only",
                "executed": False,
                "outside_plan": False,
                "stop_present": True,
            },
            {
                "risk_level": "high",
                "violated_rules": ["no_stop"],
                "guardrail_action": "block",
                "executed": True,
                "outside_plan": True,
                "stop_present": False,
                "user_override": True,
            },
            {
                "risk_level": "normal",
                "guardrail_action": "allow",
                "executed": True,
                "outside_plan": False,
                "stop_present": True,
            },
        ]
        result = prediction_replay_evaluation.evaluate_behavior(rows)

        self.assertEqual(3, result["behavior_event_count"])
        self.assertEqual(2, result["executed_count"])
        self.assertEqual(2, result["high_risk_attempt_count"])
        self.assertEqual(2, result["guarded_high_risk_count"])
        self.assertEqual(1, result["outside_plan_executed_count"])
        self.assertEqual(0.5, result["plan_adherence_rate"])
        self.assertEqual(0.5, result["no_stop_trade_rate"])
        self.assertEqual(1, result["override_count"])

    def test_cli_evaluation_reads_jsonl_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            prediction_path = tmp_path / "predictions.jsonl"
            outcome_path = tmp_path / "outcomes.jsonl"
            behavior_path = tmp_path / "behavior.jsonl"
            write_jsonl(
                prediction_path,
                [
                    {
                        "plan_id": "p1",
                        "base_rate": 0.50,
                        "base_rate_source": "replay",
                        "base_rate_sample_size": 30,
                        "success_probability": 0.50,
                        "failure_probability": 0.30,
                        "noise_probability": 0.20,
                        "expected_r": 0.40,
                    }
                ],
            )
            write_jsonl(outcome_path, [{"plan_id": "p1", "actual": "success", "result_r": 0.8}])
            write_jsonl(behavior_path, [{"risk_level": "high", "guardrail_action": "block"}])

            result = prediction_replay_evaluation.evaluate(prediction_path, outcome_path, behavior_path)
            markdown = prediction_replay_evaluation.render_markdown(result)

        self.assertIn("Binary success Brier", markdown)
        self.assertIn("Behavior-Risk Metrics", markdown)
        self.assertIn("does not prove live investment returns", markdown)


if __name__ == "__main__":
    unittest.main()
