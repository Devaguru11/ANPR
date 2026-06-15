from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class QueryModeDef:
    name: str
    description: str
    dataset_type: str
QUERY_MODES: dict[str, QueryModeDef] = {'count': QueryModeDef('count', 'Single scalar count', 'scalar'), 'aggregation': QueryModeDef('aggregation', 'Single aggregated value', 'scalar'), 'grouped_analysis': QueryModeDef('grouped_analysis', 'Breakdown by dimension', 'grouped'), 'record_listing': QueryModeDef('record_listing', 'Row-level records', 'record_set'), 'comparison': QueryModeDef('comparison', 'Compare two periods', 'comparison'), 'trend_analysis': QueryModeDef('trend_analysis', 'Time series over periods', 'time_series'), 'ranking': QueryModeDef('ranking', 'Ranked entities', 'grouped'), 'top_n': QueryModeDef('top_n', 'Top N by metric', 'grouped'), 'bottom_n': QueryModeDef('bottom_n', 'Bottom N by metric', 'grouped'), 'anomaly_detection': QueryModeDef('anomaly_detection', 'Outlier detection', 'grouped'), 'growth_analysis': QueryModeDef('growth_analysis', 'Period-over-period growth by entity', 'growth')}

def mode_names() -> list[str]:
    return list(QUERY_MODES.keys())

def registry_prompt() -> str:
    return '\n'.join((f'- {m.name}: {m.description}' for m in QUERY_MODES.values()))

def dataset_type_for_mode(mode: str) -> str:
    return QUERY_MODES.get(mode, QUERY_MODES['count']).dataset_type