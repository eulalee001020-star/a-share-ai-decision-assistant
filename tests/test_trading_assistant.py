import importlib.util
import json
import sys
import tempfile
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

    def test_etf_filter_allows_portfolio_instruments(self):
        self.assertTrue(trading_assistant.is_exchange_traded_fund("159611.SZ"))
        self.assertTrue(trading_assistant.is_exchange_traded_fund("588060.SH"))
        self.assertTrue(trading_assistant.is_allowed_portfolio_instrument("159201.SZ"))
        self.assertFalse(trading_assistant.is_allowed_portfolio_instrument("300750.SZ"))

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
        self.assertIn("docs/opening_permission_model.md", packet)
        self.assertIn("docs/prediction_automation_system.md", packet)
        self.assertNotIn("09:10 早盘", packet)

    def test_stop_risk_estimate(self):
        candidate = {
            "current_position_pct": 12,
            "risk_plan": {
                "reference_price": 10,
                "stop_price_for_sizing": 9,
            },
        }
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

    def test_opening_confirmation_signal_from_0935_metrics(self):
        metrics = trading_assistant.enrich_quote_metrics(
            {
                "price": 10.4,
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "vwap": 10.2,
                "target_price": 10.3,
                "target_vwap": 10.1,
            }
        )

        self.assertEqual("confirmed", metrics["opening_confirmation_signal"])
        self.assertAlmostEqual(3.0, metrics["target_vs_open_pct"], places=2)

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
        self.assertEqual("tail_defensive_only", health["action_permission_ceiling"]["code"])
        self.assertIn("stable_data_readiness", health)

    def test_decision_weights_sum_to_one_hundred(self):
        weights = trading_assistant.load_decision_weights(ROOT)
        total = sum(item["weight"] for item in weights["primary_weights"].values())

        self.assertEqual("2026-05-28-stable-data-permission", weights["version"])
        self.assertEqual(100, total)
        self.assertIn("a2_auction_early_permission", weights["optional_modifiers"])

    def test_render_user_packet_contains_requested_targets(self):
        packet = trading_assistant.render_run_packet(
            ROOT,
            "user",
            "2026-05-27",
            requested_themes=["半导体", "AI硬件"],
            requested_codes=["002156.SZ", "300750.SZ"],
        )
        self.assertIn("用户给定板块/个股/持仓综合分析", packet)
        self.assertIn("## 7A. 用户输入分析对象", packet)
        self.assertIn("| 半导体 |", packet)
        self.assertIn("002156.SZ", packet)
        self.assertIn("300750.SZ", packet)
        self.assertIn("不符合沪深主板-only", packet)
        self.assertIn("边界解决机制", packet)
        self.assertIn("User Request Analysis Prompt", packet)

    def test_render_market_flow_packet_contains_1430_sections(self):
        packet = trading_assistant.render_run_packet(ROOT, "market-flow", "2026-06-02")

        self.assertIn("# A股助手运行包｜2026-06-02｜14:30 大盘资金流向与观察机会", packet)
        self.assertIn("14:30 Market Flow And Opportunity Scan Prompt", packet)
        self.assertIn("13:05 到 14:30", packet)
        self.assertIn("reports/{YYYY-MM-DD}-1430-market-flow-opportunity-scan.md", packet)
        self.assertEqual(
            ROOT / "reports" / "2026-06-02-1430-market-flow-run.md",
            trading_assistant.output_path_for(ROOT, "market-flow", "2026-06-02"),
        )

    def test_data_health_user_mode_has_user_permission_text(self):
        health = trading_assistant.assess_data_health(
            ROOT,
            "2099-01-01",
            "1430",
            "user",
        )
        self.assertEqual("C", health["grade"])
        self.assertIn("手动核验表", health["permission"])

    def test_auction_health_without_a2_allows_only_opening_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            coverage_path = Path(tmp) / "coverage.json"
            coverage_path.write_text(
                json.dumps(
                    {
                        "coverage": {
                            "code_count": 1,
                            "quote_count": 1,
                            "minute_count": 1,
                            "daily_metric_count": 1,
                            "market_activity": {"limit_up_pool_count": 10},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            missing_auction_path = Path(tmp) / "missing-auction.json"
            health = trading_assistant.assess_data_health(
                ROOT,
                "2099-01-01",
                "0935",
                "auction",
                coverage_path=coverage_path,
                auction_path=missing_auction_path,
            )

        self.assertEqual("B", health["grade"])
        self.assertTrue(health["opening_confirmation_ok"])
        self.assertFalse(health["early_chase_ok"])
        self.assertIn("确认前禁止追强", health["permission"])
        self.assertEqual("opening_confirmation_only", health["action_permission_ceiling"]["code"])
        self.assertIn("09:28_chase_strength", health["action_permission_ceiling"]["blocked_actions"])
        self.assertGreaterEqual(health["stable_data_readiness"]["score"], 90)

    def test_data_health_with_a2_allows_only_validated_early_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            coverage_path = Path(tmp) / "coverage.json"
            coverage_path.write_text(
                json.dumps(
                    {
                        "coverage": {
                            "code_count": 1,
                            "quote_count": 1,
                            "minute_count": 1,
                            "daily_metric_count": 1,
                            "market_activity": {"limit_up_pool_count": 10},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            auction_path = Path(tmp) / "auction.json"
            auction_path.write_text(
                json.dumps(
                    {
                        "stocks": [
                            {
                                "code": "002156.SZ",
                                "auction_price": 10.5,
                                "auction_amount_cny": 120000000,
                                "post_0920_cancel_signal": "benign",
                                "role_signal": "core",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            health = trading_assistant.assess_data_health(
                ROOT,
                "2099-01-01",
                "0928",
                "auction",
                coverage_path=coverage_path,
                auction_path=auction_path,
            )

        self.assertEqual("A", health["grade"])
        self.assertTrue(health["early_chase_ok"])
        self.assertEqual("auction_early_plan_with_0935_validation", health["action_permission_ceiling"]["code"])
        self.assertIn("skip_0935_validation", health["action_permission_ceiling"]["blocked_actions"])

    def test_auction_sample_summary_counts_a2_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_dir = root / "data" / "manual" / "auction"
            sample_dir.mkdir(parents=True)
            payload = {
                "date": "2026-05-27",
                "source": "manual test",
                "stocks": [
                    {
                        "code": "002156.SZ",
                        "auction_price": 10.0,
                        "auction_change_pct": 1.2,
                        "auction_amount_cny": 12000000,
                        "post_0920_cancel_signal": "benign",
                        "role_signal": "core",
                    },
                    {"code": "603920.SH", "role_signal": "unknown"},
                ],
            }
            (sample_dir / "2026-05-27.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            summary = trading_assistant.summarize_auction_samples(root)

        self.assertEqual(1, summary["sample_file_count"])
        self.assertEqual(2, summary["stock_row_count"])
        self.assertEqual(1, summary["usable_a2_row_count"])
        self.assertEqual(1, summary["complete_core_row_count"])

    def test_incomplete_or_zero_auction_core_is_not_a2(self):
        incomplete = {
            "stocks": [
                {
                    "code": "002156.SZ",
                    "auction_price": 10.0,
                    "auction_change_pct": 1.2,
                }
            ]
        }
        zero_placeholder = {
            "stocks": [
                {
                    "code": "002156.SZ",
                    "auction_price": 0,
                    "auction_amount_cny": 0,
                    "post_0920_cancel_signal": "unknown",
                    "role_signal": "unknown",
                }
            ]
        }

        self.assertFalse(trading_assistant.has_manual_auction_a2(incomplete))
        self.assertFalse(trading_assistant.has_manual_auction_a2(zero_placeholder))

    def test_auction_payload_from_csv_maps_core_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "portfolio.json").write_text(
                json.dumps(
                    {
                        "total_assets_cny": 1000000,
                        "total_position_pct": 0,
                        "cash_pct": 100,
                        "max_loss_per_trade_pct": 1,
                        "positions": [{"code": "002156.SZ", "name": "通富微电"}],
                        "watchlist": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            csv_path = root / "auction.csv"
            csv_path.write_text(
                "股票代码,竞价价,竞价成交额,09:20后撤单,板块角色\n"
                "002156,10.5,1.2亿,良性,中军\n",
                encoding="utf-8",
            )
            payload = trading_assistant.auction_payload_from_csv(
                root,
                "2026-05-27",
                csv_path,
                "test csv",
            )

        stock = payload["stocks"][0]
        self.assertEqual("002156.SZ", stock["code"])
        self.assertEqual(120000000, stock["auction_amount_cny"])
        self.assertEqual("benign", stock["post_0920_cancel_signal"])
        self.assertEqual("core", stock["role_signal"])
        self.assertTrue(trading_assistant.has_manual_auction_a2(payload))

    def test_auction_csv_template_includes_extra_sector_core_codes(self):
        rows = trading_assistant.auction_csv_template_rows(ROOT, "2026-05-27", ["603920.SH"])

        codes = {row["股票代码"] for row in rows}
        self.assertIn("603920.SH", codes)
        self.assertTrue(all("竞价成交额" in row for row in rows))

    def test_auction_calibration_compares_a2_and_no_a2_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prediction_dir = root / "reports" / "predictions"
            outcome_dir = root / "reports" / "outcomes"
            auction_dir = root / "data" / "manual" / "auction"
            prediction_dir.mkdir(parents=True)
            outcome_dir.mkdir(parents=True)
            auction_dir.mkdir(parents=True)
            (auction_dir / "2026-05-27.json").write_text(
                json.dumps(
                    {
                        "stocks": [
                            {
                                "code": "002156.SZ",
                                "auction_price": 10.5,
                                "auction_amount_cny": 120000000,
                                "post_0920_cancel_signal": "benign",
                                "role_signal": "core",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (prediction_dir / "2026-05-27-predictions.jsonl").write_text(
                json.dumps(
                    {
                        "plan_id": "a2",
                        "automation": "auction",
                        "code": "002156.SZ",
                        "action": "buy",
                        "expected_r": 0.4,
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "plan_id": "no-a2",
                        "automation": "auction",
                        "code": "603920.SH",
                        "action": "buy",
                        "expected_r": 0.2,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (outcome_dir / "2026-05-27-outcomes.jsonl").write_text(
                json.dumps(
                    {
                        "plan_id": "a2",
                        "actual": "failure",
                        "result_r": -1,
                        "false_permission": True,
                        "invalidated_at_0935": True,
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "plan_id": "no-a2",
                        "actual": "success",
                        "result_r": 1,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            summary = trading_assistant.auction_calibration_summary(root, "2026-05-27", "2026-05-27", min_a2_rows=1)

        self.assertEqual(1, summary["a2_complete_core_rows"])
        self.assertEqual(1, summary["groups"]["a2_confirmed"]["false_permission_count"])
        self.assertEqual(1, summary["groups"]["a2_confirmed"]["invalidated_0935_count"])
        self.assertEqual(1, summary["groups"]["no_a2"]["matched_count"])

    def test_outcome_and_behavior_templates_are_generated(self):
        outcomes = trading_assistant.outcome_template_rows(ROOT, "2026-05-14", "auction")
        behaviors = trading_assistant.behavior_template_rows(ROOT, "2099-01-01")

        self.assertTrue(outcomes)
        self.assertIn("actual", outcomes[0])
        self.assertIn("error_type", outcomes[0])
        self.assertIn("false_permission", outcomes[0])
        self.assertIn("invalidated_at_0935", outcomes[0])
        self.assertEqual(1, len(behaviors))
        self.assertIn("guardrail_action", behaviors[0])

    def test_message_evidence_template_and_summary_track_source_quality(self):
        payload = trading_assistant.message_evidence_template(
            "2026-05-27",
            codes=["002156.SZ"],
            themes=["半导体"],
        )
        payload["evidence"][0].update(
            {
                "source_name": "",
                "published_at": "2026-04-01",
                "stance": "positive",
                "is_rumor": True,
                "conflicts_with": ["risk-1"],
            }
        )
        summary = trading_assistant.summarize_message_evidence(payload, "2026-05-27")

        self.assertEqual(["002156.SZ"], payload["scope"]["codes"])
        self.assertEqual(1, summary["evidence_count"])
        self.assertEqual(1, summary["missing_source_count"])
        self.assertEqual(1, summary["stale_count"])
        self.assertEqual(1, summary["rumor_count"])
        self.assertEqual(1, summary["conflict_count"])

    def test_weekly_review_summarizes_logs_and_recommendations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prediction_dir = root / "reports" / "predictions"
            outcome_dir = root / "reports" / "outcomes"
            behavior_dir = root / "reports" / "behavior"
            prediction_dir.mkdir(parents=True)
            outcome_dir.mkdir(parents=True)
            behavior_dir.mkdir(parents=True)
            (prediction_dir / "2026-05-27-predictions.jsonl").write_text(
                json.dumps({"plan_id": "p1", "data_grade": "A"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (outcome_dir / "2026-05-27-outcomes.jsonl").write_text(
                json.dumps({"plan_id": "p1", "error_type": "scenario_error"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (behavior_dir / "2026-05-27-events.jsonl").write_text(
                json.dumps({"executed": True, "outside_plan": True, "stop_present": False}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            summary = trading_assistant.weekly_review_summary(root, "2026-05-27", "2026-05-27")

        self.assertEqual(1, summary["prediction_count"])
        self.assertEqual(1, summary["matched_count"])
        self.assertEqual(1, summary["outside_plan_executed"])
        self.assertEqual(1, summary["no_stop_executed"])
        self.assertIn("A", summary["data_grade_counts"])

    def test_weekly_review_does_not_count_blank_templates_as_completed_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prediction_dir = root / "reports" / "predictions"
            outcome_dir = root / "reports" / "outcomes"
            behavior_dir = root / "reports" / "behavior"
            prediction_dir.mkdir(parents=True)
            outcome_dir.mkdir(parents=True)
            behavior_dir.mkdir(parents=True)
            (prediction_dir / "2026-05-27-predictions.jsonl").write_text(
                json.dumps({"plan_id": "p1", "data_grade": "A"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (outcome_dir / "2026-05-27-auction-outcome-template.jsonl").write_text(
                json.dumps({"plan_id": "p1", "actual": "", "result_r": None, "error_type": ""}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (behavior_dir / "2026-05-27-behavior-template.jsonl").write_text(
                json.dumps({"plan_id": "p1", "attempted_action": "", "stop_present": True}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            summary = trading_assistant.weekly_review_summary(root, "2026-05-27", "2026-05-27")

        self.assertEqual(0, summary["outcome_count"])
        self.assertEqual(0, summary["matched_count"])
        self.assertEqual(0, summary["behavior_count"])

    def test_decision_brief_prioritizes_permissions(self):
        brief = trading_assistant.render_decision_brief(
            ROOT,
            "2099-01-01",
            "1430",
            "user",
        )
        self.assertIn("# 决策简报", brief)
        self.assertIn("数据等级：C", brief)
        self.assertIn("动作权限上限", brief)
        self.assertIn("最小下一步", brief)

    def test_sector_flow_csv_import_normalizes_external_board_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "sector_flow.csv"
            csv_path.write_text(
                "板块,方向,净流入,评分,来源,更新时间\n"
                "有色金属,承接,52.27亿,67,QMT截图,2026-06-02 14:30\n"
                "电子,退潮,-391.80亿,,PTrade导出,2026-06-02 14:30\n",
                encoding="utf-8",
            )
            payload = trading_assistant.sector_flow_payload_from_csv("2026-06-02", csv_path, "manual test")

        self.assertEqual(2, len(payload["records"]))
        self.assertEqual("inflow", payload["records"][0]["direction"])
        self.assertEqual(5227000000.0, payload["records"][0]["net_amount_cny"])
        self.assertEqual("outflow", payload["records"][1]["direction"])

    def test_manual_sector_flow_can_supply_b1_without_quote_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            reports_dir = root / "reports"
            sector_dir = root / "data" / "manual" / "sector_flow"
            config_dir.mkdir(parents=True)
            reports_dir.mkdir(parents=True)
            sector_dir.mkdir(parents=True)
            (config_dir / "portfolio.json").write_text((ROOT / "config" / "portfolio.json").read_text(encoding="utf-8"), encoding="utf-8")
            (reports_dir / "2026-06-02-1430-tail-data.json").write_text(
                json.dumps(
                    {
                        "coverage": {
                            "run_date": "2026-06-02",
                            "target_time": "1430",
                            "code_count": 1,
                            "quote_count": 0,
                            "minute_count": 0,
                            "daily_metric_count": 0,
                        },
                        "rows": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (sector_dir / "2026-06-02.json").write_text(
                json.dumps(
                    {
                        "date": "2026-06-02",
                        "records": [
                            {
                                "sector": "有色金属",
                                "direction": "inflow",
                                "net_amount_cny": 5227000000.0,
                                "source": "manual",
                                "source_time": "2026-06-02 14:30",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            health = trading_assistant.assess_data_health(root, "2026-06-02", "1430", "tail")

        self.assertTrue(health["b1_ok"])
        self.assertTrue(health["manual_sector_flow_ok"])
        self.assertEqual("C", health["grade"])
        self.assertIn("A1报价/分时/均线覆盖>=80%", health["missing_decision_data"])


if __name__ == "__main__":
    unittest.main()
