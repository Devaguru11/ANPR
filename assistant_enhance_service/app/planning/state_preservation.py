from __future__ import annotations
import copy
import re
from typing import Any
from app.entity.canonical import normalize_entity_scope
from app.planning.plan import AnalyticalPlan
from app.planning.temporal_resolver import TemporalResolver
STICKY_FILTER_KEYS = frozenset({'location', 'violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix', 'hour'})
STICKY_ENTITY_SCOPE_KEYS = frozenset({'camera_id', 'location', 'display', 'display_name', 'violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix', 'peak_hour'})
TRANSFORMABLE_PLAN_KEYS = frozenset({'user_objective', 'query_mode', 'dimensions', 'group_by', 'retrieval_scope', 'sort', 'limit', 'intent', 'compare_to'})
VIOLATION_CUES: tuple[tuple[str, str], ...] = (('no helmet', 'NO_HELMET'), ('no-helmet', 'NO_HELMET'), ('no_helmet', 'NO_HELMET'), ('triple riding', 'TRIPLE_RIDING'), ('triple-riding', 'TRIPLE_RIDING'), ('wrong route', 'WRONG_ROUTE'), ('wrong-route', 'WRONG_ROUTE'), ('wrong parking', 'WRONG_PARKING'), ('wrong-parking', 'WRONG_PARKING'))
LOCATION_CUES = ('chowking', 'luvers', 'baliwag', 'highway', 'market', 'at ')

def sticky_snapshot(plan: AnalyticalPlan | None) -> dict[str, Any]:
    if plan is None:
        return {}
    return {'metric': plan.metric, 'time_range': dict(plan.time_range or {}), 'filters': dict(plan.filters or {}), 'entity_scope': dict(plan.entity_scope or {})}

def question_mentions_time(question: str) -> bool:
    return TemporalResolver._question_mentions_time(question)

def question_mentions_violation_type(question: str) -> bool:
    q = question.lower()
    if any((cue in q for (cue, _) in VIOLATION_CUES)):
        return True
    return bool(re.search('\\b(?:no[_ -]?helmet|triple[_ -]?riding|wrong[_ -]?route|wrong[_ -]?parking)\\b', q))

def question_mentions_location(question: str) -> bool:
    q = question.lower()
    return any((cue in q for cue in LOCATION_CUES))

def question_mentions_plate_pattern(question: str) -> bool:
    q = question.lower()
    return bool(re.search('\\bending (?:with|in)\\b', q) or re.search('\\bplate(?:s)? ending\\b', q) or re.search('\\bplates? ending\\b', q))

def question_mentions_vehicle_type(question: str) -> bool:
    q = question.lower()
    return any((w in q for w in ('motorcycle', 'car', 'truck', 'bus', 'bicycle', 'two-wheeler', 'two wheeler')))

def time_range_equal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    return dict(a or {}) == dict(b or {})

def explicit_time_change(question: str, proposed: dict[str, Any], previous: dict[str, Any] | None) -> bool:
    from app.planning.temporal_override import question_has_explicit_time
    if question_has_explicit_time(question):
        return True
    if not previous:
        return bool(proposed)
    return False

def explicit_metric_change(question: str, proposed_metric: str, previous_metric: str | None, proposed_filters: dict[str, Any]) -> bool:
    if proposed_metric != previous_metric and previous_metric:
        if question_mentions_plate_pattern(question) or proposed_filters.get('plate_suffix'):
            return True
        if question_mentions_violation_type(question):
            return True
    if not previous_metric:
        return True
    if proposed_filters.get('plate_suffix') and question_mentions_plate_pattern(question):
        return True
    return proposed_metric != previous_metric and (question_mentions_plate_pattern(question) or 'plate' in question.lower() or 'vehicle' in question.lower() or ('detection' in question.lower()))

def explicit_filter_change(question: str, filter_key: str, proposed_val: Any, previous_val: Any) -> bool:
    if proposed_val is None:
        return False
    if previous_val is None:
        return True
    if proposed_val == previous_val:
        return False
    if filter_key == 'location':
        return question_mentions_location(question)
    if filter_key == 'violation_type':
        return question_mentions_violation_type(question)
    if filter_key == 'plate_suffix':
        return question_mentions_plate_pattern(question)
    if filter_key in ('vehicle_type', 'vehicle_category'):
        return question_mentions_vehicle_type(question)
    if filter_key == 'hour':
        from app.planning.scope import question_references_peak_hour
        return question_references_peak_hour(question)
    return True

def preserve_sticky_scope(previous: AnalyticalPlan | None, proposed: AnalyticalPlan, *, question: str, inherit: bool) -> tuple[AnalyticalPlan, dict[str, Any]]:
    audit: dict[str, Any] = {'state_before_merge': sticky_snapshot(previous), 'resolved_changes': [], 'sticky_preserved': [], 'sticky_overridden': []}
    if not inherit or previous is None:
        audit['resolved_changes'].append('new_scope')
        audit['state_after_merge'] = sticky_snapshot(proposed)
        return (proposed, audit)
    merged = copy.deepcopy(previous)
    changes: list[str] = ['inherited_scope']
    if proposed.user_objective:
        merged.user_objective = proposed.user_objective
        changes.append(f'objective={proposed.user_objective}')
    if proposed.query_mode:
        merged.query_mode = proposed.query_mode
        changes.append(f'query_mode={proposed.query_mode}')
        if proposed.query_mode == 'record_listing':
            merged.dimensions = []
            merged.group_by = []
        if proposed.query_mode != 'comparison':
            merged.compare_to = None
    if proposed.dimensions is not None:
        merged.dimensions = list(proposed.dimensions)
        merged.group_by = list(proposed.dimensions)
        changes.append(f'dimensions={proposed.dimensions}')
    if proposed.retrieval_scope:
        merged.retrieval_scope = proposed.retrieval_scope
        changes.append(f'retrieval_scope={proposed.retrieval_scope}')
    if proposed.sort:
        merged.sort = dict(proposed.sort)
        changes.append('sort_updated')
    if proposed.limit is not None:
        merged.limit = proposed.limit
        changes.append(f'limit={proposed.limit}')
    elif proposed.retrieval_scope == 'all':
        merged.limit = None
        changes.append('limit=none (all)')
    if proposed.compare_to is not None and proposed.query_mode in ('comparison', 'growth_analysis'):
        merged.compare_to = proposed.compare_to
        changes.append('compare_to_updated')
    merged.intent = proposed.intent or merged.intent
    prev_metric = previous.metric
    if explicit_metric_change(question, proposed.metric, prev_metric, proposed.filters):
        merged.metric = proposed.metric
        changes.append(f'metric={proposed.metric}')
        audit['sticky_overridden'].append('metric')
        
        # Context Shift Detector: clear prior filters/scope to prevent filter bleed
        # Time ranges are kept via previous logic, proposed filters will be applied below.
        merged.filters = {}
        merged.entity_scope = {}
    else:
        audit['sticky_preserved'].append('metric')
    if explicit_time_change(question, proposed.time_range, previous.time_range):
        merged.time_range = dict(proposed.time_range)
        changes.append('time_range_updated')
        audit['sticky_overridden'].append('time_range')
        audit['previous_time_range'] = dict(previous.time_range)
        audit['new_time_range'] = dict(proposed.time_range)
        audit['override_applied'] = True
    else:
        audit['sticky_preserved'].append('time_range')
        audit['previous_time_range'] = dict(previous.time_range)
        audit['new_time_range'] = dict(previous.time_range)
        audit['override_applied'] = False
    for key in STICKY_FILTER_KEYS:
        proposed_val = proposed.filters.get(key)
        previous_val = merged.filters.get(key)
        if proposed_val is None:
            continue
        if explicit_filter_change(question, key, proposed_val, previous_val):
            merged.filters[key] = proposed_val
            changes.append(f'filter:{key}')
            audit['sticky_overridden'].append(f'filters.{key}')
        else:
            audit['sticky_preserved'].append(f'filters.{key}')
    if proposed.entity_scope:
        scope = dict(merged.entity_scope)
        for (key, val) in proposed.entity_scope.items():
            if val is None or key not in STICKY_ENTITY_SCOPE_KEYS:
                continue
            prev_val = scope.get(key)
            filter_key = {'camera_id': 'location', 'location': 'location', 'violation_type': 'violation_type', 'vehicle_type': 'vehicle_type', 'vehicle_category': 'vehicle_category', 'plate_suffix': 'plate_suffix', 'peak_hour': 'hour'}.get(key, key)
            if explicit_filter_change(question, filter_key, val, prev_val):
                scope[key] = val
                audit['sticky_overridden'].append(f'entity_scope.{key}')
            else:
                audit['sticky_preserved'].append(f'entity_scope.{key}')
        merged.entity_scope = normalize_entity_scope(scope)
        changes.append('entity_scope_updated')
    merged.entity_scope = normalize_entity_scope(merged.entity_scope)
    from app.planning.scope import _apply_entity_scope_to_filters
    _apply_entity_scope_to_filters(merged)
    audit['resolved_changes'] = changes
    audit['state_after_merge'] = sticky_snapshot(merged)
    audit['inherit'] = True
    return (merged, audit)