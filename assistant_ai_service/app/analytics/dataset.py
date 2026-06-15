from __future__ import annotations
from typing import Any

def classify_dataset(query_mode: str, columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return 'empty'
    data = [dict(zip(columns, r)) for r in rows]
    if query_mode == 'record_listing':
        return 'record_set'
    if query_mode == 'comparison':
        return 'comparison'
    if query_mode == 'growth_analysis' or _is_growth_shape(columns):
        return 'growth'
    if query_mode in ('top_n', 'ranking', 'grouped_analysis') and _has_group_label(columns, data):
        return 'grouped'
    if len(rows) == 1 and len(columns) == 1:
        return 'scalar'
    if _has_time_dimension(columns, data):
        return 'time_series'
    if len(rows) > 1 and _has_group_label(columns, data):
        return 'grouped'
    if len(rows) > 1:
        return 'record_set'
    return 'scalar'

def _has_time_dimension(columns: list[str], data: list[dict]) -> bool:
    time_cols = {'period', 'date', 'day', 'month', 'hour', 'week'}
    return any((c in time_cols for c in columns))

def _is_growth_shape(columns: list[str]) -> bool:
    growth_cols = {'delta', 'current_count', 'previous_count', 'growth'}
    return len(growth_cols.intersection(columns)) >= 2

def _has_group_label(columns: list[str], data: list[dict]) -> bool:
    label_cols = {'violation_type', 'camera_id', 'vehicle_type', 'site_name', 'period'}
    return any((c in label_cols for c in columns)) and any((isinstance(data[0].get(c), (str, int)) for c in columns if c in data[0]))