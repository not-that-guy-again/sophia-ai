# ADR-013: Three-tier memory model

**Date:** 2025
**Status:** Accepted

## Context

AI systems typically handle memory in one of two ways: either they stuff the entire conversation history into the context window (expensive, hits token limits), or they run a compaction step that summarizes history into a condensed block (lossy, loses detail). Neither approach reflects how biological memory actually works, and both produce agents that feel mechanical.

Human memory operates in tiers. Working memory holds the current conversation in full detail but decays within hours. Episodic memory retains the gist of recent experiences for days to weeks. Long-term memory stores durable knowledge indefinitely, recalled on demand through associative queries rather than sequential replay.

The key insight is that memory recall is associative, not exhaustive. A person about to hang a door does not load every memory they have ever formed. They recall memories of past doors, similar challenges, and tools that helped. This is closer to a database query than a context window.

## Decision

The memory system operates in three tiers:

**Tier 1: Working Memory (context window).** The current conversation in its raw form. Held in the LLM context window for the duration of the interaction. Not persisted by the memory system. Most detailed, most expensive.

**Tier 2: Episodic Memory (conversation summaries).** After a conversation ends or at periodic intervals, an LLM call extracts a structured summary: who was involved, what was discussed, what actions were taken, what the outcome was, and what entities were referenced. Stored with timestamps and metadata. Represents recent experience with moderate detail.

**Tier 3: Long-term Memory (entity knowledge and relationship graph).** Durable facts extracted from conversations: entities (people, products, orders), their attributes, and the relationships between them. "Abbie owns a cat named Waldo. Abbie purchased a Litter Robot. The Litter Robot had a motor defect." Most compressed, most durable. Supports associative recall through structured queries, semantic similarity search, and graph traversal.

The agent does not load all memory into the context window. At the start of a new interaction, the agent queries Tier 3 for relevant entities and Tier 2 for recent related episodes. Only the relevant results are injected into the context window alongside the current conversation.

## Consequences

**Positive:**
- Token usage is proportional to relevance, not total history
- The agent can maintain long-term relationships with recurring contacts across many conversations
- Pattern detection (same defect reported by multiple customers) emerges naturally from the entity graph
- The tiered model degrades gracefully: if long-term recall fails, episodic memory provides fallback
- The approach maps to well-understood cognitive science, making behavior more predictable

**Negative:**
- Tier 2 extraction requires an LLM call per conversation, adding cost
- Tier 3 entity extraction is lossy by design, discarding some conversational nuance permanently
- The quality of long-term memory depends on the LLM's ability to extract entities and relationships accurately
- Three tiers means three different query patterns, storage formats, and retention policies
- The boundary between "important enough to store" and "mundane enough to discard" is a judgment call made by the extraction LLM
