from __future__ import annotations
import copy
import re
from typing import Any
from app.planning.conversation_state import load_previous_plan, plan_snapshot
from app.planning.plan import AnalyticalPlan

def question_references_peak_hour(question: str) -> bool:
    q = question.lower()
    return bool(re.search('\\b(?:that|the)\\s+hour\\b|\\bduring\\s+(?:that|the)\\s+hour\\b|\\bat\\s+that\\s+hour\\b|\\bpeak\\s+hour\\b', q))

def should_inherit(question: str, context: str, previous: AnalyticalPlan) -> bool:
    tokens = question.lower().split()
    if len(tokens) <= 8:
        return True
    refs = ('these', 'those', 'them', 'that', 'this', 'same', 'previous', 'above')
    if any((r in question.lower() for r in refs)):
        return True
    if previous.entity_scope and len(tokens) <= 14:
        return True
    return bool(context.strip())

def merge_scope(previous: AnalyticalPlan | None, proposed: AnalyticalPlan, *, inherit: bool) -> tuple[AnalyticalPlan, dict[str, Any]]:
    changes: list[str] = []
    if not inherit or previous is None:
        changes.append('new_scope')
        return (proposed, {'inherit': False, 'changes': changes})
    merged = copy.deepcopy(previous)
    changes.append('inherited_scope')
    if proposed.user_objective:
        merged.user_objective = proposed.user_objective
        changes.append(f'objective={proposed.user_objective}')
    if proposed.metric and proposed.metric != merged.metric:
        merged.metric = proposed.metric
        changes.append(f'metric={proposed.metric}')
        if proposed.metric == 'plate_reads':
            merged.filters.pop('violation_type', None)
    if proposed.query_mode:
        merged.query_mode = proposed.query_mode
        changes.append(f'query_mode={proposed.query_mode}')
        if proposed.query_mode == 'record_listing':
            merged.dimensions = []
            merged.group_by = []
        if proposed.query_mode != 'comparison':
            merged.compare_to = None
    if proposed.dimensions is not None:
        merged.dimensions = proposed.dimensions
        merged.group_by = proposed.dimensions
        changes.append(f'dimensions={proposed.dimensions}')
    if proposed.filters:
        for (key, val) in proposed.filters.items():
            merged.filters[key] = val
        changes.append('filters_updated')
    if proposed.entity_scope:
        merged.entity_scope = _merge_entity_scope(merged.entity_scope, proposed.entity_scope)
        _apply_entity_scope_to_filters(merged)
        changes.append('entity_scope_updated')
    if proposed.time_range:
        merged.time_range = proposed.time_range
        changes.append('time_range_updated')
    if proposed.compare_to is not None:
        merged.compare_to = proposed.compare_to
        changes.append('compare_to_updated')
    if proposed.limit is not None:
        merged.limit = proposed.limit
        changes.append(f'limit={proposed.limit}')
    elif proposed.retrieval_scope == 'all':
        merged.limit = None
        changes.append('limit=none (all)')
    if proposed.retrieval_scope:
        merged.retrieval_scope = proposed.retrieval_scope
        changes.append(f'retrieval_scope={proposed.retrieval_scope}')
    if proposed.sort:
        merged.sort = proposed.sort
    merged.intent = proposed.intent or merged.intent
    return (merged, {'inherit': True, 'changes': changes})

def _merge_entity_scope(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(current)
    for (key, val) in incoming.items():
        if val is None:
            continue
        out[key] = val
    return out

def _apply_entity_scope_to_filters(plan: AnalyticalPlan) -> None:
    scope = plan.entity_scope
    if scope.get('camera_id'):
        plan.filters['location'] = scope['camera_id']
    if scope.get('violation_type'):
        plan.filters['violation_type'] = scope['violation_type']
    if scope.get('vehicle_type'):
        plan.filters['vehicle_type'] = scope['vehicle_type']
    if scope.get('vehicle_category'):
        plan.filters['vehicle_category'] = scope['vehicle_category']
    if scope.get('peak_hour') is not None:
        plan.filters['hour'] = scope['peak_hour']

def update_scope_from_result(plan: AnalyticalPlan, columns: list[str], rows: list[tuple], camera_names: dict[str, str]) -> AnalyticalPlan:
    if not rows:
        return plan
    updated = copy.deepcopy(plan)
    data = [dict(zip(columns, r)) for r in rows]
    scope = dict(updated.entity_scope)
    if updated.query_mode in ('top_n', 'ranking', 'grouped_analysis') and data:
        row = data[0]
        cid = row.get('camera_id')
        if cid:
            scope['camera_id'] = cid
            scope['location'] = camera_names.get(str(cid), str(cid))
            updated.filters['location'] = cid
        dims = updated.dimensions or updated.group_by or []
        if 'hour' in dims:
            period = row.get('period')
            if period is not None:
                try:
                    scope['peak_hour'] = int(period)
                    updated.filters['hour'] = int(period)
                except (TypeError, ValueError):
                    pass
    if updated.query_mode in ('count', 'aggregation') and len(data) == 1 and (len(columns) == 1):
        val = data[0].get(columns[0])
        if isinstance(val, (int, float)):
            scope['last_result_count'] = int(val)
    updated.entity_scope = scope
    return updated

def entity_scope_from_resolutions(resolutions: list[dict[str, Any]]) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    for item in resolutions:
        etype = item.get('type') or item.get('entity_type')
        value = item.get('value')
        if etype == 'camera' and value:
            scope['camera_id'] = value
            scope['location'] = item.get('display', value)
        elif etype == 'violation_type' and value:
            scope['violation_type'] = value
        elif etype == 'vehicle_type' and value:
            scope['vehicle_type'] = value
        elif etype == 'vehicle_category' and value:
            scope['vehicle_category'] = value
        elif etype == 'plate_suffix' and value:
            scope['plate_suffix'] = value
    return scope
__all__ = ['should_inherit', 'load_previous_plan', 'merge_scope', 'update_scope_from_result', 'entity_scope_from_resolutions', 'plan_snapshot']