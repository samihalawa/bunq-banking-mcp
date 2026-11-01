"""Read-only, exact-decimal financial evidence helpers. No persistence or credentials."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, Inexact, InvalidOperation, localcontext
import re
from urllib.parse import parse_qs, urlparse


def _day(value):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("Missing or invalid created date")
    return date.fromisoformat(value[:10])


def _path(value):
    return value[3:] if value.startswith("/v1/") else value


def collect_pages(fetch, path: str, start_date: str, end_date: str,
                  page_limit: int = 100) -> dict:
    """Fetch a collection to its terminal page; date bounds are [start, end).

    fetch(query) must return the native bunq payload. No sort-order assumption is
    made. Incomplete results retain successful records and an exact resume query;
    they must never be presented as complete history.
    """
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if (end <= start or isinstance(page_limit, bool) or not isinstance(page_limit, int)
            or not 1 <= page_limit <= 10000):
        raise ValueError("Require end_date > start_date and page_limit in 1..10000")
    if not path.startswith("/") or "?" in path or "#" in path or ".." in path:
        raise ValueError("Invalid collection path")
    query = {"count": 200}
    seen_queries, indexed, undated = set(), {}, []
    coverage = {"requested_start": start_date, "requested_end_exclusive": end_date,
                "date_basis": "provider created date", "pages": 0,
                "complete": False, "duplicates": 0, "errors": []}
    while coverage["pages"] < page_limit:
        fingerprint = tuple(sorted(query.items()))
        if fingerprint in seen_queries:
            coverage["errors"].append("repeated_pagination_cursor")
            break
        seen_queries.add(fingerprint)
        try:
            payload = fetch(dict(query))
        except Exception as exc:
            coverage["errors"].append("fetch_failed:" + type(exc).__name__)
            break
        if (not isinstance(payload, dict) or not isinstance(payload.get("Response"), list)
                or not isinstance(payload.get("Pagination"), dict)):
            coverage["errors"].append("malformed_collection_payload")
            break
        coverage["pages"] += 1
        malformed = False
        for wrapped in payload["Response"]:
            if (not isinstance(wrapped, dict) or len(wrapped) != 1
                    or not isinstance(next(iter(wrapped.values())), dict)):
                coverage["errors"].append("malformed_collection_record")
                malformed = True
                break
            record = next(iter(wrapped.values()))
            identity = record.get("id")
            if not isinstance(identity, (str, int)) or isinstance(identity, bool) or identity == "":
                coverage["errors"].append("missing_record_identity")
                malformed = True
                break
            key = str(identity)
            if key in indexed:
                if indexed[key] != record:
                    coverage["errors"].append("conflicting_duplicate_record")
                    malformed = True
                    break
                coverage["duplicates"] += 1
                continue
            indexed[key] = record
            try:
                _day(record.get("created"))
            except (ValueError, TypeError):
                undated.append(record)
                coverage["errors"].append("record_without_valid_created_date")
        if malformed:
            break
        older = payload["Pagination"].get("older_url")
        if older is None or older == "":
            coverage["complete"] = not coverage["errors"]
            query = None
            break
        try:
            if not isinstance(older, str):
                raise ValueError
            parsed = urlparse(older)
            if (parsed.scheme not in ("", "https") or parsed.netloc not in ("", "api.bunq.com")
                    or parsed.fragment or _path(parsed.path) != _path(path)):
                raise ValueError
            values = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
            if not values or not set(values) <= {"count", "older_id", "newer_id"}:
                raise ValueError
            if "older_id" not in values or "newer_id" in values:
                raise ValueError
            if any(len(v) != 1 or not v[0].isascii() or not v[0].isdigit() for v in values.values()):
                raise ValueError
            next_query = {k: int(v[0]) for k, v in values.items()}
            if "count" in next_query and not 1 <= next_query["count"] <= 200:
                raise ValueError
            query = next_query
        except (ValueError, TypeError):
            coverage["errors"].append("invalid_pagination_url")
            break
    else:
        coverage["errors"].append("page_limit_reached")
    dated = [(r, _day(r["created"])) for r in indexed.values() if r not in undated]
    coverage.update(records_scanned=len(indexed), selected=sum(start <= d < end for _, d in dated),
                    earliest_created=min((r["created"] for r, _ in dated), default=None),
                    latest_created=max((r["created"] for r, _ in dated), default=None),
                    resume_query=query, undated_count=len(undated))
    return {"records": [r for r, d in dated if start <= d < end],
            "undated_records": undated, "coverage": coverage}


def _money(value):
    if not isinstance(value, dict) or not isinstance(value.get("currency"), str) or not value["currency"]:
        raise ValueError("An amount requires value and currency")
    try:
        number = Decimal(str(value["value"]))
    except (KeyError, InvalidOperation):
        raise ValueError("Invalid exact-decimal amount") from None
    if not number.is_finite():
        raise ValueError("Amount must be finite")
    return number, value["currency"]


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError, AttributeError):
        return None


def _fx_role(row):
    """Recognize only the full native BUNQ conversion marker and currency role."""
    description = row["description"]
    marker = re.fullmatch(r"Currency Conversion ([A-Z]{3})-([A-Z]{3}) \(([0-9]+(?:\.[0-9]+)?)\)",
                          description) if isinstance(description, str) else None
    if row["type"] != "BUNQ" or not marker:
        return None
    source, destination, amount = marker.groups()
    expected, value = Decimal(amount), Decimal(row["amount"])
    if source == destination or expected <= 0:
        return None
    if row["currency"] == source and value == -expected:
        return "source"
    if row["currency"] == destination and value > 0:
        return "destination"
    return None


def review_payments(payments: list[dict], own_accounts: list[dict]) -> dict:
    """Keep every unique account/payment row and pair only reciprocal transfers.

    Pass records from the Payment collection, not card authorizations. Business
    purpose and contract status remain unknown until supported by other evidence.

    Pairing is an evidence-based record match, not a provider-supplied transfer
    link. Both legs must uniquely identify reciprocal owned accounts, have the
    same currency and exact opposite nonzero amounts, and have equal descriptions.
    Equal nonempty descriptions allow a 120-second timestamp difference; two
    empty descriptions allow only 2 seconds. Explicit FX pairs additionally
    require BUNQ type, the same full native "Currency Conversion SRC-DST (amount)"
    marker, the source debit matching that amount/currency and a positive credit
    in the destination currency within 2 seconds. Both directions must remain
    unique. Other FX and ambiguous candidates stay unresolved. Both currency cash
    legs remain; no exchange rate or FX profit/loss is invented. Each row states
    the matching basis and confidence.
    """
    if (not isinstance(payments, list) or not all(isinstance(p, dict) for p in payments)
            or not isinstance(own_accounts, list)
            or not all(isinstance(a, dict) for a in own_accounts)):
        raise ValueError("Payments and own_accounts must be lists of records")
    for account in own_accounts:
        aliases = account.get("alias", [])
        if not isinstance(aliases, list) or not all(isinstance(a, dict) for a in aliases):
            raise ValueError("Account aliases must be a list of records")
    amounts = [_money(payment.get("amount"))[0] for payment in payments]
    # Decimal construction preserves digits, but addition and unary negation use
    # the ambient precision. Cover the full input range plus a possible sum carry;
    # never silently round a cash total or a reciprocal-transfer lookup key.
    least_place = min((value.as_tuple().exponent for value in amounts), default=0)
    most_place = max((value.adjusted() for value in amounts), default=0)
    with localcontext() as context:
        context.prec = max(context.prec, most_place - min(0, least_place)
                           + len(str(max(1, len(amounts)))) + 2)
        context.traps[Inexact] = True
        try:
            return _review_payments(payments, own_accounts)
        except DecimalException:
            raise ValueError("Amounts exceed the supported exact-decimal range") from None


def _review_payments(payments: list[dict], own_accounts: list[dict]) -> dict:
    ids = {a["id"] for a in own_accounts}
    iban_accounts = defaultdict(set)
    for account in own_accounts:
        for alias in account.get("alias", []):
            if alias.get("type") == "IBAN" and alias.get("value"):
                iban_accounts[alias["value"]].add(account["id"])
    raw, rows, duplicates = {}, [], 0
    for payment in payments:
        account, identity = payment.get("monetary_account_id"), payment.get("id")
        if account is None or identity is None:
            raise ValueError("Payment needs monetary_account_id and id")
        key = (account, identity)
        if key in raw:
            if raw[key] != payment:
                raise ValueError("Conflicting duplicate payment identity")
            duplicates += 1
            continue
        raw[key] = payment
        value, currency = _money(payment.get("amount"))
        cp = payment.get("counterparty_alias") or {}
        if not isinstance(cp, dict):
            raise ValueError("Invalid counterparty alias")
        cp_id = cp.get("monetary_account_id")
        matches = iban_accounts.get(cp.get("iban"), set())
        if cp_id not in ids:
            cp_id = next(iter(matches)) if len(matches) == 1 else None
        state = payment.get("status")
        posted = state in (None, "", "SETTLED", "COMPLETED", "ACCEPTED")
        rows.append({"account_id": account, "payment_id": identity,
                     "created": payment.get("created"), "amount": str(value), "currency": currency,
                     "merchant": cp.get("display_name") or cp.get("name") or "",
                     "description": payment.get("description") or "", "type": payment.get("type"),
                     "value_date": payment.get("value_date"),
                     "original_amount": payment.get("original_amount"),
                     "balance_after_mutation": payment.get("balance_after_mutation"),
                     "provider_status": state, "included_in_cash_totals": posted,
                     "classification": "owned_transfer_unmatched" if cp_id in ids else
                     "posted_debit" if posted and value < 0 else
                     "posted_credit_unclassified" if posted and value > 0 else
                     "zero_value" if posted else "unsettled_or_unknown_status",
                     "purpose": "unknown", "purpose_confidence": "unverified",
                     "recurring_status": "unverified", "counterparty_account_id": cp_id,
                     "transfer_pair": None,
                     "transfer_matching_basis": "unresolved_owned_counterparty" if cp_id in ids else "not_applicable",
                     "transfer_matching_confidence": "unverified" if cp_id in ids else "not_applicable",
                     "review": "Confirm purpose and receipt; merchant alone does not establish a contract or tax deduction."})
    candidates, fx_candidates = defaultdict(list), defaultdict(list)
    for i, row in enumerate(rows):
        if (row["counterparty_account_id"] in ids and row["counterparty_account_id"] != row["account_id"]
                and row["included_in_cash_totals"]):
            candidates[(row["account_id"], row["counterparty_account_id"], row["currency"],
                        Decimal(row["amount"]))].append(i)
            if _fx_role(row):
                fx_candidates[(row["account_id"], row["counterparty_account_id"], row["description"])].append(i)
    links = {}
    for i, row in enumerate(rows):
        amount = Decimal(row["amount"])
        if not amount or not row["included_in_cash_totals"]:
            continue
        when = _instant(row["created"])
        alternatives = []
        # Conversion markers use the stricter FX rule, never the generic named-description rule.
        conversion_marker = isinstance(row["description"], str) and row["description"].startswith("Currency Conversion ")
        normal_candidates = [] if conversion_marker else candidates.get(
            (row["counterparty_account_id"], row["account_id"], row["currency"], -amount), [])
        for j in normal_candidates:
            other = rows[j]
            at = _instant(other["created"])
            seconds = 120 if row["description"] else 2
            if (i != j and when and at and abs((when - at).total_seconds()) <= seconds
                    and row["description"] == other["description"]):
                alternatives.append(j)
        if len(alternatives) == 1:
            links[i] = alternatives[0]
        role = _fx_role(row)
        if role:
            alternatives = []
            for j in fx_candidates.get((row["counterparty_account_id"], row["account_id"], row["description"]), []):
                other, at = rows[j], _instant(rows[j]["created"])
                if (i != j and _fx_role(other) != role and when and at
                        and abs((when - at).total_seconds()) <= 2):
                    alternatives.append(j)
            if len(alternatives) == 1:
                links[i] = alternatives[0]
    for i, j in links.items():
        if links.get(j) == i:
            row, other = rows[i], rows[j]
            row["classification"] = "paired_internal_transfer"
            row["transfer_pair"] = {"account_id": other["account_id"], "payment_id": other["payment_id"]}
            row["transfer_matching_basis"] = ("explicit_currency_conversion_2s" if _fx_role(row) else
                "reciprocal_owned_accounts_exact_opposite_amount_same_currency_unique_both_directions_"
                + ("equal_named_description_120s" if row["description"] else "empty_descriptions_2s"))
            row["transfer_matching_confidence"] = "high_record_match_not_provider_link"
            row["review"] = "Reciprocal owned-account records matched on the stated basis. Exclude both legs from consolidated income and expense; retain account cash movements."
    for row in rows:
        if row["classification"] == "owned_transfer_unmatched":
            row["review"] = "Owned-account counterparty found; matching leg is unresolved. Do not treat as consumption."
    totals = defaultdict(lambda: {"inflows": Decimal(0), "outflows": Decimal(0),
                                  "external_unclassified_inflows": Decimal(0),
                                  "external_unclassified_outflows": Decimal(0),
                                  "unresolved_owned_inflows": Decimal(0),
                                  "unresolved_owned_outflows": Decimal(0),
                                  "paired_internal_legs": 0, "unresolved_owned_legs": 0})
    for row in rows:
        if not row["included_in_cash_totals"]:
            continue
        total, value = totals[row["currency"]], Decimal(row["amount"])
        total["inflows"] += max(value, Decimal(0))
        total["outflows"] += max(-value, Decimal(0))
        total["paired_internal_legs"] += row["classification"] == "paired_internal_transfer"
        total["unresolved_owned_legs"] += row["classification"] == "owned_transfer_unmatched"
        if row["classification"] == "owned_transfer_unmatched":
            total["unresolved_owned_inflows"] += max(value, Decimal(0))
            total["unresolved_owned_outflows"] += max(-value, Decimal(0))
        elif row["classification"] != "paired_internal_transfer":
            total["external_unclassified_inflows"] += max(value, Decimal(0))
            total["external_unclassified_outflows"] += max(-value, Decimal(0))
    return {"rows": rows, "coverage": {"input_records": len(payments), "unique_records": len(rows),
                                       "duplicates_removed": duplicates},
            "currency_cash_totals": {c: {k: str(v) if isinstance(v, Decimal) else v for k, v in t.items()}
                                     for c, t in totals.items()},
            "totals_basis": "All posted Payment cash legs, including internal transfers; not consolidated spending or revenue."}


def card_state(record: dict) -> dict:
    """Preserve native card states; authorization events never add to cash totals."""
    return {"id": record.get("id"),
            **{key: record.get(key) for key in ("payment_status", "authorisation_status",
                                               "settlement_status", "clearing_status")},
            "included_in_payment_cash_totals": False}


def flatten_fee_items(invoices: list[dict]) -> list[dict]:
    """Expose invoice category and nested items separately from bank settlement."""
    rows = []
    for invoice in invoices:
        for group_index, group in enumerate(invoice.get("group", [])):
            for item_index, item in enumerate(group.get("item", [])):
                rows.append({"invoice_id": invoice.get("id"), "invoice_date": invoice.get("invoice_date"),
                             "created": invoice.get("created"), "status": invoice.get("status"),
                             "category": invoice.get("category"), "group_index": group_index,
                             "item_index": item_index, "group_description": group.get("description"),
                             "label": item.get("type_description"), "quantity": item.get("quantity"),
                             "total_vat_inclusive": item.get("total_vat_inclusive"),
                             "classification": "invoice_item_unverified",
                             "cash_settlement_verified": False})
    return rows
