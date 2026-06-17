from __future__ import annotations
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.audit.metadata import build_audit_metadata
from app.engines.analytics import analytics_health
router = APIRouter(tags=['legacy-assistant'])

class LegacyChatRequest(BaseModel):
    message: str
    sessionId: str | None = None

@router.get('/health')
async def legacy_health(request: Request) -> dict[str, Any]:
    payload = await analytics_health(request)
    payload['route'] = 'assistant'
    return payload

@router.post('/chat')
async def legacy_chat(req: LegacyChatRequest, request: Request) -> dict[str, Any]:
    from app.metrics.http_metrics import LATENCY, REQUESTS
    REQUESTS.labels('assistant_enhance_chat').inc()
    if not req.message.strip():
        raise HTTPException(400, detail='message is required')
    sid = (req.sessionId or '').strip() or str(uuid.uuid4())
    with LATENCY.labels('assistant_enhance_chat').time():
        state = await request.app.state.workflow.run(sid, req.message.strip())
    audit = build_audit_metadata(state)
    return {'sessionId': sid, 'message': state.get('final_answer', ''), 'cards': [], 'context': {'intent': state.get('intent'), 'entities': state.get('entities'), 'confidence': state.get('confidence')}, '_audit': audit}

@router.get('/help')
async def legacy_help() -> dict[str, Any]:
    return {'message': 'Ask about plate reads, violations, and camera sites — answers come from your database only.'}