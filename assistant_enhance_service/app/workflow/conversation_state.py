from __future__ import annotations
import copy
import re
from typing import Any
from app.entity.canonical import display_for_camera, normalize_entity_scope
SCOPE_REFERENCE_RE = re.compile('\\b(these|those|them|that|this|previous|same|above|earlier)\\b', re.I)
MODIFICATION_RE = re.compile('^(?:at|in|for|only|just|also|now|and)\\b|^(?:at|in|for)\\s+\\w', re.I)
RECORD_REQUEST_RE = re.compile('\\b(?:show|list|display|view|give)\\b.*\\b(?:records?|rows?|reads?|plates?|list|those|these)\\b|\\blist\\s+(?:of\\s+)?(?:those|these|the|first)\\b|\\bshow\\s+those\\b|\\bthose\\s+\\d+\\s+(?:reads?|records?|plates?)\\b', re.I)
PLATE_SUFFIX_RE = re.compile('(?:ending|ends)\\s+with\\s+(\\w+)', re.I)
SHORT_QUERY_WORDS = 8

def has_scope_reference(question: str) -> bool:
    return bool(SCOPE_REFERENCE_RE.search(question))

def is_scope_modification(question: str) -> bool:
    q = question.strip()
    if not q:
        return False
    if MODIFICATION_RE.search(q):
        return True
    words = q.split()
    return len(words) <= SHORT_QUERY_WORDS and (not has_scope_reference(q)) and (len(words) <= 4)

def is_record_request(question: str) -> bool:
    return bool(RECORD_REQUEST_RE.search(question))

def inherits_previous_scope(question: str) -> bool:
    return has_scope_reference(question) or is_record_request(question) or is_scope_modification(question)

def explicit_intent_change(question: str) -> str | None:
    q = question.lower()
    if is_record_request(question):
        return 'record_list'
    if re.search('day\\s*wise|by\\s+day', q) or ('day' in q and 'segregat' in q):
        return 'day_wise_segregation'
    if re.search('type\\s*wise|by\\s+type', q) or ('type' in q and 'segregat' in q):
        return 'type_wise_segregation'
    if 'which day' in q and 'increased' in q:
        return 'day_growth_analysis'
    if 'compare' in q or 'previous month' in q or 'last month' in q:
        return 'comparison'
    if 'increased most' in q or 'which one increased' in q:
        return 'growth_analysis'
    if re.search('\\btop\\b|\\bhighest\\b|\\bmost active\\b', q):
        return 'top_n'
    if re.search('only\\s+(no\\s+)?helmet|no\\s+helmet\\s+only', q):
        return 'count'
    if re.search('only\\s+motorcycle', q):
        return 'count'
    if plate_suffix(question) or ('plate' in q and 'read' in q):
        return 'count'
    return None

def plate_suffix(question: str) -> str | None:
    m = PLATE_SUFFIX_RE.search(question)
    return m.group(1).replace('letter ', '') if m else None

def empty_state() -> dict[str, Any]:
    return {'metric': 'violations', 'location': None, 'entity_scope': {}, 'filters': {}, 'group_by': [], 'dimensions': [], 'time_range': {'preset': 'last_30_days'}, 'query_type': 'aggregation', 'intent': 'count', 'limit': 10, 'compare_to': {}, 'plate_suffix': None, 'last_result_count': None}

def state_from_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not plan:
        return empty_state()
    cs = plan.get('conversation_state')
    if cs:
        return copy.deepcopy(cs)
    agg = plan.get('aggregation_spec', {})
    entities = plan.get('entities', {})
    location = entities.get('display_name') or entities.get('location') or entities.get('display')
    if not location and entities.get('camera_id'):
        location = display_for_camera(entities.get('camera_id'))
    return {'metric': _metric_from_spec(agg, plan), 'location': location, 'entity_scope': normalize_entity_scope(copy_scope_dict(entities)), 'filters': copy.deepcopy(plan.get('filters') or agg.get('filters') or {}), 'group_by': list(agg.get('group_by') or []), 'dimensions': list(agg.get('dimensions') or []), 'time_range': copy.deepcopy(plan.get('time_range') or {'preset': 'last_30_days'}), 'query_type': plan.get('query_type', 'aggregation'), 'intent': plan.get('intent', 'count'), 'limit': plan.get('limit', 10), 'compare_to': copy.deepcopy(plan.get('compare_to') or agg.get('compare_to') or {}), 'plate_suffix': plan.get('plate_suffix'), 'last_result_count': plan.get('last_result_count')}

def _metric_from_spec(agg: dict[str, Any], plan: dict[str, Any]) -> str:
    if plan.get('plate_suffix') or plate_suffix_from_filters(agg):
        return 'plate_reads'
    if agg.get('metric') == 'period_comparison':
        return 'violations'
    return 'violations'

def plate_suffix_from_filters(agg: dict[str, Any]) -> str | None:
    return None

def copy_scope_dict(entities: dict[str, Any]) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    for key in ('camera_id', 'location', 'display', 'display_name', 'violation_type', 'vehicle_type', 'vehicle_category'):
        if key in entities and entities[key]:
            scope[key] = entities[key]
    return scope

def apply_scope_modifications(prev: dict[str, Any], question: str, entities: dict[str, Any], intent: str, filters: dict[str, Any], time_range: dict[str, Any] | None=None, *, inherit: bool=False, record_request: bool=False) -> tuple[dict[str, Any], dict[str, Any]]:
    state = copy.deepcopy(prev) if inherit else empty_state()
    modifications: dict[str, Any] = {'inherited': inherit, 'changes': []}
    if inherit:
        modifications['changes'].append('inherited_previous_scope')
    if entities:
        state['entity_scope'] = normalize_entity_scope({**state.get('entity_scope', {}), **copy_scope_dict(entities)})
        loc = state['entity_scope'].get('display_name') or state['entity_scope'].get('location') or state['entity_scope'].get('display')
        if loc:
            state['location'] = loc
        modifications['changes'].append('updated_entity_scope')
    if filters:
        state['filters'].update(filters)
        modifications['changes'].append('updated_filters')
    if time_range:
        state['time_range'] = time_range
        modifications['changes'].append('updated_time_range')
    suffix = plate_suffix(question)
    if suffix:
        state['plate_suffix'] = suffix
        state['metric'] = 'plate_reads'
        modifications['changes'].append(f'plate_suffix={suffix}')
    if record_request:
        state['query_type'] = 'record_list'
        modifications['changes'].append('switched_to_record_list')
    else:
        state['query_type'] = 'aggregation'
        state['intent'] = intent
    if intent == 'type_wise_segregation':
        state['group_by'] = ['tv.violation_type']
        state['dimensions'] = ['violation_type']
        modifications['changes'].append('group_by=violation_type')
    elif intent == 'day_wise_segregation':
        state['group_by'] = ['DATE(tv.created_at)']
        state['dimensions'] = ['date']
        modifications['changes'].append('group_by=date')
    elif intent == 'day_growth_analysis':
        state['group_by'] = ['DATE(tv.created_at)']
        state['dimensions'] = ['date']
        state['metric'] = 'day_delta'
        modifications['changes'].append('group_by=date_growth')
    elif intent == 'top_n' and 'camera' in question.lower():
        state['group_by'] = ['ve.camera_id']
        state['dimensions'] = ['camera_id']
    elif intent == 'comparison':
        state['group_by'] = []
        state['dimensions'] = ['period']
        state['compare_to'] = state.get('compare_to') or {'preset': 'last_month'}
    m = re.search('\\b(?:first|top)\\s+(\\d+)\\b', question.lower())
    if m:
        state['limit'] = int(m.group(1))
        modifications['changes'].append(f"limit={state['limit']}")
    return (state, modifications)

def update_scope_from_result(state: dict[str, Any], intent: str, columns: list[str], rows: list[tuple], camera_names: dict[str, str]) -> dict[str, Any]:
    if not rows:
        return state
    data = [dict(zip(columns, r)) for r in rows]
    updated = copy.deepcopy(state)
    if intent in ('top_n', 'camera_analysis') and data and ('camera_id' in data[0]):
        top = data[0]
        cid = top.get('camera_id')
        if cid:
            display = display_for_camera(str(cid), camera_names)
            updated['entity_scope'] = normalize_entity_scope({**updated.get('entity_scope', {}), 'camera_id': str(cid), 'location': display, 'display': display, 'display_name': display}, camera_names=camera_names)
            updated['location'] = display
    if updated['query_type'] == 'aggregation':
        if len(data) == 1 and len(columns) == 1:
            val = data[0].get(columns[0])
            if isinstance(val, (int, float)):
                updated['last_result_count'] = int(val)
        elif data:
            updated['last_result_count'] = len(data)
    if state.get('plate_suffix') and updated['query_type'] == 'aggregation':
        updated['metric'] = 'plate_reads'
    return updated

def entities_from_scope(state: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(state.get('entity_scope') or {})

def resolved_context(state: dict[str, Any], modifications: dict[str, Any]) -> dict[str, Any]:
    return {'metric': state.get('metric'), 'location': state.get('location'), 'entity_scope': state.get('entity_scope'), 'filters': state.get('filters'), 'group_by': state.get('group_by'), 'dimensions': state.get('dimensions'), 'time_range': state.get('time_range'), 'query_type': state.get('query_type'), 'intent': state.get('intent'), 'plate_suffix': state.get('plate_suffix'), 'compare_to': state.get('compare_to'), 'limit': state.get('limit'), 'modifications': modifications}