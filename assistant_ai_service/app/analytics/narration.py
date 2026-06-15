from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from app.analytics.context import dimension_label, entity_label, location_descriptor, metric_label, scope_phrase, time_context_phrase
from app.analytics.insights import InsightResult
from app.planning.plan import AnalyticalPlan

@dataclass
class NarrationFacts:
    dataset_type: str
    bullets: list[str] = field(default_factory=list)
    follow_up: str | None = None

def narrate(plan: AnalyticalPlan, insight: InsightResult) -> str:
    dataset = insight.dataset_type
    if _is_ranking_plan(plan) and dataset in ('grouped', 'scalar'):
        return _narrate_ranking(plan, insight)
    if dataset == 'scalar':
        return _narrate_scalar(plan, insight)
    if dataset == 'time_series':
        return _narrate_trend(plan, insight)
    if dataset == 'grouped':
        return _narrate_breakdown(plan, insight)
    if dataset == 'comparison':
        return _narrate_comparison(plan, insight)
    if dataset == 'growth':
        return _narrate_growth(plan, insight)
    if dataset == 'record_set':
        return _narrate_records(plan, insight)
    return insight.summary or 'No data was returned for this query.'

def _is_ranking_plan(plan: AnalyticalPlan) -> bool:
    return plan.user_objective == 'ranking' or plan.query_mode in ('top_n', 'ranking', 'bottom_n')

def _narrate_scalar(plan: AnalyticalPlan, insight: InsightResult) -> str:
    val = insight.metrics.get('value')
    if not isinstance(val, (int, float)):
        return insight.summary or 'No result.'
    scope = scope_phrase(plan)
    when = time_context_phrase(plan)
    if scope and when:
        return f'There are {val:,} {scope} {when}.'
    if scope:
        return f'There are {val:,} {scope}.'
    return f'The total count is {val:,}.'

def _narrate_ranking(plan: AnalyticalPlan, insight: InsightResult) -> str:
    ranking = insight.metrics.get('ranking') or []
    if not ranking and insight.rankings:
        val_key = 'total'
        ranking = [{'label': row.get('site_name') or row.get('camera_id') or row.get('label', 'unknown'), 'value': float(row.get(val_key, row.get('total', 0)) or 0)} for row in insight.rankings]
    winner_name = insight.metrics.get('winner_name') or insight.metrics.get('top_entity')
    winner_value = insight.metrics.get('winner_value') or insight.metrics.get('value')
    if ranking:
        winner_name = winner_name or ranking[0].get('label')
        winner_value = winner_value if winner_value is not None else ranking[0].get('value')
    if winner_name is None or not isinstance(winner_value, (int, float)):
        return insight.summary or 'No ranking data available.'
    name = _ranking_display_name(str(winner_name), plan)
    val_i = int(winner_value) if float(winner_value).is_integer() else winner_value
    metric = metric_label(plan.metric)
    when = time_context_phrase(plan)
    superlative = _ranking_superlative(plan)
    if when:
        lead = f'{name} is the {superlative} {when} with {val_i:,} {metric}.'
    else:
        lead = f'{name} is the {superlative} with {val_i:,} {metric}.'
    parts = [lead]
    runner_name = insight.metrics.get('runner_up_name')
    runner_value = insight.metrics.get('runner_up_value')
    if ranking and len(ranking) >= 2:
        runner_name = runner_name or ranking[1].get('label')
        runner_value = runner_value if runner_value is not None else ranking[1].get('value')
    if runner_name and isinstance(runner_value, (int, float)):
        runner_i = int(runner_value) if float(runner_value).is_integer() else runner_value
        parts.append(f'{_ranking_display_name(str(runner_name), plan)} followed with {runner_i:,} {metric}.')
    return ' '.join(parts)

def _ranking_display_name(label: str, plan: AnalyticalPlan) -> str:
    dim = (plan.dimensions or plan.group_by or [None])[0]
    if dim == 'hour':
        return _format_period(label, plan)
    scope = plan.entity_scope or {}
    if label and str(label) == str(scope.get('camera_id', '')):
        loc = scope.get('location') or scope.get('display')
        if loc:
            return str(loc)
    return entity_label(label, plan)

def _ranking_superlative(plan: AnalyticalPlan) -> str:
    dim = (plan.dimensions or plan.group_by or [None])[0]
    mapping = {'camera': 'most active camera', 'location': 'most active area', 'hour': 'peak hour', 'violation_type': 'most common violation type', 'vehicle_type': 'most common vehicle type'}
    return mapping.get(str(dim), 'top-ranked category')

def _narrate_trend(plan: AnalyticalPlan, insight: InsightResult) -> str:
    m = insight.metrics
    peak_label = m.get('peak_period_label') or _format_period(m.get('peak_period'), plan)
    peak_val = m.get('peak_value')
    low_label = m.get('low_period_label') or _format_period(m.get('low_period'), plan)
    low_val = m.get('low_value')
    average = m.get('average')
    net_change = m.get('net_change')
    growth_pct = m.get('growth_pct')
    direction = m.get('trend_direction')
    declined_after_peak = m.get('declined_after_peak')
    if peak_val is None:
        return insight.summary or 'No trend data available.'
    metric = metric_label(plan.metric)
    dim = dimension_label(plan)
    period_noun = _trend_period_noun(plan)
    peak_val_i = int(peak_val) if float(peak_val).is_integer() else peak_val
    parts = [f'Peak {metric} {period_noun} was {peak_label} with {peak_val_i:,} {metric}.']
    if low_label and low_val is not None and (low_label != peak_label):
        low_i = int(low_val) if float(low_val).is_integer() else low_val
        parts.append(f'Lowest was {low_label} with {low_i:,} {metric}.')
    if isinstance(growth_pct, (int, float)) and growth_pct != 0:
        direction_word = 'increased' if growth_pct > 0 else 'decreased'
        parts.append(f'Overall trend {direction_word} by {abs(growth_pct):.0f}%.')
    elif direction == 'up':
        parts.append('Overall trend increased.')
    elif direction == 'down':
        parts.append('Overall trend decreased.')
    elif direction == 'flat':
        parts.append('Overall trend remained stable.')
    if declined_after_peak:
        parts.append('Activity declined after the peak period.')
    loc = location_descriptor(plan)
    if loc and loc.lower() not in ' '.join(parts).lower():
        parts[0] = f'At {loc}, {parts[0]}'
    return ' '.join(parts)

def _trend_period_noun(plan: AnalyticalPlan) -> str:
    dim = (plan.dimensions or plan.group_by or [None])[0]
    mapping = {'date': 'day', 'day': 'day', 'hour': 'hour', 'week': 'week', 'month': 'month'}
    return mapping.get(str(dim), 'period')

def _narrate_breakdown(plan: AnalyticalPlan, insight: InsightResult) -> str:
    ranking = insight.metrics.get('ranking') or []
    if not ranking:
        return insight.summary or 'No breakdown data available.'
    top = ranking[0]
    top_name = entity_label(str(top.get('label', '')), plan)
    top_share = float(top.get('share_pct', 0) or 0)
    dim = dimension_label(plan)
    metric = metric_label(plan.metric)
    parts = [f'{top_name} is the dominant {dim}, accounting for {top_share:.0f}% of {metric}.']
    if len(ranking) >= 2:
        bottom = ranking[-1]
        bottom_name = entity_label(str(bottom.get('label', '')), plan)
        bottom_share = float(bottom.get('share_pct', 0) or 0)
        if bottom_name != top_name:
            parts.append(f'{bottom_name} is the smallest contributor at {bottom_share:.0f}%.')
    return ' '.join(parts)

def _narrate_comparison(plan: AnalyticalPlan, insight: InsightResult) -> str:
    m = insight.metrics
    cur = m.get('current')
    prev = m.get('previous')
    delta = m.get('delta')
    pct = m.get('pct_change')
    if not isinstance(cur, (int, float)):
        return insight.summary or 'No comparison data.'
    scope = metric_label(plan.metric)
    loc = location_descriptor(plan)
    loc_p = f' at {loc}' if loc else ''
    current_label = m.get('current_period_label') or 'the current period'
    previous_label = m.get('previous_period_label') or 'the previous period'
    parts = [f'{current_label.capitalize()} recorded {cur:,} {scope}{loc_p}, compared with {prev:,} in {previous_label}.']
    if isinstance(delta, (int, float)):
        if delta > 0:
            parts.append(f'That is an increase of {delta:,} ({pct:+.1f}%).' if isinstance(pct, (int, float)) else f'That is an increase of {delta:,}.')
        elif delta < 0:
            parts.append(f'That is a decrease of {abs(delta):,} ({pct:+.1f}%).' if isinstance(pct, (int, float)) else f'That is a decrease of {abs(delta):,}.')
        else:
            parts.append('There was no change between the two periods.')
    direction = m.get('change_direction')
    if direction == 'increase':
        parts.append('Violations increased compared with the prior period.')
    elif direction == 'decrease':
        parts.append('Violations decreased compared with the prior period.')
    return ' '.join(parts)

def _narrate_growth(plan: AnalyticalPlan, insight: InsightResult) -> str:
    m = insight.metrics
    entity = m.get('fastest_growing_entity') or m.get('top_growth_entity')
    delta = m.get('fastest_growth_delta') or m.get('top_growth_delta')
    pct = m.get('fastest_growth_pct') or m.get('top_growth_pct')
    cur = m.get('fastest_growth_current') or m.get('top_growth_current')
    prev = m.get('fastest_growth_previous') or m.get('top_growth_previous')
    if not entity or not isinstance(delta, (int, float)):
        return insight.summary or 'No growth data.'
    name = entity_label(str(entity), plan)
    dim = dimension_label(plan)
    scope = metric_label(plan.metric)
    delta_i = int(delta) if float(delta).is_integer() else delta
    line = f'{name} shows the fastest growth among {dim}s, rising by {delta_i:,} {scope}'
    if isinstance(pct, (int, float)):
        line += f' ({pct:+.1f}% increase)'
    if isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
        line += f' — from {int(prev):,} to {int(cur):,}.'
    else:
        line += '.'
    parts = [line]
    ranking = insight.metrics.get('growth_ranking') or []
    if len(ranking) >= 2:
        second = ranking[1]
        second_name = entity_label(second.get('label', ''), plan)
        second_delta = second.get('delta', 0)
        parts.append(f'The next largest increase was {second_name} (+{int(second_delta):,}).')
    decreases = [r for r in ranking if float(r.get('delta', 0) or 0) < 0]
    if decreases:
        worst = min(decreases, key=lambda r: float(r.get('delta', 0) or 0))
        worst_name = entity_label(worst.get('label', ''), plan)
        worst_delta = worst.get('delta', 0)
        parts.append(f'{worst_name} saw the largest decline ({int(worst_delta):,}).')
    return ' '.join(parts)

def _narrate_records(plan: AnalyticalPlan, insight: InsightResult) -> str:
    count = insight.metrics.get('row_count', len(insight.records))
    scope = scope_phrase(plan) or metric_label(plan.metric)
    when = time_context_phrase(plan)
    header = f'Found {count:,} matching {scope}'
    if when:
        header += f' {when}'
    header += '.'
    lines = []
    for row in insight.records[:10]:
        plate = str(row.get('vehicle_num') or '').strip() or '(plate unavailable)'
        site = row.get('site_name') or row.get('camera_id', '')
        created = _format_timestamp(row.get('created_at'))
        vio = row.get('violation_type', '')
        if vio:
            lines.append(f'- {plate} at {site} ({entity_label(vio, plan)}) — {created}')
        else:
            lines.append(f'- {plate} at {site} — {created}')
    if count > 10:
        lines.append(f'- … and {count - 10:,} more')
    body = '\n'.join(lines) if lines else 'No record details available.'
    return f'{header}\n{body}'

def _series_subject(plan: AnalyticalPlan, dim: str, loc: str, when: str) -> str:
    metric = metric_label(plan.metric)
    if dim == 'hour':
        base = f'{metric} hour'
    elif dim == 'day':
        base = f'{metric} day'
    elif dim == 'date':
        base = metric
    else:
        base = metric
    if loc and when:
        return f"{base} at {loc} on {when.replace('on ', '')}"
    if loc:
        return f'{base} at {loc}'
    if when:
        return f'{base} {when}'
    return base

def _group_context(dim: str, loc: str, when: str) -> str:
    chunks: list[str] = []
    if loc:
        chunks.append(f'at {loc}')
    if when:
        chunks.append(when)
    if not chunks:
        return ''
    return ' ' + ' '.join(chunks)

def _format_period(value: Any, plan: AnalyticalPlan) -> str:
    if value is None:
        return 'unknown period'
    dims = plan.dimensions or plan.group_by or []
    text = str(value).strip()
    if len(text) >= 10 and text[4:5] == '-':
        try:
            dt = datetime.strptime(text[:10], '%Y-%m-%d')
            return f'{dt.day} {_month_name(dt.month)}'
        except ValueError:
            pass
    try:
        hour = int(value)
        if 0 <= hour <= 23 or 'hour' in dims:
            return f'{hour:02d}:00–{hour:02d}:59'
    except (TypeError, ValueError):
        pass
    return text

def _format_timestamp(value: Any) -> str:
    if value is None:
        return ''
    text = str(value)
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(text[:19], fmt)
            return dt.strftime('%d %b %Y %H:%M')
        except ValueError:
            continue
    return text

def _month_name(month: int) -> str:
    names = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
    return names[month - 1] if 1 <= month <= 12 else str(month)