from __future__ import annotations
import json
import re
from datetime import datetime, timezone
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
from app.engines.legacy import generate_sql_from_query_plan
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
        self.planner = AnalyticalPlanner(services.llm)
        self.sql_builder = SQLBuilder()
        self._graph = self._build()

    def _build(self):
        g = StateGraph(GraphState)
        g.add_node('intent_detection', self.intent_detection_node)
        g.add_node('direct_reply', self.direct_reply_node)
        g.add_node('content_manager', self.content_manager_node)
        g.add_node('query_planner', self.query_planner_node)
        g.add_node('sql_generator', self.sql_generator)
        g.add_node('sql_validator', self.sql_validator)
        g.add_node('sql_executor', self.sql_executor)
        g.add_node('insight_generator', self.insight_generator_node)
        g.add_node('response_generator', self.response_generator)
        g.add_node('error_response', self.error_response_node)
        g.add_edge(START, 'intent_detection')
        g.add_conditional_edges(
            'intent_detection',
            self.route_after_intent_detection,
            {
                'conversational': 'direct_reply',
                'data_query': 'content_manager',
            },
        )
        g.add_edge('direct_reply', END)
        g.add_edge('content_manager', 'query_planner')
        g.add_edge('query_planner', 'sql_generator')
        g.add_edge('sql_generator', 'sql_validator')
        g.add_conditional_edges(
            'sql_validator',
            self.route_after_sql_validation,
            {
                'retry': 'sql_generator',
                'execute': 'sql_executor',
                'error': 'error_response',
            },
        )
        g.add_edge('sql_executor', 'insight_generator')
        g.add_edge('insight_generator', 'response_generator')
        g.add_edge('error_response', END)
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

    def route_after_intent_detection(self, state: GraphState) -> str:
        return 'conversational' if state.get('intent') == 'conversational' else 'data_query'

    def route_after_sql_validation(self, state: GraphState) -> str:
        if state.get('sql_validation_error'):
            if int(state.get('retry_count') or 0) < 2:
                return 'retry'
            return 'error'
        return 'execute'

    async def intent_detection_node(self, state: GraphState) -> GraphState:
        t = Timer()
        question = re.sub(r'\s+', ' ', state['question'].strip())
        system = (
            'You are an intent detector for a traffic analytics assistant. '\
            'Classify the user question as either data_query or conversational. '\
            'Return JSON only in the format: {"intent":"data_query|conversational","reasoning":"..."}.'
        )
        user = f'Question: {question}\n\nReturn only JSON.'
        intent = 'data_query'
        reasoning = ''
        try:
            data = await self.s.llm.chat_json(system, user, max_tokens=128)
            raw_intent = str(data.get('intent') or 'data_query').strip().lower()
            intent = 'conversational' if raw_intent == 'conversational' else 'data_query'
            reasoning = str(data.get('reasoning') or '')
        except Exception:
            conversational_hint = bool(re.search(r'\b(hi|hello|hey|thanks|thank you|how are you|what can you do|who are you)\b', question, re.I))
            intent = 'conversational' if conversational_hint else 'data_query'
            reasoning = 'fallback heuristic'
        state['normalized_question'] = question
        state['intent'] = intent
        state['intent_detection_reasoning'] = reasoning
        state['latencies']['intent_detection_ms'] = t.elapsed_ms()
        return state

    async def direct_reply_node(self, state: GraphState) -> GraphState:
        t = Timer()
        question = state.get('normalized_question') or re.sub(r'\s+', ' ', state['question'].strip())
        conversation_context = self.s.memory.context_text(state['session_id'])
        system = (
            'You are the assistant for an ANPR operations dashboard. '\
            'Answer conversationally and briefly. Do not mention SQL, database internals, or schema.'
        )
        user = f'Conversation context:\n{conversation_context[:2000]}\n\nUser question: {question}\n\nProvide a direct helpful reply.'
        try:
            reply = await self.s.llm.chat(system, user, max_tokens=256)
        except Exception:
            reply = 'How can I help you with the ANPR dashboard?'
        state['final_answer'] = str(reply).strip() or 'How can I help you with the ANPR dashboard?'
        state['latencies']['direct_reply_ms'] = t.elapsed_ms()
        return state

    def _schema_summary(self) -> dict[str, Any]:
        tables: dict[str, Any] = {}
        for (name, table) in self.s.schema.tables.items():
            tables[name] = {
                'columns': [c.name for c in table.columns],
                'foreign_keys': [dict(fk) for fk in table.foreign_keys],
            }
        return {'tables': tables}

    def _schema_text(self) -> str:
        lines: list[str] = []
        for name, table in self.s.schema.tables.items():
            cols = ', '.join(c.name for c in table.columns)
            lines.append(f'{name}: {cols}')
        return '\n'.join(lines)

    def _normalize_scoped_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        tables_in = data.get('tables') if isinstance(data, dict) else {}
        tables: dict[str, Any] = {}
        if isinstance(tables_in, dict):
            for table_name, meta in tables_in.items():
                if isinstance(meta, dict):
                    cols = meta.get('columns') or meta.get('fields') or []
                    reason = str(meta.get('reason') or '')
                else:
                    cols = meta if isinstance(meta, list) else []
                    reason = ''
                tables[str(table_name)] = {
                    'columns': [str(c) for c in cols if str(c).strip()],
                    'reason': reason,
                }
        relationships = data.get('relationships') if isinstance(data.get('relationships'), list) else []
        return {'tables': tables, 'relationships': relationships}

    def _scope_schema_fallback(self, question: str) -> dict[str, Any]:
        q = question.lower()
        tables: dict[str, Any] = {}
        for (name, table) in self.s.schema.tables.items():
            cols = [c.name for c in table.columns]
            matched = [c for c in cols if c.lower() in q]
            if matched or any(token in q for token in name.lower().split('_')):
                tables[name] = {'columns': matched or cols[:8], 'reason': 'heuristic match'}
        if not tables:
            for name in list(self.s.schema.tables.keys())[:3]:
                table = self.s.schema.tables[name]
                tables[name] = {'columns': [c.name for c in table.columns[:8]], 'reason': 'default scope'}
        return {'tables': tables, 'relationships': []}

    async def content_manager_node(self, state: GraphState) -> GraphState:
        t = Timer()
        question = state.get('normalized_question') or re.sub(r'\s+', ' ', state['question'].strip())
        system = (
            'You are a content manager for an ANPR data assistant. '\
            'Given the user question and the full database schema, select only the relevant tables and columns. '\
            'Return JSON only in the format: {"tables": {"table_name": {"columns": ["col1", "col2"], "reason": "..."}}, "relationships": []}.'
        )
        user = f'Question: {question}\n\nFull schema:\n{self._schema_text()}\n\nReturn only relevant tables and columns.'
        scoped_schema = None
        try:
            data = await self.s.llm.chat_json(system, user, max_tokens=768)
            if isinstance(data, dict):
                scoped_schema = self._normalize_scoped_schema(data)
        except Exception:
            scoped_schema = None
        state['scoped_schema'] = scoped_schema or self._scope_schema_fallback(question)
        state['latencies']['content_manager_ms'] = t.elapsed_ms()
        return state

    async def query_planner_node(self, state: GraphState) -> GraphState:
        t = Timer()
        question = state.get('normalized_question') or re.sub(r'\s+', ' ', state['question'].strip())
        conversation_context = self.s.memory.context_text(state['session_id'])
        memory_state = self.s.memory.load(state['session_id'])
        previous_plan = memory_state.get('query_plan') or memory_state.get('plan') or {}
        query_plan = await self.planner.build_query_plan(question, state.get('scoped_schema') or {}, conversation_context, memory_state, previous_plan)
        state['query_plan'] = query_plan
        state['plan'] = query_plan
        state['conversation_context'] = conversation_context
        state['latencies']['query_planner_ms'] = t.elapsed_ms()
        return state

    async def sql_generator(self, state: GraphState) -> GraphState:
        t = Timer()
        if state.get('sql_validation_error'):
            state['sql_correction_message'] = state.get('sql_validation_error')
        question = state.get('normalized_question') or re.sub(r'\s+', ' ', state['question'].strip())
        sql = await generate_sql_from_query_plan(
            self.s.llm,
            question,
            state.get('query_plan') or {},
            state.get('scoped_schema') or {},
            state.get('sql_correction_message'),
        )
        state['sql'] = sql
        state['latencies']['sql_gen_ms'] = t.elapsed_ms()
        return state

    async def sql_validator(self, state: GraphState) -> GraphState:
        t = Timer()
        sql = StringOrEmpty(state.get('sql')).strip() if False else str(state.get('sql') or '').strip()
        if not sql:
            state['sql_validation_error'] = 'Empty SQL'
            state['retry_count'] = int(state.get('retry_count') or 0) + 1
            state['latencies']['validate_ms'] = t.elapsed_ms()
            return state
        try:
            self.s.db.query_all(f'EXPLAIN {sql}')
            state['sql_validation_error'] = ''
        except Exception as exc:
            state['sql_validation_error'] = str(exc)
            state['retry_count'] = int(state.get('retry_count') or 0) + 1
            state['sql_correction_message'] = str(exc)
        state['latencies']['validate_ms'] = t.elapsed_ms()
        return state

    async def sql_executor(self, state: GraphState) -> GraphState:
        t = Timer()
        sql = str(state.get('sql') or '').strip()
        if not sql:
            state['error'] = 'No SQL generated.'
            state['columns'] = []
            state['rows'] = []
            state['row_count'] = 0
            state['latencies']['sql_ms'] = t.elapsed_ms()
            return state
        try:
            (cols, rows) = self.s.db.execute(sql)
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

    def _relax_query_plan(self, query_plan: dict[str, Any]) -> dict[str, Any]:
        relaxed = json.loads(json.dumps(query_plan or {}))
        filters = relaxed.get('filters') if isinstance(relaxed.get('filters'), dict) else {}
        for key in ('vehicle_num', 'plate_suffix', 'camera_id', 'violation_type'):
            if key in filters:
                filters.pop(key, None)
                break
        time_range = relaxed.get('time_range') if isinstance(relaxed.get('time_range'), dict) else {}
        if time_range.get('preset') in ('today', 'yesterday'):
            relaxed['time_range'] = {'preset': 'last_7_days'}
        else:
            relaxed['time_range'] = time_range or {'preset': 'last_7_days'}
        relaxed['filters'] = filters
        return relaxed

    async def insight_generator_node(self, state: GraphState) -> GraphState:
        t = Timer()
        row_count = int(state.get('row_count') or 0)
        if row_count == 0 and not state.get('relaxation_attempted'):
            state['relaxation_attempted'] = True
            state['query_plan'] = self._relax_query_plan(state.get('query_plan') or {})
            state['plan'] = state['query_plan']
            state['sql_correction_message'] = 'No rows returned. Relax the WHERE clause and broaden the time range.'
            state = await self.sql_generator(state)
            state = await self.sql_validator(state)
            if not state.get('sql_validation_error'):
                state = await self.sql_executor(state)
                row_count = int(state.get('row_count') or 0)
        if row_count == 0:
            state['final_answer'] = 'No matching data was found after relaxing the filters once.'
            state['latencies']['insight_ms'] = t.elapsed_ms()
            return state
        rows = state.get('rows') or []
        if row_count >= 10000:
            limited_sql = f"SELECT * FROM ({str(state.get('sql') or '').rstrip(';')}) AS limited_query LIMIT 500"
            try:
                (cols, limited_rows) = self.s.db.execute(limited_sql)
                state['columns'] = cols
                state['rows'] = limited_rows
                state['row_count'] = len(limited_rows)
                state['truncated'] = True
                rows = limited_rows
            except Exception:
                state['truncated'] = True
        question = state.get('normalized_question') or state.get('question', '')
        system = (
            'You are a data assistant for an ANPR platform. '\
            'Use the provided rows and the user question to write a concise natural-language answer. '\
            'Focus on key observations, not raw rows.'
        )
        sample_rows = rows[:50]
        user = f'User question: {question}\n\nColumns: {json.dumps(state.get("columns") or [], default=str)}\n\nRows sample: {json.dumps(sample_rows, default=str)}\n\nWrite a concise answer with key observations.'
        try:
            answer = await self.s.llm.chat(system, user, max_tokens=512)
            state['final_answer'] = str(answer).strip() or 'No data was returned for this query.'
        except Exception:
            state['final_answer'] = f'Returned {state.get("row_count", 0)} rows.' + (' Results were truncated.' if state.get('truncated') else '')
        if state.get('truncated'):
            state['final_answer'] = f"{state['final_answer']} Results were truncated to 500 rows for summarization."
        state['latencies']['insight_ms'] = t.elapsed_ms()
        return state

    async def error_response_node(self, state: GraphState) -> GraphState:
        state['final_answer'] = state.get('sql_validation_error') or state.get('error') or 'I could not complete that request.'
        return state

    def _finalize_observability(self, state: GraphState) -> None:
        state['timing_report'] = build_timing_report(state.get('latencies', {}), state.get('semantic_timing'))
        state['prompt_audit'] = build_prompt_audit(state.get('prompt_metrics'))
        dbg = state.get('debug_context') or state.get('debug') or {}
        dbg.update({'timing_report': state['timing_report'], 'prompt_audit': state['prompt_audit'], 'llm_calls': state.get('llm_calls', 0), 'semantic_timing': state.get('semantic_timing'), 'prompt_metrics': state.get('prompt_metrics'), 'latencies': state.get('latencies')})
        state['debug_context'] = dbg
        state['debug'] = dbg

    def _persist(self, session_id: str, state: GraphState, error: str | None=None) -> None:
        plan = state.get('query_plan') or state.get('plan') or {}
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
        if not state.get('final_answer'):
            state['final_answer'] = 'I could not complete that request.'
        state['llm_calls'] = get_llm_calls()
        state['timing_report'] = build_timing_report(state.get('latencies', {}), state.get('semantic_timing'))
        state['prompt_audit'] = build_prompt_audit(state.get('prompt_metrics'))
        state['debug_context'] = {
            'intent': state.get('intent'),
            'question': state.get('question'),
            'scoped_schema': state.get('scoped_schema'),
            'query_plan': state.get('query_plan'),
            'sql': state.get('sql'),
            'row_count': state.get('row_count'),
            'sql_validation_error': state.get('sql_validation_error'),
            'retry_count': state.get('retry_count'),
            'latencies': state.get('latencies'),
            'llm_calls': state.get('llm_calls'),
        }
        state['debug'] = state['debug_context']
        state['latencies']['response_ms'] = t.elapsed_ms()
        return state