from __future__ import annotations
from typing import Any

def build_timing_report(latencies: dict[str, Any], semantic_timing: dict[str, Any] | None=None) -> dict[str, float]:
    phases = (semantic_timing or {}).get('phases_ms') or {}
    sql_ms = float(latencies.get('sql_gen_ms') or 0) + float(latencies.get('validate_ms') or 0) + float(latencies.get('sql_ms') or 0)
    return {'semantic_ms': round(float(latencies.get('unified_semantic_ms') or latencies.get('semantic_ms') or 0), 2), 'objective_ms': round(float(phases.get('llm_inference') or latencies.get('business_semantic_ms') or 0), 2), 'planner_ms': round(float(latencies.get('plan_ms') or 0), 2), 'sql_ms': round(sql_ms, 2), 'analytics_ms': round(float(latencies.get('analytics_ms') or 0), 2), 'answer_ms': round(float(latencies.get('response_ms') or 0), 2), 'total_ms': round(float(latencies.get('total_ms') or 0), 2)}

def build_prompt_audit(prompt_metrics: dict[str, Any] | None) -> dict[str, Any]:
    pm = prompt_metrics or {}
    return {'semantic_prompt_tokens': int(pm.get('semantic_prompt_tokens') or pm.get('total_tokens') or 0), 'answer_prompt_tokens': int(pm.get('answer_prompt_tokens') or 0), 'schema_tokens': int(pm.get('schema_tokens') or pm.get('catalog_tokens') or 0), 'conversation_tokens': int(pm.get('conversation_tokens') or pm.get('conversation_context_tokens') or 0)}