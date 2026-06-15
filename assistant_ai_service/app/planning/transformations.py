from __future__ import annotations
import re
from typing import FrozenSet
from app.planning.retrieval_scope import RetrievalScopeSpec
TRANSITIONS: dict[str, FrozenSet[str]] = {'metric_summary': frozenset({'breakdown', 'trend', 'comparison', 'ranking', 'record_detail'}), 'breakdown': frozenset({'trend', 'record_detail', 'ranking', 'metric_summary'}), 'trend': frozenset({'record_detail', 'metric_summary', 'breakdown', 'ranking', 'growth'}), 'comparison': frozenset({'growth', 'ranking', 'trend', 'breakdown'}), 'ranking': frozenset({'record_detail', 'growth', 'breakdown', 'trend', 'metric_summary'}), 'growth': frozenset({'trend', 'record_detail', 'ranking', 'breakdown'}), 'record_detail': frozenset({'metric_summary', 'breakdown', 'ranking'})}
LISTING_SCOPE_KINDS = frozenset({'all', 'single', 'sample', 'first_n', 'latest_n'})
TRANSFORMATION_CUE_PHRASES: tuple[str, ...] = ('these', 'those', 'them', 'of these', 'show records', 'show details', 'first 10', 'first 5', 'first 20', 'latest', 'examples', 'list them', 'list those', 'give me first', 'show first')
TRANSFORMATION_CONFIDENCE_BOOST = 0.18

def is_valid_transition(from_objective: str | None, to_objective: str) -> bool:
    if not from_objective:
        return True
    allowed = TRANSITIONS.get(from_objective, frozenset())
    return to_objective == from_objective or to_objective in allowed

def transformation_label(from_objective: str | None, to_objective: str) -> dict[str, str] | None:
    if not from_objective or from_objective == to_objective:
        return None
    return {'from': from_objective, 'to': to_objective}

def signals_transformation_intent(question: str) -> bool:
    q = question.lower()
    if any((phrase in q for phrase in TRANSFORMATION_CUE_PHRASES)):
        return True
    if re.search('\\bfirst\\s+\\d+\\b', q):
        return True
    if re.search('\\blatest\\s+\\d+\\b', q):
        return True
    return False

def infer_transformation_objective(prior_objective: str | None, question: str, retrieval_scope: str='default') -> str | None:
    if not prior_objective:
        return None
    q = question.lower()
    spec = RetrievalScopeSpec.parse(retrieval_scope)
    if spec.kind in LISTING_SCOPE_KINDS and is_valid_transition(prior_objective, 'record_detail'):
        return 'record_detail'
    if prior_objective == 'metric_summary':
        breakdown_cues = ('segregation', 'breakdown', 'type wise', 'by type', 'distribution', 'split', 'categor', 'break these', 'break down')
        if any((cue in q for cue in breakdown_cues)) and is_valid_transition(prior_objective, 'breakdown'):
            return 'breakdown'
        ranking_cues = ('most', 'highest', 'top ', 'which camera', 'which area', 'peak hour', 'busiest')
        if any((cue in q for cue in ranking_cues)) and is_valid_transition(prior_objective, 'ranking'):
            return 'ranking'
        trend_cues = ('trend', 'over time', 'daily', 'over the last')
        if any((cue in q for cue in trend_cues)) and is_valid_transition(prior_objective, 'trend'):
            return 'trend'
    if prior_objective == 'breakdown':
        ranking_cues = ('biggest problem', 'main problem', 'worst', 'main issue', 'biggest issue', 'most serious')
        if any((cue in q for cue in ranking_cues)) and is_valid_transition(prior_objective, 'ranking'):
            return 'ranking'
        if signals_transformation_intent(question) and is_valid_transition(prior_objective, 'record_detail'):
            return 'record_detail'
    if prior_objective == 'comparison':
        growth_cues = ('increased', 'increase', 'growth', 'grew', 'fastest growing', 'largest increase')
        if any((cue in q for cue in growth_cues)) and is_valid_transition(prior_objective, 'growth'):
            return 'growth'
    if prior_objective in {'trend', 'ranking', 'growth', 'breakdown'} and signals_transformation_intent(question):
        if is_valid_transition(prior_objective, 'record_detail'):
            return 'record_detail'
    return None

def apply_transformation_confidence_boost(prior_objective: str | None, objective: str, confidence: float, question: str, retrieval_scope: str='default') -> tuple[str, float, str]:
    if not prior_objective:
        return (objective, confidence, '')
    reasoning = ''
    proposed = objective
    inferred = infer_transformation_objective(prior_objective, question, retrieval_scope)
    if proposed == prior_objective:
        if inferred and inferred != prior_objective:
            proposed = inferred
            confidence = max(confidence, 0.72)
            reasoning = f'; transformation boost: inferred {prior_objective}→{proposed}'
    elif is_valid_transition(prior_objective, proposed):
        if signals_transformation_intent(question) or inferred == proposed:
            confidence = min(1.0, confidence + TRANSFORMATION_CONFIDENCE_BOOST)
            reasoning = f'; transformation boost: {prior_objective}→{proposed}'
    return (proposed, confidence, reasoning)