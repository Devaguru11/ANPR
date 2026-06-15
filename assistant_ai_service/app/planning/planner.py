from __future__ import annotations
from app.planning.business_concepts import concept_to_metric
from app.planning.business_semantic_resolver import BusinessSemanticResolution
from app.planning.dimensions import dimension_names, relocate_time_filters
from app.planning.objective_resolver import ObjectiveResolution
from app.planning.objectives import MODE_FOR_OBJECTIVE, default_objective, objective_names
from app.planning.plan import AnalyticalPlan
from app.planning.retrieval_scope import RetrievalScopeSpec, apply_retrieval_scope
from app.planning.semantic_coherence import LISTING_SCOPE_KINDS, reconcile_objective_and_scope
from app.planning.scope import load_previous_plan, merge_scope, should_inherit
from app.planning.temporal_resolver import TemporalResolution

class AnalyticalPlanner:

    async def plan(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, entity_resolutions: list[dict[str, Any]], entity_scope: dict[str, Any], resolved_objective: ObjectiveResolution, resolved_dimension: DimensionResolution, resolved_temporal: TemporalResolution, retrieval_scope: str | None=None, business_resolution: BusinessSemanticResolution | None=None) -> tuple[AnalyticalPlan, dict[str, Any]]:
        previous = load_previous_plan(previous_mem_plan)
        inherit = previous is not None and should_inherit(question, conversation_context, previous)
        proposed = self._construct_plan(question, previous, entity_scope, resolved_objective, resolved_dimension, resolved_temporal, retrieval_scope, business_resolution)
        (merged, modifications) = merge_scope(previous, proposed, inherit=inherit)
        self._apply_resolved_semantics(merged, resolved_objective, resolved_dimension, resolved_temporal)
        self._normalize_plan(merged, resolved_dimension)
        if retrieval_scope:
            merged.retrieval_scope = retrieval_scope
        self._apply_plan_coherence(merged, previous)
        apply_retrieval_scope(merged, merged.retrieval_scope)
        debug = {'inherit': inherit, 'modifications': modifications, 'proposed': proposed.to_dict(), 'previous': previous.to_dict() if previous else None, 'retrieval_scope': retrieval_scope, 'objective_resolution': resolved_objective.to_dict(), 'dimension_resolution': resolved_dimension.to_dict(), 'temporal_resolution': resolved_temporal.to_dict(), 'business_semantic_resolution': business_resolution.to_dict() if business_resolution else None}
        return (merged, debug)

    def _construct_plan(self, question: str, previous: AnalyticalPlan | None, entity_scope: dict[str, Any], resolved_objective: ObjectiveResolution, resolved_dimension: DimensionResolution, resolved_temporal: TemporalResolution, retrieval_scope: str | None=None, business_resolution: BusinessSemanticResolution | None=None) -> AnalyticalPlan:
        metric = self._resolve_metric(previous, entity_scope, business_resolution)
        plan = AnalyticalPlan(intent=self._intent_label(question, resolved_objective.objective), user_objective=resolved_objective.objective, metric=metric, entity_scope={**dict(previous.entity_scope if previous else {}), **entity_scope}, time_range=dict(resolved_temporal.time_range), retrieval_scope=retrieval_scope or 'default', sort=self._resolve_sort(resolved_objective.objective, resolved_dimension.dimension, retrieval_scope))
        self._apply_entity_scope(plan)
        self._apply_resolved_semantics(plan, resolved_objective, resolved_dimension, resolved_temporal)
        apply_retrieval_scope(plan, retrieval_scope)
        return plan

    def _apply_resolved_semantics(self, plan: AnalyticalPlan, resolved_objective: ObjectiveResolution, resolved_dimension: DimensionResolution, resolved_temporal: TemporalResolution) -> None:
        plan.user_objective = resolved_objective.objective
        plan.time_range = dict(resolved_temporal.time_range)
        self._apply_objective(plan)
        if resolved_dimension.dimension and plan.user_objective in ('breakdown', 'ranking', 'growth', 'trend'):
            plan.dimensions = [resolved_dimension.dimension]
            plan.group_by = [resolved_dimension.dimension]
        self._apply_entity_scope(plan)

    def _resolve_metric(self, previous: AnalyticalPlan | None, entity_scope: dict[str, Any], business_resolution: BusinessSemanticResolution | None=None) -> str:
        if entity_scope.get('plate_suffix'):
            return 'plate_reads'
        if business_resolution and business_resolution.business_concept:
            return concept_to_metric(business_resolution.business_concept)
        if previous and previous.metric:
            return previous.metric
        return 'violations'

    def _resolve_sort(self, objective: str, dimension: str | None, retrieval_scope: str | None=None) -> dict[str, str]:
        spec_kind = retrieval_scope or 'default'
        if spec_kind.startswith('latest_'):
            return {'field': 've.created_at', 'direction': 'DESC'}
        if spec_kind.startswith('first_'):
            return {'field': 've.created_at', 'direction': 'ASC'}
        if spec_kind == 'all':
            return {'field': 've.created_at', 'direction': 'ASC'}
        if objective == 'record_detail':
            return {'field': 've.created_at', 'direction': 'DESC'}
        if objective in ('ranking', 'growth') or dimension == 'hour':
            return {'field': 'total', 'direction': 'DESC'}
        if objective == 'trend':
            return {'field': 'period', 'direction': 'ASC'}
        return {'field': 'total', 'direction': 'DESC'}

    def _intent_label(self, question: str, objective: str) -> str:
        q = question.strip()
        return q[:80] if q else objective

    def _apply_plan_coherence(self, plan: AnalyticalPlan, previous: AnalyticalPlan | None) -> None:
        prior_obj = previous.user_objective if previous else None
        result = reconcile_objective_and_scope(plan.user_objective, plan.retrieval_scope, prior_objective=prior_obj, dimension=plan.dimensions[0] if plan.dimensions else None)
        if not result.adjusted:
            return
        plan.user_objective = result.objective
        plan.retrieval_scope = result.retrieval_scope
        self._apply_objective(plan)
        spec = RetrievalScopeSpec.parse(plan.retrieval_scope)
        if spec.kind in LISTING_SCOPE_KINDS:
            plan.sort = self._resolve_sort('record_detail', None, plan.retrieval_scope)

    def _apply_objective(self, plan: AnalyticalPlan) -> None:
        obj = plan.user_objective
        if obj not in objective_names():
            obj = default_objective()
            plan.user_objective = obj
        if obj == 'record_detail':
            plan.query_mode = 'record_listing'
            plan.dimensions = []
            plan.group_by = []
            plan.compare_to = None
            if not plan.sort:
                plan.sort = {'field': 've.created_at', 'direction': 'DESC'}
            return
        if obj == 'metric_summary':
            plan.query_mode = 'count'
            plan.dimensions = []
            plan.group_by = []
            plan.compare_to = None
        elif obj == 'breakdown':
            plan.query_mode = 'grouped_analysis'
        elif obj == 'trend':
            plan.query_mode = 'trend_analysis'
        elif obj == 'comparison':
            plan.query_mode = 'comparison'
            plan.time_range = {'preset': 'this_month'}
            plan.compare_to = {'preset': 'last_month'}
            plan.dimensions = []
            plan.group_by = []
        elif obj == 'ranking':
            plan.query_mode = 'top_n'
        elif obj == 'growth':
            plan.query_mode = 'growth_analysis'
            if plan.time_range.get('preset') in (None, 'last_30_days'):
                plan.time_range = {'preset': 'this_month'}
            plan.compare_to = {'preset': 'last_month'}
        else:
            plan.query_mode = MODE_FOR_OBJECTIVE.get(obj, 'count')

    def _normalize_plan(self, plan: AnalyticalPlan, resolved_dimension: DimensionResolution) -> None:
        (plan.filters, plan.time_range) = relocate_time_filters(plan.filters, plan.time_range)
        if plan.query_mode == 'comparison':
            plan.time_range = {'preset': 'this_month'}
            plan.compare_to = {'preset': 'last_month'}
            plan.dimensions = []
            plan.group_by = []
            return
        if plan.compare_to and plan.query_mode not in ('comparison', 'growth_analysis'):
            plan.compare_to = None
        if plan.filters.get('violation_type') and plan.metric in ('cameras', 'detections', 'plate_reads', 'vehicles'):
            plan.metric = 'violations'
        dims = [d for d in plan.dimensions if d in dimension_names()]
        if len(dims) >= len(dimension_names()) - 2:
            dims = []
        time_dims = ('date', 'day', 'week', 'month', 'hour')
        scope_dims = {'location', 'plate_suffix'}
        breakdown_dims = [d for d in dims if d not in scope_dims]
        if plan.query_mode == 'growth_analysis':
            plan.dimensions = breakdown_dims[:1] if breakdown_dims else list(plan.dimensions[:1])
            plan.group_by = list(plan.dimensions)
            return
        if plan.query_mode in ('count', 'aggregation') and breakdown_dims:
            time_only = all((d in time_dims for d in breakdown_dims))
            if time_only:
                breakdown_dims = []
            elif any((d in breakdown_dims for d in time_dims)):
                plan.query_mode = 'trend_analysis'
                breakdown_dims = [d for d in breakdown_dims if d in time_dims][:1]
            else:
                plan.query_mode = 'grouped_analysis'
        if plan.query_mode in ('count', 'aggregation', 'record_listing', 'comparison'):
            plan.dimensions = []
            plan.group_by = []
            if plan.query_mode != 'record_listing':
                return
        if plan.query_mode == 'trend_analysis':
            breakdown_dims = [d for d in breakdown_dims if d in time_dims][:1]
        resolved_dim = resolved_dimension.dimension
        if resolved_dim and plan.user_objective in ('breakdown', 'ranking', 'growth', 'trend'):
            plan.dimensions = [resolved_dim]
            plan.group_by = [resolved_dim]
            return
        plan.dimensions = breakdown_dims[:3]
        plan.group_by = list(plan.dimensions)

    def _apply_entity_scope(self, plan: AnalyticalPlan) -> None:
        scope = plan.entity_scope
        if scope.get('camera_id'):
            plan.filters['location'] = scope['camera_id']
        if scope.get('violation_type'):
            plan.filters['violation_type'] = scope['violation_type']
        if scope.get('vehicle_type'):
            plan.filters['vehicle_type'] = scope['vehicle_type']
        if scope.get('vehicle_category'):
            plan.filters['vehicle_category'] = scope['vehicle_category']
        if scope.get('plate_suffix'):
            plan.filters['plate_suffix'] = scope['plate_suffix']
            plan.metric = 'plate_reads'
            plan.filters.pop('violation_type', None)