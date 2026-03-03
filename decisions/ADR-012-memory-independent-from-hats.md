# ADR-012: Memory system independent from Hat system

**Date:** 2025
**Status:** Accepted

## Context

The existing `MemoryStore` in `sophia/memory/store.py` is not a memory system. It is a passthrough that holds a reference to the active Hat's configuration, exposing domain constraints and stakeholders as properties. When a Hat is unequipped, the "memory" is cleared entirely. This couples memory to domain context, which is incorrect.

The Hat system is analogous to a professional role. A person putting on a "manager hat" or an "engineer hat" changes their considerations, tools, and constraints, but it does not change their memories. A customer service agent who switches to a billing role should still remember that Abbie called last week about her Litter Robot. Memories are a property of the agent, not of the role.

The current design makes it impossible to persist knowledge across hat switches, recall past interactions with returning customers, detect patterns across conversations, or build the kind of relational awareness that makes human interactions feel valued.

## Decision

The memory system is a standalone subsystem, independent from the Hat system. It has its own database, its own interface, and its own lifecycle. Hats do not own memories. Hats cannot clear memories. All hats can read from and write to the same memory system.

The Hat system retains ownership of domain configuration: constraints, stakeholders, evaluator weights, prompt fragments, and tool definitions. These are loaded from flat files on disk when a Hat is equipped and are not stored in the memory system.

The memory system owns experiential knowledge: conversation records, entity information, relationship graphs, interaction history, and semantic embeddings. This data persists across hat switches, server restarts, and configuration changes.

The core loop provides both systems to pipeline components. A component like the consequence engine receives Hat context (what rules apply) and memory context (what has happened before) as separate inputs.

## Consequences

**Positive:**
- Knowledge persists across hat switches, matching how human memory actually works
- Returning customers, recurring issues, and cross-conversation patterns become detectable
- The Hat system stays simple: flat files on disk, loaded at equip time, no database dependency
- Clear separation of "what role am I playing" (Hat) from "what do I know" (Memory)
- Memory can be tested independently from the Hat system

**Negative:**
- The memory system becomes a new subsystem with its own database, interface, and operational requirements
- Pipeline components now receive context from two sources, increasing integration complexity
- The existing `sophia/memory/` module needs to be substantially rewritten rather than extended
- Memory queries add latency to the pipeline if not carefully managed
