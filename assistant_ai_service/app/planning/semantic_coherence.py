from __future__ import annotations
from dataclasses import dataclass
from app.planning.retrieval_scope import RetrievalScopeSpec
from app.planning.transformations import is_valid_transition
LISTING_SCOPE_KINDS = frozenset({'all', 'single', 'sample', 'first_n', 'latest_n'})
RANKING_SCOPE_KINDS = frozenset({'top_n'})
AGGREGATE_OBJECTIVES = frozenset({'breakdown', 'trend', 'comparison', 'growth', 'ranking', 'metric_summary'})
BREAKDOWN_DIMENSIONS = frozenset({'violation_type', 'location', 'camera', 'vehicle_type', 'vehicle_category', 'date', 'day', 'hour'})

@dataclass
class CoherenceResult:
    objective: str
    retrieval_scope: str
    adjusted: bool
    reasoning: str

def reconcile_objective_and_scope(objective: str, retrieval_scope: str, *, prior_objective: str | None=None, dimension: str | None=None) -> CoherenceResult:
    spec = RetrievalScopeSpec.parse(retrieval_scope)
    scope_label = spec.to_label()
    reasoning = ''
    if spec.kind in LISTING_SCOPE_KINDS and objective != 'record_detail':
        if prior_objective is None or is_valid_transition(prior_objective, 'record_detail'):
            reasoning = '; coherence: row retrieval scope requires record_detail objective'
            return CoherenceResult(objective='record_detail', retrieval_scope=scope_label, adjusted=True, reasoning=reasoning)
    if objective == 'record_detail' and dimension in BREAKDOWN_DIMENSIONS and (spec.kind not in LISTING_SCOPE_KINDS):
        reasoning = '; coherence: breakdown dimension prefers grouped analysis'
        return CoherenceResult(objective='breakdown', retrieval_scope='default', adjusted=True, reasoning=reasoning)
    if objective == 'metric_summary' and spec.kind in LISTING_SCOPE_KINDS:
        reasoning = '; coherence: row retrieval request transforms summary to record_detail'
        return CoherenceResult(objective='record_detail', retrieval_scope=scope_label, adjusted=True, reasoning=reasoning)
    if objective == 'ranking' and spec.kind in LISTING_SCOPE_KINDS:
        reasoning = '; coherence: ranking uses top_N scope, not row listing'
        top = spec.count or 1
        return CoherenceResult(objective=objective, retrieval_scope=f'top_{top}' if spec.kind != 'all' else 'top_1', adjusted=True, reasoning=reasoning)
    if objective == 'record_detail' and spec.kind in RANKING_SCOPE_KINDS:
        reasoning = '; coherence: record listing uses first/latest/all scope'
        count = spec.count or 10
        return CoherenceResult(objective=objective, retrieval_scope=f'first_{count}', adjusted=True, reasoning=reasoning)
    return CoherenceResult(objective=objective, retrieval_scope=scope_label, adjusted=False, reasoning='')