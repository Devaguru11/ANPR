from __future__ import annotations
from typing import Any
from app.entity.canonical import user_facing_label
from app.planning.conversation_state import load_conversation_state, load_previous_plan, plan_snapshot
from app.planning.plan import AnalyticalPlan

def compact_analytics_output(analytics: dict[str, Any] | None, *, entity_scope: dict[str, Any] | None=None) -> dict[str, Any]:
    if not analytics:
        return {}
    metrics = analytics.get('metrics') or {}
    ranking = analytics.get('rankings') or metrics.get('ranking') or []
    top = ranking[0] if ranking else {}
    raw_winner = metrics.get('winner_name') or metrics.get('largest_contributor') or top.get('label')
    winner_name = user_facing_label(raw_winner, scope=entity_scope) if raw_winner else None
    ranking_top = [{**row, 'label': user_facing_label(row.get('label'), scope=entity_scope)} for row in ranking[:3]]
    return {'dataset_type': analytics.get('dataset_type'), 'summary': analytics.get('summary'), 'value': metrics.get('value') or metrics.get('total'), 'winner_name': winner_name, 'winner_value': metrics.get('winner_value') or metrics.get('largest_contributor_value') or top.get('value'), 'peak_period': metrics.get('peak_period') or metrics.get('peak_period_label'), 'peak_value': metrics.get('peak_value'), 'ranking_top': ranking_top, 'record_count': metrics.get('row_count') or len(analytics.get('records') or [])}

def compact_result_set(*, columns: list[str] | None=None, rows: list[tuple] | None=None, row_count: int | None=None) -> dict[str, Any]:
    cols = columns or []
    data = rows or []
    sample: list[dict[str, Any]] = []
    for row in data[:5]:
        sample.append(dict(zip(cols, row)))
    return {'row_count': row_count if row_count is not None else len(data), 'columns': cols, 'sample_rows': sample}

def build_analytical_state(mem: dict[str, Any] | None, previous: AnalyticalPlan | None) -> dict[str, Any]:
    conv = load_conversation_state(mem)
    current = plan_snapshot(conv.current_state) if conv.current_state else {}
    previous_snap = plan_snapshot(conv.previous_state) if conv.previous_state else {}
    plan = previous or load_previous_plan(mem.get('plan') if mem else None)
    snap = plan_snapshot(plan) if plan else current
    return {'current_state': current, 'previous_state': previous_snap, 'active_plan': snap, 'metric': snap.get('metric'), 'user_objective': snap.get('user_objective'), 'dimensions': snap.get('dimensions'), 'filters': snap.get('filters'), 'time_range': snap.get('time_range'), 'entity_scope': snap.get('entity_scope'), 'query_mode': snap.get('query_mode'), 'retrieval_scope': snap.get('retrieval_scope'), 'business_concept': (mem.get('plan') or {}).get('business_semantic_resolution', {}).get('business_concept')}