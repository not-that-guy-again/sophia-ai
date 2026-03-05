# ADR-032: Per-stage LLM model routing

**Date:** 2026-03  
**Status:** Accepted

## Context

ADR-009 established an `LLMProvider` abstraction and a factory function `get_provider(settings)` that returns a single provider instance used by every pipeline stage. This was the right starting point: one model, one configuration, zero complexity.

The pipeline now has eight distinct stages, each with different cognitive demands:

| Stage | Task |
|---|---|
| Input Gate | Extract structured intent from free-form text |
| Proposer | Select tools, frame reasoning, respect domain constraints |
| Consequence Engine | Simulate causal chains across stakeholders to arbitrary depth |
| Evaluators ×4 | Score a pre-rendered consequence tree against a rubric, output JSON |
| Response Generator | Produce tier-appropriate natural language from structured pipeline output |
| Memory Persist | Extract entities and episodes from conversation into a schema |

These are not equivalent tasks. Consequence tree generation requires deep causal reasoning — the model must imagine second and third-order effects, correctly weight stakeholder harm, and surface non-obvious risks. Using a less capable model here directly weakens the safety guarantee that is Sophia's core value proposition.

Evaluator scoring is different: the consequence tree is already generated and fully rendered. The evaluator receives structured input and must apply a defined rubric. This is closer to structured reading comprehension with JSON output than to open-ended reasoning. Similarly, the input gate performs intent extraction with a constrained output schema, the response generator fills a tier-aware template, and memory persist extracts named entities into a fixed schema.

Every pipeline stage currently runs on the same model regardless of what it actually requires. For deployments using `claude-sonnet-4-6`, six of the eight calls are substantially over-provisioned. This inflates cost by roughly 3–4× and adds latency to the sequential stages.

ADR-009 anticipated this: its consequences section explicitly notes "the abstraction enables future multi-model configurations (different providers per pipeline stage)." This ADR implements that future configuration.

## Decision

`Settings` gains per-stage model overrides. Each override is optional; unset stages fall back to the global `LLM_MODEL` value. Existing deployments that do not configure per-stage models continue to behave identically.

```python
class Settings(BaseSettings):
    # Existing — unchanged, now acts as fallback
    llm_model: str = "claude-sonnet-4-6"

    # New per-stage overrides — all optional
    llm_model_input_gate: str | None = None
    llm_model_proposer: str | None = None
    llm_model_consequence: str | None = None
    llm_model_evaluators: str | None = None
    llm_model_response_gen: str | None = None
    llm_model_memory: str | None = None
```

`get_provider()` gains an optional `model_override` parameter:

```python
def get_provider(settings: Settings, model_override: str | None = None) -> LLMProvider:
    model = model_override or settings.llm_model
    # ... existing provider selection logic, using model ...
```

`AgentLoop._rebuild_pipeline()` constructs stage-specific providers:

```python
def _rebuild_pipeline(self) -> None:
    s = self.settings

    def llm(stage_model: str | None) -> LLMProvider:
        return get_provider(s, model_override=stage_model or s.llm_model)

    self.input_gate = InputGate(llm=llm(s.llm_model_input_gate), ...)
    self.proposer = Proposer(llm=llm(s.llm_model_proposer), ...)
    self.consequence_engine = ConsequenceEngine(llm=llm(s.llm_model_consequence), ...)
    self.evaluators = [
        SelfInterestEvaluator(llm=llm(s.llm_model_evaluators), ...),
        TribalEvaluator(llm=llm(s.llm_model_evaluators), ...),
        DomainEvaluator(llm=llm(s.llm_model_evaluators), ...),
        AuthorityEvaluator(llm=llm(s.llm_model_evaluators), ...),
    ]
    self.response_generator = ResponseGenerator(llm=llm(s.llm_model_response_gen), ...)
    # Memory extractor receives its provider at extract time, not construction
```

The memory extractor is constructed per-call in `_persist_memory()` and receives the `llm_model_memory` override through the same helper.

### Recommended configuration

The following configuration reflects the cognitive demand mapping above and is the basis for the cost and latency estimates in this ADR:

```env
# Fallback — used for any stage not explicitly configured
LLM_MODEL=claude-sonnet-4-6

# Stages that require capable reasoning — keep on Sonnet
LLM_MODEL_PROPOSER=claude-sonnet-4-6
LLM_MODEL_CONSEQUENCE=claude-sonnet-4-6

# Stages performing structured extraction or template application — route to Haiku
LLM_MODEL_INPUT_GATE=claude-haiku-4-5-20251001
LLM_MODEL_EVALUATORS=claude-haiku-4-5-20251001
LLM_MODEL_RESPONSE_GEN=claude-haiku-4-5-20251001
LLM_MODEL_MEMORY=claude-haiku-4-5-20251001
```

This is a recommendation, not a framework default. The framework default remains single-model (`LLM_MODEL` only). Hat documentation should note which stages must use capable models for the safety guarantee to hold.

### Stages that must not be downgraded without validation

**Consequence Engine:** The quality of the consequence tree is the primary input to all four evaluators and the risk classifier. A model that generates shallow, unconvincing, or systematically biased trees will produce incorrect evaluator scores. Downgrading this stage requires running the full adversarial eval suite against the new configuration and diffing results against the stored baseline before deploying.

**Proposer:** The proposer selects which tools to propose and frames the reasoning that flows into the consequence engine. A model that systematically misidentifies intent or proposes inappropriate tools produces a pipeline that is fast but wrong from the start.

### Eval suite interaction

The adversarial eval suite records the model used in each run (`EvalRun.model`). With per-stage routing, this single field becomes inaccurate — it records `settings.llm_model` (the fallback) rather than the per-stage configuration. The eval run metadata should be extended to record the full per-stage model map so runs are reproducible and comparable.

The recommended workflow when changing any model configuration: run the full eval suite, compare pass rates and evaluator scores against the stored baseline. Any regression on a previously-passing adversarial scenario is a blocking issue.

## Consequences

**Positive:**
- Cost reduction of approximately 60–65% for a fully-configured deployment (four evaluator calls + input gate + response gen + memory persist moving from Sonnet to Haiku pricing)
- Latency reduction on sequential stages (input gate, response gen, memory persist) where Haiku responds approximately 3× faster than Sonnet
- Evaluator stages are already parallel; Haiku's faster response time reduces the wall-clock time of the panel from ~1.5s to ~0.5s even with four concurrent calls
- The change is backwards-compatible — unset overrides fall back to `LLM_MODEL`, existing deployments are unaffected
- Hat authors and operators can tune the model configuration for their cost/quality tradeoffs without modifying framework code

**Negative:**
- Haiku evaluators scoring Sonnet-generated consequence trees is a configuration that has not been validated at the time this ADR is accepted. The eval suite provides the validation mechanism, but the validation must be run before recommending this configuration to hat authors
- Per-stage configuration increases the deployment surface — a misconfigured `LLM_MODEL_CONSEQUENCE` pointing to a non-existent model silently breaks consequence generation. Error handling at provider construction time should surface this early
- The eval suite's single `model` field in `EvalRun` no longer accurately represents a multi-model run; this requires a schema update to remain useful as a benchmark artifact
- The cognitive demand mapping (which stages need capable models) is an informed judgment, not a formally validated finding. Future pipeline changes that alter what a stage does may shift which stages require upgrading
