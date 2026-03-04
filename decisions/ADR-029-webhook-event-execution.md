# ADR-029: Webhook event action execution

**Date:** 2026-03
**Status:** Accepted

## Context

ADR-025 introduced webhook event ingestion: HTTP endpoints receive events from external systems, validate signatures, normalize payloads into `SophiaEvent` dataclasses, and route them via `EventRouter` to one of three action types: `memory_update`, `trigger_pipeline`, or `memory_update_and_notify`.

The ingestion, validation, normalization, and routing infrastructure is built and tested. However, the action handlers are incomplete — `EventRouter.route()` returns an `EventAction` describing what should happen, but nothing executes the action. The `memory_update` action doesn't write to `MemoryProvider`. The `trigger_pipeline` action doesn't invoke `AgentLoop.process()`. The `memory_update_and_notify` action doesn't send notifications.

This means webhook events are received, validated, categorized, and logged — but have no effect on the system's state or behavior.

Alternatives considered:

- **Handle actions in the webhook route handler** (rejected: puts business logic in the HTTP layer, makes testing harder, couples route code to memory and pipeline internals).
- **Use a background task queue** (considered for future: would enable reliable retry and async processing, but adds infrastructure complexity — Redis, Celery, or similar. The synchronous-in-request approach is sufficient for initial volume and can be migrated later).
- **Add execute() to EventRouter** (selected: keeps routing and execution co-located, the router already has the config context needed to dispatch actions, dependencies are injected at construction time).

## Decision

The `EventRouter` gains an `async execute(action: EventAction)` method and three dependencies injected at construction:

```python
class EventRouter:
    def __init__(
        self,
        webhooks_config: dict | None = None,
        memory: MemoryProvider | None = None,
        agent_loop: AgentLoop | None = None,
        notification_service: NotificationService | None = None,
    ):
```

### memory_update

Converts the `SophiaEvent` into a `memory.models.Entity` and upserts it via `MemoryProvider.store_entity()`. The entity ID is scoped by source to prevent collisions: `{source}:{entity_type}:{entity_id}`. The entity's `attributes` dict contains the normalized event data.

This is idempotent — storing the same entity twice with the same or newer data simply updates it. This satisfies the at-least-once processing guarantee from ADR-025.

### trigger_pipeline

Calls `AgentLoop.process()` with the synthetic message from the event config and `source="webhook"` metadata. The synthetic message goes through the full pipeline — input gate, proposer, consequence engine, evaluation panel, risk classifier, executor. There is no pipeline shortcut for webhook-originated messages. If the consequence engine determines the proposed action is harmful, it is refused or escalated just like a user-initiated action.

Webhook-triggered pipeline runs skip the preflight acknowledgment (ADR-021) since there is no user to acknowledge to. The `source` metadata is attached to the `PipelineResult` and audit record for traceability.

If `agent_loop` is None (not yet initialized), the trigger is logged and skipped. This can happen during startup if a webhook arrives before the hat is fully equipped.

### memory_update_and_notify

Executes `memory_update` first, then delegates to the `NotificationService` (ADR-028) for outbound delivery. If no notification service is configured, the memory update still happens and the notification is silently skipped.

### Webhook Route Changes

The webhook HTTP handler (`sophia/api/webhook_routes.py`) changes from log-only to execute:

```python
# Before
action = _event_router.route(event, topic)
_record_event(event, action)

# After
action = _event_router.route(event, topic)
if action:
    await _event_router.execute(action)
    _record_event(event, action)
```

The 200 response is still returned immediately. Execution happens synchronously within the request for now. If execution time becomes a concern (e.g., `trigger_pipeline` running the full evaluation pipeline takes several seconds), the execute call can be moved to a background task without changing the external contract — the webhook sender already got its 200.

### Dependency Injection

`configure_webhooks()` in `webhook_routes.py` is updated to accept and pass through the memory provider and agent loop:

```python
def configure_webhooks(
    webhooks_config: dict,
    memory: MemoryProvider | None = None,
    agent_loop: AgentLoop | None = None,
    notification_service: NotificationService | None = None,
) -> None:
```

`HatRegistry.equip()` passes these through when configuring webhooks.

## Consequences

**Positive:**
- Webhook events now have real effects: memory is updated with real-time state, the pipeline can be triggered proactively, and customers can be notified of important changes.
- The full consequence evaluation pipeline applies to webhook-triggered actions. A proactive refund triggered by a webhook goes through the same safety review as a user-requested refund.
- Memory updates from webhooks mean the next customer conversation has accurate, current data — the agent knows the order shipped even if the customer hasn't asked yet.
- The execute-in-request approach is simple and testable. No message queue infrastructure is needed initially.

**Negative:**
- Synchronous execution within the HTTP request means webhook processing time increases. A `trigger_pipeline` action that runs the full evaluation pipeline could take 3–10 seconds. Most webhook senders have generous timeouts (30–60 seconds), but this should be monitored.
- The `AgentLoop` reference in `EventRouter` creates a bidirectional dependency between the webhook system and the core pipeline. This is managed by injecting the reference at runtime rather than at import time, but it increases the coupling between subsystems.
- If memory updates fail (e.g., SurrealDB is down), the webhook returns 200 but the update is lost. At-least-once processing depends on the sender retrying, which only happens if the webhook returns a non-2xx status. A future enhancement could return 503 on memory failures to trigger retry.
- Background task migration will require changes to the execute path. The current synchronous approach is a stepping stone, not the final architecture for high-volume deployments.
