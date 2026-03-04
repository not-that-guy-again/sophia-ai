# ADR-026: MCP as backend transport, not tool-calling

**Date:** 2026-03
**Status:** Accepted

## Context

Sophia's service provider layer (ADR-022) defines five service interfaces backed by mock implementations. Real deployments need connectors to external platforms (Shopify, Stripe, ShipStation, etc.). Writing a purpose-built connector for each platform takes 1–2 weeks and requires deep knowledge of the platform's API.

The Model Context Protocol (MCP) is an open standard for connecting AI models to external data sources and tools. MCP servers already exist for many e-commerce and business platforms. In the standard MCP integration pattern, the LLM discovers available tools from the MCP server and calls them directly — the model decides to call `shopify_get_order` and the MCP client executes it immediately.

This standard pattern is incompatible with Sophia's architecture. ADR-001 establishes that the LLM proposes actions and a separate system evaluates whether to execute them. Direct MCP tool-calling bypasses the Proposer → Consequence Engine → Evaluation Panel → Risk Classifier → Tiered Executor pipeline entirely. An agent that calls MCP tools directly goes from "I want to do this" to "it's done" with no safety review.

Alternatives considered:

- **Write purpose-built connectors per platform** (viable but slow: 1–2 weeks each, requires platform API expertise, mapping boilerplate is repetitive). This remains an option for platforms where MCP servers don't exist or where the MCP server's coverage is insufficient.
- **Expose MCP tools directly to the LLM** (rejected: violates ADR-001, bypasses the entire consequence evaluation pipeline, makes Sophia architecturally identical to every other agent framework).
- **Use MCP for read-only operations only, purpose-built for writes** (rejected: creates two integration paths for the same platform, doubles the mapping code, confusing contributor experience).

## Decision

MCP is integrated as a **backend transport layer**, hidden behind Sophia's existing service interfaces. The LLM never sees MCP tools. MCP servers are called by service adapter implementations that sit behind the same `OrderService`, `CustomerService`, etc. ABCs that mock and purpose-built connectors implement.

The integration consists of three components:

### 1. MCPClient

A thin async wrapper (`sophia/services/mcp/client.py`) that manages connections to MCP servers via HTTP/SSE transport. It handles:
- Connection establishment and tool discovery
- Tool invocation with argument passing
- Response parsing into `MCPToolResult` dataclasses
- Connection lifecycle (reconnection, timeout, graceful close)

The client uses `httpx` for HTTP transport. One client instance is created per unique MCP server URL. When multiple services share the same server (e.g., Shopify handles orders, customers, and inventory), the `ServiceRegistry` deduplicates clients by `(server_url, server_name)`.

### 2. Platform Mapping Modules

Each platform gets a mapping module (`sophia/services/mcp/shopify_mapping.py`, etc.) that defines how service interface methods map to MCP tool calls. A mapping specifies:
- Which MCP tool to call for each service method
- How to transform service method arguments into MCP tool arguments
- How to parse MCP tool results into Sophia's framework-owned dataclasses

The mapping is declarative — a dict of `{method_name: {tool_name, build_args, parse_response}}`. The `parse_response` callable handles the impedance mismatch between the platform's data model and Sophia's. This is where platform-specific knowledge lives.

### 3. MCP Service Adapters

Generic adapter classes (`MCPOrderService`, `MCPCustomerService`, etc.) implement the service interfaces by delegating to the MCP client using the platform mapping. The adapter pattern is generic — the same `MCPOrderService` class works for Shopify, Square, or any other platform by swapping the mapping module.

### Configuration

MCP backends are configured in `hat.json` using `"provider": "mcp"`:

```json
{
  "order": {
    "provider": "mcp",
    "config": {
      "server_url_env": "SHOPIFY_MCP_URL",
      "server_name": "shopify",
      "platform": "shopify",
      "auth_token_env": "SHOPIFY_MCP_TOKEN"
    }
  }
}
```

The `platform` field selects which mapping module to load. The `_env` suffix convention (ADR-023) resolves server URLs and auth tokens from environment variables.

### Startup Validation

On connection, the MCP client discovers available tools via `list_tools()`. The adapter validates that all tools referenced in the platform mapping exist on the server. Missing tools produce a clear startup error with the missing tool names, rather than a runtime failure on first customer interaction.

### Error Handling

MCP-specific errors (connection failures, tool errors, malformed responses, timeouts) are caught by the adapter and mapped to service-level failures that tools already handle — `None` for failed lookups, failure result dataclasses for failed mutations. The pipeline never sees MCP-specific error types.

## Consequences

**Positive:**
- Existing MCP servers for Shopify, Stripe, ShipStation, and other platforms can be used immediately, reducing per-platform connector work from weeks to days (mapping module only).
- The propose-then-evaluate pipeline is completely preserved. MCP calls happen only after the executor greenlights the action. Read operations are still called by tools, but the tools are only invoked after the proposer selects them and the consequence engine approves.
- The pattern is consistent with existing provider abstractions (ADR-009 LLMProvider, ADR-015 MemoryProvider, ADR-022 ServiceProvider). Contributors learn one pattern.
- Purpose-built connectors remain a first-class option. A `ShopifyOrderService` that calls the Shopify REST API directly is still valid and may outperform the MCP adapter for high-volume deployments.
- Multiple services can share a single MCP client when backed by the same server, reducing connection overhead.

**Negative:**
- Adds a dependency on MCP server availability and correctness. If a community MCP server has bugs or missing features, Sophia's service quality is affected.
- The mapping layer introduces indirection: service method → adapter → MCP client → MCP server → platform API. Debugging requires tracing through more layers than a direct API call.
- MCP servers may not cover all operations in Sophia's service interfaces. A Shopify MCP server might support `get_order` but not `cancel_order`. Missing operations must be documented per-platform, and the mapping must raise clear `NotImplementedError`s.
- The MCP ecosystem is young. Server quality, API stability, and authentication patterns vary. Some servers may require custom auth flows not covered by the standard `auth_token` pattern.
- Contributors and users familiar with MCP will expect the standard direct-integration pattern and may be confused by Sophia's transport-only approach. ADR-001 must be cited clearly in documentation explaining why.
