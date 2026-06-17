from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from app.analytics.quality import DataQualityReport, assess
from app.entity.canonical import display_for_camera
from app.planning.plan import AnalyticalPlan

@dataclass
class InsightResult:
    summary: str = ''
    dataset_type: str = ''
    metrics: dict[str, Any] = field(default_factory=dict)
    trends: list[dict] = field(default_factory=list)
    comparisons: list[dict] = field(default_factory=list)
    rankings: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    data_quality: DataQualityReport | None = None

def analyze(dataset_type: str, columns: list[str], rows: list[tuple], camera_names: dict[str, str] | None=None, plan: AnalyticalPlan | None=None) -> InsightResult:
    data = [dict(zip(columns, r)) for r in rows]
    if camera_names:
        for row in data:
            cid = row.get('camera_id') or row.get('entity')
            if cid is not None:
                row['site_name'] = display_for_camera(str(cid), camera_names)
    out = InsightResult(dataset_type=dataset_type)
    if not data:
        out.summary = 'No data was returned for this query.'
        return out
    if dataset_type in ('record_set',):
        out.data_quality = assess(columns, data)
    if dataset_type == 'scalar':
        return _scalar(data, columns, out)
    if dataset_type == 'record_set':
        return _records(data, out)
    if dataset_type == 'comparison':
        return _comparison(data, out, plan)
    if dataset_type == 'time_series':
        return _time_series(data, out, plan)
    if dataset_type == 'growth':
        return _growth(data, out)
    if dataset_type == 'grouped':
        return _grouped(data, out, plan)
    out.summary = f'Retrieved {len(data)} rows.'
    out.rankings = data
    return out

def _value_col(columns: list[str], row: dict) -> str | None:
    for c in columns:
        if c in ('total', 'violation_count', 'plate_count', 'detection_count', 'total_violations', 'current_count', 'delta'):
            return c
    for c in columns:
        v = row.get(c)
        if isinstance(v, (int, float)):
            return c
    return columns[0] if columns else None

def _label_col(row: dict) -> str:
    for k in ('site_name', 'violation_type', 'camera_id', 'entity', 'period'):
        if k in row and row.get(k) not in (None, ''):
            return k
    return next(iter(row.keys()), 'label')

def _scalar(data: list[dict], columns: list[str], out: InsightResult) -> InsightResult:
    col = _value_col(columns, data[0])
    val = data[0].get(col) if col else None
    out.metrics['value'] = val
    out.metrics['total'] = val
    out.summary = f'Total: {val:,}.' if isinstance(val, (int, float)) else f'Result: {val}'
    return out

def _records(data: list[dict], out: InsightResult) -> InsightResult:
    out.records = data
    out.metrics['row_count'] = len(data)
    out.summary = f'Retrieved {len(data)} records.'
    return out

def _comparison(data: list[dict], out: InsightResult, plan: AnalyticalPlan | None) -> InsightResult:
    out.comparisons = data
    current = next((d for d in data if str(d.get('period', '')).startswith('current')), data[0])
    previous = next((d for d in data if str(d.get('period', '')).startswith('previous')), data[-1])
    cur = current.get('total', current.get('violation_count', 0))
    prev = previous.get('total', previous.get('violation_count', 0))
    out.metrics['current'] = cur
    out.metrics['previous'] = prev
    if plan:
        out.metrics['current_period_label'] = _period_label(plan.time_range)
        out.metrics['previous_period_label'] = _period_label(plan.compare_to or {'preset': 'last_month'})
    if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
        delta = cur - prev
        pct = delta / prev * 100 if prev else None
        out.metrics['delta'] = delta
        out.metrics['pct_change'] = pct
        out.metrics['absolute_change'] = abs(delta)
        if delta > 0:
            out.metrics['change_direction'] = 'increase'
            out.metrics['largest_change'] = 'increase'
        elif delta < 0:
            out.metrics['change_direction'] = 'decrease'
            out.metrics['largest_change'] = 'decrease'
        else:
            out.metrics['change_direction'] = 'flat'
        out.summary = f'Comparison: {cur:,} vs {prev:,} (Δ {delta:+,}).'
    else:
        out.summary = 'Comparison data retrieved.'
    return out

def _time_series(data: list[dict], out: InsightResult, plan: AnalyticalPlan | None) -> InsightResult:
    out.trends = data
    label = 'period' if 'period' in data[0] else next(iter(data[0].keys()))
    val_key = _value_col(list(data[0].keys()), data[0]) or 'total'
    values = [(row.get(label), float(row.get(val_key, 0) or 0)) for row in data]
    if not values:
        out.summary = 'No time series data.'
        return out
    peak = max(values, key=lambda x: x[1])
    low = min(values, key=lambda x: x[1])
    average = sum((v[1] for v in values)) / len(values)
    net_change = values[-1][1] - values[0][1]
    growth_pct = net_change / values[0][1] * 100 if values[0][1] else None
    if net_change > 0:
        direction = 'up'
    elif net_change < 0:
        direction = 'down'
    else:
        direction = 'flat'
    peak_idx = next((i for (i, v) in enumerate(values) if v[1] == peak[1]))
    declined_after_peak = peak_idx < len(values) - 1 and values[-1][1] < peak[1]
    out.metrics.update({'peak_period': peak[0], 'peak_period_label': _format_period_label(peak[0], plan), 'peak_value': peak[1], 'low_period': low[0], 'low_period_label': _format_period_label(low[0], plan), 'low_value': low[1], 'average': average, 'net_change': net_change, 'growth_pct': growth_pct, 'trend_direction': direction, 'declined_after_peak': declined_after_peak, 'period_count': len(values)})
    out.summary = f'Time series over {len(values)} periods.'
    return out

def _growth(data: list[dict], out: InsightResult) -> InsightResult:
    out.rankings = data
    if not data:
        out.summary = 'No growth data.'
        return out
    ranked = sorted(data, key=lambda r: float(r.get('delta', r.get('growth', 0)) or 0), reverse=True)
    growth_ranking: list[dict[str, Any]] = []
    for row in ranked:
        label_key = _label_col(row)
        lbl = row.get('site_name') or row.get(label_key, 'unknown')
        cur = float(row.get('current_count', row.get('current', 0)) or 0)
        prev = float(row.get('previous_count', row.get('previous', 0)) or 0)
        delta = float(row.get('delta', cur - prev) or 0)
        pct = delta / prev * 100 if prev else None
        growth_ranking.append({'label': lbl, 'current': cur, 'previous': prev, 'delta': delta, 'growth_pct': pct})
    top = growth_ranking[0]
    out.metrics['growth_ranking'] = growth_ranking
    out.metrics.update({'fastest_growing_entity': top['label'], 'fastest_growth_current': top['current'], 'fastest_growth_previous': top['previous'], 'fastest_growth_delta': top['delta'], 'fastest_growth_pct': top['growth_pct'], 'top_growth_entity': top['label'], 'top_growth_current': top['current'], 'top_growth_previous': top['previous'], 'top_growth_delta': top['delta'], 'top_growth_pct': top['growth_pct']})
    out.summary = f'Growth analysis across {len(growth_ranking)} entities.'
    return out

def _grouped(data: list[dict], out: InsightResult, plan: AnalyticalPlan | None) -> InsightResult:
    out.rankings = data
    val_key = _value_col(list(data[0].keys()), data[0]) or 'total'
    label_key = _label_col(data[0])
    total = sum((float(r.get(val_key, 0) or 0) for r in data))
    ranked_rows = sorted(data, key=lambda r: float(r.get(val_key, 0) or 0), reverse=True)
    ranking: list[dict[str, Any]] = []
    for row in ranked_rows:
        lbl = row.get('site_name') or row.get(label_key, 'unknown')
        val = float(row.get(val_key, 0) or 0)
        share = val / total * 100 if total else 0.0
        ranking.append({'label': lbl, 'value': val, 'share_pct': share})
    top = ranking[0]
    bottom = ranking[-1]
    metrics: dict[str, Any] = {'total': total, 'ranking': ranking, 'largest_contributor': top['label'], 'largest_contributor_value': top['value'], 'largest_contributor_share_pct': top['share_pct'], 'smallest_contributor': bottom['label'], 'smallest_contributor_value': bottom['value'], 'smallest_contributor_share_pct': bottom['share_pct'], 'headline': f"{top['label']}: {top['value']:,.0f} ({top['share_pct']:.1f}%)", 'winner_name': top['label'], 'winner_value': top['value']}
    if len(ranking) >= 2:
        metrics['runner_up_name'] = ranking[1]['label']
        metrics['runner_up_value'] = ranking[1]['value']
    if plan and (plan.user_objective == 'ranking' or plan.query_mode in ('top_n', 'ranking', 'bottom_n')):
        metrics['top_entity'] = top['label']
    out.metrics.update(metrics)
    out.summary = f'Grouped breakdown across {len(ranking)} categories.'
    return out

def _format_period_label(value: Any, plan: AnalyticalPlan | None) -> str:
    if value is None:
        return 'unknown period'
    dims = plan.dimensions or plan.group_by or [] if plan else []
    text = str(value).strip()
    if len(text) >= 10 and text[4:5] == '-':
        try:
            from datetime import datetime
            dt = datetime.strptime(text[:10], '%Y-%m-%d')
            months = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
            return f'{dt.day} {months[dt.month - 1]}'
        except ValueError:
            pass
    try:
        hour = int(value)
        if 0 <= hour <= 23 or 'hour' in dims:
            return f'{hour:02d}:00–{hour:02d}:59'
    except (TypeError, ValueError):
        pass
    return text

def _period_label(time_range: dict[str, Any] | None) -> str:
    if not time_range:
        return 'the period'
    preset = time_range.get('preset', '')
    labels = {'today': 'today', 'yesterday': 'yesterday', 'this_week': 'this week', 'this_month': 'this month', 'last_month': 'last month', 'last_7_days': 'the last 7 days', 'last_30_days': 'the last 30 days'}
    if preset in labels:
        return labels[preset]
    if preset == 'specific_date':
        start = time_range.get('start') or time_range.get('date')
        return str(start)[:10] if start else 'the selected date'
    return preset.replace('_', ' ')