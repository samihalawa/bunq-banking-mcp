---
name: expense-audit
description: "Use when reviewing every charge and finding savings across personal, business and mixed spending, including one-off purchases, usage bills and recurring contracts."
---

# Every-charge review

Apply finance-reconciliation first and subscription-audit for current contracts. Keep financial actions read-only. A request for recommendations or a plugin improvement does not authorize cancellations, returns, payment changes or money movement.

## Cover the requested population

State an explicit start/end date, booking timezone and account/entity scope. Reuse already fetched records and inspected evidence; expand missing slices instead of restarting the audit. Enumerate every accessible account, including closed accounts with in-window activity, and page each relevant collection. A pending invitation is a separately reported excluded account. Search results, a dashboard balance, one page, a monthly aggregate and an installed aggregator do not prove transaction coverage.

When asked to go deeper, identify the previous audit's unresolved amounts, missing time slices, uninspected attachments and current contract gaps first. Expand to earlier exposed bank history and annual evidence when useful, retaining the original window as a labelled comparison. Continue only missing cursors, deduplicate by account/native ID, and recheck the expanded balance boundaries. Prioritize unresolved records by amount and decision impact; repeating the same top vendors with more prose is not a deeper audit. Give the incremental record count and which uncertainties were actually resolved.

When the user requests **all charges**, retain one review row per unique settled payment with native account/payment IDs, date, merchant/reference, signed amount and currency, evidence, classification, confidence, recommendation and unresolved question. Keep credits and transfers visible in separate classes so every source row is accounted for. Include unfamiliar merchants and small charges. Summaries must reconcile to the detailed rows, with exact amounts and separate currencies. Do not substitute a top-vendor list for the requested ledger.

Use read_account_history for paginated payment reads and review_financial_records for conservative initial classifications. Treat returned incomplete coverage, missing timestamps, conflicting IDs or unmatched owned transfers as unresolved; the helper is not proof of all-bank coverage. Card actions and invoices enrich payment rows and are not extra settled spending. Export private records only within the user's requested deliverable; never put them in plugin source, fixtures, logs, screenshots or releases.

## Explain each charge

Classify **cash-flow type**, **personal/business purpose**, and **contract status** separately. Use personal, business, mixed or unknown with supporting evidence. A business-named account, software merchant or VAT invoice alone does not establish business use or Spanish tax deductibility. For shared use, leave the allocation unresolved until supported. Distinguish a possible reduction in expenses from a possible tax deduction; a deduction is not a euro-for-euro refund.

For every debit, choose an evidenced action: keep with reason; compare/reprice; reduce seats/plan; cap variable usage; consolidate an overlapping service; investigate; seek a possible refund; or monitor a dated renewal. Give a concrete next step and conditional savings where justified. Unknown merchants get an investigation action rather than an invented product. Review credits as completed credits, unidentified receipts or possible refunds, not negative subscriptions.

Cover bank fees, debt/overdraft costs, insurance, telecom, utilities, housing, transport, groceries/delivery, professional services, advertising, cloud/AI usage, domains, annual memberships and one-off hardware where records support them. Review payment rails or funding intermediaries as possible transfers, not automatic consumption. Separate cash withdrawals from the spending they may later fund.

For business acquisition costs (ads, teaching-listing boosts, freelancer credits and marketplace listings), distinguish one-off exposure, credit funding, recurring seats and actual metered use. Evaluate attributable paying customers and contribution margin before recommending a cut; website visits or applications are not revenue. Separate investment purchases, sales proceeds and dividends from consumption and earned work revenue. Bank cash differences alone do not establish investment profit/loss, current holdings or tax treatment.

## Use savings estimates honestly

Rank recommendations by evidenced avoidable cost, disruption and certainty. Keep realized savings, conditional future savings, one-time recoveries and tax questions separate. Do not add overlapping alternatives. Never carry a historical variable usage bill forward as a fixed monthly saving. Annual equivalents are budgeting figures, not monthly debits; next renewal amount and renewal status require evidence.

Read [evidence pitfalls](../finance-reconciliation/references/evidence-pitfalls.md) before interpreting fees, app-store purchases, migrations, usage bills, consolidated arrears, cancellations, refunds or utility changes. Finish with the detailed ledger, reconciled summaries, prioritized opportunities and exact coverage gaps. Reuse the existing canonical report when present.
