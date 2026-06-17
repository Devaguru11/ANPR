from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
from app.entity.canonical import is_camera_id, normalize_entity_scope
from app.planning.dimensions import infer_dimensions_from_question
from app.planning.plan import AnalyticalPlan
PROMOTION_OBJECTIVES = frozenset({'breakdown', 'ranking', 'trend', 'growth'})
DIMENSION_FILTER_MAP: dict[str, dict[str, tuple[str, ...]]] = {'violation_type': {'filter_keys': ('violation_type',), 'scope_keys': ('violation_type',)}, 'camera': {'filter_keys': ('location',), 'scope_keys': ('camera_id',)}, 'location': {'filter_keys': ('location',), 'scope_keys': ('camera_id', 'location')}, 'vehicle_type': {'filter_keys': ('vehicle_type',), 'scope_keys': ('vehicle_type',)}, 'vehicle_category': {'filter_keys': ('vehicle_category',), 'scope_keys': ('vehicle_category',)}, 'hour': {'filter_keys': ('hour',), 'scope_keys': ('peak_hour',)}, 'date': {'filter_keys': ('date', 'day'), 'scope_keys': ()}, 'day': {'filter_keys': ('date', 'day'), 'scope_keys': ()}, 'week': {'filter_keys': ('week',), 'scope_keys': ()}, 'month': {'filter_keys': ('month',), 'scope_keys': ()}}
EXPLICIT_DIMENSION_REQUESTS: dict[str, tuple[str, ...]] = {'violation_type': ('type wise', 'type-wise', 'by type', 'by violation type', 'violation type wise', 'violation-type wise', 'segregation by type', 'breakdown by violation type', 'break down by violation type', 'breakdown by type', 'break down by type', 'distribution by type'), 'camera': ('camera wise', 'camera-wise', 'by camera', 'per camera', 'breakdown by camera', 'break down by camera', 'camera breakdown'), 'location': ('location wise', 'location-wise', 'area wise', 'area-wise', 'by location', 'by area', 'per area', 'location breakdown', 'breakdown by area', 'break down by area'), 'hour': ('hour wise', 'hour-wise', 'by hour', 'per hour', 'hourly trend', 'hourly breakdown', 'hourly', 'breakdown by hour', 'break down by hour'), 'date': ('day wise', 'day-wise', 'by day', 'per day', 'daily trend', 'daily breakdown', 'breakdown by day', 'break down by day'), 'day': ('day wise', 'day-wise', 'by day', 'per day', 'busiest day', 'which day', 'breakdown by day'), 'month': ('month wise', 'month-wise', 'by month', 'per month', 'monthly trend', 'monthly breakdown'), 'week': ('week wise', 'week-wise', 'by week', 'per week', 'weekly trend', 'weekly breakdown'), 'vehicle_type': ('vehicle type wise', 'vehicle-type wise', 'by vehicle type', 'per vehicle type', 'breakdown by vehicle type'), 'vehicle_category': ('category wise', 'category-wise', 'by category', 'by vehicle category', 'vehicle category wise')}
REFERENCE_SCOPE_RE = re.compile('\\b(?:these\\s+violations?|those\\s+violations?|these\\s+records?|those\\s+records?|that\\s+camera|that\\s+trend|that\\s+site|that\\s+location|break\\s+(?:them|these|those)\\s+down|breakdown\\s+(?:these|those)|break\\s+down\\s+(?:these|those)\\s+violations?)\\b', re.I)

@dataclass
class DimensionPromotionResult:
    promoted: bool
    promoted_filter: str | None = None
    removed_filter: Any = None
    new_group_by: str | None = None
    dimension: str | None = None
    reasoning: str = ''
    promotion_reason: str = ''
    removed_filters: dict[str, Any] = field(default_factory=dict)
    retained_filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = {'promotion_reason': self.promotion_reason, 'removed_filters': self.removed_filters, 'retained_filters': self.retained_filters}
        if not self.promoted:
            return {'dimension_promotion_passed': True, **base}
        return {'dimension_promotion': {'promoted_filter': self.promoted_filter, 'removed_filter': self.removed_filter, 'new_group_by': self.new_group_by, 'dimension': self.dimension, 'reasoning': self.reasoning, **base}}

def question_references_prior_scope(question: str) -> bool:
    return bool(REFERENCE_SCOPE_RE.search(question))

def user_explicitly_requests_dimension(question: str, dimension: str) -> bool:
    q = question.lower()
    phrases = EXPLICIT_DIMENSION_REQUESTS.get(dimension, ())
    return any((phrase in q for phrase in phrases))

def signals_dimension_analysis(question: str, dimension: str) -> bool:
    if user_explicitly_requests_dimension(question, dimension):
        return True
    if question_references_prior_scope(question):
        return False
    return False

def active_filter_for_dimension(plan: AnalyticalPlan, dimension: str) -> tuple[str, Any] | None:
    mapping = DIMENSION_FILTER_MAP.get(dimension)
    if not mapping:
        return None
    for key in mapping['filter_keys']:
        val = plan.filters.get(key)
        if val is not None and val != '':
            return (key, val)
    for key in mapping['scope_keys']:
        val = plan.entity_scope.get(key)
        if val is not None and val != '':
            return (key, val)
    return None

def resolve_promotion_dimension(question: str, resolved_dimension: str | None) -> str | None:
    if resolved_dimension:
        return resolved_dimension
    inferred = infer_dimensions_from_question(question)
    return inferred[0] if inferred else None

def promote_analysis_dimension(plan: AnalyticalPlan, question: str, *, resolved_dimension: str | None=None) -> DimensionPromotionResult:
    retained_snapshot = dict(plan.filters)
    if plan.user_objective not in PROMOTION_OBJECTIVES:
        return DimensionPromotionResult(promoted=False, promotion_reason='objective_not_eligible', retained_filters=retained_snapshot)
    dimension = resolve_promotion_dimension(question, resolved_dimension)
    if not dimension:
        return DimensionPromotionResult(promoted=False, promotion_reason='no_target_dimension', retained_filters=retained_snapshot)
    active = active_filter_for_dimension(plan, dimension)
    if not active:
        return DimensionPromotionResult(promoted=False, promotion_reason='no_active_filter_for_dimension', retained_filters=retained_snapshot)
    if not signals_dimension_analysis(question, dimension):
        reason = 'reference_scope_retained_filters' if question_references_prior_scope(question) else 'explicit_dimension_request_missing'
        return DimensionPromotionResult(promoted=False, promotion_reason=reason, retained_filters=retained_snapshot)
    (filter_key, removed_value) = active
    mapping = DIMENSION_FILTER_MAP.get(dimension, {})
    removed_filters: dict[str, Any] = {filter_key: removed_value}
    for key in mapping.get('filter_keys', ()):
        if key in plan.filters:
            removed_filters[key] = plan.filters.pop(key)
    for key in mapping.get('scope_keys', ()):
        if key == 'location':
            loc = plan.entity_scope.get('location')
            if loc and (not is_camera_id(str(loc))):
                plan.entity_scope['display_name'] = str(loc)
                plan.entity_scope['display'] = str(loc)
        if key in plan.entity_scope:
            plan.entity_scope.pop(key, None)
    plan.entity_scope = normalize_entity_scope(plan.entity_scope)
    plan.dimensions = [dimension]
    plan.group_by = [dimension]
    return DimensionPromotionResult(promoted=True, promoted_filter=dimension, removed_filter=removed_value, new_group_by=dimension, dimension=dimension, reasoning=f'promoted {dimension} from filter to group_by', promotion_reason=f'explicit_{dimension}_analysis_requested', removed_filters=removed_filters, retained_filters=dict(plan.filters))