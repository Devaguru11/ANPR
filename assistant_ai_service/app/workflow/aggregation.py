from __future__ import annotations
import re
from datetime import datetime, timedelta
from typing import Any

def normalize_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if v is not None and str(v).strip()]
    s = str(val).strip()
    return [s] if s else []

def in_clause(column: str, values: list[str]) -> str:
    if not values:
        return ''
    safe = [v.replace("'", "''") for v in values]
    if len(safe) == 1:
        return f"{column} = '{safe[0]}'"
    quoted = ', '.join(("'" + v + "'" for v in safe))
    return f'{column} IN ({quoted})'

def is_transform_followup(question: str) -> bool:
    from app.workflow.conversation_state import inherits_previous_scope
    q = question.lower()
    patterns = ('day\\s*wise', 'type\\s*wise', 'segregat', 'break\\s*down', 'by\\s+day', 'by\\s+type', 'compare', 'previous\\s+month', 'last\\s+month', 'increased\\s+most', 'which\\s+one', 'which\\s+day')
    return inherits_previous_scope(question) or any((re.search(p, q) for p in patterns))

def explicit_violation_type(question: str, violation_types: list[str]) -> str | None:
    q = question.lower()
    if re.search('only\\s+(no\\s+)?helmet', q) or re.search('no\\s+helmet\\s+only', q):
        return 'NO_HELMET'
    for vio in violation_types:
        label = vio.lower().replace('_', ' ')
        if label in q or vio.lower() in q:
            return vio
    return None

def explicit_vehicle_type(question: str, vehicle_types: list[str]) -> str | None:
    q = question.lower()
    for vt in vehicle_types:
        if vt.lower() in q:
            return vt
    return None

def explicit_vehicle_category(question: str) -> list[int] | None:
    q = question.lower()
    if re.search('only\\s+motorcycle', q) or 'only motorcycles' in q or 'only motorcycle' in q:
        return [5, 6]
    return None

def copy_scope_entities(entities: dict[str, Any]) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    for key in ('camera_id', 'location', 'display', 'violation_type', 'vehicle_type', 'vehicle_category'):
        if key in entities and entities[key]:
            scope[key] = entities[key]
    return scope

def time_clause(tr: dict, table_prefix: str='ve') -> str:
    col = f'{table_prefix}.created_at'
    preset = tr.get('preset', 'last_30_days')
    now = datetime.utcnow()
    if preset == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif preset == 'yesterday':
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return f"{col} >= '{start:%Y-%m-%d %H:%M:%S}' AND {col} < '{end:%Y-%m-%d %H:%M:%S}'"
    elif preset == 'this_week':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif preset == 'last_month':
        first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (first - timedelta(days=1)).replace(day=1)
        end = first
        return f"{col} >= '{start:%Y-%m-%d %H:%M:%S}' AND {col} < '{end:%Y-%m-%d %H:%M:%S}'"
    elif preset == 'this_month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=30)
    return f"{col} >= '{start:%Y-%m-%d %H:%M:%S}'"

def month_bounds() -> tuple[datetime, datetime, datetime]:
    now = datetime.utcnow()
    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = this_month
    last_month_start = (this_month - timedelta(days=1)).replace(day=1)
    return (this_month, last_month_start, last_month_end)

def normalize_intent(intent: str, question: str) -> str:
    q = question.lower()
    intent_l = (intent or 'count').lower().replace(' ', '_')
    if 'which day' in q and 'increased' in q:
        return 'day_growth_analysis'
    if 'increased most' in q or 'which one increased' in q or 'which increased most' in q:
        return 'growth_analysis'
    if any((w in q for w in ('top', 'highest', 'leading'))) or ('most' in q and 'increased' not in q):
        return 'top_n'
    if re.search('only\\s+(no\\s+)?helmet|no\\s+helmet\\s+only', q):
        return 'count'
    if re.search('only\\s+motorcycle', q) or 'only motorcycles' in q:
        return 'count'
    if 'day' in q and ('wise' in q or 'segregat' in q or 'by day' in q):
        return 'day_wise_segregation'
    if 'type' in q and ('wise' in q or 'segregat' in q or 'by type' in q):
        return 'type_wise_segregation'
    if 'violation type' in q and 'top' not in q and ('wise' not in q):
        return 'type_wise_segregation'
    if intent_l in ('show_violations', 'violation_analysis') and (not any((w in q for w in ('wise', 'segregat', 'break', 'top', 'compare')))):
        return 'count'
    return intent_l

def build_aggregation_spec(intent: str, entities: dict[str, Any], filters: dict[str, Any], time_range: dict[str, Any], question: str, limit: int=10, compare_to: dict[str, Any] | None=None, transform_from_previous: bool=False) -> dict[str, Any]:
    intent_norm = normalize_intent(intent, question)
    q = question.lower()
    sql_filters: dict[str, list[str]] = {}
    cameras = normalize_list(entities.get('camera_id'))
    if cameras:
        sql_filters['camera_id'] = cameras
    vio = filters.get('violation_type') or entities.get('violation_type')
    vios = normalize_list(vio)
    if vios:
        sql_filters['violation_type'] = vios
    vt = filters.get('vehicle_type') or entities.get('vehicle_type')
    vts = normalize_list(vt)
    if vts:
        sql_filters['vehicle_type'] = vts
    vcat = filters.get('vehicle_category') or entities.get('vehicle_category')
    vcats = normalize_list(vcat)
    if vcats:
        sql_filters['vehicle_category'] = vcats
    group_by: list[str] = []
    dimensions: list[str] = []
    metric = 'violation_count'
    order_by: str | None = None
    if intent_norm == 'day_wise_segregation':
        group_by = ['DATE(tv.created_at)']
        dimensions = ['date']
        order_by = 'period ASC'
    elif intent_norm == 'type_wise_segregation':
        group_by = ['tv.violation_type']
        dimensions = ['violation_type']
        order_by = 'violation_count DESC'
    elif intent_norm in ('top_n', 'camera_analysis', 'hotspot_detection'):
        if 'camera' in q or 'site' in q:
            group_by = ['ve.camera_id']
            dimensions = ['camera_id']
        else:
            group_by = ['tv.violation_type']
            dimensions = ['violation_type']
        order_by = 'violation_count DESC'
    elif intent_norm in ('trend_analysis', 'trend'):
        group_by = ['DATE(tv.created_at)']
        dimensions = ['date']
        order_by = 'period ASC'
    elif intent_norm == 'repeat_offenders':
        group_by = ['ve.vehicle_num']
        dimensions = ['vehicle_num']
        order_by = 'violation_count DESC'
    elif intent_norm in ('comparison', 'growth_analysis'):
        if 'increased' in q or 'which one' in q:
            group_by = ['ve.camera_id']
            dimensions = ['camera_id']
            metric = 'period_delta'
        else:
            dimensions = ['period']
            metric = 'period_comparison'
    return {'intent': intent_norm, 'metric': metric, 'dimensions': dimensions, 'filters': sql_filters, 'group_by': group_by, 'time_range': time_range, 'compare_to': compare_to or {}, 'limit': limit, 'order_by': order_by, 'transform_from_previous': transform_from_previous}

def _base_where(spec: dict[str, Any], question: str) -> list[str]:
    where = ['1=1']
    tr = spec.get('time_range', {})
    if tr and spec.get('intent') not in ('comparison', 'growth_analysis'):
        clause = time_clause(tr, 've')
        if clause:
            where.append(clause)
    filters = spec.get('filters', {})
    cam = in_clause('ve.camera_id', filters.get('camera_id', []))
    if cam:
        where.append(cam)
    vio = in_clause('tv.violation_type', filters.get('violation_type', []))
    if vio:
        where.append(vio)
    vt = in_clause('ve.vehicle_type', filters.get('vehicle_type', []))
    if vt:
        where.append(vt)
    vcat_vals = filters.get('vehicle_category', [])
    if vcat_vals:
        nums = ', '.join((str(int(v)) for v in vcat_vals))
        where.append(f've.vehicle_category IN ({nums})')
    suffix = spec.get('plate_suffix')
    if not suffix:
        plate_end = re.search('(?:ending|ends) with (\\d|letter [a-z])', question.lower())
        if plate_end:
            suffix = plate_end.group(1).replace('letter ', '')
    if suffix:
        where.append(f"ve.vehicle_num LIKE '%{suffix}'")
    return where

def build_spec_from_conversation_state(state: dict[str, Any], question: str) -> dict[str, Any]:
    entities = state.get('entity_scope') or {}
    filters = dict(state.get('filters') or {})
    if state.get('plate_suffix'):
        filters['plate_suffix'] = state['plate_suffix']
    spec = build_aggregation_spec(intent=state.get('intent', 'count'), entities=entities, filters=filters, time_range=state.get('time_range') or {'preset': 'last_30_days'}, question=question, limit=state.get('limit', 10), compare_to=state.get('compare_to'), transform_from_previous=True)
    spec['group_by'] = list(state.get('group_by') or spec.get('group_by') or [])
    spec['dimensions'] = list(state.get('dimensions') or spec.get('dimensions') or [])
    spec['query_type'] = state.get('query_type', 'aggregation')
    spec['plate_suffix'] = state.get('plate_suffix')
    spec['metric'] = state.get('metric') or spec.get('metric')
    if state.get('intent') == 'day_growth_analysis':
        spec['intent'] = 'day_growth_analysis'
        spec['group_by'] = ['DATE(tv.created_at)']
        spec['dimensions'] = ['date']
        spec['metric'] = 'day_delta'
    return spec

def build_record_sql(spec: dict[str, Any], question: str) -> str:
    limit = int(spec.get('limit', 10))
    where = _base_where(spec, question)
    w = ' AND '.join(where)
    metric = spec.get('metric', 'violations')
    if metric == 'plate_reads' or spec.get('plate_suffix'):
        return f'SELECT ve.vehicle_num, ve.camera_id, ve.created_at FROM vehicle_events ve WHERE {w} ORDER BY ve.created_at DESC LIMIT {limit}'
    return f'SELECT ve.vehicle_num, ve.camera_id, ve.created_at, tv.violation_type FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} ORDER BY ve.created_at DESC LIMIT {limit}'

def build_sql(spec: dict[str, Any], question: str) -> str:
    if spec.get('query_type') == 'record_list':
        return build_record_sql(spec, question)
    intent = spec.get('intent', 'count')
    limit = int(spec.get('limit', 10))
    group_by = spec.get('group_by', [])
    where = _base_where(spec, question)
    w = ' AND '.join(where)
    if intent == 'day_growth_analysis':
        (this_month, last_month_start, last_month_end) = month_bounds()
        return f"SELECT DATE(ve.created_at) AS period, SUM(CASE WHEN ve.created_at >= '{this_month:%Y-%m-%d %H:%M:%S}' THEN 1 ELSE 0 END) AS current_count, SUM(CASE WHEN ve.created_at >= '{last_month_start:%Y-%m-%d %H:%M:%S}' AND ve.created_at < '{last_month_end:%Y-%m-%d %H:%M:%S}' THEN 1 ELSE 0 END) AS previous_count FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} AND ve.created_at >= '{last_month_start:%Y-%m-%d %H:%M:%S}' GROUP BY DATE(ve.created_at) ORDER BY period ASC LIMIT 365"
    use_detections = spec.get('metric') == 'plate_reads' or spec.get('plate_suffix') or ('plate' in question.lower() and 'read' in question.lower()) or ('detection' in question.lower() and 'violation' not in question.lower())
    if use_detections and (not group_by):
        return f'SELECT COUNT(DISTINCT ve.vehicle_num) AS plate_count FROM vehicle_events ve WHERE {w} LIMIT 1'
    if use_detections and group_by:
        gb = ', '.join(group_by)
        sel = ', '.join(group_by) + ', COUNT(DISTINCT ve.vehicle_num) AS plate_count'
        return f'SELECT {sel} FROM vehicle_events ve WHERE {w} GROUP BY {gb} ORDER BY plate_count DESC LIMIT {limit}'
    if intent == 'comparison' and spec.get('compare_to'):
        current = time_clause(spec.get('time_range', {}), 've')
        previous = time_clause(spec.get('compare_to', {}), 've')
        return f"SELECT 'current_period' AS period, COUNT(*) AS violation_count FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} AND {current} UNION ALL SELECT 'previous_period' AS period, COUNT(*) AS violation_count FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} AND {previous}"
    if intent == 'growth_analysis' and spec.get('metric') == 'period_delta':
        (this_month, last_month_start, last_month_end) = month_bounds()
        return f"SELECT ve.camera_id, SUM(CASE WHEN ve.created_at >= '{this_month:%Y-%m-%d %H:%M:%S}' THEN 1 ELSE 0 END) AS current_count, SUM(CASE WHEN ve.created_at >= '{last_month_start:%Y-%m-%d %H:%M:%S}' AND ve.created_at < '{last_month_end:%Y-%m-%d %H:%M:%S}' THEN 1 ELSE 0 END) AS previous_count, SUM(CASE WHEN ve.created_at >= '{this_month:%Y-%m-%d %H:%M:%S}' THEN 1 ELSE 0 END) - SUM(CASE WHEN ve.created_at >= '{last_month_start:%Y-%m-%d %H:%M:%S}' AND ve.created_at < '{last_month_end:%Y-%m-%d %H:%M:%S}' THEN 1 ELSE 0 END) AS delta FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} GROUP BY ve.camera_id ORDER BY delta DESC LIMIT {limit}"
    if group_by:
        select_dims = []
        aliases = []
        for col in group_by:
            if col.startswith('DATE('):
                select_dims.append(f'{col} AS period')
                aliases.append('period')
            elif col == 'tv.violation_type':
                select_dims.append('tv.violation_type')
                aliases.append('violation_type')
            elif col == 've.camera_id':
                select_dims.append('ve.camera_id')
                aliases.append('camera_id')
            elif col == 've.vehicle_num':
                select_dims.append('ve.vehicle_num')
                aliases.append('vehicle_num')
            else:
                select_dims.append(col)
                aliases.append(col.split('.')[-1])
        select_sql = ', '.join(select_dims) + ', COUNT(*) AS violation_count'
        gb_sql = ', '.join(group_by)
        order = spec.get('order_by') or 'violation_count DESC'
        return f"SELECT {select_sql} FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} GROUP BY {gb_sql} ORDER BY {order} LIMIT {(limit if intent in ('top_n', 'repeat_offenders', 'growth_analysis') else 365)}"
    return f'SELECT COUNT(*) AS total_violations FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {w} LIMIT 1'