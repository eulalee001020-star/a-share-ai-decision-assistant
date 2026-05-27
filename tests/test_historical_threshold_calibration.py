import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "historical_threshold_calibration.py"
SPEC = importlib.util.spec_from_file_location("historical_threshold_calibration", MODULE_PATH)
historical_threshold_calibration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = historical_threshold_calibration
SPEC.loader.exec_module(historical_threshold_calibration)


class HistoricalThresholdCalibrationTests(unittest.TestCase):
    def test_summary_counts_threshold_days(self):
        result = {
            "dates": ["2026-05-20", "2026-05-21"],
            "auction_samples": [
                {"a1_core_coverage": 1.0, "a2_available": False, "b1_available": True, "avg_abs_open_gap_pct": 1.0, "avg_first_15m_range_pct": 2.0, "gap_up_fade_rate": 0.2},
                {"a1_core_coverage": 0.6, "a2_available": False, "b1_available": False, "avg_abs_open_gap_pct": 3.0, "avg_first_15m_range_pct": 4.0, "gap_up_fade_rate": 0.4},
            ],
            "tail_samples": [
                {"a1_core_coverage": 0.8, "b1_available": True, "avg_abs_tail_to_close_pct": 0.5, "avg_abs_next_open_gap_pct": 1.2},
                {"a1_core_coverage": 0.4, "b1_available": False, "avg_abs_tail_to_close_pct": 0.7, "avg_abs_next_open_gap_pct": 1.4},
            ],
            "observations_0928": [{"date": "2026-05-20"}],
            "observations_1430": [{"date": "2026-05-20"}, {"date": "2026-05-21"}],
        }
        summary = historical_threshold_calibration.summarize(result)
        self.assertEqual(2, summary["sample_days"])
        self.assertEqual(1, summary["a1_0928_days_ge_80"])
        self.assertEqual(1, summary["a1_1430_days_ge_80"])
        self.assertEqual(1, summary["b1_days_available"])
        self.assertEqual(0, summary["a2_days_available"])
        self.assertAlmostEqual(2.0, summary["avg_abs_open_gap_pct"])

    def test_markdown_mentions_a2_boundary(self):
        result = {
            "codes": ["002156.SZ"],
            "date_range": {"start": "2026-05-20", "end": "2026-05-21"},
            "dates": ["2026-05-20"],
            "auction_samples": [
                {
                    "date": "2026-05-20",
                    "a1_core_coverage": 1.0,
                    "a2_available": False,
                    "b1_available": True,
                    "limit_up_count": 61,
                    "limit_down_count": 22,
                    "avg_abs_open_gap_pct": 1.0,
                    "avg_first_15m_range_pct": 2.0,
                    "gap_up_fade_rate": 0.2,
                    "permission": "缺 A2：只允许 09:30-09:45 确认，禁止追强。",
                }
            ],
            "tail_samples": [
                {
                    "date": "2026-05-20",
                    "a1_core_coverage": 1.0,
                    "b1_available": True,
                    "limit_up_count": 61,
                    "limit_down_count": 22,
                    "avg_abs_tail_to_close_pct": 0.5,
                    "avg_abs_next_open_gap_pct": 1.2,
                    "permission": "A1+B1 可用时可输出尾盘计划；隔夜动作仍要给次日竞价验证条件。",
                }
            ],
            "observations_0928": [{"date": "2026-05-20"}],
            "observations_1430": [{"date": "2026-05-20"}],
        }
        markdown = historical_threshold_calibration.render_markdown(result)
        self.assertIn("A2 historical auction available", markdown)
        self.assertIn("Keep missing-A2 downgrade", markdown)
        self.assertIn("does not prove live alpha", markdown)


if __name__ == "__main__":
    unittest.main()
