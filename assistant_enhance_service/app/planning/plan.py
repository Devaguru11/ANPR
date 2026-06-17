from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass
class AnalyticalPlan:
    intent: str = 'analyze'
    user_objective: str = 'metric_summary'
    metric: str = 'violations'
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)
    time_range: dict[str, Any] = field(default_factory=lambda : {'preset': 'last_30_days'})
    sort: dict[str, Any] = field(default_factory=dict)
    limit: int | None = 10
    retrieval_scope: str = 'default'
    query_mode: str = 'count'
    compare_to: dict[str, Any] | None = None
    entity_scope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AnalyticalPlan:
        if not data:
            return cls()
        return cls(intent=str(data.get('intent', 'analyze')), user_objective=str(data.get('user_objective', 'metric_summary')), metric=str(data.get('metric', 'violations')), dimensions=list(data.get('dimensions') or []), filters=dict(data.get('filters') or {}), group_by=list(data.get('group_by') or []), time_range=dict(data.get('time_range') or {'preset': 'last_30_days'}), sort=dict(data.get('sort') or {}), limit=data.get('limit'), retrieval_scope=str(data.get('retrieval_scope') or 'default'), query_mode=str(data.get('query_mode', 'count')), compare_to=data.get('compare_to'), entity_scope=dict(data.get('entity_scope') or {}))