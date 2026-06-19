from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from app.planning.dimensions import dimension_names
from app.planning.objectives import MODE_FOR_OBJECTIVE
from app.planning.plan import AnalyticalPlan
OBJECTIVE_QUERY_MODE: dict[str, str] = {'metric_summary': 'count', 'breakdown': 'grouped_analysis', 'ranking': 'top_n', 'trend': 'trend_analysis', 'comparison': 'comparison', 'growth': 'growth_analysis', 'record_detail': 'record_listing'}
DIMENSION_OBJECTIVES = frozenset({'breakdown', 'ranking', 'growth', 'trend'})
TIME_DIMENSIONS = frozenset({'date', 'day', 'week', 'month', 'hour'})

@dataclass
class SemanticConsistencyResult:
    passed: bool
    repaired: bool
    objective: str
    query_mode_before: str
    query_mode_after: str
    repairs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.passed:
            return {'semantic_consistency_passed': True, 'objective': self.objective, 'query_mode': self.query_mode_after}
        return {'semantic_consistency_repair': True, 'objective': self.objective, 'query_mode_before': self.query_mode_before, 'query_mode_after': self.query_mode_after, 'repairs': self.repairs}

def expected_query_mode(objective: str) -> str:
    return OBJECTIVE_QUERY_MODE.get(objective) or MODE_FOR_OBJECTIVE.get(objective, 'count')

def is_semantically_consistent(plan: AnalyticalPlan) -> bool:
    return plan.query_mode == expected_query_mode(plan.user_objective)

def enforce_semantic_consistency(plan: AnalyticalPlan, *, resolved_dimension: str | None=None) -> SemanticConsistencyResult:
    objective = plan.user_objective
    before = plan.query_mode
    expected = expected_query_mode(objective)
    repairs: list[str] = []
    if before != expected:
        plan.query_mode = expected
        repairs.append(f'query_mode:{before}->{expected}')
    if objective == 'record_detail':
        if plan.dimensions or plan.group_by:
            plan.dimensions = []
            plan.group_by = []
            repairs.append('cleared_dimensions_for_record_listing')
        plan.compare_to = None
        if not plan.sort:
            plan.sort = {'field': 've.created_at', 'direction': 'DESC'}
    elif objective == 'metric_summary':
        if plan.dimensions or plan.group_by:
            plan.dimensions = []
            plan.group_by = []
            repairs.append('cleared_dimensions_for_count')
        plan.compare_to = None
    elif objective == 'comparison':
        plan.time_range = {'preset': 'this_month'}
        plan.compare_to = {'preset': 'last_month'}
        if plan.dimensions or plan.group_by:
            plan.dimensions = []
            plan.group_by = []
            repairs.append('cleared_dimensions_for_comparison')
    elif objective == 'growth':
        if plan.time_range.get('preset') in (None, 'last_30_days'):
            plan.time_range = {'preset': 'this_month'}
        plan.compare_to = {'preset': 'last_month'}
        _apply_dimension_grouping(plan, resolved_dimension, repairs)
    elif objective in DIMENSION_OBJECTIVES:
        _apply_dimension_grouping(plan, resolved_dimension, repairs)
        if objective == 'trend' and plan.dimensions:
            time_dims = [d for d in plan.dimensions if d in TIME_DIMENSIONS]
            if time_dims:
                plan.dimensions = [time_dims[0]]
                plan.group_by = [time_dims[0]]
                repairs.append(f'group_by={time_dims[0]}')
    passed = not repairs
    return SemanticConsistencyResult(passed=passed, repaired=bool(repairs), objective=objective, query_mode_before=before, query_mode_after=plan.query_mode, repairs=repairs)

def _apply_dimension_grouping(plan: AnalyticalPlan, resolved_dimension: str | None, repairs: list[str]) -> None:
    dim = resolved_dimension
    if dim == 'camera':
        dim = 'camera_id'
    if not dim and plan.dimensions:
        dim = plan.dimensions[0]
    if not dim:
        return
    if dim not in dimension_names():
        return
    if plan.dimensions != [dim] or plan.group_by != [dim]:
        plan.dimensions = [dim]
        plan.group_by = [dim]
        repairs.append(f'group_by=[{dim}]')