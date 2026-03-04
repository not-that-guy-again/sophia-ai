# ADR-025: Webhook event ingestion for proactive behavior

**Date:** 2026-03
**Status:** Accepted

## Context

Sophia is currently purely reactive. It processes a user message and produces a response. Nothing happens between messages. The pipeline runs only when a human sends input through the chat API or WebSocket.

Real customer service is not purely reactive. External events happen constantly: an order ships, a payment fails, a return is received at the warehouse, inventory drops below threshold. Human CS agents respond to these events — following up with customers, processing refunds triggered by returned goods, proactively notifying customers of delays.

Without event ingestion, Sophia cannot:
- Know that a shipment was delayed unless the customer asks
- Process a refund when a returned item is inspected and approved
- Proactively reach out to a customer whose payment failed
- Update its memory with real-time order/shipment state changes

This gap means Sophia's memory of order state diverges from reality between conversations, leading to stale or incorrect information in future interactions.

Alternatives considered:
- Polling external systems on a schedule (rejected: wasteful for most events, misses real-time signals, complicates rate limiting across platforms)
- Processing events only when the next user message arrives (rejected: introduces unpredictable latency and couples event processing to user activity)
- Full event-driven architecture with a message bus (rejected for now: over-engineered for Phase 1; can be introduced later if event volume demands it)

## Decision

Sophia exposes webhook endpoints that receive HTTP POST requests from external systems. Each incoming webhook is validated, normalized into a `SophiaEvent` dataclass, and routed to one or more handlers.

### Endpoint

```
POST /webhooks/{source}
```

Where `{source}` matches a configured webhook provider (e.g., `shopify`, `shipstation`, `stripe`). Unrecognized sources receive a 404.

### Processing Pipeline

1. **Signature validation.** Each source has a validator that checks the request signature against a shared secret. Shopify uses HMAC-SHA256 over the raw body. Stripe uses a timestamp + signature scheme. Requests that fail validation receive a 401 and are logged to the audit trail.

2. **Normalization.** A source-specific `EventNormalizer` maps the platform's payload into a `SophiaEvent` dataclass: `event_type`, `source`, `entity_type`, `entity_id`, `data`, `timestamp`, `raw_payload`. This is the same provider pattern used for service backends (ADR-022) and LLM providers (ADR-009).

3. **Routing.** An `EventRouter` decides what to do with the normalized event:
   - **Always: update memory.** Store or update the relevant entity in the memory system (via `MemoryProvider`). A shipment delay event updates the order's last-known state.
   - **Conditionally: trigger pipeline.** Some events warrant proactive action (e.g., `payment.failed` should trigger outreach). The Hat's config specifies which event types trigger pipeline runs and with what synthetic user message.
   - **Conditionally: queue notification.** Some events should notify the user if they're connected (e.g., "Your order just shipped"). These are queued and delivered via WebSocket if a session is active.

### Configuration

Webhook sources are configured per-Hat in `hat.json`:

```json
{
  "webhooks": {
    "shopify": {
      "secret_env": "SHOPIFY_WEBHOOK_SECRET",
      "events": {
        "orders/cancelled": { "action": "memory_update" },
        "orders/fulfilled": { "action": "memory_update" },
        "refunds/create": { "action": "memory_update" }
      }
    },
    "shipstation": {
      "secret_env": "SHIPSTATION_WEBHOOK_SECRET",
      "events": {
        "SHIP_NOTIFY": { "action": "memory_update_and_notify" },
        "DELIVERY_EXCEPTION": {
          "action": "trigger_pipeline",
          "synthetic_message": "Shipment delay detected for order {entity_id}. Check status and notify customer if they have an active conversation."
        }
      }
    }
  }
}
```

### Event Processing Guarantees

Webhook processing is **at-least-once**. The endpoint returns 200 immediately after signature validation and queues the event for async processing. If processing fails, the event is logged to the audit trail with the failure reason. Retry logic is the responsibility of the sending platform (most webhook senders retry on non-2xx responses).

Idempotency is handled by deduplication on `(source, event_type, entity_id, timestamp)`. Duplicate events within a configurable window (default 5 minutes) are acknowledged but not reprocessed.

## Consequences

**Positive:**
- Sophia can maintain accurate, real-time state about orders, shipments, and returns between conversations, leading to better-informed responses.
- Proactive pipeline triggers enable follow-up workflows (payment failure outreach, delay notification) without human initiation.
- The normalizer pattern keeps platform-specific parsing isolated, consistent with the project's provider abstraction approach.
- Webhook config is per-Hat, so different Hats can listen for different events from different sources.
- Immediate 200 response + async processing avoids webhook timeout issues with external platforms.

**Negative:**
- Adds an HTTP ingestion surface that must be secured (signature validation, rate limiting, IP allowlisting in production).
- Proactive pipeline triggers (synthetic messages) are a new category of pipeline input that needs testing to ensure the consequence engine and evaluators handle them correctly.
- At-least-once processing means handlers must be idempotent. Memory updates are naturally idempotent (last write wins), but pipeline triggers could produce duplicate outreach if the deduplication window is too narrow.
- Webhook registration with external platforms is a manual operational step outside Sophia's control. Shopify requires configuring webhooks in the admin panel or via API. This operational burden is not reduced by this ADR.
- The `webhooks` block in `hat.json` adds another config surface. Combined with `backends` (ADR-023), Hat configuration is becoming more complex. Documentation must be clear about which blocks are required vs. optional.
