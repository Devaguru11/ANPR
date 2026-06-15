from __future__ import annotations
import json
from typing import Any

def format_record_list(columns: list[str], rows: list[tuple], camera_names: dict[str, str]) -> str:
    if not rows:
        return 'No records were returned for that request.'
    lines = []
    for row in rows:
        rec = dict(zip(columns, row))
        plate = rec.get('vehicle_num', '')
        cid = rec.get('camera_id', '')
        site = camera_names.get(str(cid), str(cid)) if cid else ''
        created = rec.get('created_at', '')
        vio = rec.get('violation_type', '')
        if vio:
            lines.append(f'- {plate} at {site} ({vio}) — {created}')
        else:
            lines.append(f'- {plate} at {site} — {created}')
    return 'Records:\n' + '\n'.join(lines)

def format_day_growth(rankings: list[dict]) -> str:
    if not rankings or len(rankings) < 2:
        return 'Not enough day-level data to determine which day increased most.'
    best_day = None
    best_delta = None
    prev_count = None
    for row in rankings:
        cur = row.get('current_count', 0) or 0
        if prev_count is not None:
            delta = cur - prev_count
            if best_delta is None or delta > best_delta:
                best_delta = delta
                best_day = row.get('period')
        prev_count = cur
    if best_day is None or best_delta is None:
        top = max(rankings, key=lambda r: r.get('current_count', 0) or 0)
        return f"Highest activity day: {top.get('period')} with {top.get('current_count', 0):,} violations."
    return f'Day with largest increase: {best_day} (+{best_delta:,} day-over-day).'

def _scope_label(state: dict[str, Any], camera_names: dict[str, str]) -> str:
    cs = state.get('plan', {}).get('conversation_state', {})
    loc = cs.get('location')
    if loc:
        return str(loc)
    cid = (cs.get('entity_scope') or {}).get('camera_id')
    if cid:
        return camera_names.get(str(cid), str(cid))
    return ''

def grounded_answer(state: dict[str, Any], camera_names: dict[str, str]) -> str | None:
    plan = state.get('plan', {})
    cs = plan.get('conversation_state', {})
    scope = _scope_label(state, camera_names)
    if cs.get('query_type') == 'record_list':
        return format_record_list(state.get('columns', []), state.get('rows', []), camera_names)
    ao = state.get('analytics_output') or {}
    intent = (state.get('intent') or '').lower().replace(' ', '_')
    if intent == 'day_growth_analysis':
        rankings = ao.get('rankings') or []
        if rankings:
            return format_day_growth(rankings)
        trends = ao.get('trends') or []
        if trends:
            return format_day_growth(trends)
    summary = ao.get('summary')
    if summary and summary != 'No data returned.':
        if scope and scope.lower() not in summary.lower():
            return f'At {scope}: {summary}'
        return summary
    metrics = ao.get('metrics') or {}
    if metrics.get('value') is not None:
        return str(metrics['value'])
    if ao.get('rankings'):
        return json.dumps(ao['rankings'][:5], default=str)
    if ao.get('trends'):
        return json.dumps(ao['trends'][:10], default=str)
    if ao.get('comparisons'):
        return json.dumps(ao['comparisons'], default=str)
    if state.get('row_count', 0) == 0:
        return 'No data was returned for that query.'
    return None