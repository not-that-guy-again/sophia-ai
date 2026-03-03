# ADR-009: LLM provider abstraction

**Date:** 2025
**Status:** Accepted

## Context

Sophia makes multiple LLM calls per pipeline run: input gate, proposer, consequence engine, and four evaluators. The choice of LLM provider affects cost, latency, capability, and privacy. Different deployments may have different requirements: a production system might use Claude via the Anthropic API, while a development setup might use a local model via Ollama to avoid API costs and keep data local.

Some future scenarios (see ADR-004, multi-model evaluator panel) may require different models for different pipeline stages within the same deployment.

## Decision

The LLM layer is abstracted behind a `LLMProvider` interface defined in `sophia/llm/provider.py`. The interface exposes a single method:

```
async complete(system_prompt: str, user_message: str, response_format: dict | None = None) -> LLMResponse
```

`LLMResponse` contains the content string, token usage, and the raw provider response.

Two implementations ship with the framework:
- `AnthropicProvider` (`sophia/llm/anthropic.py`): Claude via the Anthropic SDK
- `OllamaProvider` (`sophia/llm/ollama.py`): local models via Ollama's HTTP API using httpx

A factory function `get_provider(settings)` returns the appropriate implementation based on the `LLM_PROVIDER` environment variable.

All pipeline components receive an `LLMProvider` instance and call `complete()` without knowing which backend is in use.

## Consequences

**Positive:**
- Switching providers requires only changing an environment variable, not code changes
- Local development can use Ollama at zero API cost
- The abstraction enables future multi-model configurations (different providers per pipeline stage)
- Testing uses a `MockLLMProvider` that returns predetermined responses, making tests fast and deterministic
- New providers can be added by implementing the interface without touching pipeline code

**Negative:**
- The interface is lowest-common-denominator; provider-specific features (streaming, tool use, vision) require interface extensions
- Ollama models may not match the quality of Claude for consequence analysis and evaluation, producing different safety outcomes for the same input
- The single `complete()` method does not support multi-turn conversations, which some future pipeline stages may need
- Token usage tracking is provider-dependent and may not be comparable across providers
