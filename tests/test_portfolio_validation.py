import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "portfolio_validation.py"
SPEC = importlib.util.spec_from_file_location("portfolio_validation", MODULE_PATH)
portfolio_validation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = portfolio_validation
SPEC.loader.exec_module(portfolio_validation)


class PortfolioValidationTests(unittest.TestCase):
    def test_public_guardrail_cases_all_pass(self):
        results = portfolio_validation.evaluate_all()
        summary = portfolio_validation.aggregate(results)
        self.assertEqual(30, summary["case_count"])
        self.assertEqual(summary["case_count"], summary["passed_count"])
        self.assertEqual(1.0, summary["score_rate"])

    def test_missing_auction_layer_blocks_chasing(self):
        case = next(item for item in portfolio_validation.CASES if item["id"] == "DV-003")
        result = portfolio_validation.evaluate_case(case)
        self.assertTrue(result.passed)
        self.assertIn("no_chase", result.derived_controls)
        self.assertIn("opening_confirmation_only", result.derived_controls)

    def test_rumor_case_requires_no_source_no_claim(self):
        case = next(item for item in portfolio_validation.CASES if item["id"] == "RG-003")
        result = portfolio_validation.evaluate_case(case)
        self.assertTrue(result.passed)
        self.assertIn("rumor_not_fact", result.derived_controls)
        self.assertIn("no_source_no_claim", result.derived_controls)


if __name__ == "__main__":
    unittest.main()
