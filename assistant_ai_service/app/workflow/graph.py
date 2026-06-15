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
from app.planning.scope import entity_scope_from_resolutions, update_scope_from_result
from app.planning.business_concept_catalog import BusinessConceptCatalog
from app.planning.semantic_cache import SemanticResolutionCache
from app.planning.unified_semantic_resolver import UnifiedSemanticResolver
from app.schema.semantic_catalog import SchemaSemanticCatalog
from app.planning.sql_builder import SQLBuilder
from app.schema.discovery import SchemaCatalog
from app.sql.validator import SQLValidator
from app.llm.call_tracker import get_llm_calls, reset_llm_calls
from app.workflow.state import GraphState
from app.workflow.timing_report import build_prompt_audit, build_timing_report

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
        self.planner = AnalyticalPlanner()
        self.sql_builder = SQLBuilder()
        self._graph = self._build()

    def _build(self):
        g = StateGraph(GraphState)
        g.add_node('unified_semantic_resolver', self.unified_semantic_resolver_node)
        g.add_node('analytical_planner', self.analytical_planner)
        g.add_node('sql_generator', self.sql_generator)
        g.add_node('sql_validator', self.sql_validator)
        g.add_node('sql_executor', self.sql_executor)
        g.add_node('analytics_engine', self.analytics_engine)
        g.add_node('response_generator', self.response_generator)
        g.add_edge(START, 'unified_semantic_resolver')
        g.add_edge('unified_semantic_resolver', 'analytical_planner')
        g.add_edge('analytical_planner', 'sql_generator')
        g.add_edge('sql_generator', 'sql_validator')
        g.add_edge('sql_validator', 'sql_executor')
        g.add_edge('sql_executor', 'analytics_engine')
        g.add_edge('analytics_engine', 'response_generator')
        g.add_edge('response_generator', END)
        return g.compile()

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
        self.s.memory.update_context(session_id, state.get('entities') or {}, plan.get('filters', {}), plan.get('time_range', {}), plan, state.get('debug') or state.get('debug_context') or {})
        self.s.logger.write(session_id, {'question': state.get('question'), 'context': state.get('conversation_context'), 'intent': state.get('intent'), 'semantic_resolution': state.get('semantic_resolution'), 'business_semantic_resolution': state.get('business_semantic_resolution'), 'objective_resolution': state.get('objective_resolution'), 'entities': state.get('entities'), 'confidence': state.get('confidence'), 'plan': plan, 'sql': state.get('sql'), 'rows': state.get('row_count'), 'latency': state.get('latencies'), 'semantic_timing': state.get('semantic_timing'), 'prompt_metrics': state.get('prompt_metrics'), 'prompt_audit': state.get('prompt_audit'), 'timing_report': state.get('timing_report'), 'llm_calls': state.get('llm_calls'), 'answer': state.get('final_answer'), 'errors': error or state.get('error')})

    async def unified_semantic_resolver_node(self, state: GraphState) -> GraphState:
        t = Timer()
        state['normalized_question'] = re.sub('\\s+', ' ', state['question'].strip())
        state['conversation_context'] = self.s.memory.context_text(state['session_id'])
        mem = self.s.memory.load(state['session_id'])
        result = await self.unified_resolver.resolve_unified(state['normalized_question'], state.get('conversation_context', ''), mem.get('plan'), mem_time_range=mem.get('time_range'))
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
        state['sql'] = self.sql_builder.build(plan)
        state['latencies']['sql_gen_ms'] = t.elapsed_ms()
        return state

    async def sql_validator(self, state: GraphState) -> GraphState:
        t = Timer()
        if not state.get('sql'):
            state['latencies']['validate_ms'] = t.elapsed_ms()
            return state
        result = self.s.validator.validate(state['sql'])
        state['sql'] = result.sql if result.ok else state.get('sql', '')
        if not result.ok:
            state['sql_errors'] = result.errors
        state['latencies']['validate_ms'] = t.elapsed_ms()
        return state

    async def sql_executor(self, state: GraphState) -> GraphState:
        t = Timer()
        if not state.get('sql'):
            state['latencies']['sql_ms'] = t.elapsed_ms()
            return state
        try:
            (cols, rows) = self.s.db.execute(state['sql'])
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
        if state.get('error') and (not state.get('rows')):
            state['final_answer'] = f"I could not retrieve analytics data. {state['error']}"
        else:
            ao = state.get('analytics_output') or {}
            answer = ao.get('composed_answer') or ao.get('summary')
            state['final_answer'] = answer if answer else 'No data was returned for this query.'
        plan = state.get('plan', {})
        ap = plan.get('analytical_plan', {})
        sem_res = state.get('semantic_resolution') or plan.get('semantic_resolution') or {}
        obj_res = state.get('objective_resolution') or plan.get('objective_resolution') or {}
        state['debug_context'] = {'intent': ap.get('intent'), 'user_objective': ap.get('user_objective'), 'semantic_resolution': sem_res, 'business_semantic_resolution': state.get('business_semantic_resolution') or plan.get('business_semantic_resolution'), 'objective_resolution': obj_res, 'dimension_resolution': state.get('dimension_resolution') or plan.get('dimension_resolution'), 'temporal_resolution': state.get('temporal_resolution') or plan.get('temporal_resolution'), 'conversation_state': state.get('conversation_state') or plan.get('conversation_state'), 'objective_transform': plan.get('objective_transform'), 'metric': ap.get('metric'), 'dimensions': ap.get('dimensions'), 'filters': ap.get('filters'), 'group_by': ap.get('group_by'), 'query_mode': ap.get('query_mode'), 'entity_scope': ap.get('entity_scope'), 'time_range': ap.get('time_range'), 'retrieval_scope': sem_res.get('retrieval_scope') or ap.get('retrieval_scope'), 'sql': state.get('sql'), 'dataset_type': state.get('analytics_output', {}).get('dataset_type'), 'analytics_summary': state.get('analytics_output', {}).get('summary'), 'active_scope': state.get('active_scope'), 'inherited_scope': state.get('inherited_scope'), 'query_modifications': state.get('query_modifications'), 'resolved_context': state.get('resolved_context'), 'confidence': state.get('confidence'), 'analytics_output': state.get('analytics_output'), 'entity_resolution': state.get('entity_resolution'), 'latencies': state.get('latencies'), 'semantic_timing': state.get('semantic_timing'), 'prompt_metrics': state.get('prompt_metrics'), 'prompt_audit': state.get('prompt_audit'), 'timing_report': state.get('timing_report'), 'llm_calls': state.get('llm_calls')}
        state['llm_calls'] = get_llm_calls()
        state['timing_report'] = build_timing_report(state.get('latencies', {}), state.get('semantic_timing'))
        state['prompt_audit'] = build_prompt_audit(state.get('prompt_metrics'))
        state['debug_context']['llm_calls'] = state['llm_calls']
        state['debug_context']['timing_report'] = state['timing_report']
        state['debug_context']['prompt_audit'] = state['prompt_audit']
        state['debug'] = state['debug_context']
        state['latencies']['response_ms'] = t.elapsed_ms()
        return state