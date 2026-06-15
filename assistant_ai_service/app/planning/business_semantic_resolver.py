from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any
from app.llm.vllm_client import VLLMClient
from app.planning.business_concepts import BUSINESS_CONCEPTS, concept_names, default_concept, registry_prompt
from app.planning.conversation_state import load_previous_plan
from app.schema.semantic_catalog import SchemaSemanticCatalog
RESOLVER_SYSTEM = "You are a business semantic resolver for a traffic analytics assistant.\n\nYour ONLY job: determine which BUSINESS CONCEPT the user is asking about.\n\nUse:\n- the user's question and phrasing\n- conversation context and prior analytical focus\n- database table meanings, column meanings, relationships, and sample values\n- canonical business concept descriptions provided\n\nReason about meaning — do not pattern-match isolated words or phrases.\n\nDo NOT choose objectives (count, trend, ranking), dimensions, time ranges, or SQL.\nDo NOT choose filters or entities — only the underlying business concept.\n\nIf conversation context already established a business concept and the user is refining\nthe same subject (new filter, location, or time), inherit that concept unless they\nclearly switch to a different subject.\n\nReturn JSON only."

@dataclass
class BusinessSemanticResolution:
    business_concept: str = 'violations'
    confidence: float = 0.5
    alternatives: list[str] = field(default_factory=list)
    reasoning: str = ''
    resolution_tier: str = 'primary'
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    candidate_concepts: list[str] = field(default_factory=list)
    candidate_scores: dict[str, float] = field(default_factory=dict)
    selection_rationale: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class BusinessSemanticResolver:
    LOW = 0.5

    def __init__(self, llm: VLLMClient, schema_catalog: SchemaSemanticCatalog) -> None:
        self.llm = llm
        self.schema_catalog = schema_catalog

    async def resolve(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None) -> BusinessSemanticResolution:
        previous = load_previous_plan(previous_mem_plan)
        prior_concept = self._prior_concept(previous_mem_plan, previous)
        data = await self._llm_pass(question, conversation_context, prior_concept, previous)
        resolution = self._parse(data, prior_concept)
        return self._apply_recovery(resolution, prior_concept, question, conversation_context)

    def _prior_concept(self, previous_mem_plan: dict[str, Any] | None, previous: Any) -> str | None:
        if previous_mem_plan:
            bsr = previous_mem_plan.get('business_semantic_resolution') or {}
            if bsr.get('business_concept'):
                return str(bsr['business_concept'])
        if previous and getattr(previous, 'metric', None):
            for (cid, concept) in BUSINESS_CONCEPTS.items():
                if concept.metric == previous.metric:
                    return cid
        return None

    async def _llm_pass(self, question: str, context: str, prior_concept: str | None, previous: Any) -> dict[str, Any]:
        state = {'prior_business_concept': prior_concept, 'prior_metric': previous.metric if previous else None, 'prior_objective': previous.user_objective if previous else None}
        user = f'Question: {question}\n\nConversation:\n{context[:2000]}\n\nAnalytical state:\n{json.dumps(state, default=str)}\n\n{self.schema_catalog.to_prompt()}\n\n{registry_prompt()}\n\nReturn JSON:\n{{"business_concept":"...", "confidence":0.0-1.0, "alternatives":["..."], "reasoning":"..."}}'
        try:
            return await self.llm.chat_json(RESOLVER_SYSTEM, user, max_tokens=512)
        except Exception:
            return {'business_concept': prior_concept or default_concept(), 'confidence': 0.4, 'alternatives': [], 'reasoning': 'fallback: business semantic resolver unavailable'}

    def _parse(self, data: dict[str, Any], prior_concept: str | None) -> BusinessSemanticResolution:
        concept = str(data.get('business_concept') or prior_concept or default_concept())
        if concept not in concept_names():
            concept = prior_concept or default_concept()
        alts = [str(a) for a in data.get('alternatives') or [] if str(a) in concept_names()][:3]
        conf = max(0.0, min(1.0, float(data.get('confidence', 0.7))))
        return BusinessSemanticResolution(business_concept=concept, confidence=conf, alternatives=alts, reasoning=str(data.get('reasoning', '')))

    def _apply_recovery(self, resolution: BusinessSemanticResolution, prior_concept: str | None, question: str, context: str) -> BusinessSemanticResolution:
        _ = (question, context)
        if resolution.confidence >= self.LOW:
            return resolution
        if prior_concept:
            resolution.business_concept = prior_concept
            resolution.confidence = max(resolution.confidence, 0.55)
            resolution.resolution_tier = 'recovery'
            resolution.reasoning += '; inherited prior business concept'
            return resolution
        resolution.resolution_tier = 'low_confidence'
        resolution.reasoning += '; proceeding with best-effort business concept'
        return resolution