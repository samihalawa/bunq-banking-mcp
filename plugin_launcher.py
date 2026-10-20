"""Start the plugin using inherited settings or optional local item references."""
import json
import os
from pathlib import Path


def configure():
    settings_path = Path.home() / ".config" / "bunq-banking-mcp" / "settings.json"
    if not settings_path.exists():
        return
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("bunq plugin settings.json must contain a JSON object")
    allowed = {"BUNQ_OP_ITEM_ID", "BUNQ_OP_VAULT_ID"}
    if set(settings) - allowed:
        raise ValueError("bunq plugin settings.json accepts only vault and item references")
    for name, value in settings.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"bunq plugin setting {name} must be a nonempty string")
        os.environ.setdefault(name, value)


if __name__ == "__main__":
    configure()
    from server import mcp

    mcp.run(transport="stdio")
