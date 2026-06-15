from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ObjectiveDef:
    name: str
    description: str
    default_mode: str
OBJECTIVES: dict[str, ObjectiveDef] = {'metric_summary': ObjectiveDef('metric_summary', 'Scalar count or total for a metric within scope (how many, total, show summary)', 'count'), 'breakdown': ObjectiveDef('breakdown', 'Distribution or segregation by dimension (by type, breakdown, segregation)', 'grouped_analysis'), 'trend': ObjectiveDef('trend', 'Change over time buckets (trend, daily, over last N days)', 'trend_analysis'), 'comparison': ObjectiveDef('comparison', 'Compare two time periods (this month vs last month)', 'comparison'), 'ranking': ObjectiveDef('ranking', 'Rank entities by current period volume (top, most, highest)', 'top_n'), 'growth': ObjectiveDef('growth', 'Rank entities by period-over-period increase (increased most, fastest growing)', 'growth_analysis'), 'record_detail': ObjectiveDef('record_detail', 'Row-level records (list, details, cases, examples, first N, show those records)', 'record_listing')}
MODE_FOR_OBJECTIVE = {o.name: o.default_mode for o in OBJECTIVES.values()}
ANALYTICAL_OBJECTIVES = frozenset({'metric_summary', 'breakdown', 'trend', 'comparison', 'ranking', 'growth'})

def objective_names() -> list[str]:
    return list(OBJECTIVES.keys())

def registry_prompt() -> str:
    return '\n'.join((f'- {o.name}: {o.description}' for o in OBJECTIVES.values()))

def default_objective() -> str:
    return 'metric_summary'