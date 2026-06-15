from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from app.entity.cache import EntityDiscovery
from app.llm.vllm_client import VLLMClient
from app.planning.business_concept_catalog import BusinessConceptCatalog
from app.planning.business_concept_scorer import extract_candidates, score_candidates
from app.planning.business_concepts import BUSINESS_CONCEPTS, concept_names, default_concept
from app.planning.business_semantic_resolver import BusinessSemanticResolution
from app.planning.conversation_state import load_previous_plan
from app.planning.objectives import default_objective, objective_names
from app.planning.dimension_profiles import resolver_prompt as dimension_resolver_prompt
from app.planning.dimension_scorer import apply_dimension_selection
from app.planning.state_summary import active_state_for_resolver
from app.planning.prompt_metrics import breakdown_prompt
from app.planning.resolution_timing import ResolutionTiming
from app.planning.semantic_cache import SemanticResolutionCache
from app.planning.retrieval_scope import RetrievalScopeSpec
from app.planning.semantic_coherence import reconcile_objective_and_scope
from app.planning.semantic_resolver import SemanticResolution, SemanticResolver
from app.planning.temporal_resolver import TemporalResolver
from app.config import settings
UNIFIED_SYSTEM = 'You are a unified semantic resolver for a traffic analytics assistant.\n\nIn ONE response resolve:\n1. business_concept — which domain subject the user is asking about\n2. objective — analytical transformation\n3. dimension — grouping/ranking axis, or null\n4. entities — filter hints from question text (location name, violation_type, vehicle_type, plate_suffix)\n5. time_range — temporal scope\n6. retrieval_scope — how many / which rows to return\n\nBusiness concepts: return ranked candidate concepts in business_candidates (2-3 items).\nUse catalog descriptions, examples, and negative examples. Reason about meaning, not isolated keywords.\n\nObjectives:\n- metric_summary: scalar count (how many)\n- breakdown: distribution by dimension\n- trend: values over time\n- comparison: compare two time periods\n- ranking: highest/lowest by volume\n- growth: largest increase between periods\n- record_detail: row-level records (list, all, plate reads, first N, latest N)\n\nDimensions: return ranked dimension_candidates (2-3 items) when grouping applies; null for scalar counts.\nDimension mapping: highest area→location, peak hour→hour, busiest day→day, worst violation type→violation_type,\ntop camera→camera, daily trend→date, largest growth by camera→camera.\n\nTemporal: presets today, yesterday, this_week, this_month, last_month, last_7_days, last_30_days;\nspecific dates {"preset":"specific_date","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}.\n\nRetrieval scope (must align with objective):\n- metric_summary → default only (scalar count; no row limit)\n- record_detail → all, first_N, latest_N, sample, single (row retrieval)\n- ranking → top_N (ranked aggregate rows)\n- breakdown/trend/comparison/growth → default unless user asks for sample rows\n\nConversational transformations:\n- Follow-ups may CHANGE objective while keeping filters, metric, and time range.\n- When the user references prior results and asks for rows, examples, or a subset,\n  transform to record_detail with the appropriate retrieval_scope.\n- When the user asks how many / a total, use metric_summary with default scope.\n- metric_summary + first_N is invalid; choose one coherent interpretation.\n\nUse prior analytical state (objective, query_mode, filters, retrieval_scope) to\nreason about refinements — do not blindly inherit the prior objective when the\nuser is clearly requesting a different analytical form.\n\nReturn JSON only.'
_TIME_PHRASES: tuple[tuple[str, str], ...] = (('today', 'today'), ('yesterday', 'yesterday'), ('this week', 'this_week'), ('this month', 'this_month'), ('last month', 'last_month'), ('last 7 days', 'last_7_days'), ('last 5 days', 'last_5_days'), ('last 30 days', 'last_30_days'))

@dataclass
class UnifiedResolveResult:
    business: BusinessSemanticResolution
    semantic: SemanticResolution
    entity_scope: dict[str, Any]
    entity_resolutions: list[dict[str, Any]]
    timing: ResolutionTiming
    prompt_metrics: dict[str, Any]

class UnifiedSemanticResolver(SemanticResolver):

    def __init__(self, llm: VLLMClient, entities: EntityDiscovery, catalog: BusinessConceptCatalog, cache: SemanticResolutionCache | None=None) -> None:
        super().__init__(llm, entities)
        self.catalog = catalog
        self.cache = cache or SemanticResolutionCache()

    async def resolve(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, mem_time_range: dict[str, Any] | None=None, business_concept: str | None=None) -> tuple[SemanticResolution, dict[str, Any], list[dict[str, Any]]]:
        result = await self.resolve_unified(question, conversation_context, previous_mem_plan, mem_time_range)
        return (result.semantic, result.entity_scope, result.entity_resolutions)

    async def resolve_unified(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, mem_time_range: dict[str, Any] | None=None) -> UnifiedResolveResult:
        timing = ResolutionTiming()
        context = conversation_context[:settings.semantic_context_max_chars]
        t0 = timing.start('schema_load')
        catalog_text = self.catalog.resolver_prompt()
        timing.stop('schema_load', t0)
        previous = load_previous_plan(previous_mem_plan)
        prior_obj = previous.user_objective if previous else None
        prior_concept = self._prior_concept(previous_mem_plan, previous)
        active_tr = (previous.time_range if previous else None) or mem_time_range or {'preset': 'last_30_days'}
        reporting = TemporalResolver._reporting_period(active_tr, conversation_context)
        inherit = previous is not None and self._should_inherit(question, conversation_context, previous)
        prev_scope = previous.entity_scope if previous and inherit else {}
        partial_date = TemporalResolver._resolve_partial_date(question, reporting)
        cached = None
        if settings.semantic_cache_enabled and (not inherit):
            t_cache = timing.start('cache_lookup')
            cached = self.cache.lookup(question)
            timing.stop('cache_lookup', t_cache)
        t_prompt = timing.start('prompt_construction')
        state = active_state_for_resolver(previous, prior_concept=prior_concept, inherit=inherit)
        if reporting.get('conversation_year'):
            state['conversation_year'] = reporting['conversation_year']
        metadata = json.dumps(state, default=str)
        user = f'Question: {question}\n\nToday (UTC): {datetime.utcnow():%Y-%m-%d}\nContext:\n{context}\n\nActive state:\n{metadata}\n\n{catalog_text}\n\n{dimension_resolver_prompt()}\n\nReturn JSON:\n{{"business_candidates":[{{"concept":"...","confidence":0.0-1.0}},...], "dimension_candidates":[{{"dimension":"...|null","confidence":0.0-1.0}},...], "business_concept":"...", "objective":"...", "dimension":"...|null", "entities":{{"location":"...", "violation_type":"...", "vehicle_type":"...", "plate_suffix":"..."}}, "time_range":{{"preset":"today|specific_date|..."}}, "retrieval_scope":"all|first_10|latest_20|top_5|sample|single|default", "confidence":0.0-1.0, "reasoning":"...", "alternatives":["..."]}}'
        prompt_metrics = breakdown_prompt(UNIFIED_SYSTEM, user, catalog=catalog_text, metadata=metadata, context=context)
        timing.stop('prompt_construction', t_prompt)
        if cached:
            timing.cache_hit = True
            business = self._business_from_cache(cached, prior_concept)
            semantic = self._semantic_from_cache(cached, prior_obj)
            semantic.entities = {}
            semantic.time_range = self._time_for_cache_hit(question, reporting, partial_date, active_tr, inherit)
            semantic = self._apply_dimension_scoring(semantic, {'dimension': semantic.dimension, 'confidence': semantic.confidence, 'dimension_candidates': [{'dimension': semantic.dimension, 'confidence': 0.85}] if semantic.dimension else []}, question, previous, inherit)
        else:
            t_llm = timing.start('llm_inference')
            data = await self._llm_pass_unified(user, prior_concept, prior_obj, previous, active_tr)
            timing.stop('llm_inference', t_llm)
            t_parse = timing.start('response_parsing')
            business = self._parse_business(data, prior_concept, question=question, conversation_context=context, prior_metric=previous.metric if previous else None, inherit=inherit)
            semantic = self._parse_unified(data, prior_obj)
            semantic = self._apply_dimension_scoring(semantic, data, question, previous, inherit)
            timing.stop('response_parsing', t_parse)
            if settings.semantic_cache_enabled and (not inherit) and (business.confidence >= 0.5):
                self.cache.store(question, {'business_concept': business.business_concept, 'objective': semantic.objective, 'dimension': semantic.dimension, 'retrieval_scope': semantic.retrieval_scope})
        t_post = timing.start('post_processing')
        semantic = self._normalize_time(semantic, question, reporting, partial_date, active_tr, inherit)
        semantic = self._apply_record_listing_intent(semantic, question, prior_obj)
        semantic = self._apply_semantic_coherence(semantic, prior_obj, dimension=semantic.dimension)
        semantic = self._apply_transformation_boost(semantic, prior_obj, question)
        semantic = self._apply_confidence_recovery(semantic, previous, prior_obj, question)
        business = self._apply_business_recovery(business, prior_concept)
        (entity_scope, entity_resolutions) = self._enrich_entities(semantic.entities, question, prev_scope, inherit)
        from app.planning.scope import question_references_peak_hour
        if inherit and question_references_peak_hour(question) and (prev_scope.get('peak_hour') is not None):
            entity_scope = dict(entity_scope)
            entity_scope['peak_hour'] = prev_scope['peak_hour']
        clarification = self.entity_resolver.needs_clarification(entity_resolutions)
        if clarification:
            semantic.needs_clarification = True
            semantic.clarification_prompt = clarification
        timing.stop('post_processing', t_post)
        return UnifiedResolveResult(business=business, semantic=semantic, entity_scope=entity_scope, entity_resolutions=entity_resolutions, timing=timing, prompt_metrics=prompt_metrics)

    def _should_inherit(self, question: str, context: str, previous: Any) -> bool:
        from app.planning.scope import should_inherit
        return should_inherit(question, context, previous)

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

    async def _llm_pass_unified(self, user: str, prior_concept: str | None, prior_obj: str | None, previous: Any, active_tr: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.llm.chat_json(UNIFIED_SYSTEM, user, max_tokens=512)
        except Exception:
            return {'business_concept': prior_concept or default_concept(), 'objective': prior_obj or default_objective(), 'dimension': previous.dimensions[0] if previous and previous.dimensions else None, 'entities': {}, 'time_range': active_tr, 'retrieval_scope': 'default', 'confidence': 0.4, 'alternatives': [], 'reasoning': 'fallback: unified semantic resolver unavailable'}

    def _parse_business(self, data: dict[str, Any], prior_concept: str | None, *, question: str='', conversation_context: str='', prior_metric: str | None=None, inherit: bool=False) -> BusinessSemanticResolution:
        candidates = extract_candidates(data, prior_concept)
        llm_conf = max(0.0, min(1.0, float(data.get('confidence', 0.7))))
        selection = score_candidates(question, candidates, prior_concept=prior_concept, prior_metric=prior_metric, inherit=inherit, conversation_context=conversation_context, llm_confidence=llm_conf)
        alts = [c for c in selection.candidates if c != selection.business_concept][:3]
        score_map = {d.concept: d.score for d in selection.scores}
        return BusinessSemanticResolution(business_concept=selection.business_concept, confidence=selection.confidence, alternatives=alts, reasoning=str(data.get('reasoning', '')), resolution_tier='scored', candidate_concepts=selection.candidates, candidate_scores=score_map, selection_rationale=selection.rationale)

    def _parse_unified(self, data: dict[str, Any], prior_obj: str | None) -> SemanticResolution:
        semantic = self._parse(data, prior_obj)
        semantic.resolution_tier = 'unified'
        return semantic

    def _apply_dimension_scoring(self, semantic: SemanticResolution, data: dict[str, Any], question: str, previous: Any, inherit: bool) -> SemanticResolution:
        prior_dim = previous.dimensions[0] if previous and previous.dimensions else None
        (dim, dim_conf, candidates, scores, rationale) = apply_dimension_selection(data, question=question, objective=semantic.objective, prior_dimension=prior_dim, inherit=inherit, llm_confidence=semantic.confidence)
        semantic.dimension = dim
        semantic.dimension_confidence = dim_conf
        semantic.candidate_dimensions = [c for c in candidates if c]
        semantic.dimension_candidate_scores = {str(k): v for (k, v) in scores.items() if k}
        semantic.dimension_selection_rationale = rationale
        return semantic

    def _apply_semantic_coherence(self, resolution: SemanticResolution, prior_objective: str | None, dimension: str | None=None) -> SemanticResolution:
        result = reconcile_objective_and_scope(resolution.objective, resolution.retrieval_scope, prior_objective=prior_objective, dimension=dimension or resolution.dimension)
        if not result.adjusted:
            return resolution
        resolution.objective = result.objective
        resolution.retrieval_scope = result.retrieval_scope
        resolution.reasoning += result.reasoning
        if result.adjusted:
            resolution.resolution_tier = 'coherence'
        return resolution

    def _apply_business_recovery(self, resolution: BusinessSemanticResolution, prior_concept: str | None) -> BusinessSemanticResolution:
        if resolution.confidence >= self.LOW:
            return resolution
        if prior_concept:
            resolution.business_concept = prior_concept
            resolution.confidence = max(resolution.confidence, 0.55)
            resolution.resolution_tier = 'recovery'
            resolution.reasoning += '; inherited prior business concept'
        return resolution

    def _business_from_cache(self, cached: dict[str, Any], prior_concept: str | None) -> BusinessSemanticResolution:
        concept = str(cached.get('business_concept') or prior_concept or default_concept())
        if concept not in concept_names():
            concept = prior_concept or default_concept()
        return BusinessSemanticResolution(business_concept=concept, confidence=0.85, reasoning=f"cache hit (similarity={cached.get('_cache_similarity', 1.0)})", resolution_tier='cache')

    def _semantic_from_cache(self, cached: dict[str, Any], prior_obj: str | None) -> SemanticResolution:
        obj = str(cached.get('objective') or prior_obj or default_objective())
        if obj not in objective_names():
            obj = prior_obj or default_objective()
        dim = cached.get('dimension')
        if dim in (None, 'null', ''):
            dim = None
        scope = RetrievalScopeSpec.parse(str(cached.get('retrieval_scope') or 'default')).to_label()
        return SemanticResolution(objective=obj, dimension=dim, retrieval_scope=scope, confidence=0.85, reasoning='cache hit', resolution_tier='cache')

    @staticmethod
    def _infer_time_preset(question: str) -> dict[str, Any] | None:
        q = question.lower()
        for (phrase, preset) in _TIME_PHRASES:
            if phrase in q:
                return {'preset': preset}
        return None

    def _time_for_cache_hit(self, question: str, reporting: dict[str, Any], partial_date: dict[str, Any] | None, active_tr: dict[str, Any], inherit: bool) -> dict[str, Any]:
        if partial_date:
            return partial_date
        inferred = self._infer_time_preset(question)
        if inferred:
            return inferred
        if inherit and (not TemporalResolver._question_mentions_time(question)):
            return dict(active_tr)
        return {'preset': 'last_30_days'}