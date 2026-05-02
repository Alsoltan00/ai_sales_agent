import unittest

from merchant.ai_training.quality_evaluator import (
    ReleaseGateThresholds,
    compare_with_baseline,
    compute_classification_metrics,
    evaluate_message_flow,
    validate_release_gate,
)


class QualityEvaluatorTests(unittest.TestCase):
    def test_compute_classification_metrics(self):
        y_true = ["greeting", "product_query", "product_query", "out_of_scope"]
        y_pred = ["greeting", "product_query", "out_of_scope", "out_of_scope"]

        metrics = compute_classification_metrics(y_true, y_pred)

        self.assertEqual(metrics["samples"], 4)
        self.assertAlmostEqual(metrics["accuracy"], 0.75, places=4)
        self.assertIn("product_query", metrics["per_label"])
        self.assertGreater(metrics["macro_f1"], 0.0)

    def test_evaluate_message_flow(self):
        records = [
            {
                "expected_label": "greeting",
                "predicted_label": "greeting",
                "hallucinated": False,
                "column_leakage": False,
                "success": True,
                "latency_ms": 1200,
            },
            {
                "expected_label": "product_query",
                "predicted_label": "product_query",
                "hallucinated": False,
                "column_leakage": False,
                "success": True,
                "latency_ms": 2200,
            },
            {
                "expected_label": "product_query",
                "predicted_label": "out_of_scope",
                "hallucinated": True,
                "column_leakage": True,
                "success": False,
                "latency_ms": 9000,
            },
        ]

        result = evaluate_message_flow(records)

        self.assertEqual(result["samples"], 3)
        self.assertAlmostEqual(result["hallucination_rate"], 1 / 3, places=4)
        self.assertAlmostEqual(result["column_leakage_rate"], 1 / 3, places=4)
        self.assertAlmostEqual(result["success_rate"], 2 / 3, places=4)
        self.assertIn("p95", result["latency_ms"])

    def test_compare_with_baseline(self):
        baseline = {
            "classification": {"macro_f1": 0.72},
            "success_rate": 0.90,
            "hallucination_rate": 0.08,
            "column_leakage_rate": 0.04,
            "latency_ms": {"p95": 9200},
        }
        current = {
            "classification": {"macro_f1": 0.83},
            "success_rate": 0.95,
            "hallucination_rate": 0.03,
            "column_leakage_rate": 0.01,
            "latency_ms": {"p95": 7800},
        }

        delta = compare_with_baseline(current, baseline)

        self.assertAlmostEqual(delta["delta_macro_f1"], 0.11, places=4)
        self.assertAlmostEqual(delta["delta_success_rate"], 0.05, places=4)
        self.assertAlmostEqual(delta["delta_hallucination_rate"], -0.05, places=4)
        self.assertAlmostEqual(delta["delta_column_leakage_rate"], -0.03, places=4)
        self.assertAlmostEqual(delta["delta_p95_latency_ms"], -1400.0, places=2)

    def test_validate_release_gate_pass(self):
        metrics = {
            "classification": {"macro_f1": 0.91},
            "hallucination_rate": 0.01,
            "column_leakage_rate": 0.0,
            "success_rate": 0.99,
            "latency_ms": {"p95": 6200},
        }

        gate = validate_release_gate(metrics)
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["failures"], [])

    def test_validate_release_gate_fail(self):
        metrics = {
            "classification": {"macro_f1": 0.70},
            "hallucination_rate": 0.07,
            "column_leakage_rate": 0.02,
            "success_rate": 0.90,
            "latency_ms": {"p95": 11000},
        }
        thresholds = ReleaseGateThresholds(
            min_macro_f1=0.85,
            max_hallucination_rate=0.02,
            max_column_leakage_rate=0.0,
            min_success_rate=0.98,
            max_p95_latency_ms=8000,
        )

        gate = validate_release_gate(metrics, thresholds)
        self.assertFalse(gate["passed"])
        self.assertGreaterEqual(len(gate["failures"]), 4)


if __name__ == "__main__":
    unittest.main()
