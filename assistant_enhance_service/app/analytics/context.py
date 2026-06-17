from __future__ import annotations
from datetime import datetime
from typing import Any
from app.entity.canonical import location_display, user_facing_label
from app.planning.plan import AnalyticalPlan
METRIC_LABELS = {'violations': 'violations', 'plate_reads': 'plate reads', 'detections': 'detections', 'vehicle_detections': 'detections', 'vehicles': 'vehicles', 'cameras': 'camera events', 'challans': 'challans', 'watchlist_hits': 'watchlist hits'}
TIME_LABELS = {'today': 'today', 'yesterday': 'yesterday', 'this_week': 'this week', 'this_month': 'this month', 'last_month': 'last month', 'last_7_days': 'the last 7 days', 'last_5_days': 'the last 5 days', 'last_30_days': 'the last 30 days'}
VIOLATION_LABELS = {'NO_HELMET': 'no-helmet', 'WRONG_ROUTE': 'wrong-route', 'WRONG_PARKING': 'wrong-parking', 'TRIPLE_RIDING': 'triple-riding'}

def metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric.replace('_', ' '))

def time_label(time_range: dict[str, Any] | None) -> str:
    if not time_range:
        return ''
    preset = time_range.get('preset', '')
    return TIME_LABELS.get(preset, preset.replace('_', ' '))

def filter_descriptors(plan: AnalyticalPlan) -> list[str]:
    parts: list[str] = []
    filters = plan.filters or {}
    scope = plan.entity_scope or {}
    vio = filters.get('violation_type') or scope.get('violation_type')
    if vio:
        parts.append(VIOLATION_LABELS.get(str(vio), str(vio).replace('_', ' ').lower()))
    vt = filters.get('vehicle_type') or scope.get('vehicle_type')
    if vt:
        parts.append(str(vt).lower())
    if filters.get('vehicle_category') or scope.get('vehicle_category'):
        parts.append('motorcycle')
    suffix = filters.get('plate_suffix') or scope.get('plate_suffix')
    if suffix:
        parts.append(f'plates ending in {suffix}')
    return parts

def location_descriptor(plan: AnalyticalPlan, *, allow_internal: bool=False) -> str:
    return location_display(plan.entity_scope, plan=plan, allow_internal=allow_internal)

def time_context_phrase(plan: AnalyticalPlan) -> str:
    tr = plan.time_range or {}
    preset = tr.get('preset', '')
    if preset == 'specific_date':
        start = tr.get('start') or tr.get('date')
        if start:
            try:
                dt = datetime.strptime(str(start)[:10], '%Y-%m-%d')
                return f'on {dt.day} {_MONTHS[dt.month - 1]}'
            except ValueError:
                return f'on {start}'
    label = time_label(tr)
    if label:
        if label in ('today', 'yesterday'):
            return label
        return f'over {label}'
    return ''

def dimension_label(plan: AnalyticalPlan) -> str:
    dim = (plan.dimensions or plan.group_by or [None])[0]
    mapping = {'location': 'area', 'camera': 'camera', 'violation_type': 'violation type', 'vehicle_type': 'vehicle type', 'hour': 'hour', 'day': 'day', 'date': 'day', 'week': 'week', 'month': 'month'}
    return mapping.get(str(dim), 'category') if dim else 'category'

def entity_label(value: str, plan: AnalyticalPlan, *, allow_internal: bool=False) -> str:
    return user_facing_label(value, plan, allow_internal=allow_internal)
_MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')

def scope_phrase(plan: AnalyticalPlan) -> str:
    loc = location_descriptor(plan)
    filters = filter_descriptors(plan)
    chunks: list[str] = []
    if filters:
        chunks.append(' '.join(filters))
    chunks.append(metric_label(plan.metric))
    if loc:
        chunks.append(f'at {loc}')
    return ' '.join(chunks).strip()