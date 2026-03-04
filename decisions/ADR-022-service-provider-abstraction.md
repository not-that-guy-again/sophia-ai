# ADR-022: Service provider abstraction layer

**Date:** 2026-03
**Status:** Accepted

## Context

Sophia's tool implementations currently contain mock data inline. `LookUpOrderTool.execute()` returns a hardcoded dictionary. `CheckCurrentInventoryTool.execute()` reads from a module-level `MOCK_INVENTORY` dict. There is no separation between what a tool does (look up an order) and how it gets the data (query Shopify, call a REST API, read a database).

This means every deployment that talks to a real system requires forking the tool code. Two customers using different e-commerce platforms need different versions of the same tool, even though the tool's behavior (validate params, call backend, map result to ToolResult) is identical.

The project has already established this pattern twice. ADR-009 introduced `LLMProvider` so the pipeline doesn't know if it's talking to Claude or Ollama. ADR-015 introduced `MemoryProvider` so the pipeline doesn't know if memory lives in SurrealDB or an in-memory dict. Both follow the same shape: an ABC defines the operations, a factory resolves which implementation to use, and pipeline code depends only on the interface.

Tools need the same treatment. The dependency they hide behind an interface is not an LLM or a database — it is the external business system (POS, OMS, WMS, payment processor, shipping provider) that holds the real data.

Alternatives considered:
- Make tools configurable via subclassing (rejected: multiplies tool classes per backend, breaks the Hat's tool list)
- Use a single generic "API call" tool (rejected: the LLM would need to know API details, defeating the purpose of tools as domain abstractions)
- Put backend logic in the Hat's `__init__.py` (rejected: no clean injection point, no lifecycle management)

## Decision

A new **service provider layer** is introduced between tools and external systems. The layer consists of:

1. **Service interfaces** — ABCs in `sophia/services/` defining domain operations: `OrderService`, `CustomerService`, `ShippingService`, `InventoryService`, `CompensationService`. Each method is async and exchanges framework-owned dataclasses, never platform-specific types.

2. **Service data models** — Dataclasses in `sophia/services/models.py` representing the domain objects (`Order`, `Customer`, `ShipmentTracking`, etc.). These are the canonical shapes. Backend implementations map external data into these models. Tools consume only these models.

3. **Backend implementations** — Concrete classes that implement service interfaces for specific platforms. `MockOrderService` ships with each Hat for testing and demos. `ShopifyOrderService`, `GenericRESTOrderService`, etc. are additional implementations.

4. **ServiceRegistry** — A lifecycle manager (`sophia/services/registry.py`) that constructs service instances from Hat config, holds them during the Hat's lifetime, and tears them down on unequip.

5. **Tool injection** — The `Tool` ABC gains an optional `inject_services(services: ServiceRegistry)` method. Tools that need backend access override it to capture service references. Injection happens during hat equip, after services are initialized but before tools are registered.

6. **Hat configuration** — `hat.json` gains a `backends` block mapping service names to provider names and config. Config values ending in `_env` are resolved from environment variables.

## Consequences

**Positive:**
- Tools become portable across backends. `LookUpOrderTool` works with Shopify, Square, SAP, or a custom REST API without any code changes.
- The established pattern (LLMProvider, MemoryProvider) is extended consistently. Contributors already understand the abstraction style.
- Mock implementations remain the default, preserving zero-dependency testing and demos.
- Backend config is per-Hat, allowing different Hats to use different platforms.
- Secrets stay in environment variables, never in `hat.json`.
- Service interfaces document the exact capabilities the CS Hat needs, making it clear what a new backend must implement.

**Negative:**
- Adds an abstraction layer that increases the number of files and indirection. A tool call now goes through: tool → service interface → backend implementation → external system.
- Backend implementations must handle the impedance mismatch between Sophia's data models and the external system's models. This mapping code can be tedious.
- Some service methods may not map cleanly to all backends. A platform that doesn't support order cancellation will need the backend to raise a clear error, not silently succeed.
- The `inject_services()` lifecycle adds a new ordering dependency to hat loading that must be tested.
