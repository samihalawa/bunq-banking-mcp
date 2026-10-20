---
name: finance-reconciliation
description: Use when reconciling spending, income, cash flow, fees, invoices, transfers, refunds and balances across bunq accounts, statements and billing evidence.
---

# Finance reconciliation

Reconcile records for the requested accounts, currencies, entities, date window and deliverable. Keep this workflow read-only. It does not make payments, move money, trade, provide investment advice or change account settings.

Begin with an inventory of **all available authorized sources**: institutions/accounts, mailboxes/aliases, native provider billing records, existing statements/exports, invoice repositories and optional aggregator tools. Keep a runtime coverage matrix with source identity, actual connection state, requested/exposed window, pagination, nested payloads inspected and unavailable slices. Inspect every source relevant to the requested population; no single bank, aggregator, mailbox or familiar vendor list establishes full coverage. Use supported access recovery where available and report any exact missing slice.

Discover configured sources yourself. Include accounting, loan or investment records when relevant to the specific question, without broadening unrelated audits. Check available in-scope native provider records even if other evidence seems decisive. Present a source-coverage table showing each relevant source, connection status, requested/exposed period, inspected records/payloads and remaining gaps.

## Select evidence for the question

Use bank settlement records for actual cash movements and balances; provider invoices and billing accounts for products, billing periods and current obligations; emails for receipts, renewals, cancellations and payment-failure chronology. Statements or accounting exports can fill unavailable API history and support balance reconciliation. Previous reports are discovery leads. Optional aggregators, including Finances when available, require live account and history verification and must not duplicate the same bank feed.

Discover and enumerate the complete requested account population. Apply the bundled bunq-banking skill for exact operations, all pagination and nested payloads. Read broad relevant billing email evidence across all in-scope mailboxes and aliases with supported connectors, fully paging and inspecting action-changing bodies and attachments. Use the subscription-audit skill when current recurring commitments are part of the question. Record missing sources and the actual earliest/latest data rather than substituting a convenient window.

## Build reconciled records in runtime memory

1. Preserve native transaction/invoice IDs, account and counterparty identity, original and settlement currency/amount, booking/value timestamps, status, references and evidence links. Choose and state the date basis and timezone. Do not output raw keys or API context. Retain fetched pages and cursors rather than repeatedly downloading the same corpus.
2. Deduplicate overlapping payment, card, aggregator and statement representations. Match conservatively by native linkage first, then references, amount/currency and time; retain uncertain matches explicitly. Distinguish authorizations, pending items, declined attempts, reversals, completed refunds and settled charges. Never subtract a pending chargeback as cash received.
3. Pair transfers between owned accounts, including FX legs and any separate fee. Exclude paired internal transfers from consolidated income and expense while retaining each account's cash movements. Unmatched transfers stay unresolved. Identify card funding and debt repayments to avoid counting the original purchase twice. Never assume every incoming transfer is earned revenue.
4. Separate consumer/business expenses, subscriptions, variable compute/usage, advertising, credit top-ups, bank service fees, interest, taxes and merchant refunds only where evidence supports the label. A repeated savings-withdrawal fee is usage, not a subscription. Invoice issuance, due balance and payment settlement are different events; match receipts to obligations without erasing open or disputed items.
5. Keep currencies separate unless a supported conversion is needed. Use recorded settlement FX for historical spending, disclose a dated rate for estimates, and do not add different currencies directly. Use exact decimal arithmetic, state refund treatment and totals' inclusion rules, and round only for presentation.

## Verify and deliver

For each account/currency, compare opening balance plus settled inflows minus settled outflows with closing balance using consistent boundaries. Reconcile named discrepancies against pending movements, fees, FX, missing history and date differences; do not invent balancing entries. Consolidate only after internal-transfer and duplicate checks.

Present the requested spending, income or cash-flow view with reconciled totals, source-backed exceptions and unresolved amounts. Distinguish actual historical cash flow, current balances, invoiced liabilities, recurring run rate and projected renewals. Forecasts must state assumptions and uncertainty. State account/window coverage, unavailable history and whether balances reconcile. Use the user's existing canonical artifact when editing is requested; do not create an incidental tracker or private export. A correct sample or matching subtotal does not establish full coverage.
