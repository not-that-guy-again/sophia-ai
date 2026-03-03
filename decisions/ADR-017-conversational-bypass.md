# ADR-017: Conversational bypass in the proposer

**Date:** 2025
**Status:** Accepted

## Context

The pipeline forces every user input through tool selection. The proposer prompt instructs the LLM to "generate 1-3 candidate actions" where each candidate must reference a tool name from the equipped hat. When a user sends a conversational message like "Hello" or "Who are you?", the input gate correctly classifies it as general_inquiry, but the proposer has no way to express "just respond conversationally, no tool is needed." It must pick a tool, so it grabs the least-wrong option from the available set, typically check_current_inventory or escalate_to_human.

This was observed in testing: sending "Hello" caused Sophia to run an inventory check and dump the raw product catalog into the chat. Sending "Who are you?" triggered an escalation to a human agent. Both are incorrect behavior.

The consequence engine, evaluation panel, and risk classifier are also wasted on these inputs. There are no consequences to simulate and no risks to classify for a greeting.

## Decision

The proposer can generate a candidate with tool_name set to "converse". This is a reserved name that is never a real tool. When the executor encounters a converse candidate, it skips tool execution entirely and passes the original user message to the response generator, which produces a direct conversational reply via LLM.

The converse candidate still has reasoning and expected_outcome fields, which the LLM fills in (e.g., reasoning: "The user is greeting the agent, no action is needed", expected_outcome: "Agent responds with a friendly greeting").

When the top candidate is converse, the pipeline skips consequence tree generation, evaluation, and risk classification. The message goes directly from proposer to response generator.

The proposer prompt is updated to include converse in the available actions list with clear guidance: use it when the user is making conversation, asking a question that does not require a tool, or when no available tool is appropriate.

## Consequences

**Positive:**
- Greetings, questions, and chitchat get natural responses instead of spurious tool calls
- Saves LLM calls (no consequence tree, no evaluators, no risk classifier) for non-actionable inputs
- Saves tokens by not running the full pipeline on simple messages
- The decision to bypass is made by the LLM (via the proposer), not by hardcoded keyword matching

**Negative:**
- The LLM might use converse to avoid difficult requests it should actually evaluate
- No consequence analysis means no safety check on conversational responses
- Adds a special case to the executor that must be handled in every tier
- The boundary between "conversational" and "actionable" is a judgment call by the LLM
