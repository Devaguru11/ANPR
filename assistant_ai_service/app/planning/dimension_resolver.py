from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any
from app.llm.vllm_client import VLLMClient
from app.planning.conversation_state import load_previous_plan
from app.planning.dimensions import dimension_names, registry_prompt
from app.planning.objective_resolver import ObjectiveResolution
from app.planning.objectives import ANALYTICAL_OBJECTIVES
DIMENSION_REQUIRED_OBJECTIVES = frozenset({'breakdown', 'ranking', 'growth'})
TREND_DEFAULT_DIMENSION = 'date'
RESOLVER_SYSTEM = 'You are a dimension resolver for a traffic analytics assistant.\n\nYour ONLY job: determine which analytical DIMENSION the user wants to group or rank by.\nDo NOT choose objectives, metrics, filters, SQL, or time ranges.\n\nDimension mapping examples:\n- highest area / top location / which area → location\n- peak hour / busiest hour / hourly peak → hour\n- worst violation type / top violation type → violation_type\n- top camera / most active camera → camera\n- busiest day / which day → day\n- daily trend / over time → date\n- largest growth by camera → camera\n- largest growth by area → location\n\nReturn null dimension for scalar summaries (total count), period comparisons, or row-level record requests.\n\nReturn JSON only.'
SECONDARY_SYSTEM = RESOLVER_SYSTEM + '\n\nThis is a SECONDARY resolution pass because primary confidence was medium.\nRe-evaluate carefully using conversation context and the resolved objective.'

@dataclass
class DimensionResolution:
    dimension: str | None = None
    confidence: float = 0.5
    alternatives: list[str] = field(default_factory=list)
    candidate_dimensions: list[str] = field(default_factory=list)
    candidate_scores: dict[str, float] = field(default_factory=dict)
    selection_rationale: str = ''
    reasoning: str = ''
    resolution_tier: str = 'primary'
    needs_clarification: bool = False
    clarification_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class DimensionResolver:
    HIGH = 0.75
    MEDIUM = 0.5

    def __init__(self, llm: VLLMClient) -> None:
        self.llm = llm

    async def resolve(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, resolved_objective: ObjectiveResolution) -> DimensionResolution:
        if resolved_objective.objective not in ANALYTICAL_OBJECTIVES:
            return DimensionResolution(dimension=None, confidence=1.0, reasoning='objective does not require grouping dimension')
        previous = load_previous_plan(previous_mem_plan)
        primary = await self._pass(question, conversation_context, previous, resolved_objective, tier='primary')
        if primary.confidence >= self.HIGH:
            return primary
        if primary.confidence >= self.MEDIUM:
            secondary = await self._pass(question, conversation_context, previous, resolved_objective, tier='secondary', prior=primary)
            best = secondary if secondary.confidence >= primary.confidence else primary
            if best.confidence >= self.MEDIUM:
                return best
            primary = best
        recovery = self._dimension_recovery(primary, previous, resolved_objective.objective)
        if recovery:
            return recovery
        if resolved_objective.objective in DIMENSION_REQUIRED_OBJECTIVES | {'trend'}:
            primary.needs_clarification = True
            primary.clarification_prompt = "I'm not sure which dimension you want to analyze (location, camera, violation type, hour, day, etc.). Could you clarify?"
        return primary

    async def _pass(self, question: str, context: str, previous: Any, resolved: ObjectiveResolution, *, tier: str, prior: DimensionResolution | None=None) -> DimensionResolution:
        state = {'objective': resolved.objective, 'prior_objective': resolved.prior_objective, 'prior_dimensions': previous.dimensions if previous else [], 'prior_query_mode': previous.query_mode if previous else None}
        extra = ''
        if tier == 'secondary' and prior:
            extra = f'\nPrior dimension attempt: {prior.dimension} (confidence {prior.confidence:.2f})\nAlternatives: {prior.alternatives}\nRe-evaluate with conversation timeframe and analytical intent.\n'
        user = f'Question: {question}\n\nResolved objective: {resolved.objective}\nConversation:\n{context[:2000]}\n\nAnalytical state:\n{json.dumps(state, default=str)}\n{extra}\nDimensions:\n{registry_prompt()}\n\nReturn JSON: {{"dimension":"location|hour|...|null", "confidence":0.0-1.0, "alternatives":["..."], "reasoning":"..."}}'
        system = RESOLVER_SYSTEM if tier == 'primary' else SECONDARY_SYSTEM
        try:
            data = await self.llm.chat_json(system, user)
            return self._parse(data, tier=tier)
        except Exception:
            return DimensionResolution(dimension=previous.dimensions[0] if previous and previous.dimensions else None, confidence=0.35, reasoning='fallback: dimension resolver unavailable', resolution_tier=tier)

    def _dimension_recovery(self, resolution: DimensionResolution, previous: Any, objective: str) -> DimensionResolution | None:
        candidates: list[str | None] = [resolution.dimension, *resolution.alternatives]
        if previous and previous.dimensions:
            candidates.append(previous.dimensions[0])
        if objective == 'trend':
            candidates.append(TREND_DEFAULT_DIMENSION)
        seen: set[str] = set()
        for dim in candidates:
            if not dim or dim in seen or dim not in dimension_names():
                continue
            seen.add(dim)
            return DimensionResolution(dimension=dim, confidence=0.45, alternatives=resolution.alternatives, reasoning=f'dimension recovery from low-confidence {resolution.dimension}', resolution_tier='recovery')
        return None

    def _parse(self, data: dict[str, Any], *, tier: str) -> DimensionResolution:
        raw = data.get('dimension')
        dim = None if raw in (None, 'null', '') else str(raw)
        if dim and dim not in dimension_names():
            dim = None
        alts = [a for a in data.get('alternatives') or [] if a in dimension_names() and a != dim][:3]
        conf = float(data.get('confidence', 0.7))
        conf = max(0.0, min(1.0, conf))
        return DimensionResolution(dimension=dim, confidence=conf, alternatives=alts, reasoning=str(data.get('reasoning', '')), resolution_tier=tier)