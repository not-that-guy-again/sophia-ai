# ADR-027: API authentication and tenant isolation

**Date:** 2026-03
**Status:** Accepted

## Context

Sophia's API has no authentication. The CORS middleware allows all origins (`allow_origins=["*"]`), every endpoint is publicly accessible, and there is no concept of tenants. This is appropriate for local development but blocks any commercial deployment.

A production deployment needs at minimum:
- Authentication to prevent unauthorized access to the chat, webhook, and audit endpoints
- Tenant identification so multiple customer companies can use a shared Sophia instance
- Rate limiting to prevent abuse
- Scope-based authorization so webhook endpoints can have different access controls than chat endpoints

Alternatives considered:

- **OAuth2 / OIDC** (rejected for now: adds significant complexity, requires an identity provider, overkill for an API-first product where the consumer is another service, not a browser-based user). Can be added later as an auth provider behind the same middleware.
- **JWT tokens** (considered: stateless verification is appealing, but requires token issuance infrastructure and complicates revocation). JWT support can be added as an alternative auth method later.
- **API keys only** (selected: simplest model, well-understood by API consumers, easy to generate and revoke, sufficient for the initial deployment model where each customer company integrates via their backend).
- **Per-tenant process isolation** (rejected for now: operationally complex, wasteful for low-volume tenants). The lightweight in-process tenant model can be upgraded to process-level isolation later if needed.

## Decision

### API Key Authentication

All API endpoints (except `/health` and `/docs`) require a Bearer token in the Authorization header. The token is a Sophia API key.

**Key format:** `sk-sophia-{tenant_id}-{32_random_hex_chars}`

The prefix `sk-sophia-` makes keys identifiable in logs and secrets managers. The `tenant_id` segment is human-readable for debugging. The random suffix provides cryptographic uniqueness.

Keys are generated via a management endpoint and the full key is returned exactly once. Only the SHA-256 hash is stored in the database. Lookup is by hash — no plaintext key is ever persisted.

**Key metadata:**
- `key_id`: public identifier (first 12 chars of the hash, used in logs and rate-limit tracking)
- `key_hash`: SHA-256 of the full key
- `tenant_id`: company/organization identifier
- `hat_name`: which hat this key authorizes (one key, one hat)
- `scopes`: list of authorized operations (`chat`, `admin`, `webhooks`, `audit`)
- `rate_limit_rpm`: per-key requests-per-minute limit
- `created_at`, `expires_at`, `is_active`: lifecycle fields

The key model is stored as a SQLAlchemy table in the existing audit database, reusing the database infrastructure from ADR-011.

### Auth Middleware

A FastAPI dependency (`require_auth`) extracts the Bearer token, hashes it, looks up the key, and validates:
1. Key exists and `is_active` is True
2. Key has not expired
3. Rate limit has not been exceeded

The validated `APIKey` is attached to `request.state` for downstream scope checks. Individual routes check `key.scopes` for their required scope.

### Scopes

Four scopes control access:
- **`chat`** — POST /chat, WebSocket /ws/chat
- **`admin`** — Hat management, key management endpoints
- **`webhooks`** — POST /webhooks/{source} (can alternatively use per-source signature validation without API keys)
- **`audit`** — GET /audit/* endpoints

Webhook endpoints have dual auth: they accept either a valid API key with `webhooks` scope OR a valid platform-specific signature (Shopify HMAC, Stripe signature). This accommodates platforms that can't add custom Authorization headers to webhook payloads.

### Rate Limiting

An in-memory sliding window rate limiter tracks requests per key. Each key has a configurable `rate_limit_rpm` (default 60). When exceeded, the API returns 429 with a `Retry-After` header.

The rate limiter is in-process and resets on restart. This is adequate for single-instance deployments. Multi-instance deployments would need Redis-backed rate limiting, which can be added later behind the same `RateLimiter` interface.

### Tenant Isolation

Tenant isolation is lightweight and in-process:
- The API key's `tenant_id` is attached to every `PipelineResult`, audit record, and memory entity
- Memory entities are prefixed with `{tenant_id}:` to prevent cross-tenant data leakage
- Audit queries filter by `tenant_id` extracted from the requesting key
- Each tenant's hat config lives in a separate directory (`hats/{tenant_id}-cs/`)

This provides logical isolation suitable for a shared-instance deployment. Stronger isolation (separate databases, separate processes) is a deployment concern, not an application concern, and can be achieved by running separate Sophia instances per tenant.

### Bootstrap Key

On first startup with `auth_enabled=True`, if no keys exist in the database, Sophia generates a bootstrap key with all scopes and prints it to stdout. This key is used to create additional keys via the admin API. The bootstrap key can also be set via the `AUTH_BOOTSTRAP_KEY` environment variable for automated deployments.

### Development Mode

When `auth_enabled=False` (the default), all auth middleware is skipped. This preserves the current zero-config development experience. No API keys are needed to run tests or use the dev server.

## Consequences

**Positive:**
- Every endpoint is authenticated in production, preventing unauthorized access to customer data and agent actions.
- API keys are simple to generate, distribute, and revoke. No external identity provider required.
- Tenant isolation prevents cross-company data leakage at the application level.
- Rate limiting provides basic abuse protection.
- The `auth_enabled=False` default means no changes to the development, testing, or CI workflow.
- Scope-based authorization provides granular access control without the complexity of a full RBAC system.

**Negative:**
- API key auth is bearer-token based — anyone with the key has access. Keys must be treated as secrets. There is no request signing or mutual TLS.
- In-memory rate limiting doesn't survive restarts and doesn't work across multiple instances. Multi-instance deployments need an external rate limiter.
- Tenant isolation is logical, not physical. A bug in entity ID prefixing could leak data across tenants. Stronger isolation requires operational separation.
- The bootstrap key printed to stdout is a security risk if stdout is logged to an insecure location. Production deployments should use `AUTH_BOOTSTRAP_KEY` env var instead.
- Adding auth to webhook endpoints creates a dual-auth path (API key OR signature) that increases the auth middleware's complexity and testing surface.
