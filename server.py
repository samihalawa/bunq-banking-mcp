"""Local bunq banking MCP; official schema, vault-backed authentication."""
import uuid
import base64

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import BunqClient, BunqError, connection_lock
from registry import Registry
from finance import collect_pages, review_payments, card_state, flatten_fee_items

registry = Registry()
mcp = FastMCP("bunq-banking", instructions=(
    "Discover exact operation names with get_tool_catalog, then batch learn_tools for schemas. "
    "Use execute_tool with the learned arguments. userID is bound to the authenticated session. "
    "Pagination is explicit: follow Pagination.older_url parameters using the same operation; "
    "one page is not complete history. Money movement and trading are disabled. "
    "Nonfinancial mutations require confirm_write=true and an explicit user request for that action. "
    "Use connection_status to check authentication. Never treat an unverified write as completed."
))
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


@mcp.tool(annotations=READ)
def get_tool_catalog(search: str = "", category: str | None = None,
                     cursor: int = 0, limit: int = 25) -> dict:
    """STEP 1: Browse the official bunq operations. Do not guess operation names. Includes availability and exclusions."""
    return registry.catalog(search, category, cursor, limit)


@mcp.tool(annotations=READ)
def learn_tools(names: list[str]) -> dict:
    """STEP 2: Learn exact argument schemas and availability for up to 20 official operation names together."""
    return {"operations": registry.learn(names)}


@mcp.tool(annotations=READ)
def connection_status() -> dict:
    """Verify the vault-backed production connection by reading the authenticated user's monetary accounts."""
    try:
        with connection_lock():
            client = BunqClient()
            client.connect()
            payload = client.call("GET", f"/user/{client.state['user_id']}/monetary-account", query={"count": 1})
            return {"connected": True, "environment": "production", "user_id": client.state["user_id"],
                    "user_type": client.state.get("user_type"), "account_read_verified": "Response" in payload,
                    "credentials": "1Password", "money_movement_enabled": False}
    except (BunqError, ValueError, KeyError) as error:
        return failure(error)


@mcp.tool(annotations=READ)
def read_account_history(account_id: int, start_date: str, end_date: str,
                         page_limit: int = 100) -> dict:
    """Read all exposed Payment pages for one account; ISO dates use [start,end).

    Returns every selected payment, exact cursor coverage and incomplete errors.
    Provider created dates are used without timezone conversion. A page limit or
    missing history never counts as complete. Does not read other banks or cards.
    """
    try:
        # Validate dates before opening the bank connection.
        from datetime import date
        if date.fromisoformat(end_date) <= date.fromisoformat(start_date):
            raise ValueError("end_date must follow start_date")
        if isinstance(account_id, bool) or account_id <= 0:
            raise ValueError("account_id must be positive")
        if isinstance(page_limit, bool) or not 1 <= page_limit <= 10000:
            raise ValueError("page_limit must be in 1..10000")
        with connection_lock():
            client = BunqClient()
            client.connect()
            name = "List_all_Payment_for_User_MonetaryAccount"
            prepared = registry.prepare(name, {"path": {"monetary-accountID": account_id},
                                               "query": {"count": 200}}, client.state["user_id"])
            def fetch(query):
                return client.call(**{**prepared, "query": query})
            result = collect_pages(fetch, prepared["path"], start_date, end_date, page_limit)
            for payment in result["records"] + result["undated_records"]:
                payment["monetary_account_id"] = account_id
            return {"ok": True, "account_id": account_id,
                    "application_url": "https://web.bunq.com", **result}
    except (BunqError, ValueError, KeyError) as error:
        return failure(error)


@mcp.tool(annotations=READ)
def review_financial_records(payments: list[dict], own_accounts: list[dict],
                             card_actions: list[dict] | None = None,
                             invoices: list[dict] | None = None) -> dict:
    """Review supplied records locally with exact decimals and conservative transfers.

    Every payment needs monetary_account_id and id. This tool fetches no history,
    proves no source completeness, makes no tax or active-subscription inference,
    and never adds card attempts or invoice totals to settled Payment cash totals.
    """
    try:
        return {"ok": True, **review_payments(payments, own_accounts),
                "card_evidence": [card_state(c) for c in (card_actions or [])],
                "invoice_items": flatten_fee_items(invoices or [])}
    except (ValueError, KeyError, TypeError) as error:
        return failure(error)


def failure(error):
    return {"ok": False, "error": {"code": "BUNQ_ERROR" if isinstance(error, BunqError) else "INVALID_ARGUMENTS",
            "message": str(error), "retryable": isinstance(error, BunqError) and error.status in (429, 500, 502, 503),
            "correlation_id": str(uuid.uuid4())}}


def readback(client, prepared, result):
    """Inspect the affected native resource without replaying a mutation."""
    path = prepared["path"]
    if prepared["method"] == "POST":
        ids = [v.get("id", v.get("uuid")) for row in result.get("Response", [])
               for v in row.values() if isinstance(v, dict) and ("id" in v or "uuid" in v)]
        if ids:
            path += "/" + str(ids[0])
    # Use only a modeled GET path, never invent a readback endpoint.
    import re
    matching = any(o["method"] == "GET" and o["available"] and
                   re.fullmatch(re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(o["path"])), path)
                   for o in registry.operations.values())
    if not matching:
        return {"verified": False, "reason": "No modeled read endpoint for this response; use provider UI or related collection"}
    try:
        data = client.call("GET", path)
        return {"read_completed": True, "path": path, "data": data,
                "deletion_verified": False if prepared["method"] == "DELETE" else None}
    except BunqError as error:
        if prepared["method"] == "DELETE" and error.status == 404:
            return {"verified": True, "deletion_verified": True, "path": path}
        return {"verified": False, "path": path, "error": str(error)}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                     idempotentHint=False, openWorldHint=True))
def execute_tool(name: str, arguments: dict, confirm_write: bool = False) -> dict:
    """STEP 3: Execute one learned, validated operation. Nonfinancial writes need explicit action authority and confirm_write=true."""
    try:
        op = registry._get(name)
        if not op["available"]:
            raise ValueError(op["unavailable_reason"])
        if op["method"] != "GET" and not confirm_write:
            raise ValueError("Nonfinancial write requires confirm_write=true and explicit user authority for this action")
        with connection_lock():
            client = BunqClient()
            client.connect()
            prepared = registry.prepare(name, arguments, client.state["user_id"])
            if op.get("binary_upload"):
                prepared.pop("binary_upload", None)
                upload = prepared["body"]
                prepared["body"] = base64.b64decode(upload["data_base64"], validate=True)
                prepared["content_type"] = upload["content_type"]
                prepared["attachment_description"] = upload["description"]
            result = client.call(**prepared)
            outcome = {"ok": True, "operation": name, "user_id": client.state["user_id"],
                    "method": prepared["method"], "data": result,
                    "write_readback_required": prepared["method"] != "GET",
                    "application_url": "https://web.bunq.com"}
            if prepared["method"] != "GET":
                outcome["readback"] = readback(client, prepared, result)
            return outcome
    except (BunqError, ValueError, KeyError) as error:
        return failure(error)


if __name__ == "__main__":
    mcp.run(transport="stdio")
