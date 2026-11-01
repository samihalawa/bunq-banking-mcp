# bunq Banking MCP privacy information

This independent integration is maintained by Sami Halawa and runs locally. It is not an official bunq product. Requested account and resource operations are sent to bunq's production API. Selected nonfinancial changes are available through the operation catalog; payment, money-movement and trading operations are excluded by the bundled registry.

The client reads your API credential and resumable API context from a 1Password item using the authenticated local `op` CLI. The API context includes a private signing key and session state and is written back to that vault item for reuse. Initial connection can register an installation and device with bunq. Optional local settings contain only vault/item references; inherited environment values can also supply those references. The code keeps active request and session state in process memory.

Account records and other requested API results are returned to the invoking client or assistant. The included finance skills can also use separately connected email or bank tools when available; this package does not supply those connectors. This local package does not include a publisher-operated collection endpoint or a hosted banking account.

The package does not impose a deletion schedule on the vault item, bunq records, host conversations or saved analysis. Uninstalling it does not revoke the bunq API key, remove the registered device or delete vault context. Manage those records through bunq, 1Password and the assistant host. Each service applies its own data practices.

For package questions, use this repository's support link. Do not include API keys, signing keys, vault context or private bank records in public issues.
