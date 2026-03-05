# ADR-033: Consequence tree caching

**Date:** 2026-03  
**Status:** Accepted

## Context

The consequence engine (ADR-003) generates a depth-first consequence tree for each proposed candidate action via an LLM call. This is the most reasoning-intensive stage in the pipeline and typically the most expensive in both cost and latency.

In practice, a deployed Hat sees a narrow distribution of action types. A customer service deployment handling 1,000 interactions per day is not making 1,000 distinct kinds of decisions — it is making variations of a small set: check order status, issue refund, apply discount, escalate to human, update shipping address. The consequence tree for `check_order_status` with `{"order_id": "ORD-12345"}` and the consequence tree for `check_order_status` with `{"order_id": "ORD-99999"}` are structurally identical. The consequences of looking up an order do not depend on which order is being looked up.

The consequence tree models what *type* of action does to the world, not the specific parameter values. This is a deliberate property of the tree design (ADR-003): nodes describe categories of outcome ("customer receives accurate information," "unauthorized data exposure") rather than instance-specific results ("customer learns order 12345 shipped"). Parameter values are inputs to tool execution, which happens after evaluation; they should not materially change the consequence structure for most tools.

Regenerating structurally identical trees on every interaction is unnecessary and expensive.

## Decision

`ConsequenceEngine` gains an in-memory LRU cache keyed on `(tool_name, parameter_shape, hat_name)`. Cache hits return the stored tree immediately without an LLM call. Cache misses generate normally and populate the cache.

### Cache key design

The cache key captures what varies between consequence trees — the tool being called and the shape of its parameters — without capturing the specific parameter values, which are typically unique per interaction but do not change the tree structure:

```python
def _cache_key(self, candidate: CandidateAction, hat_name: str) -> str:
    # Normalize: keep parameter keys and value types, discard values
    param_shape = {
        key: type(value).__name__
        for key, value in sorted(candidate.parameters.items())
    }
    return f"{hat_name}:{candidate.tool_name}:{json.dumps(param_shape, sort_keys=True)}"
```

`check_order_status(order_id="ORD-12345")` and `check_order_status(order_id="ORD-99999")` both produce key `customer-service:check_order_status:{"order_id": "str"}`. They share a cache entry.

`offer_partial_refund(order_id="ORD-123", amount=25.00)` and `offer_partial_refund(order_id="ORD-456", amount=200.00)` both produce `customer-service:offer_partial_refund:{"amount": "float", "order_id": "str"}`. They share a cache entry.

If a tool's parameters include a value whose type changes meaningfully across calls (e.g., `amount` being `int` sometimes and `float` other times), the keys will diverge. This is acceptable — type-based keying is conservative rather than aggressive.

### Candidate rebinding on cache hit

When a cached tree is returned, the `candidate_action` stored in the tree is the original candidate from the cache-populating call. This must be replaced with the actual candidate from the current interaction so the audit trail shows the correct parameters:

```python
async def analyze(self, candidate: CandidateAction) -> ConsequenceTree:
    hat_name = self.hat_config.name if self.hat_config else "default"
    key = self._cache_key(candidate, hat_name)

    cached = self._cache.get(key)
    if cached and not self._is_expired(cached):
        cached.hit_count += 1
        logger.debug("Cache hit for %s (hits=%d)", key, cached.hit_count)
        return dataclasses.replace(cached.tree, candidate_action=candidate)

    tree = await self._generate(candidate)
    self._cache[key] = CachedTree(tree=tree, cached_at=time.monotonic())
    return tree
```

The `dataclasses.replace()` creates a shallow copy bound to the new candidate. The tree structure (nodes, scores, analysis) is shared with the cached entry. The `candidate_action` field on the returned tree correctly identifies the specific candidate from this interaction.

### TTL strategy

The cache uses a configurable TTL with a default of 3600 seconds (one hour). Cache entries older than the TTL are treated as misses and regenerated.

The default TTL is a starting point. Hat authors can declare a per-tool TTL override to tune for their tool's policy sensitivity:

```python
class Tool(ABC):
    # ... existing attributes ...
    consequence_cache_ttl: int | None = None  # seconds; None = use engine default
```

Guidance for hat authors:

- **`None` (use engine default, 3600s):** Most tools. Lookup, status check, standard workflow tools.
- **Short TTL (300–900s):** Tools whose consequence trees reflect current policy that may be updated frequently. Refund tools, compensation tools, discount tools.
- **`0` (no caching):** Tools where specific parameter values genuinely change the consequence structure. Rare — most parameterization is instance-level, not structure-level. An example would be a tool that takes a free-form `reason` field that meaningfully changes what downstream consequences are plausible.

### Cache invalidation on hat re-equip

The cache is scoped to the `ConsequenceEngine` instance. When a hat is re-equipped (via `AgentLoop.equip_hat()`), `_rebuild_pipeline()` creates a new `ConsequenceEngine` instance, which starts with an empty cache. This ensures that changes to hat configuration, stakeholder definitions, or constraint files take effect immediately on the next interaction after re-equip.

Cache entries from a previous hat equip are not carried forward.

### Cache statistics in `PipelineResult`

Cache hit/miss data is surfaced in the pipeline metadata for observability:

```python
# PipelineResult.metadata gains:
{
    "consequence_cache": {
        "hits": 2,      # trees returned from cache this run
        "misses": 1,    # trees generated fresh this run
        "keys_hit": ["customer-service:check_order_status:..."]
    }
}
```

This enables operators to measure actual hit rates in production and tune TTLs accordingly.

### What is not cached

`ConsequenceEngine.analyze_situation()` (ADR-030) is not cached. Situation trees evaluate the danger of a specific incoming request and are by nature context-dependent. The adversarial scenarios that trigger situation evaluation are not high-volume repeat patterns; caching them provides little benefit and the risk of returning a stale situation assessment is not worth it.

## Consequences

**Positive:**
- After cache warmup, the most common action types in a production deployment pay consequence engine cost once per TTL period rather than on every interaction. For a deployment with 10 tool types and a 70% cache hit rate, consequence engine cost drops by 70%
- Cached interactions skip the most latency-intensive single LLM call in the pipeline. Combined with parallel tree generation (ADR-031), multi-candidate proposals where some candidates are cached are noticeably faster
- The eval suite benefits on repeated runs: second and third turns within chained adversarial scenarios hit the cache for the same tool types, reducing per-run cost and runtime
- Cache invalidation on hat re-equip is simple and predictable — no stale entries from old hat configurations
- Per-tool TTL override gives hat authors control over the cost/freshness tradeoff without requiring framework changes

**Negative:**
- The cache is in-memory and lost on process restart. A freshly-started server has cold cache and pays full generation cost until it warms. This is acceptable for the current single-process deployment model but means horizontal scaling produces multiple independent cold caches
- Cache entries are not invalidated when evaluator prompts, stakeholder definitions, or consequence prompts are updated without a hat re-equip. If the consequence engine's behavior is changed at the prompt level without re-equipping the hat, stale trees may be served until TTL expires. Hat authors who modify prompts should re-equip the hat to flush the cache
- The parameter-shape key is coarser than it could be. A tool that behaves substantially differently for `amount=5.00` (minor discount) versus `amount=500.00` (large refund) produces the same cache key and the same tree. Hat authors who need amount-sensitive consequence modeling should set a short TTL or disable caching for those tools, but this requires active awareness
- Cache hit statistics in `PipelineResult.metadata` require consumers of the API to handle a new metadata field. Existing consumers that do not inspect metadata are unaffected
