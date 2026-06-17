from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
from app.planning.dimensions import infer_dimensions_from_question
from app.planning.objectives import default_objective
from app.planning.retrieval_scope import RetrievalScopeSpec, infer_listing_scope_from_question
from app.planning.transformations import infer_transformation_objective
RECORD_DETAIL_EVIDENCE_PHRASES: tuple[str, ...] = ('show records', 'show first', 'show latest', 'list them', 'list those', 'give examples', 'give me examples', 'show details', 'show detail', 'show those records', 'show these records', 'show violations during that hour', 'during that hour at', 'export', 'all vehicle numbers', 'all plate', 'vehicle numbers ending', 'show plate reads', 'list plate reads', 'show one example', 'list records', 'show the records', 'first 10 records', 'latest 10', 'show those violations', 'show these violations', 'drill into those', 'list first', 'give me first')
LISTING_SCOPE_KINDS = frozenset({'all', 'single', 'sample', 'first_n', 'latest_n'})
AGGREGATE_OBJECTIVE_ORDER = ('metric_summary', 'breakdown', 'ranking', 'trend', 'comparison', 'growth')

@dataclass
class ObjectivePolicyTelemetry:
    record_detail_without_evidence: bool = False
    metric_summary_missed: bool = False
    demoted_from: str | None = None
    promoted_to: str | None = None
    had_record_detail_evidence: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {'record_detail_without_evidence': self.record_detail_without_evidence, 'metric_summary_missed': self.metric_summary_missed, 'demoted_from': self.demoted_from, 'promoted_to': self.promoted_to, 'had_record_detail_evidence': self.had_record_detail_evidence, 'notes': self.notes}

def _explicit_row_retrieval_language(question: str) -> bool:
    q = question.lower().strip()
    if not q:
        return False
    if infer_listing_scope_from_question(question):
        return True
    if any((phrase in q for phrase in RECORD_DETAIL_EVIDENCE_PHRASES)):
        return True
    if re.search('\\b(?:show|list|give)\\s+(?:me\\s+)?(?:the\\s+)?records?\\b', q):
        return True
    if re.search('\\bshow\\s+(?:first|latest)\\s+\\d+\\b', q):
        return True
    if re.search('\\b(?:give|list)\\s+(?:me\\s+)?all\\b', q):
        return True
    return False

def has_record_detail_evidence(question: str, retrieval_scope: str='default') -> bool:
    del retrieval_scope
    if _explicit_row_retrieval_language(question):
        return True
    if signals_count_summary_intent(question):
        return False
    return False

def signals_count_summary_intent(question: str) -> bool:
    q = question.lower()
    if any((p in q for p in ('how many', 'count ', 'total ', 'number of'))):
        return True
    if re.search('\\bshow\\s+violations?\\s+at\\b', q):
        return True
    if re.search('\\bviolations?\\s+at\\b', q) and (not _explicit_row_retrieval_language(question)):
        return True
    if re.search('\\bshow\\s+violations?\\s+(?:today|yesterday|this\\s+week|this\\s+month)\\b', q):
        return True
    return False

def infer_preferred_aggregate_objective(question: str, *, prior_objective: str | None=None, retrieval_scope: str='default') -> str:
    if prior_objective and prior_objective != 'record_detail':
        inferred = infer_transformation_objective(prior_objective, question, retrieval_scope)
        if inferred and inferred != 'record_detail':
            return inferred
    q = question.lower()
    breakdown_cues = ('breakdown', 'break down', 'type wise', 'by type', 'segregation', 'distribution', 'split', 'category wise')
    ranking_cues = ('most', 'highest', 'top ', 'which camera', 'which area', 'peak hour', 'busiest', 'worst', 'biggest problem')
    trend_cues = ('trend', 'over time', 'daily', 'last 7 days', 'pattern', 'movement')
    comparison_cues = ('compare', ' versus ', ' vs ', 'compared to')
    growth_cues = ('increased', 'growth', 'grew', 'fastest growing')
    if any((c in q for c in ranking_cues)):
        return 'ranking'
    if any((c in q for c in breakdown_cues)) or infer_dimensions_from_question(question):
        return 'breakdown'
    if any((c in q for c in trend_cues)):
        return 'trend'
    if any((c in q for c in comparison_cues)):
        return 'comparison'
    if any((c in q for c in growth_cues)):
        return 'growth'
    if signals_count_summary_intent(question):
        return 'metric_summary'
    return default_objective()

def apply_objective_evidence_policy(objective: str, question: str, *, retrieval_scope: str='default', prior_objective: str | None=None, resolution_tier: str='') -> tuple[str, str, ObjectivePolicyTelemetry]:
    telemetry = ObjectivePolicyTelemetry()
    current = objective
    tier = resolution_tier
    has_evidence = has_record_detail_evidence(question, retrieval_scope)
    telemetry.had_record_detail_evidence = has_evidence
    if signals_count_summary_intent(question) and current != 'metric_summary':
        if current == 'record_detail' and (not has_evidence):
            telemetry.metric_summary_missed = True
    if current == 'record_detail' and (not has_evidence):
        replacement = infer_preferred_aggregate_objective(question, prior_objective=prior_objective, retrieval_scope=retrieval_scope)
        telemetry.record_detail_without_evidence = True
        telemetry.demoted_from = 'record_detail'
        telemetry.promoted_to = replacement
        telemetry.notes.append(f'demoted record_detail→{replacement} (no row-retrieval evidence)')
        current = replacement
        tier = 'objective_evidence_policy'
        if retrieval_scope != 'default' and RetrievalScopeSpec.parse(retrieval_scope).kind in LISTING_SCOPE_KINDS:
            retrieval_scope = 'default'
            telemetry.notes.append('cleared listing retrieval_scope without evidence')
    return (current, tier, telemetry)