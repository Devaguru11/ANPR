from __future__ import annotations
from typing import Any

def build_audit_metadata(state: dict[str, Any]) -> dict[str, Any]:
    plan = state.get('plan') or {}
    ap = plan.get('analytical_plan') or plan
    semantic = state.get('semantic_resolution') or plan.get('semantic_resolution') or {}
    objective = semantic.get('objective') or ap.get('user_objective') or state.get('intent')
    metric = ap.get('metric') or semantic.get('metric')
    return {'objective': objective, 'metric': metric, 'business_concept': (state.get('business_semantic_resolution') or {}).get('business_concept') or ap.get('metric'), 'generated_sql': state.get('sql'), 'planner_context_json': {'intent': state.get('intent'), 'plan': plan, 'semantic_resolution': semantic, 'objective_resolution': state.get('objective_resolution') or plan.get('objective_resolution'), 'dimension_resolution': state.get('dimension_resolution') or plan.get('dimension_resolution'), 'temporal_resolution': state.get('temporal_resolution') or plan.get('temporal_resolution'), 'confidence': state.get('confidence'), 'query_mode': ap.get('query_mode'), 'dataset_type': state.get('dataset_type')}, 'entities_json': state.get('entities') or {}, 'analytics_json': {'analytics_output': state.get('analytics_output'), 'analytics_summary': state.get('analytics_summary'), 'row_count': state.get('row_count'), 'latencies': state.get('latencies')}, 'latency_ms': (state.get('latencies') or {}).get('total_ms')}