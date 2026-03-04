# ADR-024: Generic REST and GraphQL service adapters

**Date:** 2026-03
**Status:** Accepted

## Context

ADR-022 defines service interfaces. ADR-023 puts backend config in the Hat. The expected deployment path is: most users will either use a first-party connector (Shopify, ShipStation) or connect to a custom in-house system.

First-party connectors are purpose-built. Custom in-house systems are the problem. Every company's internal order management API is different — different endpoint paths, different auth schemes, different response shapes — but the operations are usually the same: get an order by ID, cancel an order, list orders for a customer.

Writing a full `OrderService` implementation for every custom API is expensive and error-prone. Most custom APIs are straightforward REST or GraphQL services where the integration is purely mechanical: make an HTTP call, map the response fields to Sophia's data models. The logic is in the mapping, not the code.

Alternatives considered:
- Require custom code for every backend (rejected: too high a barrier for non-developer deployments)
- Use a general-purpose integration platform like Zapier or n8n (rejected: adds an external dependency, increases latency, breaks the local-first principle)
- Auto-generate backends from OpenAPI specs (considered for future: promising but complex; the generic adapter covers the immediate need)

## Decision

Sophia provides two generic adapter implementations that can serve as backends for any service interface:

**GenericRESTService** — Configured with a base URL, auth method, and a set of endpoint templates. Each service method maps to an HTTP call defined in config: method, path (with parameter interpolation), optional body template, and a response mapping using JSONPath expressions. The adapter handles auth header injection, retries with backoff, timeout, and response-to-dataclass conversion.

**GenericGraphQLService** — Configured with an endpoint URL, auth method, and a set of named queries. Each service method maps to a GraphQL query/mutation with variable mapping and response extraction via JSONPath.

Both adapters implement the same service interfaces as purpose-built connectors. They are selected by setting `"provider": "rest"` or `"provider": "graphql"` in the Hat's backend config.

The response mapping uses JSONPath expressions to extract fields from arbitrary response structures and map them into Sophia's framework-owned dataclasses. Required fields that cannot be mapped raise a clear error rather than producing a partially populated model.

Auth methods supported: `bearer` (token in Authorization header), `basic` (username/password), `api_key` (key in a configurable header), `none`. Auth credentials are always resolved from environment variables.

## Consequences

**Positive:**
- Any REST or GraphQL API can be connected to Sophia through configuration alone, with zero custom code.
- The JSONPath mapping is declarative and inspectable — operators can see exactly how external fields map to Sophia's models.
- The generic adapters serve as a rapid prototyping path: get connected quickly via config, then optionally replace with a purpose-built connector later for better performance or error handling.
- Covers the majority of custom in-house systems, which are typically REST APIs behind an API gateway.

**Negative:**
- JSONPath mapping cannot handle complex transformations (e.g., computing a field from two source fields, conditional logic). For these cases, a purpose-built connector is still needed.
- Error handling is generic. A purpose-built Shopify connector can interpret Shopify-specific error codes and produce helpful messages. The REST adapter can only report HTTP status codes and raw error bodies.
- Response mapping config can become verbose for APIs with deeply nested or unconventional response structures.
- The adapter adds runtime overhead: JSONPath parsing, field-by-field extraction, and dataclass construction are slower than direct deserialization in a purpose-built connector. This is negligible for single-request tools but could matter if service methods are called in tight loops.
- Testing is harder to validate exhaustively — the config is essentially a mini-DSL, and malformed mappings may not fail until a specific service method is called with specific data.
