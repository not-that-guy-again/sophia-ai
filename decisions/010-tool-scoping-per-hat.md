# ADR-010: Tool scoping per hat

**Date:** 2025
**Status:** Accepted

## Context

The proposer generates candidate actions by selecting from available tools. If the LLM sees tools from multiple domains, several problems arise: it may propose irrelevant tools, waste tokens on tools it should not use, encounter name collisions, and expand the attack surface.

The tool set available to the agent must match the domain it is currently operating in.

## Decision

When a Hat is equipped, only that Hat's tools are registered in the `ToolRegistry`. The process clears all previously registered tools, scans the Hat's `tools/` directory for Python modules, instantiates all `Tool` subclasses found, and registers only those whose `name` appears in the Hat manifest's `tools` list. Execution calls to any unregistered tool name are rejected.

The proposer's system prompt includes only the registered tools' definitions. The LLM never sees tools it cannot use.

When a Hat is switched via the API, the old tools are cleared and the new Hat's tools are registered. There is no overlap period.

## Consequences

**Positive:**
- The LLM only sees relevant tools, reducing hallucinated tool calls and wasted tokens
- Tool name collisions between Hats are impossible because only one Hat's tools exist at a time
- The registry refuses calls to unregistered tools, providing a hard boundary against tool misuse
- Smaller tool sets in the prompt improve LLM focus and reduce latency

**Negative:**
- Hat switching clears all tools, meaning mid-conversation switches lose tool context
- A Hat cannot borrow tools from another Hat without duplicating the implementation
- The manifest's `tools` list must exactly match tool class `name` attributes, creating a manual sync requirement
- Dynamic tool registration at runtime without a Hat switch is not supported
