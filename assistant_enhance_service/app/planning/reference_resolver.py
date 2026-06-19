from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any
from app.entity.canonical import display_for_camera, is_camera_id, normalize_entity_scope
from app.planning.temporal_override import question_has_explicit_time
from app.llm.vllm_client import VLLMClient
from app.planning.analytical_context import build_analytical_state, compact_analytics_output, compact_result_set
from app.planning.conversation_state import load_previous_plan
from app.planning.plan import AnalyticalPlan
REFERENCE_SYSTEM = 'You are an analytical reference resolver for a traffic analytics assistant.\n\nYour ONLY job: determine what prior analytical context the user is referring to in their question.\n\nThe user may refer to prior results using pronouns or definite phrases (these, those, them, that camera,\nthat site, those violations, those records, the 692, that trend, the peak day, etc.).\n\nUse:\n- current analytical state (filters, time_range, metric, dimensions, entity_scope)\n- previous analytics output (counts, winners, rankings, peak periods)\n- previous result set (row counts, sample rows)\n\nResolve the analytical scope the user intends to continue analyzing.\n\nRules:\n- If the question continues the same analytical thread without new explicit filters,\n  inherit location, violation_type, vehicle_type, time_range, and metric from prior context.\n- If the user cites a specific count (e.g. "these 692 violations"), bind to the matching prior result.\n- If the user refers to a ranked winner (e.g. after "Chowking had the most"), resolve location to Chowking.\n- If no analytical reference is present, return has_analytical_reference=false and empty resolved_reference.\n- Do NOT invent filters not supported by prior state or analytics output.\n- time_range may be a preset string (yesterday, this_month) or {"preset":"..."} object.\n\nReturn JSON only.'

@dataclass
class ReferenceResolution:
    resolved_reference: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ''
    has_analytical_reference: bool = False
    resolution_tier: str = 'primary'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class ReferenceResolver:
    LOW = 0.45

    def __init__(self, llm: VLLMClient) -> None:
        self.llm = llm

    async def resolve(self, question: str, analytical_state: dict[str, Any], prior_result_set: dict[str, Any] | None, prior_analytics: dict[str, Any] | None, *, conversation_context: str='') -> ReferenceResolution:
        if not analytical_state.get('active_plan') and (not prior_analytics):
            return ReferenceResolution(reasoning='no prior analytical context', resolution_tier='skipped')
        user = f'Question: {question}\n\nConversation:\n{conversation_context[:1500]}\n\nAnalytical state:\n{json.dumps(analytical_state, default=str)}\n\nPrevious analytics output:\n{json.dumps(prior_analytics or {}, default=str)}\n\nPrevious result set:\n{json.dumps(prior_result_set or {}, default=str)}\n\nReturn JSON: {{"has_analytical_reference":true|false, "confidence":0.0-1.0, "reasoning":"...", "resolved_reference":{{"location":null, "camera_id":null, "violation_type":null, "vehicle_type":null, "vehicle_category":null, "plate_suffix":null, "metric":null, "time_range":null, "dimension":null, "count_hint":null}}}}'
        try:
            data = await self.llm.chat_json(REFERENCE_SYSTEM, user)
            return self._parse(data, analytical_state, prior_result_set, prior_analytics)
        except Exception:
            return ReferenceResolution(confidence=0.3, reasoning='reference resolver fallback: no resolution', resolution_tier='fallback')

    def _parse(self, data: dict[str, Any], analytical_state: dict[str, Any], prior_result_set: dict[str, Any] | None, prior_analytics: dict[str, Any] | None) -> ReferenceResolution:
        ref_raw = data.get('resolved_reference')
        ref = dict(ref_raw) if isinstance(ref_raw, dict) else {}
        ref = {k: v for (k, v) in ref.items() if v is not None and v != '' and str(v).lower() not in ('unknown', 'null', 'none', 'default')}
        
        # Enforce validation of entity filter values to prevent LLM hallucinations
        prior_str = (
            json.dumps(analytical_state, default=str) + " " +
            json.dumps(prior_result_set or {}, default=str) + " " +
            json.dumps(prior_analytics or {}, default=str)
        ).lower()
        
        entity_keys = {'location', 'camera_id', 'violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix'}
        cleaned_ref = {}
        for k, v in ref.items():
            if k in entity_keys:
                v_str = str(v).lower()
                if v_str in prior_str:
                    cleaned_ref[k] = v
                elif k == 'location' and 'camera_id' in ref and str(ref['camera_id']).lower() in prior_str:
                    cleaned_ref[k] = v
            else:
                cleaned_ref[k] = v
        ref = cleaned_ref
        
        if 'violation_type' in ref:
            from app.entity.canonical import VIOLATION_LABELS
            val_upper = str(ref['violation_type']).upper().replace(' ', '_').replace('-', '_')
            if val_upper not in VIOLATION_LABELS:
                ref.pop('violation_type', None)
        conf = float(data.get('confidence', 0.5))
        conf = max(0.0, min(1.0, conf))
        has_ref = bool(data.get('has_analytical_reference')) and bool(ref)
        return ReferenceResolution(resolved_reference=ref, confidence=conf, reasoning=str(data.get('reasoning', '')), has_analytical_reference=has_ref, resolution_tier='primary')

    @classmethod
    def context_from_memory(cls, mem: dict[str, Any] | None, *, conversation_context: str='') -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        previous = load_previous_plan(mem.get('plan') if mem else None)
        analytical_state = build_analytical_state(mem, previous)
        entity_scope = (analytical_state.get('active_plan') or {}).get('entity_scope') or {}
        prior_analytics = compact_analytics_output(mem.get('last_analytics') if mem else None, entity_scope=entity_scope)
        prior_result = mem.get('last_result_set') or compact_result_set(columns=(mem.get('context') or {}).get('columns'), rows=None, row_count=(mem.get('context') or {}).get('row_count'))
        if not prior_analytics and mem:
            ctx = mem.get('context') or {}
            prior_analytics = compact_analytics_output(ctx.get('analytics_output'), entity_scope=entity_scope)
        return (analytical_state, prior_result, prior_analytics)

def apply_resolved_reference(semantic_entities: dict[str, Any], entity_scope: dict[str, Any], time_range: dict[str, Any], reference: ReferenceResolution | None, *, question: str='', min_confidence: float=ReferenceResolver.LOW) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    entities = dict(semantic_entities or {})
    scope = dict(entity_scope or {})
    tr = dict(time_range or {})
    if not reference or not reference.has_analytical_reference:
        return (entities, scope, tr)
    if reference.confidence < min_confidence:
        return (entities, scope, tr)
    ref = reference.resolved_reference
    for key in ('location', 'violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix'):
        val = ref.get(key)
        if val and (not entities.get(key)):
            entities[key] = val
    if ref.get('camera_id'):
        cid = str(ref['camera_id'])
        scope['camera_id'] = cid
        loc = ref.get('location')
        if loc and (not is_camera_id(loc)):
            display = str(loc)
        else:
            display = display_for_camera(cid)
        scope['location'] = display
        scope['display'] = display
        scope['display_name'] = display
    elif ref.get('location') and (not scope.get('location')):
        loc = str(ref['location'])
        if is_camera_id(loc):
            scope['camera_id'] = loc
            display = display_for_camera(loc)
            scope['location'] = display
            scope['display'] = display
            scope['display_name'] = display
        else:
            scope['location'] = loc
            scope['display'] = loc
            scope['display_name'] = loc
    for key in ('violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix'):
        if ref.get(key):
            scope[key] = ref[key]
    if ref.get('count_hint') is not None:
        scope['last_result_count'] = int(ref['count_hint'])
    ref_tr = ref.get('time_range')
    if ref_tr and (not question_has_explicit_time(question)):
        if isinstance(ref_tr, str):
            tr = {'preset': ref_tr}
        elif isinstance(ref_tr, dict):
            tr = dict(ref_tr)
    return (entities, normalize_entity_scope(scope), tr)