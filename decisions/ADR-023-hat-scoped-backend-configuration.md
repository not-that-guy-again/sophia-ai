# ADR-023: Hat-scoped backend configuration

**Date:** 2026-03
**Status:** Accepted

## Context

ADR-022 introduces service interfaces and backend implementations. The question is where backend selection and configuration lives.

Three options were considered:

1. **Global config** — Environment variables like `ORDER_BACKEND=shopify` that apply to all Hats. Rejected because different Hats may need different backends (a customer service Hat talks to Shopify; a warehouse Hat talks to a WMS). Global config conflates concerns that should be domain-specific.

2. **Per-tool config** — Each tool declares its own backend. Rejected because multiple tools share a single service instance (e.g., `look_up_order`, `check_order_status`, and `cancel_order` all use `OrderService`). Configuring the backend per-tool leads to redundancy and inconsistency.

3. **Per-Hat config** — The Hat declares which backends to use for each service in `hat.json`. This aligns with the Hat system's design principle: domain expertise is pluggable, and the Hat owns all domain-specific configuration (tools, constraints, evaluator weights, prompts, and now backends).

## Decision

Backend configuration lives in the Hat manifest (`hat.json`) under a `backends` key. Each entry maps a service name to a provider identifier and a config dict:

```json
{
  "backends": {
    "order": {
      "provider": "mock",
      "config": {}
    },
    "shipping": {
      "provider": "shipstation",
      "config": {
        "api_key_env": "SHIPSTATION_API_KEY",
        "api_secret_env": "SHIPSTATION_API_SECRET"
      }
    }
  }
}
```

The `backends` block is optional. If omitted, all services default to `mock`. If partially specified, unspecified services also default to `mock`. This preserves backward compatibility — existing Hats without a `backends` block continue to work.

Config values ending in `_env` are resolved from environment variables at service initialization time. If the environment variable is not set, service initialization fails with a clear error. Secrets are never stored in `hat.json`.

The `HatManifest` Pydantic model is extended to validate the `backends` block. Unknown service names are rejected. Unknown provider names are rejected at initialization time (not at validation time, since third-party providers may be installed dynamically).

When `HatRegistry.equip()` is called, the `ServiceRegistry` is initialized from the Hat's backend config before tools are registered. When `HatRegistry.unequip()` is called or a new Hat replaces the current one, the `ServiceRegistry` tears down existing services (closing HTTP sessions, connection pools, etc.) before initializing new ones.

## Consequences

**Positive:**
- Backend config is co-located with all other Hat configuration, making Hats fully self-describing.
- Different Hats can use different backends without conflict.
- The `mock` default means no configuration is required for development and testing.
- Partial configuration is supported — you can point `order` at Shopify while keeping `shipping` on mock during incremental integration.
- The `_env` suffix convention keeps secrets out of version-controlled files while making the required env vars discoverable.

**Negative:**
- Adds a new key to `hat.json` that existing Hats don't have. While backward-compatible, documentation and examples need updating.
- The resolution of `_env` suffixes introduces a convention that may surprise contributors expecting explicit config values.
- If a backend initialization fails (e.g., missing env var), the entire hat equip fails. This is intentional but means partial Hat startup is not supported — it's all or nothing.
