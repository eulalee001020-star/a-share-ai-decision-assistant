import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "trading_assistant.py"
SPEC = importlib.util.spec_from_file_location("trading_assistant", MODULE_PATH)
trading_assistant = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = trading_assistant
SPEC.loader.exec_module(trading_assistant)


class TradingAssistantTests(unittest.TestCase):
    def test_main_board_filter(self):
        self.assertTrue(trading_assistant.is_main_board_a_share("002428.SZ"))
        self.assertTrue(trading_assistant.is_main_board_a_share("600096.SH"))
        self.assertFalse(trading_assistant.is_main_board_a_share("300750.SZ"))
        self.assertFalse(trading_assistant.is_main_board_a_share("688981.SH"))
        self.assertFalse(trading_assistant.is_main_board_a_share("831000.BJ"))

    def test_market_code_normalization(self):
        self.assertEqual("sh600584", trading_assistant.sina_code("600584.SH"))
        self.assertEqual("sz002428", trading_assistant.tencent_code("002428.SZ"))
        self.assertEqual("600584.SH", trading_assistant.portfolio_style_code("sh600584"))
        self.assertEqual("002428.SZ", trading_assistant.portfolio_style_code("sz002428"))

    def test_current_portfolio_validates_with_expected_warning_only(self):
        data = trading_assistant.load_portfolio(ROOT)
        result = trading_assistant.validate_portfolio(data)
        self.assertEqual([], result.errors)
        self.assertTrue(any("短线合计仓位" in note for note in result.notes))

    def test_example_portfolio_is_valid_for_public_repo(self):
        example_path = ROOT / "config" / "portfolio.example.json"
        with example_path.open(encoding="utf-8") as fh:
            data = trading_assistant.json.load(fh)
        result = trading_assistant.validate_portfolio(data)
        self.assertEqual([], result.errors)
        self.assertLessEqual(float(data["total_position_pct"]), 50)

    def test_render_auction_packet_contains_core_sections(self):
        packet = trading_assistant.render_run_packet(ROOT, "auction", "2026-05-14")
        self.assertIn("# A股助手运行包｜2026-05-14｜09:28 竞价预测与开盘计划", packet)
        self.assertIn("## 4. 风控发动机与市场状态", packet)
        self.assertIn("持仓止损风险测算", packet)
        self.assertIn("## 8. 运行前必须补齐的数据", packet)
        data = trading_assistant.load_portfolio(ROOT)
        sample_name = data["positions"][0]["name"]
        self.assertIn(sample_name, packet)
        self.assertIn("Auction Prediction Prompt", packet)
        self.assertIn("docs/prediction_automation_system.md", packet)
        self.assertNotIn("09:10 早盘", packet)

    def test_stop_risk_estimate(self):
        data = trading_assistant.load_portfolio(ROOT)
        candidate = next(
            item for item in data["positions"]
            if trading_assistant.estimate_position_stop_risk(item)
        )
        metrics = trading_assistant.estimate_position_stop_risk(candidate)
        self.assertIsNotNone(metrics)
        assert metrics is not None
        plan = candidate["risk_plan"]
        reference = float(plan["reference_price"])
        stop = float(plan["stop_price_for_sizing"])
        expected_distance = (reference - stop) / reference * 100
        expected_loss = float(candidate["current_position_pct"]) * expected_distance / 100
        self.assertAlmostEqual(metrics["stop_distance_pct"], expected_distance, places=2)
        self.assertAlmostEqual(metrics["account_loss_pct"], expected_loss, places=2)

    def test_expected_r_calculation(self):
        expected = trading_assistant.calculate_expected_r(
            success_probability=0.4,
            failure_probability=0.35,
            target_r=2,
            noise_probability=0.25,
            noise_cost_r=0.2,
        )
        self.assertAlmostEqual(expected, 0.40, places=2)

    def test_prediction_template_rows_include_positions_and_watchlist(self):
        rows = trading_assistant.prediction_template_rows(ROOT, "2026-05-14", "auction")
        data = trading_assistant.load_portfolio(ROOT)
        sample_code = trading_assistant.portfolio_style_code(data["positions"][0]["code"])
        self.assertTrue(any(row["code"] == sample_code for row in rows))
        self.assertTrue(any(row["source_type"] == "watchlist" for row in rows))
        self.assertTrue(all("success_probability" in row for row in rows))
        self.assertTrue(all("plan_id" in row for row in rows))
        self.assertTrue(all("base_rate_source" in row for row in rows))
        self.assertTrue(all("base_rate_sample_size" in row for row in rows))

    def test_manual_auction_template_contains_a2_fields(self):
        payload = trading_assistant.manual_auction_template(ROOT, "2026-05-14")
        self.assertIn("market", payload)
        data = trading_assistant.load_portfolio(ROOT)
        sample_code = trading_assistant.portfolio_style_code(data["positions"][0]["code"])
        self.assertTrue(any(item["code"] == sample_code for item in payload["stocks"]))
        sample = payload["stocks"][0]
        self.assertIn("auction_amount_cny", sample)
        self.assertIn("post_0920_cancel_signal", sample)
        self.assertIn("seal_amount_cny", sample)

    def test_data_health_degrades_without_collector_coverage(self):
        health = trading_assistant.assess_data_health(
            ROOT,
            "2099-01-01",
            "1430",
            "tail",
        )
        self.assertEqual("C", health["grade"])
        self.assertIn("A1报价/分时/均线覆盖>=80%", health["missing_decision_data"])


if __name__ == "__main__":
    unittest.main()
