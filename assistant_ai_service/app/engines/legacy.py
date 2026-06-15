from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
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


def _schema_tables(scoped_schema: dict[str, Any]) -> dict[str, list[str]]:
    tables = scoped_schema.get('tables') if isinstance(scoped_schema, dict) else {}
    if isinstance(tables, dict):
        result: dict[str, list[str]] = {}
        for table, meta in tables.items():
            if isinstance(meta, dict):
                cols = meta.get('columns') or meta.get('fields') or []
            elif isinstance(meta, list):
                cols = meta
            else:
                cols = []
            result[str(table)] = [str(c) for c in cols if str(c).strip()]
        return result
    return {}


def _few_shot_examples(schema_tables: dict[str, list[str]]) -> str:
    vehicle_events_cols = schema_tables.get('vehicle_events', [])
    traffic_violations_cols = schema_tables.get('traffic_violations', [])
    cameras_cols = schema_tables.get('cameras', []) or schema_tables.get('camera', [])
    ve_camera = 'camera_id' if 'camera_id' in vehicle_events_cols else (vehicle_events_cols[0] if vehicle_events_cols else 'camera_id')
    ve_created = 'created_at' if 'created_at' in vehicle_events_cols else (vehicle_events_cols[0] if vehicle_events_cols else 'created_at')
    ve_plate = 'vehicle_num' if 'vehicle_num' in vehicle_events_cols else (vehicle_events_cols[0] if vehicle_events_cols else 'vehicle_num')
    tv_type = 'violation_type' if 'violation_type' in traffic_violations_cols else (traffic_violations_cols[0] if traffic_violations_cols else 'violation_type')
    cam_name = 'name' if 'name' in cameras_cols else (cameras_cols[0] if cameras_cols else 'name')
    return f"""Example 1\nQuestion: Count vehicle reads today by camera.\nSQL: SELECT {ve_camera}, COUNT(*) AS total_reads FROM vehicle_events WHERE DATE({ve_created}) = CURDATE() GROUP BY {ve_camera} ORDER BY total_reads DESC;\n\nExample 2\nQuestion: Show yesterday's violation counts by type.\nSQL: SELECT tv.{tv_type}, COUNT(*) AS total_violations FROM traffic_violations tv JOIN vehicle_events ve ON ve.event_id = tv.event_id WHERE DATE(ve.{ve_created}) = DATE_SUB(CURDATE(), INTERVAL 1 DAY) GROUP BY tv.{tv_type} ORDER BY total_violations DESC;\n\nExample 3\nQuestion: List the latest 5 plate reads for a camera.\nSQL: SELECT {ve_plate}, {ve_camera}, {ve_created} FROM vehicle_events WHERE {ve_camera} = 'AEYE_1' ORDER BY {ve_created} DESC LIMIT 5;"""


async def generate_sql_from_query_plan(llm, question: str, query_plan: dict[str, Any], scoped_schema: dict[str, Any], correction_message: str | None = None) -> str:
    schema_tables = _schema_tables(scoped_schema)
    system = (
        f"You are a SQL generator for an ANPR assistant. Current server time (UTC): {datetime.now(timezone.utc).replace(tzinfo=None)}. "
        "Use only the scoped schema provided. Produce a single MySQL SELECT query only. No explanations, no markdown, no code fences."
    )
    user = [
        f"User question: {question}",
        f"Query plan: {json.dumps(query_plan or {}, ensure_ascii=False, default=str)}",
        f"Scoped schema: {json.dumps(scoped_schema or {}, ensure_ascii=False, default=str)}",
        _few_shot_examples(schema_tables),
    ]
    if correction_message:
        user.append(f"Correction from validation: {correction_message}")
    prompt = "\n\n".join(user)
    sql = await llm.chat(system, prompt, max_tokens=700)
    return str(sql).strip().strip('`').strip()