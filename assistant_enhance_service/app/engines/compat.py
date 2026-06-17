from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.audit.metadata import build_audit_metadata
from app.engines.auth import verify_key
compat_router = APIRouter(tags=['analytics-assistant-compat'])

class AnalyticsChatRequest(BaseModel):
    session_id: str
    message: str

class AnalyticsDebugRequest(BaseModel):
    session_id: str

@compat_router.post('/chat', dependencies=[Depends(verify_key)])
async def compat_chat(req: AnalyticsChatRequest, request: Request) -> dict[str, Any]:
    from app.metrics.http_metrics import LATENCY, REQUESTS
    REQUESTS.labels('chat').inc()
    sid = req.session_id.strip()
    if not sid:
        raise HTTPException(400, detail='session_id is required')
    if not req.message.strip():
        raise HTTPException(400, detail='message is required')
    with LATENCY.labels('chat').time():
        state = await request.app.state.workflow.run(sid, req.message.strip())
    audit = build_audit_metadata(state)
    return {'session_id': sid, 'message': state.get('final_answer', ''), 'answer': state.get('final_answer', ''), 'context': {'intent': state.get('intent'), 'entities': state.get('entities'), 'confidence': state.get('confidence')}, '_audit': audit}

@compat_router.post('/debug', dependencies=[Depends(verify_key)])
async def compat_debug(req: AnalyticsDebugRequest, request: Request) -> dict[str, Any]:
    from app.engines.analytics import analytics_debug
    return await analytics_debug(req, request)