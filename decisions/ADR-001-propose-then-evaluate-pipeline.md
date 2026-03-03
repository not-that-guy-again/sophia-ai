# ADR-001: Propose-then-evaluate pipeline

**Date:** 2025  
**Status:** Accepted

## Context

Conventional AI agent frameworks follow a pattern where the LLM decides on an action and the framework immediately executes it. The LLM acts as both decision-maker and executor in a single step. This creates a fundamental safety problem: by the time you know what the agent decided to do, it has already done it. Guardrails in these systems are typically limited to input filtering (blocking certain prompts) or output filtering (checking the response text), neither of which evaluates the consequences of the proposed action itself.

Sophia needs a pattern where the decision to act and the act itself are separated by a deliberation layer. The LLM should be good at generating creative solutions and reasoning about what to do. A separate system should evaluate whether those solutions are safe to execute.

## Decision

The core pipeline separates proposal from execution. The LLM generates 1-3 candidate actions with reasoning and expected outcomes, but does not execute any of them. A separate consequence simulation and evaluation step sits between proposal and execution. The executor only runs after the evaluation panel has scored the action and the risk classifier has assigned a tier.

The pipeline stages are:

1. Input Gate (parse intent)
2. Proposer (generate candidates, no execution)
3. Consequence Engine (simulate outcomes)
4. Evaluation Panel (score from four perspectives)
5. Risk Classifier (assign tier)
6. Executor (act, confirm, escalate, or refuse based on tier)

## Consequences

**Positive:**
- Every action is evaluated before execution, not after
- The LLM can propose bold or creative solutions without risk, since the evaluation layer handles safety
- The separation creates a natural audit point between "what the AI wanted to do" and "what actually happened"
- Each pipeline stage can be tested, logged, and improved independently

**Negative:**
- Multiple LLM calls per user message (proposer + consequence engine + evaluators) increase latency and cost
- The pipeline is more complex than a simple prompt-and-execute loop, requiring more code and more testing
- The proposer must be carefully prompted to avoid executing actions inline (e.g., generating tool call syntax that the framework interprets as execution)
