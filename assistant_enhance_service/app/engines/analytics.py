from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.audit.metadata import build_audit_metadata
from app.entity.canonical import debug_entity_fields
from app.engines.auth import verify_key
router = APIRouter(tags=['analytics-assistant'])

class AnalyticsChatRequest(BaseModel):
    session_id: str
    message: str

class AnalyticsDebugRequest(BaseModel):
    session_id: str

@router.get('/health')
async def analytics_health(request: Request) -> dict[str, Any]:
    llm_ok = await request.app.state.llm.health()
    redis_ok = True
    try:
        request.app.state.memory.client.ping()
    except Exception:
        redis_ok = False
    db_ok = True
    try:
        request.app.state.db.query_all('SELECT 1')
    except Exception:
        db_ok = False
    from app.config import settings
    return {'status': 'ok' if llm_ok and redis_ok and db_ok else 'degraded', 'engine': 'analytics', 'llm': llm_ok, 'redis': redis_ok, 'database': db_ok, 'schema_tables': request.app.state.schema_tables, 'bind': f'{settings.ai_service_host}:{settings.ai_service_port}', 'redis_namespace': request.app.state.memory.namespace}

@router.post('/chat', dependencies=[Depends(verify_key)])
async def analytics_chat(req: AnalyticsChatRequest, request: Request) -> dict[str, Any]:
    from app.metrics.http_metrics import LATENCY, REQUESTS
    REQUESTS.labels('assistant_enhance_chat').inc()
    sid = req.session_id.strip()
    if not sid:
        raise HTTPException(400, detail='session_id is required')
    if not req.message.strip():
        raise HTTPException(400, detail='message is required')
    with LATENCY.labels('assistant_enhance_chat').time():
        state = await request.app.state.workflow.run(sid, req.message.strip())
    audit = build_audit_metadata(state)
    return {'session_id': sid, 'message': state.get('final_answer', ''), 'answer': state.get('final_answer', ''), 'context': {'intent': state.get('intent'), 'entities': state.get('entities'), 'confidence': state.get('confidence')}, '_audit': audit}

@router.post('/debug', dependencies=[Depends(verify_key)])
async def analytics_debug(req: AnalyticsDebugRequest, request: Request) -> dict[str, Any]:
    from app.metrics.http_metrics import REQUESTS
    REQUESTS.labels('assistant_enhance_debug').inc()
    sid = req.session_id.strip()
    if not sid:
        raise HTTPException(400, detail='session_id is required')
    memory = request.app.state.memory
    mem = memory.load(sid)
    ctx = mem.get('context', {})
    exchanges = mem.get('exchanges', [])
    question = None
    for ex in reversed(exchanges):
        if ex.get('role') == 'user':
            question = ex.get('content')
            break
    lat = ctx.get('latencies') if isinstance(ctx, dict) else None
    plan = mem.get('plan', {})
    ap = plan.get('analytical_plan') or plan
    return {'session_id': sid, 'memory_key': memory.memory_key(sid), 'context_size': memory.context_size(sid), 'loaded_context': memory.loaded_context(sid), 'question': question, 'normalized_question': question, 'conversation_context': memory.context_text(sid), 'intent': ap.get('intent') or ctx.get('intent'), 'user_objective': ap.get('user_objective') or ctx.get('user_objective'), 'objective_resolution': plan.get('objective_resolution') or ctx.get('objective_resolution'), 'dimension_resolution': plan.get('dimension_resolution') or ctx.get('dimension_resolution'), 'resolved_dimension': (plan.get('dimension_resolution') or ctx.get('dimension_resolution') or {}).get('dimension') or (plan.get('semantic_resolution') or ctx.get('semantic_resolution') or {}).get('dimension') or (ap.get('dimensions') or ctx.get('dimensions') or [None])[0], 'dimension_confidence': (plan.get('dimension_resolution') or ctx.get('dimension_resolution') or {}).get('confidence'), 'candidate_dimensions': (plan.get('dimension_resolution') or ctx.get('dimension_resolution') or {}).get('candidate_dimensions'), 'temporal_resolution': plan.get('temporal_resolution') or ctx.get('temporal_resolution'), 'reference_resolution': ctx.get('reference_resolution') or mem.get('last_reference_resolution'), 'semantic_resolution': plan.get('semantic_resolution') or ctx.get('semantic_resolution'), 'hour_analysis_priority': (plan.get('semantic_resolution') or ctx.get('semantic_resolution') or {}).get('hour_analysis_priority'), 'business_semantic_resolution': plan.get('business_semantic_resolution') or ctx.get('business_semantic_resolution'), 'candidate_concepts': (plan.get('business_semantic_resolution') or ctx.get('business_semantic_resolution') or {}).get('candidate_concepts'), 'candidate_scores': (plan.get('business_semantic_resolution') or ctx.get('business_semantic_resolution') or {}).get('candidate_scores'), 'selection_rationale': (plan.get('business_semantic_resolution') or ctx.get('business_semantic_resolution') or {}).get('selection_rationale'), 'conversation_state': mem.get('conversation_state') or plan.get('conversation_state') or ctx.get('conversation_state'), 'objective_transform': plan.get('objective_transform') or ctx.get('objective_transform'), 'metric': ap.get('metric') or ctx.get('metric'), 'dimensions': ap.get('dimensions') or ctx.get('dimensions'), 'filters': ap.get('filters') or ctx.get('filters'), 'group_by': ap.get('group_by') or ctx.get('group_by'), 'query_mode': ap.get('query_mode') or ctx.get('query_mode'), 'entity_scope': ap.get('entity_scope') or ctx.get('entity_scope'), **debug_entity_fields(ap.get('entity_scope') or ctx.get('entity_scope')), 'time_range': ap.get('time_range') or ctx.get('time_range') or mem.get('time_range'), 'previous_time_range': (plan.get('temporal_resolution') or ctx.get('temporal_resolution') or {}).get('previous_time_range'), 'new_time_range': (plan.get('temporal_resolution') or ctx.get('temporal_resolution') or {}).get('new_time_range') or (ap.get('time_range') or ctx.get('time_range')), 'override_applied': (plan.get('temporal_resolution') or ctx.get('temporal_resolution') or {}).get('override_applied'), 'active_scope': ctx.get('active_scope'), 'inherited_scope': ctx.get('inherited_scope'), 'query_modifications': ctx.get('query_modifications'), 'state_before_merge': (ctx.get('query_modifications') or {}).get('state_before_merge'), 'resolved_changes': (ctx.get('query_modifications') or {}).get('resolved_changes'), 'state_after_merge': (ctx.get('query_modifications') or {}).get('state_after_merge'), 'sticky_preserved': (ctx.get('query_modifications') or {}).get('sticky_preserved'), 'sticky_overridden': (ctx.get('query_modifications') or {}).get('sticky_overridden'), 'resolved_context': ctx.get('resolved_context'), 'semantic_consistency_passed': (ctx.get('resolved_context') or {}).get('semantic_consistency_passed'), 'semantic_consistency_repair': (ctx.get('resolved_context') or {}).get('semantic_consistency_repair'), 'dimension_promotion': (ctx.get('resolved_context') or {}).get('dimension_promotion'), 'dimension_promotion_passed': (ctx.get('resolved_context') or {}).get('dimension_promotion_passed'), 'promotion_reason': ((ctx.get('resolved_context') or {}).get('dimension_promotion') or {}).get('promotion_reason') or (ctx.get('resolved_context') or {}).get('promotion_reason'), 'removed_filters': ((ctx.get('resolved_context') or {}).get('dimension_promotion') or {}).get('removed_filters') or (ctx.get('resolved_context') or {}).get('removed_filters'), 'retained_filters': ((ctx.get('resolved_context') or {}).get('dimension_promotion') or {}).get('retained_filters') or (ctx.get('resolved_context') or {}).get('retained_filters'), 'dataset_type': ctx.get('dataset_type'), 'analytics_summary': ctx.get('analytics_summary'), 'entities': mem.get('entities'), 'entity_resolution': ctx.get('entity_resolution'), 'confidence': ctx.get('confidence'), 'plan': plan, 'sql': ctx.get('sql'), 'execution_time_ms': lat.get('total_ms') if isinstance(lat, dict) else None, 'timing_report': ctx.get('timing_report'), 'semantic_ms': (ctx.get('timing_report') or {}).get('semantic_ms'), 'objective_ms': (ctx.get('timing_report') or {}).get('objective_ms'), 'planner_ms': (ctx.get('timing_report') or {}).get('planner_ms'), 'sql_ms': (ctx.get('timing_report') or {}).get('sql_ms'), 'analytics_ms': (ctx.get('timing_report') or {}).get('analytics_ms'), 'answer_ms': (ctx.get('timing_report') or {}).get('answer_ms'), 'total_ms': (ctx.get('timing_report') or {}).get('total_ms'), 'llm_calls': ctx.get('llm_calls'), 'prompt_audit': ctx.get('prompt_audit'), 'semantic_prompt_tokens': (ctx.get('prompt_audit') or {}).get('semantic_prompt_tokens'), 'answer_prompt_tokens': (ctx.get('prompt_audit') or {}).get('answer_prompt_tokens'), 'schema_tokens': (ctx.get('prompt_audit') or {}).get('schema_tokens'), 'conversation_tokens': (ctx.get('prompt_audit') or {}).get('conversation_tokens'), 'analytics_output': ctx.get('analytics_output'), 'answer': exchanges[-1]['content'] if exchanges and exchanges[-1].get('role') == 'assistant' else None}