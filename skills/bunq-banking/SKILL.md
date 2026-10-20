---
name: bunq-banking
description: Use when reading bunq accounts, balances, payments, invoices or other banking records, or performing an explicitly requested supported nonfinancial change through the bunq MCP.
---

# bunq banking

Use the connected bunq banking MCP for provider records. The separate GitBook documentation MCP explains the API and does not authenticate bank access. This plugin runs locally; it needs Python dependencies, authenticated `op`, and inherited `BUNQ_OP_ITEM_ID` and `BUNQ_OP_VAULT_ID`. Read the plugin README for setup. Never print or package credentials or API context.

For a broader financial question, first inventory every available authorized source: institutions and accounts, mailboxes and aliases, native provider billing records, existing statements/exports and invoices, and optional aggregator tools. Keep a coverage matrix in runtime memory with actual connectivity, requested/exposed window, pagination, inspected payloads and missing slices. Inspect every source relevant to the requested population; bunq is one bank source, not proof that all finances are covered. Use the other bundled skills for that broader reconciliation.

1. Bind the requested account scope, resource, date window, output and action. Reads are the default. Call `connection_status` once when connection health is unknown; reuse a working session and its persisted installation/device context.
2. Discover exact names with `get_tool_catalog`, paging the catalog where needed. Batch `learn_tools` for the relevant operations before constructing arguments. Respect availability and exclusions; do not invent endpoints or use an arbitrary HTTP fallback. `userID` comes from the authenticated session.
3. Use `execute_tool` with the learned schema. For collections, enumerate every in-scope account and resource page. Follow provider `Pagination.older_url` parameters through the same learned operation, validating that its path still matches that collection. Do not forward an arbitrary URL. Preserve counts, cursor, earliest/latest dates and unavailable slices in runtime memory. A terminal page proves only the history the API exposes.
4. Read nested status, refunds, card links and invoice line items when they affect the answer. Resource IDs and display invoice numbers can differ; use the native ID. Keep payment and card representations linked instead of counting both as purchases. For rate limits, use current bunq guidance and the literal retry delay; resume at the failed page without replaying successful reads.
5. Report native values, currencies, timestamp meaning and source identifiers. Separate catalog support, authentication, a successful operation and full resource coverage. For subscription or spending analysis, apply the other bundled skills.

## Nonfinancial changes

Only execute a supported write when the user has requested that exact action and target. Learn its schema, inspect current state, and supply `confirm_write=true`. The flag records action authority; it does not create authority. Keep audits read-only. Payments, money movement, trading and other excluded operations remain disabled. Never enable them, route around an exclusion, or automatically replay a write after failure.

Compare the returned readback with the requested fields and target. When no modeled readback exists, inspect an appropriate related collection or provider UI and state any remaining verification gap. An accepted response alone is not verified completion. Preserve unrelated fields and concurrent edits. Connection setup may persist session state in the configured vault item; do not reset or re-enroll a working context.
