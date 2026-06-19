from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from app.entity.cache import EntityDiscovery
from app.entity.resolver import EntityResolver
from app.llm.vllm_client import VLLMClient
from app.planning.conversation_state import load_previous_plan
from app.planning.dimension_resolver import DimensionResolution
from app.planning.dimensions import TIME_PRESETS, dimension_names
from app.planning.objective_resolver import ObjectiveResolution
from app.planning.objectives import default_objective, objective_names, registry_prompt
from app.planning.plan import AnalyticalPlan
from app.planning.objective_evidence import apply_objective_evidence_policy, has_record_detail_evidence
from app.planning.retrieval_scope import RetrievalScopeSpec, infer_listing_scope_from_question, signals_record_listing_intent
from app.planning.scope import question_references_peak_hour, should_inherit
from app.planning.temporal_resolver import TemporalResolver, TemporalResolution
from app.planning.transformations import apply_transformation_confidence_boost, infer_transformation_objective, is_valid_transition, signals_transformation_intent, transformation_label
RESOLVER_SYSTEM = 'You are a unified semantic resolver for a traffic analytics assistant.\n\nIn ONE response, resolve ALL semantic aspects of the user question:\n- objective (analytical transformation)\n- dimension (grouping/ranking axis, or null)\n- entities (filters: location, violation_type, vehicle_type, plate_suffix)\n- time_range (temporal scope)\n- retrieval_scope (how many / which rows to return)\n\nObjectives:\n- metric_summary: scalar count (how many, show violations at X = summary NOT row listing)\n- breakdown: distribution by dimension (by type, segregation)\n- trend: values over time (daily, over period)\n- comparison: compare two time periods\n- ranking: highest/lowest by volume (most, top, highest area, peak hour)\n- growth: largest increase between periods (increased most, fastest growing)\n- record_detail: row-level records ONLY with explicit evidence (show records, first 10, list them, give examples, export)\n\nDimension mapping:\n- highest area / which area → location\n- peak hour / busiest hour → hour\n- worst violation type → violation_type\n- top camera / most active camera → camera\n- busiest day → day\n- daily trend → date\n- largest growth by camera → camera\n\nTemporal rules:\n- Relative dates inherit conversation timeframe (June 2026 discussion → "2 June" = 2026-06-02)\n- Presets: today, yesterday, this_week, this_month, last_month, last_7_days, last_5_days, last_30_days\n- Specific date: {"preset":"specific_date","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}\n\nRetrieval scope (infer from user intent — required):\n- all: user wants every matching row ("all vehicle numbers", "give me all", "list all")\n- first_N: first N rows in chronological order ("first 10 records")\n- latest_N: most recent N rows ("latest 20 violations")\n- top_N: highest-ranked N by metric ("top 5 cameras", "which area had highest")\n- sample: representative subset when user asks for a sample\n- single: exactly one example ("show one example", "give me one")\n- default: only when no quantity intent is expressed\n\nExamples:\n- "all vehicle numbers ending with 1" → record_detail, retrieval_scope=all\n- "first 10 records at Chowking" → record_detail, retrieval_scope=first_10\n- "latest 20 violations" → record_detail, retrieval_scope=latest_20\n- "top 5 cameras" → ranking, retrieval_scope=top_5\n- "which area had highest violations" → ranking, retrieval_scope=top_1\n- "show one example" → record_detail, retrieval_scope=single\n\nDo NOT choose metrics or business concepts — those are resolved upstream.\nDo NOT default to record_detail unless user explicitly requests records/listing/all/numbers.\nDo NOT use top_1 or single when user asks for ALL matching results.\nReturn JSON only.'

@dataclass
class SemanticResolution:
    objective: str = 'metric_summary'
    dimension: str | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    time_range: dict[str, Any] = field(default_factory=lambda : {'preset': 'last_30_days'})
    retrieval_scope: str = 'default'
    confidence: float = 0.5
    reasoning: str = ''
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    resolution_tier: str = 'unified'
    dimension_confidence: float | None = None
    candidate_dimensions: list[str] = field(default_factory=list)
    dimension_candidate_scores: dict[str, float] = field(default_factory=dict)
    dimension_selection_rationale: str = ''
    objective_policy: dict[str, Any] = field(default_factory=dict)
    temporal_override: dict[str, Any] = field(default_factory=dict)
    hour_analysis_priority: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_objective_resolution(self, prior_obj: str | None=None) -> ObjectiveResolution:
        return ObjectiveResolution(objective=self.objective, confidence=self.confidence, reasoning=self.reasoning, prior_objective=prior_obj, transformation=transformation_label(prior_obj, self.objective), resolution_tier=self.resolution_tier, needs_clarification=self.needs_clarification, clarification_prompt=self.clarification_prompt)

    def to_dimension_resolution(self) -> DimensionResolution:
        alts = [d for d in self.candidate_dimensions if d and d != self.dimension][:3]
        tier = 'scored' if self.dimension_selection_rationale else self.resolution_tier
        return DimensionResolution(dimension=self.dimension, confidence=self.dimension_confidence if self.dimension_confidence is not None else self.confidence, alternatives=alts, candidate_dimensions=list(self.candidate_dimensions), candidate_scores=dict(self.dimension_candidate_scores), selection_rationale=self.dimension_selection_rationale, reasoning=self.reasoning, resolution_tier=tier, needs_clarification=self.needs_clarification, clarification_prompt=self.clarification_prompt)

    def to_temporal_resolution(self) -> TemporalResolution:
        override = self.temporal_override or {}
        return TemporalResolution(time_range=dict(self.time_range), confidence=self.confidence, reasoning=self.reasoning, resolution_tier=self.resolution_tier, previous_time_range=override.get('previous_time_range'), new_time_range=override.get('new_time_range'), override_applied=bool(override.get('override_applied')), override_source=str(override.get('source', '')))

class SemanticResolver:
    LOW = 0.5

    def __init__(self, llm: VLLMClient, entities: EntityDiscovery) -> None:
        self.llm = llm
        self.entities = entities
        self.entity_resolver = EntityResolver(entities)

    async def resolve(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, mem_time_range: dict[str, Any] | None=None, business_concept: str | None=None) -> tuple[SemanticResolution, dict[str, Any], list[dict[str, Any]]]:
        previous = load_previous_plan(previous_mem_plan)
        prior_obj = previous.user_objective if previous else None
        active_tr = (previous.time_range if previous else None) or mem_time_range or {'preset': 'last_30_days'}
        reporting = TemporalResolver._reporting_period(active_tr, conversation_context)
        inherit = previous is not None and should_inherit(question, conversation_context, previous)
        prev_scope = previous.entity_scope if previous and inherit else {}
        partial_date = TemporalResolver._resolve_partial_date(question, reporting)
        data = await self._llm_pass(question, conversation_context, previous, prior_obj, active_tr, reporting, business_concept)
        resolution = self._parse(data, prior_obj)
        resolution = self._apply_record_listing_intent(resolution, question, prior_obj)
        resolution = self._apply_transformation_boost(resolution, prior_obj, question)
        resolution = self._normalize_time(resolution, question, reporting, partial_date, active_tr, inherit)
        resolution = self._apply_confidence_recovery(resolution, previous, prior_obj, question)
        resolution = self._apply_objective_evidence_policy(resolution, question, prior_obj)
        resolution = self._apply_hour_ranking_priority(resolution, question)
        (entity_scope, entity_resolutions) = self._enrich_entities(resolution.entities, question, prev_scope, inherit)
        if inherit and question_references_peak_hour(question) and (prev_scope.get('peak_hour') is not None):
            entity_scope = dict(entity_scope)
            entity_scope['peak_hour'] = prev_scope['peak_hour']
        clarification = self.entity_resolver.needs_clarification(entity_resolutions)
        if clarification:
            resolution.needs_clarification = True
            resolution.clarification_prompt = clarification
        return (resolution, entity_scope, entity_resolutions)

    async def _llm_pass(self, question: str, context: str, previous: AnalyticalPlan | None, prior_obj: str | None, active_tr: dict[str, Any], reporting: dict[str, Any], business_concept: str | None=None) -> dict[str, Any]:
        state = {'prior_objective': prior_obj, 'prior_metric': previous.metric if previous else None, 'prior_dimensions': previous.dimensions if previous else [], 'prior_time_range': active_tr, 'reporting_period': reporting, 'business_concept': business_concept}
        user = f"""Question: {question}\n\nToday's date (UTC): {datetime.utcnow():%Y-%m-%d}\nResolved business concept (do not change): {business_concept or 'unknown'}\nConversation:\n{context[:2000]}\n\nAnalytical state:\n{json.dumps(state, default=str)}\n\nKnown entities:\n{self.entities.to_prompt()}\n\n{registry_prompt()}\n\nDimensions: location, camera, violation_type, vehicle_type, vehicle_category, date, day, week, month, hour (null when not needed)\n\nReturn JSON:\n{{"objective":"...", "dimension":"...|null", "entities":{{"location":"...", "violation_type":"...", "vehicle_type":"...", "plate_suffix":"..."}}, "time_range":{{"preset":"today|specific_date|..."}} or {{"preset":"specific_date","start":"YYYY-MM-DD","end":"YYYY-MM-DD"}}, "retrieval_scope":"all|first_10|latest_20|top_5|sample|single|default", "confidence":0.0-1.0, "reasoning":"..."}}"""
        try:
            return await self.llm.chat_json(RESOLVER_SYSTEM, user, max_tokens=768)
        except Exception:
            return {'objective': prior_obj or default_objective(), 'dimension': previous.dimensions[0] if previous and previous.dimensions else None, 'entities': {}, 'time_range': active_tr, 'retrieval_scope': 'default', 'confidence': 0.4, 'reasoning': 'fallback: semantic resolver unavailable'}

    def _parse(self, data: dict[str, Any], prior_obj: str | None) -> SemanticResolution:
        obj = str(data.get('objective', default_objective()))
        if obj not in objective_names():
            obj = default_objective()
        raw_dim = data.get('dimension')
        dim = None if raw_dim in (None, 'null', '') else str(raw_dim)
        if dim and dim not in dimension_names():
            dim = None
        entities = {k: v for (k, v) in dict(data.get('entities') or {}).items() if v is not None and v != '' and str(v).lower() not in ('unknown', 'null', 'none', 'default')}
        tr_raw = data.get('time_range')
        if isinstance(tr_raw, dict):
            tr = dict(tr_raw)
        elif isinstance(tr_raw, str):
            tr = {'preset': tr_raw}
        else:
            tr = {'preset': 'last_30_days'}
        scope = RetrievalScopeSpec.parse(str(data.get('retrieval_scope') or 'default')).to_label()
        conf = max(0.0, min(1.0, float(data.get('confidence', 0.7))))
        if obj == 'record_detail' and conf < self.LOW and prior_obj and (prior_obj != 'record_detail'):
            if is_valid_transition(prior_obj, 'ranking'):
                obj = 'ranking'
                conf = max(conf, 0.45)
        return SemanticResolution(objective=obj, dimension=dim, entities=entities, time_range=tr, retrieval_scope=scope, confidence=conf, reasoning=str(data.get('reasoning', '')))

    def _normalize_time(self, resolution: SemanticResolution, question: str, reporting: dict[str, Any], partial_date: dict[str, Any] | None, active_tr: dict[str, Any], inherit: bool, *, reference_time_range: dict[str, Any] | None=None) -> SemanticResolution:
        from app.planning.temporal_override import apply_temporal_precedence
        override = apply_temporal_precedence(question, proposed=resolution.time_range, reference=reference_time_range, active=active_tr, partial_date=partial_date, inherit=inherit)
        tr = self._finalize_time_range(dict(override.time_range), question, reporting)
        override.new_time_range = tr
        resolution.time_range = tr
        resolution.temporal_override = override.to_debug_dict()
        if override.source == 'inherit':
            resolution.reasoning += '; inherited active time_range'
        elif override.override_applied:
            resolution.reasoning += f'; temporal_override: {override.source}'
        return resolution

    def _finalize_time_range(self, tr: dict[str, Any], question: str, reporting: dict[str, Any]) -> dict[str, Any]:
        if tr.get('today') is True or tr.get('preset') == 'today':
            return {'preset': 'today'}
        raw_date = tr.get('date') or tr.get('start')
        if raw_date and (not tr.get('preset')):
            day = str(raw_date)[:10]
            day = TemporalResolver._apply_reporting_year(day, question, reporting)
            return {'preset': 'specific_date', 'start': day, 'end': day}
        preset = tr.get('preset')
        if preset == 'specific_date' or tr.get('start'):
            start = tr.get('start') or tr.get('date')
            if start:
                day = TemporalResolver._apply_reporting_year(str(start)[:10], question, reporting)
                end = TemporalResolver._apply_reporting_year(str(tr.get('end', day))[:10], question, reporting)
                return {'preset': 'specific_date', 'start': day, 'end': end}
        if preset in TIME_PRESETS:
            return {'preset': preset}
        return tr

    def _apply_record_listing_intent(self, resolution: SemanticResolution, question: str, prior_obj: str | None) -> SemanticResolution:
        if not has_record_detail_evidence(question, resolution.retrieval_scope):
            return resolution
        inferred_scope = infer_listing_scope_from_question(question)
        if inferred_scope and resolution.retrieval_scope == 'default':
            resolution.retrieval_scope = inferred_scope
            resolution.reasoning += f'; inferred retrieval_scope={inferred_scope}'
        if resolution.objective != 'record_detail':
            if not prior_obj or is_valid_transition(prior_obj, 'record_detail'):
                resolution.objective = 'record_detail'
                resolution.reasoning += '; record listing: row retrieval intent'
                resolution.resolution_tier = 'record_listing'
        if resolution.dimension in {'violation_type', 'location', 'camera', 'vehicle_type', 'vehicle_category', 'date', 'day', 'hour'}:
            resolution.dimension = None
        if resolution.retrieval_scope == 'default' and signals_record_listing_intent(question):
            q = question.lower()
            if 'all' in q:
                resolution.retrieval_scope = 'all'
            elif (match := re.search('\\blatest\\s+(\\d+)\\b', q)):
                resolution.retrieval_scope = f'latest_{match.group(1)}'
            elif (match := re.search('\\bfirst\\s+(\\d+)\\b', q)):
                resolution.retrieval_scope = f'first_{match.group(1)}'
            else:
                resolution.retrieval_scope = 'first_10'
            resolution.reasoning += f'; default listing scope→{resolution.retrieval_scope}'
        return resolution

    def _apply_objective_evidence_policy(self, resolution: SemanticResolution, question: str, prior_obj: str | None) -> SemanticResolution:
        (obj, tier, telemetry) = apply_objective_evidence_policy(resolution.objective, question, retrieval_scope=resolution.retrieval_scope, prior_objective=prior_obj, resolution_tier=resolution.resolution_tier)
        if obj != resolution.objective:
            resolution.objective = obj
            resolution.resolution_tier = tier
            if telemetry.notes:
                resolution.reasoning += '; ' + '; '.join(telemetry.notes)
            spec = RetrievalScopeSpec.parse(resolution.retrieval_scope)
            if spec.kind in {'all', 'single', 'sample', 'first_n', 'latest_n'}:
                resolution.retrieval_scope = 'default'
                resolution.reasoning += '; cleared listing scope without row-retrieval evidence'
        resolution.objective_policy = telemetry.to_dict()
        return resolution

    def _apply_hour_ranking_priority(self, resolution: SemanticResolution, question: str) -> SemanticResolution:
        from app.planning.hour_analysis import apply_hour_ranking_priority
        (obj, dim, priority) = apply_hour_ranking_priority(question=question, objective=resolution.objective, dimension=resolution.dimension, has_record_detail_evidence=has_record_detail_evidence(question, resolution.retrieval_scope))
        if not priority:
            return resolution
        resolution.objective = obj
        resolution.dimension = dim
        resolution.dimension_confidence = max(resolution.dimension_confidence or 0.0, 0.92)
        resolution.candidate_dimensions = ['hour'] + [d for d in resolution.candidate_dimensions if d != 'hour']
        resolution.dimension_selection_rationale = 'hour dimension priority: explicit peak/busiest hour query'
        resolution.resolution_tier = 'hour_analysis_priority'
        resolution.reasoning += '; hour_analysis_priority: ranking by hour'
        resolution.hour_analysis_priority = priority.to_debug_dict()
        resolution.confidence = max(resolution.confidence, 0.85)
        return resolution

    def _apply_transformation_boost(self, resolution: SemanticResolution, prior_obj: str | None, question: str) -> SemanticResolution:
        (obj, conf, note) = apply_transformation_confidence_boost(prior_obj, resolution.objective, resolution.confidence, question, resolution.retrieval_scope)
        if obj != resolution.objective or note:
            resolution.objective = obj
            resolution.confidence = conf
            if note:
                resolution.reasoning += note
                resolution.resolution_tier = 'transformation_boost'
        return resolution

    def _apply_confidence_recovery(self, resolution: SemanticResolution, previous: AnalyticalPlan | None, prior_obj: str | None, question: str='') -> SemanticResolution:
        if resolution.confidence >= self.LOW:
            return resolution
        if prior_obj and resolution.objective == prior_obj and signals_transformation_intent(question):
            inferred = infer_transformation_objective(prior_obj, question, resolution.retrieval_scope)
            if inferred and inferred != prior_obj:
                resolution.objective = inferred
                resolution.confidence = max(resolution.confidence, 0.72)
                resolution.resolution_tier = 'transformation_recovery'
                resolution.reasoning += f'; transformation recovery: {prior_obj}→{inferred}'
                return resolution
        inferred = infer_transformation_objective(prior_obj, question, resolution.retrieval_scope) if prior_obj else None
        if prior_obj and prior_obj != resolution.objective and is_valid_transition(prior_obj, resolution.objective) and (signals_transformation_intent(question) or inferred == resolution.objective):
            resolution.confidence = max(resolution.confidence, 0.72)
            resolution.resolution_tier = 'transformation_recovery'
            resolution.reasoning += '; transformation recovery: kept proposed objective'
            return resolution
        if prior_obj and prior_obj != 'record_detail' and is_valid_transition(prior_obj, resolution.objective) and (resolution.objective == prior_obj):
            resolution.confidence = 0.45
            resolution.resolution_tier = 'recovery'
            resolution.reasoning += '; recovered prior objective'
            return resolution
        if resolution.objective == 'record_detail':
            resolution.objective = prior_obj or default_objective()
            resolution.needs_clarification = True
            resolution.clarification_prompt = "I'm not sure what kind of analysis you want. Could you rephrase?"
        elif resolution.confidence < self.LOW:
            resolution.needs_clarification = True
            resolution.clarification_prompt = "I'm not sure what kind of analysis you want (summary, breakdown, trend, ranking, comparison, or record listing). Could you rephrase?"
        return resolution

    def _enrich_entities(self, llm_entities: dict[str, Any], question: str, prev_scope: dict[str, Any], inherit: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        (entities, resolutions) = self.entity_resolver.resolve(question, prev_scope, inherit)
        loc_hint = llm_entities.get('location')
        if loc_hint and (not entities.get('camera_id')):
            (loc, score, log) = self.entities.resolve_location(f'at {loc_hint}')
            if loc:
                entities.update(loc)
                for item in log:
                    resolutions.append({'entity_type': 'location', 'resolved_entity': item.get('value'), 'display': item.get('display'), 'confidence': item.get('confidence', score), 'source': 'semantic_hint', 'candidates': log[:5]})
        vio = llm_entities.get('violation_type')
        if vio and (not entities.get('violation_type')):
            for vt in self.entities.cache.violation_types:
                if vt.upper() == str(vio).upper().replace(' ', '_'):
                    entities['violation_type'] = vt
                    resolutions.append({'entity_type': 'violation_type', 'resolved_entity': vt, 'confidence': 0.9, 'source': 'semantic_hint', 'candidates': []})
                    break
        vt_hint = llm_entities.get('vehicle_type')
        if vt_hint and (not entities.get('vehicle_type')):
            entities['vehicle_type'] = str(vt_hint)
            resolutions.append({'entity_type': 'vehicle_type', 'resolved_entity': vt_hint, 'confidence': 0.85, 'source': 'semantic_hint', 'candidates': []})
        plate = llm_entities.get('plate_suffix')
        if plate and (not entities.get('plate_suffix')):
            entities['plate_suffix'] = str(plate)
            resolutions.append({'entity_type': 'plate_suffix', 'resolved_entity': str(plate), 'confidence': 0.9, 'source': 'semantic_hint', 'candidates': []})
        from app.entity.canonical import normalize_entity_scope
        return (normalize_entity_scope(entities), resolutions)