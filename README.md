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

## Tools

1. `get_tool_catalog`: search and page through exact operation names,
   categories, availability, and exclusion reasons.
2. `learn_tools`: retrieve exact input and output schemas for up to 20 operations.
3. `execute_tool`: execute a modeled operation with validated path, query, and
   body arguments. The authenticated session supplies `userID`.
4. `connection_status`: verify a live account read without returning secrets.

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
exact-byte signing, response-signature rejection, and read-only session retry
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
