import copy
import unittest
from decimal import getcontext, localcontext

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


    def test_noninteger_page_limit_is_rejected_before_fetch(self):
        for limit in (True, 1.5, "2", None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                collect_pages(lambda _: self.fail("Invalid limit must not fetch"),
                              "/user/7/payment", "2026-10-01", "2026-11-01", limit)

    def test_false_numeric_cursor_does_not_prove_terminal_page(self):
        for cursor in (False, 0, [], {}):
            result = collect_pages(lambda _: page([payment(1)], cursor),
                                   "/user/7/payment", "2026-10-01", "2026-11-01")
            self.assertFalse(result["coverage"]["complete"])
            self.assertIn("invalid_pagination_url", result["coverage"]["errors"])

class ReviewTests(unittest.TestCase):
    def test_totals_keep_cents_beyond_ambient_decimal_precision(self):
        rows = [payment(1, value="9999999999999999999999999999.99"),
                payment(2, value="0.02"), payment(3, value="-0.12345678901234567890123456789")]
        with localcontext() as context:
            context.prec = 6
            result = review_payments(rows, [{"id": 1}])
            self.assertEqual(getcontext().prec, 6)
        totals = result["currency_cash_totals"]["EUR"]
        self.assertEqual(totals["inflows"], "10000000000000000000000000000.01")
        self.assertEqual(totals["outflows"], "0.12345678901234567890123456789")

    def test_large_reciprocal_transfer_keeps_exact_opposite_key(self):
        amount = "9999999999999999999999999999.99"
        result = review_payments([payment(1, cp=2, value="-" + amount),
                                  payment(2, account=2, cp=1, value=amount)],
                                 [{"id": 1}, {"id": 2}])
        self.assertTrue(all(r["classification"] == "paired_internal_transfer" for r in result["rows"]))

    def test_malformed_record_containers_have_argument_errors(self):
        for payments, accounts in [([None], [{"id": 1}]), ([], [None]),
                                   ([], [{"id": 1, "alias": [None]}])]:
            with self.subTest(payments=payments, accounts=accounts), self.assertRaises(ValueError):
                review_payments(payments, accounts)

    def test_decimal_overflow_is_an_explicit_argument_error(self):
        with self.assertRaisesRegex(ValueError, "exact-decimal range"):
            review_payments([payment(1, value="1E+1000000")], [{"id": 1}])

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

    def test_empty_descriptions_pair_only_within_two_seconds(self):
        accounts = [{"id": 1}, {"id": 2}]
        outgoing = payment(1, cp=2, value="-8", description="", created="2026-10-02 10:00:00.010000")
        incoming = payment(2, account=2, cp=1, value="8", description="", created="2026-10-02 10:00:00.090000")
        paired = review_payments([outgoing, incoming], accounts)
        self.assertTrue(all(r["classification"] == "paired_internal_transfer" for r in paired["rows"]))
        self.assertTrue(all(r["transfer_matching_basis"].endswith("empty_descriptions_2s") for r in paired["rows"]))
        self.assertTrue(all(r["transfer_matching_confidence"] == "high_record_match_not_provider_link" for r in paired["rows"]))
        incoming["created"] = "2026-10-02 10:00:02.010000"
        boundary = review_payments([outgoing, incoming], accounts)
        self.assertTrue(all(r["transfer_pair"] is not None for r in boundary["rows"]))
        incoming["created"] = "2026-10-02 10:00:02.010001"
        late = review_payments([outgoing, incoming], accounts)
        self.assertTrue(all(r["transfer_pair"] is None for r in late["rows"]))
        self.assertTrue(all(r["transfer_matching_basis"] == "unresolved_owned_counterparty" for r in late["rows"]))

    def test_empty_description_repeated_amount_is_ambiguous_in_both_directions(self):
        outgoing = payment(1, cp=2, value="-8", description="")
        incoming = payment(2, account=2, cp=1, value="8", description="")
        extra_incoming = copy.deepcopy(incoming)
        extra_incoming["id"] = 3
        result = review_payments([outgoing, incoming, extra_incoming], [{"id": 1}, {"id": 2}])
        self.assertTrue(all(r["transfer_pair"] is None for r in result["rows"]))

    def test_named_description_keeps_120_second_window_without_fallback(self):
        accounts = [{"id": 1}, {"id": 2}]
        outgoing = payment(1, cp=2, value="-8", description="named transfer")
        incoming = payment(2, account=2, cp=1, value="8", description="named transfer", created="2026-10-02 10:02:00")
        paired = review_payments([outgoing, incoming], accounts)
        self.assertTrue(all(r["transfer_matching_basis"].endswith("equal_named_description_120s") for r in paired["rows"]))
        incoming["created"] = "2026-10-02 10:02:00.000001"
        self.assertTrue(all(r["transfer_pair"] is None for r in review_payments([outgoing, incoming], accounts)["rows"]))
        incoming["created"] = outgoing["created"]
        for other_description in ("different transfer", ""):
            incoming["description"] = other_description
            self.assertTrue(all(r["transfer_pair"] is None for r in review_payments([outgoing, incoming], accounts)["rows"]))

    def test_empty_descriptions_cannot_pair_fx_or_unknown_accounts(self):
        outgoing = payment(1, cp=2, value="-8", description="")
        incoming = payment(2, account=2, cp=1, value="8", description="", currency="GBP")
        for accounts in ([{"id": 1}, {"id": 2}], [{"id": 1}]):
            result = review_payments([outgoing, incoming], accounts)
            self.assertTrue(all(r["transfer_pair"] is None for r in result["rows"]))

    def test_explicit_native_currency_conversion_pairs_and_preserves_cash_legs(self):
        marker = "Currency Conversion EUR-GBP (12.50)"
        outgoing = payment(1, cp=2, value="-12.50", description=marker)
        incoming = payment(2, account=2, cp=1, value="10.27", currency="GBP", description=marker,
                           created="2026-10-02 10:00:00.500000")
        outgoing["type"] = incoming["type"] = "BUNQ"
        result = review_payments([outgoing, incoming], [{"id": 1}, {"id": 2}])
        self.assertTrue(all(r["classification"] == "paired_internal_transfer" for r in result["rows"]))
        self.assertTrue(all(r["transfer_matching_basis"] == "explicit_currency_conversion_2s" for r in result["rows"]))
        self.assertEqual(result["currency_cash_totals"]["EUR"]["outflows"], "12.50")
        self.assertEqual(result["currency_cash_totals"]["GBP"]["inflows"], "10.27")
        self.assertTrue(all("exchange_rate" not in r and "fx_profit_loss" not in r for r in result["rows"]))

    def test_conversion_requires_exact_marker_types_currencies_and_source_amount(self):
        marker = "Currency Conversion EUR-GBP (12.50)"
        outgoing = payment(1, cp=2, value="-12.50", description=marker)
        incoming = payment(2, account=2, cp=1, value="10.27", currency="GBP", description=marker)
        outgoing["type"] = incoming["type"] = "BUNQ"
        cases = []
        for target, key, value in ((0, "amount", {"value": "-12.51", "currency": "EUR"}),
                                   (1, "amount", {"value": "10.27", "currency": "USD"}),
                                   (1, "amount", {"value": "12.50", "currency": "EUR"}),
                                   (1, "amount", {"value": "-10.27", "currency": "GBP"}),
                                   (0, "type", "CARD"), (1, "type", None),
                                   (1, "created", "2026-10-02 10:00:02.000001")):
            pair = copy.deepcopy([outgoing, incoming])
            pair[target][key] = value
            cases.append(pair)
        for bad_marker in ("", "Currency Conversion", "Currency Conversion EUR-GBP (12.50) trailing",
                           "Currency Conversion EUR-GBP (-12.50)", "Currency Conversion EUR-EUR (12.50)"):
            pair = copy.deepcopy([outgoing, incoming])
            pair[0]["description"] = pair[1]["description"] = bad_marker
            cases.append(pair)
        pair = copy.deepcopy([outgoing, incoming])
        pair[1]["description"] = "Currency Conversion EUR-GBP (12.500)"
        cases.append(pair)
        for pair in cases:
            with self.subTest(pair=pair):
                result = review_payments(pair, [{"id": 1}, {"id": 2}])
                self.assertTrue(all(r["transfer_pair"] is None for r in result["rows"]))

    def test_conversion_requires_unique_reciprocal_owned_accounts(self):
        marker = "Currency Conversion EUR-GBP (12.50)"
        outgoing = payment(1, cp=2, value="-12.50", description=marker)
        incoming = payment(2, account=2, cp=1, value="10.27", currency="GBP", description=marker)
        outgoing["type"] = incoming["type"] = "BUNQ"
        duplicate = copy.deepcopy(incoming)
        duplicate["id"] = 3
        ambiguous = review_payments([outgoing, incoming, duplicate], [{"id": 1}, {"id": 2}])
        self.assertTrue(all(r["transfer_pair"] is None for r in ambiguous["rows"]))
        unknown_owner = review_payments([outgoing, incoming], [{"id": 1}])
        self.assertTrue(all(r["transfer_pair"] is None for r in unknown_owner["rows"]))
        incoming["counterparty_alias"]["monetary_account_id"] = 9
        unreciprocated = review_payments([outgoing, incoming], [{"id": 1}, {"id": 2}])
        self.assertTrue(all(r["transfer_pair"] is None for r in unreciprocated["rows"]))

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
