import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "historical_policy_backtest.py"
SPEC = importlib.util.spec_from_file_location("historical_policy_backtest", MODULE_PATH)
historical_policy_backtest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = historical_policy_backtest
SPEC.loader.exec_module(historical_policy_backtest)


class HistoricalPolicyBacktestTests(unittest.TestCase):
    def test_daily_observations_identify_gap_chase_risk(self):
        bars = [
            historical_policy_backtest.DailyBar("2026-05-18", 10, 10, 10.2, 9.8, 1000, ma20=9.5),
            historical_policy_backtest.DailyBar("2026-05-19", 10.1, 10.4, 10.5, 10.1, 1000, ma20=9.7),
            historical_policy_backtest.DailyBar("2026-05-20", 10.8, 10.2, 11.0, 10.4, 1000, ma20=9.9),
            historical_policy_backtest.DailyBar("2026-05-21", 10.1, 10.5, 10.6, 10.0, 1000, ma20=10.0),
        ]

        observations = historical_policy_backtest.daily_observations(
            {"002156.SZ": bars},
            gap_threshold_pct=2.0,
            strong_close_threshold_pct=3.0,
            stop_loss_pct=2.5,
            target_pct=5.0,
            naive_expected_r=0.2,
        )

        self.assertEqual(2, observations["stock_days"])
        self.assertEqual(1, len(observations["opening_candidates"]))
        candidate = observations["opening_candidates"][0]
        self.assertTrue(candidate["gap_faded_by_close"])
        self.assertTrue(candidate["false_permission"])

    def test_summary_enforces_sample_thresholds(self):
        observations = {
            "stock_days": 10,
            "opening_candidates": [
                {
                    "false_permission": True,
                    "stop_hit": True,
                    "gap_faded_by_close": True,
                    "close_below_previous": False,
                    "result_r": -1.0,
                    "expected_r_error": -1.2,
                    "potential_valid_plan_proxy": False,
                    "confirmation_status": "unavailable",
                    "market_regime": "retreat",
                    "role": "follower_or_weak_proxy",
                }
            ],
            "overnight_candidates": [{"bad_next_open_gap": True}],
        }
        args = SimpleNamespace(
            start_date="2026-05-01",
            end_date="2026-05-21",
            min_stock_days=5000,
            min_opening_candidates=300,
            gap_threshold_pct=2.0,
            strong_close_threshold_pct=3.0,
            stop_loss_pct=2.5,
            target_pct=5.0,
            naive_expected_r=0.2,
            valid_plan_r_threshold=0.5,
        )

        summary = historical_policy_backtest.summarize_backtest(observations, args, ["002156.SZ"])

        self.assertFalse(summary["sample_sufficient"])
        self.assertEqual(1.0, summary["open_chase_false_permission_rate"])
        self.assertEqual(0.0, summary["current_policy_false_permission_rate_without_a2"])
        self.assertIn("below target", summary["product_decision"])
        self.assertEqual(0.0, summary["missed_valid_plan_proxy_rate"])
        self.assertIn("retreat", summary["market_regime_summary"])
        self.assertIn("follower_or_weak_proxy", summary["role_summary"])

    def test_confirmation_file_can_measure_0935_lift(self):
        bars = [
            historical_policy_backtest.DailyBar("2026-05-18", 10, 10, 10.2, 9.8, 1000, ma20=9.5),
            historical_policy_backtest.DailyBar("2026-05-19", 10.1, 10.4, 10.5, 10.1, 1000, ma20=9.7),
            historical_policy_backtest.DailyBar("2026-05-20", 10.8, 11.2, 11.4, 10.7, 1800, ma20=9.9),
            historical_policy_backtest.DailyBar("2026-05-21", 11.0, 10.9, 11.1, 10.7, 1100, ma20=10.0),
        ]
        confirmation = {
            ("2026-05-20", "002156.SZ"): historical_policy_backtest.ConfirmationRecord(
                date="2026-05-20",
                code="002156.SZ",
                price_0935=10.95,
                vwap_0935=10.9,
                sector_confirmed=True,
                role="core",
            )
        }

        observations = historical_policy_backtest.daily_observations(
            {"002156.SZ": bars},
            gap_threshold_pct=2.0,
            strong_close_threshold_pct=3.0,
            stop_loss_pct=2.5,
            target_pct=5.0,
            naive_expected_r=0.2,
            confirmation_by_key=confirmation,
        )
        candidate = observations["opening_candidates"][0]
        self.assertEqual("confirmed", candidate["confirmation_status"])
        self.assertIsNotNone(candidate["confirmation_result_r_daily_proxy"])

        args = SimpleNamespace(
            start_date="2026-05-01",
            end_date="2026-05-21",
            min_stock_days=1,
            min_opening_candidates=1,
            gap_threshold_pct=2.0,
            strong_close_threshold_pct=3.0,
            stop_loss_pct=2.5,
            target_pct=5.0,
            naive_expected_r=0.2,
            valid_plan_r_threshold=0.5,
        )
        summary = historical_policy_backtest.summarize_backtest(observations, args, ["002156.SZ"])
        self.assertEqual(1, summary["confirmation_sample_count"])
        self.assertEqual(1, summary["confirmation_confirmed_count"])
        self.assertIn("Confirmation lift", historical_policy_backtest.render_markdown(summary))

    def test_markdown_states_boundary(self):
        summary = {
            "date_range": {"start": "2024-01-01", "end": "2026-05-27"},
            "code_count": 100,
            "stock_days": 30000,
            "opening_candidate_count": 1200,
            "overnight_candidate_count": 900,
            "min_stock_days": 5000,
            "min_opening_candidates": 300,
            "sample_sufficient": True,
            "open_chase_false_permission_rate": 0.45,
            "open_chase_stop_hit_rate": 0.2,
            "open_chase_gap_fade_rate": 0.5,
            "open_chase_close_below_previous_rate": 0.3,
            "open_chase_mean_result_r": -0.1,
            "open_chase_median_result_r": -0.2,
            "mean_expected_r_error": -0.3,
            "mean_abs_expected_r_error": 0.8,
            "overnight_bad_gap_rate": 0.15,
            "current_policy_false_permission_rate_without_a2": 0.0,
            "current_policy_blocked_opening_candidates": 1200,
            "missed_valid_plan_proxy_rate": 0.1,
            "confirmation_sample_count": 0,
            "confirmation_confirmed_count": 0,
            "confirmation_failed_count": 0,
            "confirmation_lift_mean_result_r_daily_proxy": None,
            "market_regime_summary": {},
            "role_summary": {},
            "product_decision": "Sample sufficient for public guardrail backtest; keep A2-specific calibration separate.",
        }

        markdown = historical_policy_backtest.render_markdown(summary)

        self.assertIn("Historical Policy Backtest", markdown)
        self.assertIn("does not prove live investment alpha", markdown)
        self.assertIn("manual or licensed A2 samples", markdown)


if __name__ == "__main__":
    unittest.main()
