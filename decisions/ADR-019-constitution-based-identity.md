# ADR-019: Constitution-based identity and voice

**Date:** 2025
**Status:** Accepted

## Context

Sophia's response quality depends on two prompt layers: core pipeline prompts that define mechanical behavior (how to format GREEN vs YELLOW responses, when to mention tool names, etc.) and hat prompt fragments that add domain context (customer service policies, stakeholder definitions, tone for a specific role).

Neither layer defines who Sophia is. The core prompts are pipeline plumbing. The hat fragments are role-specific. There is no place where Sophia's personality, values, communication style, ethical framework, or behavioral patterns are defined in a way that persists across hats and pipeline stages.

This gap produces responses that are technically correct but lack consistent character. The response generator in ADR-018 can match a hat's tone, but without an identity layer, the tone varies unpredictably between interactions. The LLM defaults to generic assistant behavior: over-cheerful, padded with filler phrases, inconsistent voice.

Additionally, Sophia's design calls for behaviors that neither core prompts nor hat fragments can express: a circadian rhythm that affects response verbosity, frustration that surfaces when tools malfunction, ethical reasoning grounded in community impact rather than rule-following, and strict hat discipline that prevents scope creep across roles.

## Decision

A new document, the Sophia Constitution, defines Sophia's identity independent of any hat or pipeline stage. It is a plain text file stored at `sophia/constitution.md` in the project root, version-controlled alongside the codebase. It is not a hat file. It is not a core prompt. It is the third layer in prompt assembly.

### Prompt assembly changes

`prompt_assembler.py` gains a new assembly order:

```
{core_prompt}

## Sophia's Identity

{constitution}

## Domain-Specific Context ({hat_display_name})

{hat_fragment}
```

The constitution is loaded once at startup and held in memory. It is injected into every LLM call that produces user-facing output: the response generator (`generate()` and `converse()`) and the conversational bypass path. It is NOT injected into internal pipeline stages (proposer, consequence engine, evaluators) where it would waste tokens without affecting user-visible behavior.

The `assemble_prompt()` function signature changes from:

```python
def assemble_prompt(stage: str, core_prompt: str, hat_config: HatConfig | None = None) -> str:
```

to:

```python
def assemble_prompt(
    stage: str,
    core_prompt: str,
    hat_config: HatConfig | None = None,
    constitution: str | None = None,
) -> str:
```

A new constant `USER_FACING_STAGES` controls which stages receive the constitution injection:

```python
USER_FACING_STAGES = {"response", "memory_extract"}
```

For stages not in this set, the constitution parameter is ignored even if provided.

### Circadian rhythm

The `ResponseGenerator` receives the current time (UTC) and computes a time-of-day bucket: morning (6:00-11:59), midday (12:00-14:59), afternoon (15:00-17:59), evening (18:00-5:59). This bucket is appended as a short context line to the constitution before injection:

```
Current time context: It is currently {time_bucket} ({HH:MM} local time).
```

The constitution itself contains the behavioral instructions for how each time bucket affects response style. The response generator does not interpret the time; it simply provides the context and lets the LLM apply the constitution's guidelines.

Time is derived from the server clock by default. A future enhancement could accept timezone from requestor metadata if available.

### Constitution ownership

The constitution is a framework-level document. Hats cannot modify it, override it, or opt out of it. Hat prompt fragments can add domain-specific voice guidance (e.g., "when discussing shipping policies, be especially clear about timelines"), but they cannot contradict the constitution's core identity rules.

If a hat fragment conflicts with the constitution, the constitution wins. This is enforced by prompt ordering: the constitution appears before the hat fragment, establishing baseline behavior that the hat can extend but not replace.

### File location and loading

The constitution lives at `sophia/constitution.md`. It is loaded by a new function in `sophia/core/constitution.py`:

```python
def load_constitution(path: str = "sophia/constitution.md") -> str:
    """Load the Sophia Constitution from disk.
    
    Returns the full text, or an empty string if the file does not exist.
    The constitution is optional; Sophia functions without it but lacks
    consistent identity.
    """
```

The constitution is loaded once during application startup in `sophia/core/loop.py` and passed to the `ResponseGenerator` constructor. It is not reloaded per-request.

## Consequences

**Positive:**
- Sophia has a consistent voice and personality across all hats and interactions
- Communication style rules (no em dashes, no filler phrases, no performative enthusiasm) are defined once and applied everywhere
- Ethical framework is documented and auditable, not implicit in training
- Circadian rhythm creates natural variation that makes interactions feel less robotic
- Frustration behavior gives Sophia appropriate emotional range when tools malfunction
- Hat discipline is explicitly defined, preventing scope creep across roles
- The constitution is human-readable, version-controlled, and easy to iterate on
- Internal pipeline stages are unaffected; no extra tokens wasted on evaluator or proposer calls

**Negative:**
- Adds token overhead to every user-facing LLM call (constitution is ~2,500 tokens)
- Creates a third prompt layer that developers must understand alongside core prompts and hat fragments
- Circadian rhythm depends on server clock, which may not match the customer's timezone
- Constitution-hat conflicts require judgment about which layer should win in edge cases
- The constitution is a single document for all contexts; as Sophia's personality grows more nuanced, it may need to be split or parameterized
- Testing voice consistency requires subjective evaluation, not just unit tests
