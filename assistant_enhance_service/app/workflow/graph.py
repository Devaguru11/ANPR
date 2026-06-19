from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
from langgraph.graph import END, START, StateGraph
from app.analytics.engine import AnalyticsEngine
from app.db.pool import Database
from app.entity.cache import EntityDiscovery
from app.llm.vllm_client import VLLMClient
from app.logging.logger import TurnLogger
from app.memory.redis_memory import RedisMemory
from app.metrics.collector import Timer
from app.planning.conversation_state import persist_turn_state
from app.planning.plan import AnalyticalPlan
from app.planning.planner import AnalyticalPlanner
from app.entity.canonical import debug_entity_fields
from app.planning.scope import entity_scope_from_resolutions, update_scope_from_result
from app.planning.business_concept_catalog import BusinessConceptCatalog
from app.planning.semantic_cache import SemanticResolutionCache
from app.planning.analytical_context import compact_analytics_output, compact_result_set
from app.planning.reference_resolver import ReferenceResolution, ReferenceResolver
from app.planning.unified_semantic_resolver import UnifiedSemanticResolver
from app.schema.semantic_catalog import SchemaSemanticCatalog
from app.planning.sql_builder import SQLBuilder
from app.schema.discovery import SchemaCatalog
from app.sql.validator import SQLValidator
from app.llm.call_tracker import get_llm_calls, reset_llm_calls
from app.workflow.state import GraphState
from app.workflow.timing_report import build_prompt_audit, build_timing_report
from app.section_api.intent_router import classify_intent, IntentResult, SectionIntent
from app.section_api import client as section_client
from app.section_api.narrator import narrate as section_narrate


def _make_ir(intent: SectionIntent, params: dict, state: dict) -> IntentResult:
    """Build an IntentResult from graph state for use by the narrator."""
    return IntentResult(
        intent=intent,
        confidence=state.get('section_confidence', 0.0),
        vehicle_type=params.get('vehicle_type'),
        violation_type=params.get('violation_type'),
        plate=params.get('plate'),
    )


# ---------------------------------------------------------------------------
# Direct date-range parser (no LLM) for the section router
# Handles patterns like:
#   "between June 12th and June 15th"
#   "between 12th and 17th June"
#   "on June 14th"
#   "today", "this month", "last month", "this week"
#   "June 13th", "June 2026"
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, int] = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
}


def _day_num(s: str) -> int:
    """'12th' → 12"""
    return int(re.sub(r'[^\d]', '', s))


def _to_ymd(year: int, month: int, day: int) -> str:
    return f'{year:04d}-{month:02d}-{day:02d}'


def _current_year() -> int:
    from datetime import datetime
    return datetime.utcnow().year


def _current_month() -> int:
    from datetime import datetime
    return datetime.utcnow().month


def _parse_date_range_from_question(question: str) -> dict | None:
    """
    Try to extract an explicit date range directly from the question text.
    Returns a time_range dict compatible with resolve_date_range(), or None
    if no explicit date is found (caller should fall back to LLM temporal resolver).
    """
    q = question.lower()
    year = _current_year()

    # ── preset shortcuts ──────────────────────────────────────────────────
    if re.search(r'\btoday\b', q):
        return {'preset': 'today'}
    if re.search(r'\byesterday\b', q):
        return {'preset': 'yesterday'}
    if re.search(r'\bthis\s+week\b', q):
        return {'preset': 'this_week'}
    if re.search(r'\bthis\s+month\b', q):
        return {'preset': 'this_month'}
    if re.search(r'\blast\s+month\b', q):
        return {'preset': 'last_month'}
    if re.search(r'\blast\s+7\s+days\b', q):
        return {'preset': 'last_7_days'}
    if re.search(r'\blast\s+30\s+days\b', q):
        return {'preset': 'last_30_days'}

    # ── "between DAY1 and DAY2 MONTH" e.g. "between 12th and 17th june" ──
    m = re.search(
        r'between\s+(\d{1,2})(?:st|nd|rd|th)?\s+and\s+(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'(' + '|'.join(_MONTH_MAP) + r')',
        q,
    )
    if m:
        d1, d2, mon = int(m.group(1)), int(m.group(2)), _MONTH_MAP[m.group(3)]
        return {'preset': 'specific_date', 'start': _to_ymd(year, mon, d1), 'end': _to_ymd(year, mon, d2)}

    # ── "between MONTH DAY1 and MONTH DAY2" e.g. "between june 12 and june 15" ──
    m = re.search(
        r'between\s+(' + '|'.join(_MONTH_MAP) + r')\s+(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'and\s+(?:(' + '|'.join(_MONTH_MAP) + r')\s+)?(\d{1,2})(?:st|nd|rd|th)?',
        q,
    )
    if m:
        mon1 = _MONTH_MAP[m.group(1)]
        d1 = int(m.group(2))
        mon2 = _MONTH_MAP[m.group(3)] if m.group(3) else mon1
        d2 = int(m.group(4))
        return {'preset': 'specific_date', 'start': _to_ymd(year, mon1, d1), 'end': _to_ymd(year, mon2, d2)}

    # ── "between DAY1 MONTH and DAY2 MONTH" e.g. "between 12th june and 17th june" ──
    m = re.search(
        r'between\s+(\d{1,2})(?:st|nd|rd|th)?\s+(' + '|'.join(_MONTH_MAP) + r')\s+'
        r'and\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:(' + '|'.join(_MONTH_MAP) + r'))?',
        q,
    )
    if m:
        d1, mon1 = int(m.group(1)), _MONTH_MAP[m.group(2)]
        d2 = int(m.group(3))
        mon2 = _MONTH_MAP[m.group(4)] if m.group(4) else mon1
        return {'preset': 'specific_date', 'start': _to_ymd(year, mon1, d1), 'end': _to_ymd(year, mon2, d2)}

    # ── single date: "on MONTH DAY" or "MONTH DAY" e.g. "on June 14th" ──
    m = re.search(
        r'\b(?:on\s+)?(' + '|'.join(_MONTH_MAP) + r')\b\s+(\d{1,2})\b(?:st|nd|rd|th)?\b(?!\s*\d{4})',
        q,
    )
    if m:
        mon, day = _MONTH_MAP[m.group(1)], int(m.group(2))
        date = _to_ymd(year, mon, day)
        return {'preset': 'specific_date', 'start': date, 'end': date}

    # ── "DAY MONTH" e.g. "14th June" ──
    m = re.search(
        r'\b(\d{1,2})\b(?:st|nd|rd|th)?\s+\b(' + '|'.join(_MONTH_MAP) + r')\b',
        q,
    )
    if m:
        day, mon = int(m.group(1)), _MONTH_MAP[m.group(2)]
        date = _to_ymd(year, mon, day)
        return {'preset': 'specific_date', 'start': date, 'end': date}

    # ── whole month: "in june" / "june 2026" ──
    m = re.search(
        r'\b(?:in\s+)?(' + '|'.join(_MONTH_MAP) + r')\b(?:\s+(\d{4}))?\b(?!\s*\d)',
        q,
    )
    if m:
        mon = _MONTH_MAP[m.group(1)]
        yr = int(m.group(2)) if m.group(2) else year
        from datetime import datetime, timedelta
        import calendar
        last_day = calendar.monthrange(yr, mon)[1]
        # Don't return a future full month — cap at today if current month
        today = datetime.utcnow()
        if yr == today.year and mon == today.month:
            return {'preset': 'this_month'}
        return {
            'preset': 'specific_date',
            'start': _to_ymd(yr, mon, 1),
            'end': _to_ymd(yr, mon, last_day),
        }

    return None


@dataclass
class Services:
    db: Database
    schema: SchemaCatalog
    schema_semantic: SchemaSemanticCatalog
    concept_catalog: BusinessConceptCatalog
    semantic_cache: SemanticResolutionCache
    llm: VLLMClient
    memory: RedisMemory
    entities: EntityDiscovery
    validator: SQLValidator
    analytics: AnalyticsEngine
    logger: TurnLogger
    metrics: Any

class AnalyticsWorkflow:

    def __init__(self, services: Services) -> None:
        self.s = services
        self.unified_resolver = UnifiedSemanticResolver(services.llm, services.entities, services.concept_catalog, services.semantic_cache)
        self.reference_resolver = ReferenceResolver(services.llm)
        self.planner = AnalyticalPlanner()
        self.sql_builder = SQLBuilder()
        self._graph = self._build()

    # Confidence threshold: above this → use section API, below → LLM SQL fallback
    SECTION_CONFIDENCE_THRESHOLD = 0.42

    def _build(self):
        g = StateGraph(GraphState)
        g.add_node('analytical_reference_resolver', self.analytical_reference_resolver_node)
        g.add_node('unified_semantic_resolver', self.unified_semantic_resolver_node)
        g.add_node('section_router', self.section_router_node)
        g.add_node('section_api_fetcher', self.section_api_fetcher_node)
        g.add_node('analytical_planner', self.analytical_planner)
        g.add_node('sql_generator', self.sql_generator)
        g.add_node('sql_validator', self.sql_validator)
        g.add_node('sql_executor', self.sql_executor)
        g.add_node('analytics_engine', self.analytics_engine)
        g.add_node('response_generator', self.response_generator)
        g.add_edge(START, 'analytical_reference_resolver')
        g.add_edge('analytical_reference_resolver', 'unified_semantic_resolver')
        g.add_edge('unified_semantic_resolver', 'section_router')
        g.add_conditional_edges(
            'section_router',
            self._route_after_section_router,
            {
                'section_api': 'section_api_fetcher',
                'llm_sql': 'analytical_planner',
            },
        )
        g.add_edge('section_api_fetcher', END)
        g.add_edge('analytical_planner', 'sql_generator')
        g.add_edge('sql_generator', 'sql_validator')
        g.add_edge('sql_validator', 'sql_executor')
        g.add_edge('sql_executor', 'analytics_engine')
        g.add_edge('analytics_engine', 'response_generator')
        g.add_edge('response_generator', END)
        return g.compile()

    def _route_after_section_router(self, state: GraphState) -> str:
        """Conditional edge: if section intent is confident, use section API path."""
        intent = state.get('section_intent')
        confidence = state.get('section_confidence', 0)
        entities = state.get('entity_scope') or state.get('entities') or {}
        
        # Specific filters that require LLM SQL path:
        has_camera = bool(entities.get('camera_id') or entities.get('location'))
        has_plate = bool(entities.get('plate_suffix'))
        has_violation_type = bool(entities.get('violation_type'))
        
        # If the query contains camera or plate filters, we must use LLM SQL since Section API does not pass/support them fully.
        if has_camera or has_plate:
            return 'llm_sql'
            
        # If the query asks for violations summary (count) or camera rankings (busiest cameras) with a specific violation type filter, we must use LLM SQL.
        if intent in ('violations_summary', 'violations_by_camera') and has_violation_type:
            return 'llm_sql'
            
        if intent and confidence >= self.SECTION_CONFIDENCE_THRESHOLD:
            return 'section_api'
            
        return 'llm_sql'

    async def run(self, session_id: str, question: str) -> GraphState:
        reset_llm_calls()
        t0 = Timer()
        state: GraphState = {'session_id': session_id, 'question': question, 'debug': {}, 'latencies': {}}
        try:
            state = await self._graph.ainvoke(state)
            state['latencies']['total_ms'] = t0.elapsed_ms()
            state['llm_calls'] = get_llm_calls()
            self._finalize_observability(state)
            self._persist(session_id, state)
            return state
        except Exception as exc:
            state['error'] = str(exc)
            state['final_answer'] = 'I could not complete that analytics request. Please try rephrasing.'
            state['latencies']['total_ms'] = t0.elapsed_ms()
            state['llm_calls'] = get_llm_calls()
            self._finalize_observability(state)
            self._persist(session_id, state, error=str(exc))
            return state

    def _finalize_observability(self, state: GraphState) -> None:
        state['timing_report'] = build_timing_report(state.get('latencies', {}), state.get('semantic_timing'))
        state['prompt_audit'] = build_prompt_audit(state.get('prompt_metrics'))
        dbg = state.get('debug_context') or state.get('debug') or {}
        dbg.update({'timing_report': state['timing_report'], 'prompt_audit': state['prompt_audit'], 'llm_calls': state.get('llm_calls', 0), 'semantic_timing': state.get('semantic_timing'), 'prompt_metrics': state.get('prompt_metrics'), 'latencies': state.get('latencies')})
        state['debug_context'] = dbg
        state['debug'] = dbg

    def _persist(self, session_id: str, state: GraphState, error: str | None=None) -> None:
        plan = state.get('plan') or {}
        self.s.memory.add_exchange(session_id, 'user', state.get('normalized_question') or state.get('question', ''))
        if state.get('final_answer'):
            self.s.memory.add_exchange(session_id, 'assistant', state['final_answer'])
        debug_ctx = state.get('debug') or state.get('debug_context') or {}
        self.s.memory.update_context(session_id, state.get('entities') or {}, plan.get('filters', {}), plan.get('time_range', {}), plan, debug_ctx)
        mem = self.s.memory.load(session_id)
        ap = plan.get('analytical_plan') or plan
        mem['last_analytics'] = compact_analytics_output(state.get('analytics_output'), entity_scope=ap.get('entity_scope') or state.get('entity_scope'))
        mem['last_reference_resolution'] = state.get('reference_resolution')
        mem['last_result_set'] = compact_result_set(columns=state.get('columns'), rows=state.get('rows'), row_count=state.get('row_count'))
        mem['last_analytical_state'] = state.get('analytical_state') or mem.get('last_analytical_state')
        self.s.memory.save(session_id, mem)
        self.s.logger.write(session_id, {'question': state.get('question'), 'context': state.get('conversation_context'), 'intent': state.get('intent'), 'reference_resolution': state.get('reference_resolution'), 'semantic_resolution': state.get('semantic_resolution'), 'business_semantic_resolution': state.get('business_semantic_resolution'), 'objective_resolution': state.get('objective_resolution'), 'entities': state.get('entities'), 'confidence': state.get('confidence'), 'plan': plan, 'sql': state.get('sql'), 'rows': state.get('row_count'), 'latency': state.get('latencies'), 'semantic_timing': state.get('semantic_timing'), 'prompt_metrics': state.get('prompt_metrics'), 'prompt_audit': state.get('prompt_audit'), 'timing_report': state.get('timing_report'), 'llm_calls': state.get('llm_calls'), 'answer': state.get('final_answer'), 'errors': error or state.get('error')})

    # -----------------------------------------------------------------------
    # Section router node — classify intent, extract params, decide route
    # -----------------------------------------------------------------------

    async def section_router_node(self, state: GraphState) -> GraphState:
        """Classify the question into a section intent using keyword scoring."""
        t = Timer()
        question = state.get('normalized_question') or state.get('question', '')

        # 1. Try to parse date ranges directly from the question text (no LLM needed).
        #    This is more reliable than the LLM temporal resolver for explicit date spans
        #    like "between June 12th and June 15th".
        direct_time_range = _parse_date_range_from_question(question)

        # 2. Fall back to the temporal resolution from unified_semantic_resolver.
        if not direct_time_range:
            temporal = state.get('temporal_resolution') or {}
            direct_time_range = temporal.get('time_range') or {}

        ir = classify_intent(question, direct_time_range)
        state['section_intent'] = ir.intent.value
        state['section_confidence'] = ir.confidence
        state['section_params'] = {
            'vehicle_type': ir.vehicle_type,
            'violation_type': ir.violation_type,
            'plate': ir.plate,
        }
        state['section_time_range'] = direct_time_range
        state.setdefault('latencies', {})['section_router_ms'] = t.elapsed_ms()
        return state

    # -----------------------------------------------------------------------
    # Section API fetcher node — call the Node REST endpoint + narrate
    # -----------------------------------------------------------------------

    async def section_api_fetcher_node(self, state: GraphState) -> GraphState:
        """Call the relevant Node.js REST endpoint and narrate the result."""
        t = Timer()
        intent_str = state.get('section_intent', 'unknown')
        params = state.get('section_params') or {}
        time_range = state.get('section_time_range') or {}

        try:
            intent = SectionIntent(intent_str)
        except ValueError:
            intent = SectionIntent.UNKNOWN

        from_date, to_date = section_client.resolve_date_range(time_range)

        try:
            data: dict[str, Any] = {}

            if intent == SectionIntent.VIOLATIONS_SUMMARY:
                data = await section_client.fetch_violations_summary(
                    from_date, to_date,
                    camera_id=params.get('camera_id'),
                    plate=params.get('plate'),
                )

            elif intent == SectionIntent.VIOLATIONS_BY_CAMERA:
                data = await section_client.fetch_violations_by_camera(from_date, to_date)

            elif intent == SectionIntent.VIOLATIONS_LIST:
                data = await section_client.fetch_violations_list(
                    from_date, to_date,
                    violation_type=params.get('violation_type'),
                    plate=params.get('plate'),
                )

            elif intent == SectionIntent.PLATE_READS:
                data = await section_client.fetch_range_stats(
                    from_date, to_date,
                    vehicle_type=params.get('vehicle_type'),
                )

            elif intent == SectionIntent.OVERVIEW:
                data = await section_client.fetch_overview(from_date, to_date)

            elif intent == SectionIntent.RECIDIVISM:
                data = await section_client.fetch_recidivism()

            elif intent == SectionIntent.CAMERA_STATUS:
                data = await section_client.fetch_overview(from_date, to_date)

            else:
                # Should not reach here — router should have sent unknown to LLM path
                state['final_answer'] = 'I could not complete that analytics request. Please try rephrasing.'
                state.setdefault('latencies', {})['section_api_ms'] = t.elapsed_ms()
                return state

            answer = section_narrate(intent, data, _make_ir(intent, params, state), from_date, to_date)
            state['final_answer'] = answer
            state['section_api_data'] = data

            metric = 'violations'
            if intent == SectionIntent.PLATE_READS:
                metric = 'detections'
            elif intent == SectionIntent.OVERVIEW:
                metric = 'overview'
            elif intent == SectionIntent.CAMERA_STATUS:
                metric = 'cameras'

            from app.planning.plan import AnalyticalPlan
            from app.planning.conversation_state import persist_turn_state

            ap = AnalyticalPlan(
                intent=intent_str,
                user_objective='metric_summary',
                metric=metric,
                time_range=time_range,
                query_mode='count',
                entity_scope={}
            )
            mem = self.s.memory.load(state['session_id'])
            envelope = persist_turn_state(mem, ap)
            state['plan'] = envelope
            # Clear entities to avoid filter bleed in memory context
            state['entities'] = {}

        except Exception as exc:
            # On any HTTP/network error, gracefully fall back to error message
            import logging
            logging.getLogger(__name__).warning('section_api_fetcher error: %s', exc)
            state['final_answer'] = (
                'I was unable to fetch the data right now. '
                'Please check that the server is running, or try rephrasing your question.'
            )

        # NOTE: We intentionally do NOT write to LLM conversation memory here.
        # The section API path is stateless — each question is answered directly
        # from the REST API using the question's own date/intent context.
        # Saving the full answer text (which contains camera names, location names etc.)
        # would cause those entity names to bleed into the next LLM SQL fallback question.

        state.setdefault('debug_context', {}).update({
            'section_intent': intent_str,
            'section_confidence': state.get('section_confidence'),
            'section_params': params,
            'section_time_range': time_range,
            'from_date': from_date,
            'to_date': to_date,
        })
        state['debug'] = state['debug_context']
        state.setdefault('latencies', {})['section_api_ms'] = t.elapsed_ms()
        return state

    async def analytical_reference_resolver_node(self, state: GraphState) -> GraphState:
        t = Timer()
        state['normalized_question'] = re.sub('\\s+', ' ', state['question'].strip())
        state['conversation_context'] = self.s.memory.context_text(state['session_id'])
        mem = self.s.memory.load(state['session_id'])
        (analytical_state, prior_result, prior_analytics) = ReferenceResolver.context_from_memory(mem, conversation_context=state.get('conversation_context', ''))
        ref = await self.reference_resolver.resolve(state['normalized_question'], analytical_state, prior_result, prior_analytics, conversation_context=state.get('conversation_context', ''))
        state['reference_resolution'] = ref.to_dict()
        state['analytical_state'] = analytical_state
        state['latencies'] = state.get('latencies', {})
        state['latencies']['reference_resolver_ms'] = t.elapsed_ms()
        return state

    async def unified_semantic_resolver_node(self, state: GraphState) -> GraphState:
        t = Timer()
        mem = self.s.memory.load(state['session_id'])
        ref_data = state.get('reference_resolution') or {}
        reference = ReferenceResolution(**ref_data) if ref_data else None
        result = await self.unified_resolver.resolve_unified(state['normalized_question'], state.get('conversation_context', ''), mem.get('plan'), mem_time_range=mem.get('time_range'), reference_resolution=reference)
        business = result.business
        semantic = result.semantic
        prior_obj = None
        if mem.get('plan'):
            from app.planning.conversation_state import load_previous_plan
            previous = load_previous_plan(mem.get('plan'))
            if previous:
                prior_obj = previous.user_objective
        state['business_semantic_resolution'] = business.to_dict()
        state['semantic_resolution'] = semantic.to_dict()
        state['objective_resolution'] = semantic.to_objective_resolution(prior_obj).to_dict()
        state['dimension_resolution'] = semantic.to_dimension_resolution().to_dict()
        state['temporal_resolution'] = semantic.to_temporal_resolution().to_dict()
        state['user_objective'] = semantic.objective
        state['entities'] = result.entity_scope
        state['entity_resolution'] = result.entity_resolutions
        state['entity_scope'] = entity_scope_from_resolutions(result.entity_resolutions) or result.entity_scope
        state['confidence'] = semantic.confidence
        if result.entity_resolutions:
            state['confidence'] = max(state['confidence'], max((float(r.get('confidence', 0.5)) for r in result.entity_resolutions)))
        if semantic.needs_clarification:
            state['clarification_needed'] = semantic.clarification_prompt
        timing = result.timing.to_dict()
        state['semantic_timing'] = timing
        state['prompt_metrics'] = result.prompt_metrics
        elapsed = t.elapsed_ms()
        state['latencies']['unified_semantic_ms'] = elapsed
        state['latencies']['business_semantic_ms'] = timing.get('phases_ms', {}).get('llm_inference', elapsed)
        state['latencies']['semantic_ms'] = 0
        return state

    async def analytical_planner(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('clarification_needed'):
            state['final_answer'] = state['clarification_needed']
            state['plan'] = {}
            state['latencies']['plan_ms'] = t.elapsed_ms()
            return state
        from app.planning.business_semantic_resolver import BusinessSemanticResolution
        from app.planning.semantic_resolver import SemanticResolution
        mem = self.s.memory.load(state['session_id'])
        semantic = SemanticResolution(**state.get('semantic_resolution') or {})
        business = BusinessSemanticResolution(**state.get('business_semantic_resolution') or {})
        obj_res = state.get('objective_resolution') or {}
        prior_obj = obj_res.get('prior_objective')
        (plan, planner_debug) = await self.planner.plan(state['normalized_question'], state.get('conversation_context', ''), mem.get('plan'), state.get('entity_resolution', []), state.get('entity_scope', {}), semantic.to_objective_resolution(prior_obj), semantic.to_dimension_resolution(), semantic.to_temporal_resolution(), retrieval_scope=semantic.retrieval_scope, business_resolution=business)
        envelope = persist_turn_state(mem, plan, objective_resolution=state.get('objective_resolution'), dimension_resolution=state.get('dimension_resolution'), temporal_resolution=state.get('temporal_resolution'), semantic_resolution=state.get('semantic_resolution'), business_semantic_resolution=state.get('business_semantic_resolution'))
        envelope['objective_transform'] = state.get('objective_resolution', {}).get('transformation')
        envelope['semantic_resolution'] = state.get('semantic_resolution')
        envelope['entities'] = state.get('entities', {})
        state['intent'] = plan.intent
        state['plan'] = envelope
        state['conversation_state'] = envelope.get('conversation_state')
        state['active_scope'] = envelope.get('analytical_plan', plan.to_dict())
        state['inherited_scope'] = planner_debug.get('previous')
        state['query_modifications'] = planner_debug.get('modifications')
        state['resolved_context'] = planner_debug
        state['latencies']['plan_ms'] = t.elapsed_ms()
        return state

    async def sql_generator(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('clarification_needed'):
            state['latencies']['sql_gen_ms'] = t.elapsed_ms()
            return state
        plan = AnalyticalPlan.from_dict(state.get('plan', {}).get('analytical_plan', {}))
        if plan.query_mode == 'macro_summary':
            import copy
            p1 = copy.deepcopy(plan)
            p1.metric = 'vehicles'
            p1.query_mode = 'count'
            sql1 = self.sql_builder.build(p1)
            p2 = copy.deepcopy(plan)
            p2.metric = 'violations'
            p2.query_mode = 'count'
            sql2 = self.sql_builder.build(p2)
            p3 = copy.deepcopy(plan)
            p3.metric = 'cameras'
            p3.query_mode = 'top_n'
            p3.dimensions = ['camera']
            p3.group_by = ['camera']
            p3.limit = 3
            sql3 = self.sql_builder.build(p3)
            state['sql_list'] = [sql1, sql2, sql3]
            state['sql'] = sql1
        else:
            state['sql'] = self.sql_builder.build(plan)
        state['latencies']['sql_gen_ms'] = t.elapsed_ms()
        return state

    async def sql_validator(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('sql_list'):
            valid_sqls = []
            errors = []
            for s in state['sql_list']:
                result = self.s.validator.validate(s)
                valid_sqls.append(result.sql if result.ok else s)
                if not result.ok:
                    errors.extend(result.errors)
            state['sql_list'] = valid_sqls
            if errors:
                state['sql_errors'] = errors
        elif state.get('sql'):
            result = self.s.validator.validate(state['sql'])
            state['sql'] = result.sql if result.ok else state.get('sql', '')
            if not result.ok:
                state['sql_errors'] = result.errors
        state['latencies']['validate_ms'] = t.elapsed_ms()
        return state

    async def sql_executor(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('sql_list'):
            results = {}
            for i, sql in enumerate(state['sql_list']):
                try:
                    cols, rows = self.s.db.execute(sql)
                    results[f'query_{i}'] = {'columns': cols, 'rows': rows, 'row_count': len(rows)}
                except Exception as exc:
                    results[f'query_{i}'] = {'error': str(exc)}
            state['macro_summary_results'] = results
            state['columns'] = []
            state['rows'] = []
            state['row_count'] = 0
        elif state.get('sql'):
            try:
                cols, rows = self.s.db.execute(state['sql'])
                state['columns'] = cols
                state['rows'] = rows
                state['row_count'] = len(rows)
            except Exception as exc:
                state['error'] = f'SQL execution failed: {exc}'
                state['columns'] = []
                state['rows'] = []
                state['row_count'] = 0
        state['latencies']['sql_ms'] = t.elapsed_ms()
        return state

    async def analytics_engine(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('clarification_needed'):
            state['latencies']['analytics_ms'] = t.elapsed_ms()
            return state
        plan_dict = state.get('plan', {}).get('analytical_plan', {})
        result = self.s.analytics.run(plan_dict, state.get('columns', []), state.get('rows', []), camera_names=self.s.entities.camera_name_map())
        state['analytics_output'] = {'summary': result.summary, 'composed_answer': result.composed_answer, 'dataset_type': result.dataset_type, 'metrics': result.metrics, 'trends': result.trends, 'comparisons': result.comparisons, 'rankings': result.rankings, 'records': result.records, 'insights': result.insights, 'data_quality': result.data_quality, 'grounded': result.grounded}
        plan = AnalyticalPlan.from_dict(plan_dict)
        updated = update_scope_from_result(plan, state.get('columns', []), state.get('rows', []), self.s.entities.camera_name_map())
        if state.get('plan'):
            mem = self.s.memory.load(state['session_id'])
            envelope = persist_turn_state(mem, updated, objective_resolution=state.get('objective_resolution'), dimension_resolution=state.get('dimension_resolution'), temporal_resolution=state.get('temporal_resolution'), semantic_resolution=state.get('semantic_resolution'), business_semantic_resolution=state.get('business_semantic_resolution'))
            envelope['objective_transform'] = state.get('plan', {}).get('objective_transform')
            envelope['semantic_resolution'] = state.get('semantic_resolution')
            envelope['entities'] = state.get('plan', {}).get('entities', {})
            state['plan'] = envelope
            state['conversation_state'] = envelope.get('conversation_state')
        state['latencies']['analytics_ms'] = t.elapsed_ms()
        return state

    async def response_generator(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('clarification_needed'):
            state['latencies']['response_ms'] = t.elapsed_ms()
            return state
        if state.get('macro_summary_results'):
            import json
            summary_data = json.dumps(state['macro_summary_results'], default=str)
            sys_msg = 'You are a traffic analytics assistant. Based on these three data points (vehicles, violations, top cameras), synthesize a short, natural language summary of the current traffic situation.'
            user_msg = f'Data: {summary_data}'
            try:
                ans = await self.s.llm.chat(sys_msg, user_msg, max_tokens=150)
                state['final_answer'] = str(ans).strip()
            except Exception:
                state['final_answer'] = 'Traffic data was retrieved, but synthesis failed.'
        elif state.get('error') and (not state.get('rows')):
            state['final_answer'] = f"I could not retrieve analytics data. {state['error']}"
        else:
            ao = state.get('analytics_output') or {}
            answer = ao.get('composed_answer') or ao.get('summary')
            
            # Phrase and structure the response using the LLM for high-quality natural language output
            question = state.get('question', '')
            sql_query = state.get('sql', '')
            columns = state.get('columns', [])
            rows = state.get('rows', [])
            row_count = state.get('row_count', 0)
            
            sys_msg = (
                "You are an expert AI Data Assistant for an Automatic Number Plate Recognition (ANPR) and traffic enforcement dashboard.\n"
                "Your job is to write, phrase, and structure the final answer for the user based on the database query results and a draft summary.\n\n"
                "Strict Guidelines:\n"
                "1. Base your answer strictly on the provided SQL query results and draft summary. Do not invent any numbers, plates, or cameras.\n"
                "2. Use clean markdown formatting. Use bolding, bullet points, or simple markdown tables where appropriate to make the data highly readable and premium.\n"
                "3. Keep the tone professional, helpful, and concise.\n"
                "4. If no data was returned, explain that politely.\n"
                "5. Return only the phrased final answer. Do not include JSON structures, system labels, or conversational preambles."
            )
            
            subset_rows = rows[:15]
            rows_str = str(subset_rows)
            if len(rows) > 15:
                rows_str += f"\n... and {len(rows) - 15} more rows"
                
            user_msg = (
                f"User Question: {question}\n\n"
                f"Draft Summary: {answer}\n\n"
                f"SQL Query Executed: {sql_query}\n\n"
                f"Columns Returned: {columns}\n"
                f"Sample Data Rows: {rows_str}\n"
                f"Total Data Rows Count: {row_count}\n"
            )
            
            try:
                formatted_answer = await self.s.llm.chat(sys_msg, user_msg, max_tokens=1024)
                if formatted_answer and formatted_answer.strip():
                    state['final_answer'] = formatted_answer.strip()
                else:
                    state['final_answer'] = answer if answer else 'No data was returned for this query.'
            except Exception:
                state['final_answer'] = answer if answer else 'No data was returned for this query.'
        plan = state.get('plan', {})
        ap = plan.get('analytical_plan', {})
        sem_res = state.get('semantic_resolution') or plan.get('semantic_resolution') or {}
        obj_res = state.get('objective_resolution') or plan.get('objective_resolution') or {}
        state['debug_context'] = {'intent': ap.get('intent'), 'user_objective': ap.get('user_objective'), 'reference_resolution': state.get('reference_resolution'), 'semantic_resolution': sem_res, 'hour_analysis_priority': sem_res.get('hour_analysis_priority'), 'business_semantic_resolution': state.get('business_semantic_resolution') or plan.get('business_semantic_resolution'), 'objective_resolution': obj_res, 'dimension_resolution': state.get('dimension_resolution') or plan.get('dimension_resolution'), 'temporal_resolution': state.get('temporal_resolution') or plan.get('temporal_resolution'), 'conversation_state': state.get('conversation_state') or plan.get('conversation_state'), 'objective_transform': plan.get('objective_transform'), 'metric': ap.get('metric'), 'dimensions': ap.get('dimensions'), 'filters': ap.get('filters'), 'group_by': ap.get('group_by'), 'query_mode': ap.get('query_mode'), 'entity_scope': ap.get('entity_scope'), **debug_entity_fields(ap.get('entity_scope')), 'time_range': ap.get('time_range'), 'previous_time_range': (state.get('temporal_resolution') or {}).get('previous_time_range'), 'new_time_range': (state.get('temporal_resolution') or {}).get('new_time_range') or ap.get('time_range'), 'override_applied': (state.get('temporal_resolution') or {}).get('override_applied'), 'retrieval_scope': sem_res.get('retrieval_scope') or ap.get('retrieval_scope'), 'sql': state.get('sql'), 'dataset_type': state.get('analytics_output', {}).get('dataset_type'), 'analytics_summary': state.get('analytics_output', {}).get('summary'), 'active_scope': state.get('active_scope'), 'inherited_scope': state.get('inherited_scope'), 'query_modifications': state.get('query_modifications'), 'state_before_merge': (state.get('query_modifications') or {}).get('state_before_merge'), 'resolved_changes': (state.get('query_modifications') or {}).get('resolved_changes'), 'state_after_merge': (state.get('query_modifications') or {}).get('state_after_merge'), 'sticky_preserved': (state.get('query_modifications') or {}).get('sticky_preserved'), 'sticky_overridden': (state.get('query_modifications') or {}).get('sticky_overridden'), 'resolved_context': state.get('resolved_context'), 'semantic_consistency_passed': (state.get('resolved_context') or {}).get('semantic_consistency_passed'), 'semantic_consistency_repair': (state.get('resolved_context') or {}).get('semantic_consistency_repair'), 'dimension_promotion': (state.get('resolved_context') or {}).get('dimension_promotion'), 'dimension_promotion_passed': (state.get('resolved_context') or {}).get('dimension_promotion_passed'), 'promotion_reason': (state.get('resolved_context') or {}).get('promotion_reason') or ((state.get('resolved_context') or {}).get('dimension_promotion') or {}).get('promotion_reason'), 'removed_filters': (state.get('resolved_context') or {}).get('removed_filters') or ((state.get('resolved_context') or {}).get('dimension_promotion') or {}).get('removed_filters'), 'retained_filters': (state.get('resolved_context') or {}).get('retained_filters') or ((state.get('resolved_context') or {}).get('dimension_promotion') or {}).get('retained_filters'), 'confidence': state.get('confidence'), 'analytics_output': state.get('analytics_output'), 'entity_resolution': state.get('entity_resolution'), 'latencies': state.get('latencies'), 'semantic_timing': state.get('semantic_timing'), 'prompt_metrics': state.get('prompt_metrics'), 'prompt_audit': state.get('prompt_audit'), 'timing_report': state.get('timing_report'), 'llm_calls': state.get('llm_calls')}
        state['llm_calls'] = get_llm_calls()
        state['timing_report'] = build_timing_report(state.get('latencies', {}), state.get('semantic_timing'))
        state['prompt_audit'] = build_prompt_audit(state.get('prompt_metrics'))
        state['debug_context']['llm_calls'] = state['llm_calls']
        state['debug_context']['timing_report'] = state['timing_report']
        state['debug_context']['prompt_audit'] = state['prompt_audit']
        state['debug'] = state['debug_context']
        state['latencies']['response_ms'] = t.elapsed_ms()
        return state