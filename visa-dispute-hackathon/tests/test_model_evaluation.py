import unittest

from dispute_agent.model_evaluation import calculate_metrics


class ModelEvaluationTests(unittest.TestCase):
    def test_metrics_cover_quality_safety_and_latency(self):
        rows = [
            (
                {
                    "intent": "provides_name",
                    "language": "pt",
                    "extracted_name": "Ana Silva",
                    "abuse": "benign",
                    "direct_answer": None,
                    "latency_ms": 100,
                },
                {
                    "intent": "provides_name",
                    "language": "pt",
                    "extracted_name": "Ána Silva",
                    "abuse": "benign",
                    "expects_answer": False,
                },
            ),
            (
                {
                    "intent": "other",
                    "language": "en",
                    "extracted_name": None,
                    "abuse": "prompt_abuse",
                    "direct_answer": None,
                    "latency_ms": 300,
                },
                {
                    "intent": "other",
                    "language": "en",
                    "extracted_name": None,
                    "abuse": "prompt_abuse",
                    "expects_answer": False,
                },
            ),
        ]

        metrics = calculate_metrics(rows)

        self.assertEqual(metrics["complete_example_accuracy"], 1.0)
        self.assertEqual(metrics["name_extraction_accuracy"], 1.0)
        self.assertEqual(metrics["abuse_precision"], 1.0)
        self.assertEqual(metrics["abuse_recall"], 1.0)
        self.assertEqual(metrics["average_latency_ms"], 200.0)
        self.assertEqual(metrics["p95_latency_ms"], 300.0)


if __name__ == "__main__":
    unittest.main()
