# ADR-018: LLM-based response generation

**Date:** 2025
**Status:** Accepted

## Context

After tool execution, the agent loop calls _build_response() to convert the ExecutionResult into a string for the user. The current implementation dumps raw tool result data directly:

```python
def _build_response(self, execution: ExecutionResult) -> str:
    result = execution.tool_result
    parts = [result.message]
    if result.data and isinstance(result.data, dict):
        for key, value in result.data.items():
            parts.append(f"  {key}: {value}")
    return "\n".join(parts)
```

This produces responses like "Full inventory: 5 products\n  products: [{'product_id': 'PROD-001', ...}]" which is a Python dict dumped into the chat window. This is not a usable response. No customer should ever see raw data structures.

The same problem affects all tiers. GREEN responses dump tool output. YELLOW responses show raw consequence data. ORANGE and RED responses are slightly better because they include hand-written templates, but they still lack conversational awareness.

## Decision

A new pipeline component, the response generator, sits between the executor and the final output. It receives the original user message, the tool result (or tier-specific data), the hat context, and any memory context, then makes an LLM call to produce a natural language response.

The response generator is implemented in sophia/core/response_generator.py with a dedicated prompt in sophia/llm/prompts/core/response.py. The prompt instructs the LLM to: write in the voice and tone defined by the hat's system prompt, reference specific data from the tool result (order numbers, amounts, product names), never expose internal data structures or tool names, and keep the response focused on the customer's original question.

For each tier:
- GREEN: generate a natural response incorporating the tool result
- YELLOW: generate an explanation of what the agent wants to do and why confirmation is needed, citing the top consequence branches
- ORANGE: generate an explanation of why this is being escalated
- RED: generate a refusal that cites specific concerns from the consequence tree

The _build_response() method in the loop is replaced by an async call to the response generator.

## Consequences

**Positive:**
- Users never see raw Python dicts, JSON, or internal data structures
- Responses can match the hat's defined tone and voice
- The response can incorporate memory context (e.g., "Welcome back, Abbie!")
- YELLOW/ORANGE/RED explanations become more natural and specific
- The response generator can be tested independently with mock tool results

**Negative:**
- Adds one more LLM call to every pipeline run, increasing latency and cost
- The LLM might hallucinate details not present in the tool result
- Response quality depends on the prompt and the hat's system prompt fragment
- Error handling becomes more complex (what if the response generation call fails after the tool already executed?)
- The response generator needs access to multiple context sources (message, tool result, hat config, memory)
