from __future__ import annotations
from typing import Any, TypedDict

class GraphState(TypedDict, total=False):
    session_id: str
    question: str
    normalized_question: str
    conversation_context: str
    intent: str
    entities: dict[str, Any]
    entity_resolution: list[dict[str, Any]]
    confidence: float
    plan: dict[str, Any]
    sql: str
    sql_errors: list[str]
    columns: list[str]
    rows: list[tuple]
    row_count: int
    analytics_output: dict[str, Any]
    final_answer: str
    error: str
    debug: dict[str, Any]
    debug_context: dict[str, Any]
    clarification_needed: str
    active_scope: dict[str, Any]
    inherited_scope: dict[str, Any]
    query_modifications: dict[str, Any]
    resolved_context: dict[str, Any]
    entity_scope: dict[str, Any]
    user_objective: str
    objective_resolution: dict[str, Any]
    dimension_resolution: dict[str, Any]
    temporal_resolution: dict[str, Any]
    semantic_resolution: dict[str, Any]
    business_semantic_resolution: dict[str, Any]
    conversation_state: dict[str, Any]
    latencies: dict[str, float]
    semantic_timing: dict[str, Any]
    prompt_metrics: dict[str, Any]
    timing_report: dict[str, float]
    prompt_audit: dict[str, Any]
    llm_calls: int