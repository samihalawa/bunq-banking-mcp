import copy
import unittest

from finance import card_state, collect_pages, flatten_fee_items, review_payments


def page(records, older=None):
    return {"Response": [{"Payment": r} for r in records], "Pagination": {"older_url": older}}


def payment(identity, account=1, value="-0.10", currency="EUR", cp=9, created="2026-10-02 10:00:00", description="transfer"):
    return {"id": identity, "monetary_account_id": account, "amount": {"value": value, "currency": currency},
            "created": created, "description": description,
            "counterparty_alias": {"monetary_account_id": cp, "display_name": "Example"}}


class CollectionTests(unittest.TestCase):
    def test_exhausts_unsorted_pages_and_deduplicates_overlap(self):
        a, b = payment(1), payment(2, created="2026-09-01 10:00:00")
        c = payment(3, created="2026-10-03 10:00:00")
        calls = []
        def fetch(query):
            calls.append(query)
            return page([a, b], "/v1/user/7/payment?older_id=2&count=200") if len(calls) == 1 else page([b, c])
        result = collect_pages(fetch, "/user/7/payment", "2026-10-01", "2026-11-01")
        self.assertEqual([r["id"] for r in result["records"]], [1, 3])
        self.assertEqual(result["coverage"]["duplicates"], 1)
        self.assertTrue(result["coverage"]["complete"])
        self.assertEqual(len(calls), 2)

    def test_cursor_path_and_host_are_rejected(self):
        for url in ("/user/8/payment?older_id=2", "https://evil.example/user/7/payment?older_id=2",
                    "/user/7/payment?older_id=2&secret=3", "/user/7/payment?older_id=2&older_id=3"):
            result = collect_pages(lambda _: page([payment(1)], url), "/user/7/payment", "2026-10-01", "2026-11-01")
            self.assertFalse(result["coverage"]["complete"])
            self.assertIn("invalid_pagination_url", result["coverage"]["errors"])

    def test_failed_or_partial_history_is_explicit_and_retained(self):
        def fetch(query):
            if "older_id" in query:
                raise TimeoutError("not echoed")
            return page([payment(1)], "/user/7/payment?older_id=1")
        result = collect_pages(fetch, "/user/7/payment", "2026-10-01", "2026-11-01")
        self.assertEqual(len(result["records"]), 1)
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(result["coverage"]["resume_query"], {"older_id": 1})
        self.assertNotIn("not echoed", str(result))

    def test_repeated_cursor_conflict_undated_and_malformed_do_not_pass(self):
        variants = [lambda _: {"Response": []},
                    lambda _: page([{"id": 1}]),
                    lambda _: page([payment(1)], "/user/7/payment?older_id=1")]
        for fetch in variants:
            result = collect_pages(fetch, "/user/7/payment", "2026-10-01", "2026-11-01", 4)
            self.assertFalse(result["coverage"]["complete"])
        calls = iter([page([payment(1)], "/user/7/payment?older_id=1"), page([payment(1, value="-2")])])
        result = collect_pages(lambda _: next(calls), "/user/7/payment", "2026-10-01", "2026-11-01")
        self.assertIn("conflicting_duplicate_record", result["coverage"]["errors"])

    def test_window_is_inclusive_start_exclusive_end(self):
        rows = [payment(1, created="2026-10-01 00:00:00"), payment(2, created="2026-11-01 00:00:00")]
        result = collect_pages(lambda _: page(rows), "/user/7/payment", "2026-10-01", "2026-11-01")
        self.assertEqual([r["id"] for r in result["records"]], [1])
        with self.assertRaises(ValueError):
            collect_pages(lambda _: page([]), "/user/7/payment", "2026-11-01", "2026-10-01")


class ReviewTests(unittest.TestCase):
    def test_exact_decimal_and_currencies_never_mix(self):
        rows = [payment(1), payment(2, value="-0.20"), payment(3, currency="USD", value="-7.00")]
        result = review_payments(rows, [{"id": 1}])
        self.assertEqual(result["currency_cash_totals"]["EUR"]["outflows"], "0.30")
        self.assertEqual(result["currency_cash_totals"]["USD"]["outflows"], "7.00")
        self.assertTrue(all(r["purpose"] == "unknown" for r in result["rows"]))

    def test_only_unique_reciprocal_transfer_legs_pair(self):
        a, b = payment(1, cp=2, value="-8"), payment(2, account=2, cp=1, value="8")
        result = review_payments([a, b, payment(3, cp=2, value="-9")], [{"id": 1}, {"id": 2}])
        self.assertEqual([r["classification"] for r in result["rows"]],
                         ["paired_internal_transfer", "paired_internal_transfer", "owned_transfer_unmatched"])
        # Two plausible incoming legs are ambiguous; do not select one arbitrarily.
        duplicate_candidate = copy.deepcopy(b)
        duplicate_candidate["id"] = 4
        ambiguous = review_payments([a, b, duplicate_candidate], [{"id": 1}, {"id": 2}])
        self.assertTrue(all(r["transfer_pair"] is None for r in ambiguous["rows"]))

    def test_iban_identifies_owner_but_cross_currency_or_missing_leg_stays_unresolved(self):
        a = payment(1, cp=99)
        a["counterparty_alias"]["iban"] = "TEST-IBAN"
        accounts = [{"id": 1}, {"id": 2, "alias": [{"type": "IBAN", "value": "TEST-IBAN"}]}]
        result = review_payments([a, payment(2, account=2, cp=1, currency="GBP", value="0.10")], accounts)
        self.assertTrue(all(r["classification"] == "owned_transfer_unmatched" for r in result["rows"]))

    def test_account_identity_dedup_and_credits_not_automatically_refunds(self):
        a = payment(1, value="1.00")
        result = review_payments([a, copy.deepcopy(a), payment(1, account=2)], [{"id": 1}, {"id": 2}])
        self.assertEqual(result["coverage"]["unique_records"], 2)
        self.assertEqual(result["coverage"]["duplicates_removed"], 1)
        self.assertEqual(result["rows"][0]["classification"], "posted_credit_unclassified")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            review_payments([a, payment(1, value="2")], [{"id": 1}])

    def test_same_account_reversal_is_not_an_internal_transfer(self):
        result = review_payments([payment(1, cp=1), payment(2, cp=1, value="0.10")], [{"id": 1}])
        self.assertTrue(all(r["transfer_pair"] is None for r in result["rows"]))
        self.assertEqual(result["currency_cash_totals"]["EUR"]["unresolved_owned_outflows"], "0.10")

    def test_nonsettled_records_and_card_retries_are_not_cash(self):
        a = payment(1, value="-3000")
        a["status"] = "DECLINED"
        result = review_payments([a], [{"id": 1}])
        self.assertEqual(result["currency_cash_totals"], {})
        card = card_state({"id": 9, "payment_status": "DENIED", "settlement_status": "NOT_SETTLED", "status": "irrelevant"})
        self.assertEqual(card["payment_status"], "DENIED")
        self.assertFalse(card["included_in_payment_cash_totals"])
        self.assertNotIn("status", card)

    def test_invoice_items_preserve_fee_category_and_two_date_bases(self):
        result = flatten_fee_items([{"id": 4, "invoice_date": "2026-10-01", "created": "2026-09-30 23:00:00",
                                    "category": "SavingsWithdrawalFee", "status": "SETTLED",
                                    "group": [{"description": "Plan label", "item": [{"type_description": "Usage fee", "quantity": 3}]}]}])
        self.assertEqual(result[0]["category"], "SavingsWithdrawalFee")
        self.assertEqual(result[0]["quantity"], 3)
        self.assertNotEqual(result[0]["invoice_date"], result[0]["created"][:10])
        self.assertFalse(result[0]["cash_settlement_verified"])


if __name__ == "__main__":
    unittest.main()
