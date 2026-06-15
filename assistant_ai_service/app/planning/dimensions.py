from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class DimensionDef:
    name: str
    description: str
    filter_key: str | None
    group_expression: str | None
    select_alias: str | None
DIMENSIONS: dict[str, DimensionDef] = {'location': DimensionDef('location', 'Site or camera', 'camera_id', 've.camera_id', 'camera_id'), 'camera': DimensionDef('camera', 'Camera identifier', 'camera_id', 've.camera_id', 'camera_id'), 'violation_type': DimensionDef('violation_type', 'Violation category', 'violation_type', 'tv.violation_type', 'violation_type'), 'vehicle_type': DimensionDef('vehicle_type', 'Vehicle type', 'vehicle_type', 've.vehicle_type', 'vehicle_type'), 'vehicle_category': DimensionDef('vehicle_category', 'Vehicle category code', 'vehicle_category', 've.vehicle_category', 'vehicle_category'), 'date': DimensionDef('date', 'Calendar date', None, 'DATE(ve.created_at)', 'period'), 'day': DimensionDef('day', 'Day bucket', None, 'DATE(ve.created_at)', 'period'), 'week': DimensionDef('week', 'Week bucket', None, 'YEARWEEK(ve.created_at)', 'period'), 'month': DimensionDef('month', 'Month bucket', None, "DATE_FORMAT(ve.created_at, '%Y-%m')", 'period'), 'hour': DimensionDef('hour', 'Hour bucket', 'hour', 'HOUR(ve.created_at)', 'period'), 'plate_suffix': DimensionDef('plate_suffix', 'Plate ending pattern', 'plate_suffix', None, None)}

def dimension_names() -> list[str]:
    return list(DIMENSIONS.keys())

def registry_prompt() -> str:
    return '\n'.join((f'- {d.name}: {d.description}' for d in DIMENSIONS.values()))

def filters_to_sql(filters: dict[str, Any]) -> list[str]:
    clauses: list[str] = []
    for (dim_name, value) in filters.items():
        dim = DIMENSIONS.get(dim_name)
        if not dim or not dim.filter_key or value is None:
            continue
        key = dim.filter_key
        if dim_name == 'plate_suffix':
            suffix = str(value).replace("'", "''")
            clauses.append(f"ve.vehicle_num LIKE '%{suffix}'")
            continue
        if dim_name == 'hour':
            clauses.append(f'HOUR(ve.created_at) = {int(value)}')
            continue
        if isinstance(value, list):
            if not value:
                continue
            safe = [str(v).replace("'", "''") for v in value]
            col = _filter_column(key)
            if len(safe) == 1:
                clauses.append(f"{col} = '{safe[0]}'")
            else:
                quoted = ', '.join((f"'{s}'" for s in safe))
                clauses.append(f'{col} IN ({quoted})')
        else:
            col = _filter_column(key)
            clauses.append(f"{col} = '{str(value).replace(chr(39), chr(39) + chr(39))}'")
    return clauses

def _filter_column(key: str) -> str:
    mapping = {'camera_id': 've.camera_id', 'violation_type': 'tv.violation_type', 'vehicle_type': 've.vehicle_type', 'vehicle_category': 've.vehicle_category'}
    return mapping.get(key, key)
TIME_PRESETS = {'today', 'yesterday', 'this_week', 'this_month', 'last_month', 'last_7_days', 'last_5_days', 'last_30_days'}
TIME_FILTER_KEYS = {'date', 'day', 'week', 'month'}

def relocate_time_filters(filters: dict[str, Any], time_range: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    out = dict(filters)
    tr = dict(time_range or {'preset': 'last_30_days'})
    for key in list(out.keys()):
        val = out.get(key)
        if key in TIME_FILTER_KEYS and isinstance(val, str) and (val in TIME_PRESETS):
            tr = {'preset': val}
            out.pop(key, None)
    return (out, tr)

def infer_dimensions_from_question(question: str) -> list[str]:
    q = question.lower()
    if any((w in q for w in ('compare', 'versus', ' vs ', 'how many', 'how much', 'total'))):
        return []
    breakdown_time_cues = ('day wise', 'daily', 'by day', 'per day', 'over time', 'trend', 'hourly', 'by hour', 'by week', 'by month', 'last 7 days', 'last 5 days')
    has_time_breakdown = any((c in q for c in breakdown_time_cues))
    found: list[str] = []
    for (name, dim) in DIMENSIONS.items():
        token = name.replace('_', ' ')
        if token in q and (name not in TIME_FILTER_KEYS or has_time_breakdown):
            found.append(name)
    registry_aliases = {'violation_type': ('type wise', 'by type', 'violation type', 'breakdown', 'segregation'), 'date': ('day wise', 'daily', 'by day', 'per day', 'over time', 'trend'), 'camera': ('by camera', 'which camera', 'per camera', 'most active', 'increased'), 'hour': ('hourly', 'by hour', 'per hour')}
    for (dim, phrases) in registry_aliases.items():
        if dim in TIME_FILTER_KEYS and (not has_time_breakdown):
            continue
        if any((p in q for p in phrases)) and dim not in found:
            found.append(dim)
    scope_only = {'location', 'plate_suffix'}
    return [d for d in found if d not in scope_only]

def infer_time_preset(question: str) -> dict[str, Any] | None:
    q = question.lower()
    for preset in TIME_PRESETS:
        if preset.replace('_', ' ') in q or preset in q:
            return {'preset': preset}
    return None

def group_expressions(dimensions: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for dim in dimensions:
        d = DIMENSIONS.get(dim)
        if d and d.group_expression:
            out.append((d.group_expression, d.select_alias or dim))
    return out