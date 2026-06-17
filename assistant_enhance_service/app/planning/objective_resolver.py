from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any
from app.llm.vllm_client import VLLMClient
from app.planning.conversation_state import load_previous_plan
from app.planning.objectives import default_objective, objective_names, registry_prompt
from app.planning.plan import AnalyticalPlan
from app.planning.transformations import is_valid_transition, transformation_label
RESOLVER_SYSTEM = 'You are an objective resolver for a traffic analytics assistant.\n\nYour ONLY job: determine what analytical TRANSFORMATION the user wants this turn.\nDo NOT choose metrics, filters, dimensions, SQL, or grouping.\n\nObjectives:\n- metric_summary: scalar count or total (how many, show violations at X = summary NOT row listing)\n- breakdown: distribution or segregation by a dimension (by type, breakdown, segregation)\n- trend: values over time (trend, daily, over period)\n- comparison: compare two time periods (vs, compare months)\n- ranking: highest/lowest by CURRENT period volume (most, top, which has the most, highest area, peak hour)\n- growth: largest INCREASE between periods (increased most, fastest growing) — NOT the same as ranking\n- record_detail: explicit row-level data ONLY when user asks for records, list, details, cases, first N, show those records\n\nContext-aware rules:\n- If prior objective was metric_summary and user asks for segregation/breakdown → breakdown\n- If prior was breakdown and user asks for first N / list / records → record_detail\n- If prior was comparison and user asks which increased most → growth (not ranking)\n- If prior was trend and user asks highest area / peak hour / top camera → ranking (NOT record_detail)\n- If prior was ranking and user asks for trend over days → trend\n- "Show violations at X" without record language → metric_summary (NOT record_detail)\n\nReturn JSON only.'
SECONDARY_SYSTEM = RESOLVER_SYSTEM + '\n\nThis is a SECONDARY resolution pass because primary confidence was medium.\nRe-evaluate carefully. Prefer analytical objectives (ranking, trend, breakdown) over record_detail\nunless the user explicitly requests row-level records.'

@dataclass
class ObjectiveResolution:
    objective: str = 'metric_summary'
    confidence: float = 0.5
    alternatives: list[str] = field(default_factory=list)
    reasoning: str = ''
    transformation: dict[str, str] | None = None
    prior_objective: str | None = None
    prior_dataset_type: str | None = None
    resolution_tier: str = 'primary'
    needs_clarification: bool = False
    clarification_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class ObjectiveResolver:
    HIGH = 0.75
    MEDIUM = 0.5

    def __init__(self, llm: VLLMClient) -> None:
        self.llm = llm

    async def resolve(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, prior_dataset_type: str | None=None) -> ObjectiveResolution:
        previous = load_previous_plan(previous_mem_plan)
        prior_obj = previous.user_objective if previous else None
        prior_ds = prior_dataset_type or self._dataset_from_plan(previous_mem_plan)
        primary = await self._pass(question, conversation_context, previous, prior_obj, prior_ds, tier='primary')
        primary = self._apply_transition_prior(primary, prior_obj)
        if primary.confidence >= self.HIGH:
            primary.transformation = transformation_label(prior_obj, primary.objective)
            return primary
        if primary.confidence >= self.MEDIUM:
            secondary = await self._pass(question, conversation_context, previous, prior_obj, prior_ds, tier='secondary', prior=primary)
            secondary = self._apply_transition_prior(secondary, prior_obj)
            best = secondary if secondary.confidence >= primary.confidence else primary
            if best.confidence >= self.MEDIUM:
                best.transformation = transformation_label(prior_obj, best.objective)
                return best
            primary = best
        recovery = self._planner_recovery(primary, prior_obj)
        if recovery:
            recovery.transformation = transformation_label(prior_obj, recovery.objective)
            return recovery
        primary.needs_clarification = True
        primary.clarification_prompt = "I'm not sure what kind of analysis you want (summary, breakdown, trend, ranking, comparison, or record listing). Could you rephrase?"
        if primary.objective == 'record_detail':
            primary.objective = prior_obj or default_objective()
        primary.transformation = transformation_label(prior_obj, primary.objective)
        return primary

    async def _pass(self, question: str, context: str, previous: AnalyticalPlan | None, prior_obj: str | None, prior_ds: str | None, *, tier: str, prior: ObjectiveResolution | None=None) -> ObjectiveResolution:
        system = RESOLVER_SYSTEM if tier == 'primary' else SECONDARY_SYSTEM
        user = self._build_prompt(question, context, previous, prior_obj, prior_ds, prior=prior, tier=tier)
        try:
            data = await self.llm.chat_json(system, user)
            return self._parse(data, prior_obj, prior_ds, tier=tier)
        except Exception:
            return ObjectiveResolution(objective=prior_obj or default_objective(), confidence=0.4, reasoning='fallback: resolver unavailable', prior_objective=prior_obj, prior_dataset_type=prior_ds, resolution_tier=tier)

    def _build_prompt(self, question: str, context: str, previous: AnalyticalPlan | None, prior_obj: str | None, prior_ds: str | None, *, prior: ObjectiveResolution | None=None, tier: str='primary') -> str:
        state = {'prior_objective': prior_obj, 'prior_dataset_type': prior_ds, 'prior_query_mode': previous.query_mode if previous else None, 'prior_metric': previous.metric if previous else None, 'prior_dimensions': previous.dimensions if previous else [], 'prior_filters': previous.filters if previous else {}, 'prior_time_range': previous.time_range if previous else {}}
        extra = ''
        if tier == 'secondary' and prior:
            extra = f'\nPrimary attempt: {prior.objective} (confidence {prior.confidence:.2f})\nAlternatives: {prior.alternatives}\nPrimary reasoning: {prior.reasoning}\n'
        return f'Question: {question}\n\nConversation:\n{context[:2000]}\n\nCurrent analytical state:\n{json.dumps(state, default=str)}\n\nFull prior plan:\n{json.dumps(previous.to_dict() if previous else {}, default=str)}\n{extra}\n{registry_prompt()}\n\nReturn JSON:\n{{"objective":"...", "confidence":0.0-1.0, "alternatives":["..."], "reasoning":"..."}}'

    def _parse(self, data: dict[str, Any], prior_obj: str | None, prior_ds: str | None, *, tier: str) -> ObjectiveResolution:
        obj = str(data.get('objective', default_objective()))
        if obj not in objective_names():
            obj = default_objective()
        alts = [a for a in data.get('alternatives') or [] if a in objective_names() and a != obj][:3]
        conf = float(data.get('confidence', 0.7))
        conf = max(0.0, min(1.0, conf))
        return ObjectiveResolution(objective=obj, confidence=conf, alternatives=alts, reasoning=str(data.get('reasoning', '')), prior_objective=prior_obj, prior_dataset_type=prior_ds, resolution_tier=tier)

    def _apply_transition_prior(self, resolution: ObjectiveResolution, prior_obj: str | None) -> ObjectiveResolution:
        if not prior_obj:
            return resolution
        if is_valid_transition(prior_obj, resolution.objective):
            return resolution
        if resolution.objective in ('ranking', 'growth', 'trend', 'breakdown', 'comparison', 'metric_summary'):
            resolution.reasoning += f'; kept {resolution.objective} (analytical objective preserved)'
            return resolution
        for alt in resolution.alternatives:
            if alt == 'record_detail':
                continue
            if is_valid_transition(prior_obj, alt):
                resolution.reasoning += f'; adjusted from {resolution.objective} to {alt} (invalid transition)'
                resolution.objective = alt
                resolution.confidence = max(0.5, resolution.confidence - 0.1)
                return resolution
        resolution.reasoning += f'; kept {resolution.objective} despite transition tension from {prior_obj}'
        return resolution

    def _planner_recovery(self, resolution: ObjectiveResolution, prior_obj: str | None) -> ObjectiveResolution | None:
        candidates = [resolution.objective, *resolution.alternatives]
        for obj in candidates:
            if obj == 'record_detail':
                continue
            if obj in objective_names() and (not prior_obj or is_valid_transition(prior_obj, obj)):
                return ObjectiveResolution(objective=obj, confidence=0.45, alternatives=resolution.alternatives, reasoning=f'planner recovery from low-confidence {resolution.objective}', prior_objective=resolution.prior_objective, prior_dataset_type=resolution.prior_dataset_type, resolution_tier='recovery')
        if prior_obj and prior_obj != 'record_detail':
            return ObjectiveResolution(objective=prior_obj, confidence=0.4, reasoning='planner recovery: inherited prior objective', prior_objective=prior_obj, prior_dataset_type=resolution.prior_dataset_type, resolution_tier='recovery')
        return None

    @staticmethod
    def _dataset_from_plan(mem_plan: dict[str, Any] | None) -> str | None:
        if not mem_plan:
            return None
        ctx = mem_plan.get('context') or {}
        if isinstance(ctx, dict) and ctx.get('dataset_type'):
            return ctx.get('dataset_type')
        ap = mem_plan.get('analytical_plan') or mem_plan.get('current_state') or mem_plan
        mode = ap.get('query_mode')
        mapping = {'count': 'scalar', 'comparison': 'comparison', 'record_listing': 'record_set', 'trend_analysis': 'time_series', 'growth_analysis': 'growth', 'grouped_analysis': 'grouped', 'top_n': 'grouped'}
        return mapping.get(mode)