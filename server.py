"""Local bunq banking MCP; official schema, vault-backed authentication."""
import uuid
import base64

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import BunqClient, BunqError, connection_lock
from registry import Registry

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
