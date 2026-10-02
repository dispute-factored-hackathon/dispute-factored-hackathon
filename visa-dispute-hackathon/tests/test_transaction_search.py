import json
import unittest
from datetime import date

from dispute_agent.transaction_search import (
    TRANSACTION_COLUMNS,
    InsufficientTransactionCriteriaError,
    SQLiteTransactionSearchRepository,
    TransactionSearchCriteria,
)

CUSTOMER_ID = "SYNTHETIC-CUSTOMER-19"


class SQLiteTransactionSearchTests(unittest.TestCase):
    def setUp(self):
        self.repository = SQLiteTransactionSearchRepository(seed_customer_id=CUSTOMER_ID)

    def tearDown(self):
        self.repository.close()

    def test_sqlite_schema_matches_synthetic_transaction_columns(self):
        self.assertEqual(self.repository.schema_columns(), TRANSACTION_COLUMNS)

    def test_seed_contains_ten_fruits_with_varied_locations(self):
        result = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(merchant_query="fruit"),
        )

        self.assertEqual(len(result.transactions), 10)
        self.assertEqual(
            len({transaction.merchant_name for transaction in result.transactions}), 10
        )
        self.assertEqual(len({transaction.amount for transaction in result.transactions}), 10)
        self.assertEqual(
            len({transaction.transaction_country for transaction in result.transactions}),
            10,
        )
        self.assertEqual(
            len({transaction.transaction_city for transaction in result.transactions}),
            10,
        )

        searchable_text = " ".join(
            transaction.merchant_name or "" for transaction in result.transactions
        ).casefold()
        for fruit in (
            "lemon",
            "strawberry",
            "coconut",
            "passion fruit",
            "banana",
            "apple",
            "papaya",
            "peach",
            "grapes",
            "mango",
        ):
            with self.subTest(fruit=fruit):
                self.assertIn(fruit, searchable_text)

    def test_approximate_amount_retrieval_ranks_closest_candidate_first(self):
        result = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(approximate_amount=13.0, currency="USD"),
        )

        self.assertEqual(result.retrieved_count, 10)
        self.assertEqual(result.transactions[0].merchant_name, "Lemon Drop Market")
        self.assertGreater(
            result.ranked_transactions[0].score,
            result.ranked_transactions[1].score,
        )
        self.assertIn("customer_id = ?", result.sql)
        self.assertNotIn("13.0", result.sql)

        percentage_tolerance = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(approximate_amount=136.0),
        )
        self.assertEqual(
            percentage_tolerance.transactions[0].merchant_name,
            "Mango Gold Store",
        )

    def test_new_information_retrieves_and_reranks_top_one_again(self):
        broad = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(merchant_query="fruit"),
        )
        refined = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(
                merchant_query="fruit",
                approximate_amount=13.0,
                country="Argentina",
            ),
        )

        self.assertEqual(broad.transactions[0].merchant_name, "Mango Gold Store")
        self.assertEqual(refined.transactions[0].merchant_name, "Lemon Drop Market")
        self.assertEqual(
            refined.ranked_transactions[0].matched_fields, ("merchant", "amount", "country")
        )

    def test_results_are_limited_to_ten_and_scoped_to_authenticated_customer(self):
        owned = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(merchant_query="fruit"),
            limit=999,
        )
        other_customer = self.repository.search(
            "OTHER-SYNTHETIC-CUSTOMER",
            TransactionSearchCriteria(merchant_query="fruit"),
        )

        self.assertEqual(len(owned.transactions), 10)
        self.assertEqual(other_customer.transactions, ())
        self.assertTrue(
            all(transaction.customer_id == CUSTOMER_ID for transaction in owned.transactions)
        )

    def test_untrusted_search_text_is_bound_and_cannot_change_query_scope(self):
        attack = "%' OR 1=1; DROP TABLE transactions; --"
        result = self.repository.search(
            CUSTOMER_ID,
            TransactionSearchCriteria(merchant_query=attack),
        )

        self.assertEqual(result.transactions, ())
        self.assertNotIn(attack, result.sql)
        self.assertEqual(self.repository.schema_columns(), TRANSACTION_COLUMNS)

    def test_search_requires_a_discriminative_voice_detail(self):
        with self.assertRaises(InsufficientTransactionCriteriaError):
            self.repository.search(
                CUSTOMER_ID,
                TransactionSearchCriteria(currency="USD", channel="POS"),
            )

    def test_criteria_validation_and_corrections_preserve_prior_context(self):
        original = TransactionSearchCriteria.from_mapping(
            {"merchant_query": "lemon", "date_from": "2026-09-01"}
        )
        correction = TransactionSearchCriteria.from_mapping(
            {"merchant_query": "mango", "approximate_amount": 125}
        )
        merged = original.merged_with(correction)

        self.assertEqual(merged.merchant_query, "mango")
        self.assertEqual(merged.approximate_amount, 125)
        self.assertEqual(merged.date_from, date(2026, 9, 1))

        with self.assertRaisesRegex(ValueError, "date_from cannot be after date_to"):
            TransactionSearchCriteria.from_mapping(
                {"date_from": "2026-10-01", "date_to": "2026-09-01"}
            )

    def test_criteria_can_remove_selected_filters_without_touching_others(self):
        criteria = TransactionSearchCriteria.from_mapping(
            {
                "merchant_query": "lemon",
                "approximate_amount": 13,
                "currency": "USD",
            }
        )

        updated = criteria.without(("merchant_query", "currency"))

        self.assertIsNone(updated.merchant_query)
        self.assertIsNone(updated.currency)
        self.assertEqual(updated.approximate_amount, 13)
        self.assertEqual(updated.active_filters(), (("approximate_amount", 13.0),))

    def test_criteria_rejects_unknown_filter_removal(self):
        with self.assertRaisesRegex(ValueError, "unsupported transaction filter"):
            TransactionSearchCriteria(merchant_query="lemon").without(("customer_id",))

    def test_metrics_report_latency_and_counts_without_search_values(self):
        with self.assertLogs("dispute_agent.transaction_search", level="INFO") as captured:
            self.repository.search(
                CUSTOMER_ID,
                TransactionSearchCriteria(merchant_query="private synthetic merchant"),
            )

        payload = json.loads(captured.records[-1].getMessage())
        self.assertEqual(payload["event"], "transaction.search.completed")
        self.assertEqual(payload["result_count"], 0)
        self.assertEqual(payload["retrieved_count"], 10)
        self.assertGreaterEqual(payload["latency_ms"], 0)
        self.assertNotIn("private synthetic merchant", captured.output[-1])

    def test_regional_fruit_and_location_terms_are_searchable(self):
        portuguese = TransactionSearchCriteria.from_mapping({"merchant_query": "limão"})
        spanish = TransactionSearchCriteria.from_mapping({"merchant_query": "manzana"})
        mexico = TransactionSearchCriteria.from_mapping({"country": "México"})

        lemon = self.repository.search(CUSTOMER_ID, portuguese)
        apple = self.repository.search(CUSTOMER_ID, spanish)
        mexican_transaction = self.repository.search(CUSTOMER_ID, mexico)

        self.assertEqual(lemon.transactions[0].merchant_name, "Lemon Drop Market")
        self.assertEqual(apple.transactions[0].merchant_name, "Apple Orchard Store")
        self.assertEqual(len(mexican_transaction.transactions), 1)
        self.assertEqual(mexican_transaction.transactions[0].transaction_country, "Mexico")


if __name__ == "__main__":
    unittest.main()
