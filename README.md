# bunq Banking MCP

A local [Model Context Protocol](https://modelcontextprotocol.io/) server for
bunq's production banking API. Browse the official API catalog, inspect exact
schemas, and read account balances, payments, and other supported resources.
Selected nonfinancial writes are available with explicit confirmation.

Authentication uses RSA request signing, installation/device registration, and
a renewable bunq session. Credentials and resumable API context stay in
[1Password CLI](https://developer.1password.com/docs/cli/), outside this repository.
This is an independent integration; it is not an official bunq product.

## Install and connect

Requires Python 3.11+, a POSIX system with `fcntl`, an authenticated `op` CLI
with read/write access to the chosen item, and a bunq production API key.

```sh
git clone https://github.com/samihalawa/bunq-banking-mcp.git
cd bunq-banking-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create a 1Password item containing a concealed field named `credential` with
your bunq API key. The server also writes a concealed `api_context` field into
that same item. This contains its private signing key and session state; retain
it across restarts. On first connection, the server registers an installation
and device with bunq. Your API key must permit the machine's IP address.

Register the server in Codex, replacing the example identifiers and paths:

```sh
codex mcp add bunq-banking \
  --env BUNQ_OP_ITEM_ID=YOUR_ITEM_ID \
  --env BUNQ_OP_VAULT_ID=YOUR_VAULT_ID \
  -- /absolute/path/bunq-banking-mcp/.venv/bin/python \
     /absolute/path/bunq-banking-mcp/server.py
```

Other MCP clients can use the same Python command, server path, and environment
variables. The server communicates over stdio and needs no public HTTP endpoint.
Start a new client session after registration, then call `connection_status`.
The separate [bunq documentation MCP](https://doc.bunq.com/~gitbook/mcp) can be
configured alongside this server.

Review bunq's [API terms](https://static.bunq.com/website/documents/bunq-terms-conditions-api-en.pdf)
and [authentication guide](https://doc.bunq.com/tutorials/your-first-payment/creating-the-api-context)
when setting up your integration.

## Plugin and finance skills

This repository is also a local desktop plugin. Its portable `plugin.json` and
`mcp.json` package the same six MCP tools with four reusable workflows:

- **expense-audit** reviews every charge and ranks evidence-backed personal, business and mixed-use savings without inferring tax deductibility.
- **bunq-banking** discovers schemas, reads complete collections, and verifies
  explicitly requested nonfinancial changes.
- **subscription-audit** reconciles all in-scope accounts and billing mailboxes,
  separating confirmed contracts, inferred recurrence, usage and historical items.
- **finance-reconciliation** reconciles spending, income, transfers, fees, refunds,
  currencies and balances with explicit evidence and coverage limits.

The `.codex-plugin/plugin.json` and `.mcp.json` files support older local hosts.
The portable root manifest remains canonical. These skills are reusable across
users; they contain no account identifiers, credentials or personal audit data.
The icon is an independent ledger graphic, not bunq branding.

The plugin needs a local executor with [`uv`](https://docs.astral.sh/uv/) and
authenticated `op` available on the host process's `PATH`. Its bundled MCP
configuration runs `uv run --no-project --isolated --no-env-file --python 3.11
--with-requirements requirements.txt python plugin_launcher.py` with absolute
package paths. This selects Python 3.11 and resolves the declared dependencies
in an isolated environment without installing them into the system interpreter
or relying on an unrelated virtual environment. The standalone virtual-environment
setup above remains an alternative for a raw MCP registration.

The first launch may download Python and packages through uv's configured
package sources; subsequent launches can reuse its dependency cache. Dependencies
and vault credentials are not bundled in the plugin archive. Launch and tool
discovery do not access the bank or vault; a bank-connected tool opens the
configured connection when invoked.
The vault CLI must support item reads and updates while preserving concealed
fields; retain the same item and `api_context` used by an existing connection.

Set `BUNQ_OP_ITEM_ID` and `BUNQ_OP_VAULT_ID` in the host's inherited environment.
Alternatively, create `~/.config/bunq-banking-mcp/settings.json` containing only
nonsecret references, replacing these placeholders:

```json
{
  "BUNQ_OP_ITEM_ID": "YOUR_ITEM_ID",
  "BUNQ_OP_VAULT_ID": "YOUR_VAULT_ID"
}
```

`plugin_launcher.py` loads this optional settings file before starting the same
server; inherited environment values take precedence. API keys, signing keys
and session tokens stay in the vault item, never in this file. An existing raw
MCP registration's per-server environment is not automatically inherited by a
separately installed plugin.

Use your client's local plugin marketplace or supported private-plugin import
flow to install this package. Register the repository root as the plugin source
and retain the included runtime files, schema and license notices. Discover the
six tools and call `connection_status` in the installed host to verify it.
Choose either the plugin connection or the standalone MCP registration for
active use, so tools are not duplicated. Removing a duplicate client registration
does not require deleting the vault item or enrolling another bunq device.

Email and other bank sources use whichever authenticated connectors are
available in the host; this package does not provide an email connector or
bundle a Finances app connection. Verify any optional aggregator's supported
countries, accounts, exposed tools and available history before using it.
Saving a private plugin or installing its skills does not deploy this local
process to web or mobile, establish bank authentication, or prove a complete
financial audit.

## Tools

1. `get_tool_catalog`: search and page through exact operation names,
   categories, availability, and exclusion reasons.
2. `learn_tools`: retrieve exact input and output schemas for up to 20 operations.
3. `execute_tool`: execute a modeled operation with validated path, query, and
   body arguments. The authenticated session supplies `userID`.
4. `connection_status`: verify a live account read without returning secrets.

5. `read_account_history`: exhaust Payment pages for one account and an inclusive-start, exclusive-end date window. Returns all selected records, undated exceptions, cursor coverage and explicit incomplete diagnostics; the page limit defaults to 100. It scans all exposed pages without assuming creation dates are sorted. Dates use the provider's `created` calendar date, without timezone conversion.
6. `review_financial_records`: review supplied Payment records with exact decimals, conservative reciprocal transfer pairing, separate currency totals, native card statuses and invoice line items. It fetches nothing and establishes no source completeness, business purpose, active contract or tax deduction. Cash totals include internal account legs and are labelled accordingly; they are not consolidated expenses. Blank descriptions can match only with reciprocal known accounts, exact opposite same-currency amounts, unique candidates in both directions and a two-second window. Explicit native FX markers also validate source amount and source/destination currencies. Matching basis and confidence are returned; evidence matching is not a provider-native transaction link.

Example `execute_tool` account read:

```json
{
  "name": "List_all_MonetaryAccount_for_User",
  "arguments": {"query": {"count": 200}}
}
```

Example transaction read; replace `123` with an account ID from the account list:

```json
{
  "name": "List_all_Payment_for_User_MonetaryAccount",
  "arguments": {"path": {"monetary-accountID": 123}, "query": {"count": 20}}
}
```

Collections return the provider's `Pagination` object. Follow the parameters in
`older_url` or `newer_url` through the same learned operation. A single page does
not establish complete history. Binary downloads return a content type and
base64 data. PNG, JPEG, and GIF uploads accept validated base64 content up to
10 MiB, a matching MIME type, and a description; the transport signs and sends
the decoded raw bytes.

## Coverage and write controls

The bundled official OpenAPI schema models 480 operations across 271 paths:
375 operations are enabled, including 227 reads and 148 nonfinancial writes.
The remaining 105 stay visible with explicit exclusion reasons. Exclusions
include payments, money movement, trading, financial automation, fee-bearing
creation, direct credential/session control, and sandbox-only operations.
These are catalog counts, not claims of live validation for every endpoint.
Provider permissions and resource availability still apply.

Enabled nonfinancial writes include modeled notes, categories, exports,
notifications, and profile metadata. They require an explicit request for the
specific action and `confirm_write=true`. The server reads back the affected
resource when a modeled GET endpoint exists. The caller must compare the
returned resource with the requested change before claiming verification.
When no matching read endpoint exists, the result states that verification
remains outstanding. Writes are never automatically replayed after a failure.

## Validation and limitations

```sh
.venv/bin/python -m unittest discover -v
```

Tests cover argument validation, user binding, pagination, operation exclusions,
exact-decimal currency totals, transfer pairing, conflicting/repeated pages, incomplete coverage, native card statuses, nested fee items, exact-byte signing, response-signature rejection, and read-only session retry
behavior. Live account reads have been exercised during development; the full
catalog and enabled write operations have not been individually live-tested.
The client targets production only. It does not infer subscriptions by itself;
callers can analyze payment histories and recurring resources while preserving
the distinction between provider records and inferred recurrence.

## License and schema provenance

Original integration code is licensed under [MIT](LICENSE).
`openapi.json` is derived from the official [bunq/doc schema](https://github.com/bunq/doc/blob/71d692fe22def76f88b0a41c62ac2bc530444f0b/swagger.json),
revision `71d692fe22def76f88b0a41c62ac2bc530444f0b`. Its schema license declaration and upstream repository
license notice are preserved separately; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
