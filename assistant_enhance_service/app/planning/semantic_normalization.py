from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Any
from app.planning.plan import AnalyticalPlan
from app.planning.semantic_model_registry import SEMANTIC_CONCEPTS, concepts_for_filters
SCOPE_KEYS_FOR_FILTER = {'location': ('camera_id', 'location'), 'violation_type': ('violation_type',), 'vehicle_type': ('vehicle_type',), 'vehicle_category': ('vehicle_category',), 'plate_suffix': ('plate_suffix',), 'hour': ('peak_hour',)}

@dataclass
class SemanticNormalizationResult:
    passed: bool
    normalized: bool
    active_concepts: list[str] = field(default_factory=list)
    removed_filters: dict[str, Any] = field(default_factory=dict)
    upgraded_filters: dict[str, Any] = field(default_factory=dict)
    chosen_representations: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = {'semantic_normalization_passed': self.passed, 'semantic_concepts': self.active_concepts}
        if not self.normalized:
            return base
        return {**base, 'semantic_normalization': {'removed_filters': self.removed_filters, 'upgraded_filters': self.upgraded_filters, 'chosen_representations': self.chosen_representations}}

def normalize_semantic_filters(filters: dict[str, Any], entity_scope: dict[str, Any] | None=None) -> tuple[dict[str, Any], dict[str, Any], SemanticNormalizationResult]:
    normalized_filters = copy.deepcopy(filters or {})
    normalized_scope = copy.deepcopy(entity_scope or {})
    result = SemanticNormalizationResult(passed=True, normalized=False)
    for (concept_id, concept) in SEMANTIC_CONCEPTS.items():
        hits = concept.matching_filter_keys(normalized_filters)
        if not hits:
            continue
        result.active_concepts.append(concept_id)
        preferred = concept.preferred_representation()
        if len(hits) > 1:
            result.normalized = True
            keep_key = preferred.filter_key
            for (filter_key, _rep) in hits:
                if filter_key == keep_key:
                    normalized_filters[keep_key] = preferred.value
                    continue
                removed = normalized_filters.pop(filter_key, None)
                if removed is not None:
                    result.removed_filters[filter_key] = removed
                for scope_key in SCOPE_KEYS_FOR_FILTER.get(filter_key, ()):
                    if normalized_scope.get(scope_key) == removed:
                        normalized_scope.pop(scope_key, None)
            result.chosen_representations[concept_id] = {'filter_key': keep_key, 'value': preferred.value}
            _sync_scope_for_filter(normalized_scope, keep_key, preferred.value)
            continue
        (active_key, active_rep) = hits[0]
        if active_rep.priority > preferred.priority:
            result.normalized = True
            normalized_filters.pop(active_key, None)
            normalized_filters[preferred.filter_key] = preferred.value
            result.upgraded_filters[active_key] = active_rep.value
            result.chosen_representations[concept_id] = {'filter_key': preferred.filter_key, 'value': preferred.value}
            for scope_key in SCOPE_KEYS_FOR_FILTER.get(active_key, ()):
                if scope_key in normalized_scope:
                    normalized_scope.pop(scope_key, None)
            _sync_scope_for_filter(normalized_scope, preferred.filter_key, preferred.value)
        else:
            result.chosen_representations[concept_id] = {'filter_key': active_key, 'value': normalized_filters.get(active_key)}
    if result.active_concepts:
        normalized_scope['semantic_concepts'] = list(dict.fromkeys(result.active_concepts))
    result.passed = not _has_contradictory_concept_filters(normalized_filters)
    return (normalized_filters, normalized_scope, result)

def _sync_scope_for_filter(scope: dict[str, Any], filter_key: str, value: Any) -> None:
    if filter_key == 'vehicle_category':
        scope['vehicle_category'] = value
    elif filter_key == 'vehicle_type':
        scope['vehicle_type'] = value
    elif filter_key == 'violation_type':
        scope['violation_type'] = value

def _has_contradictory_concept_filters(filters: dict[str, Any]) -> bool:
    for concept in SEMANTIC_CONCEPTS.values():
        if len(concept.matching_filter_keys(filters)) > 1:
            return True
    return False

def filters_over_constrained(filters: dict[str, Any]) -> bool:
    return _has_contradictory_concept_filters(filters)

def apply_semantic_normalization(plan: AnalyticalPlan) -> SemanticNormalizationResult:
    (filters, scope, result) = normalize_semantic_filters(plan.filters, plan.entity_scope)
    plan.filters = filters
    plan.entity_scope = scope
    return result
__all__ = ['SemanticNormalizationResult', 'apply_semantic_normalization', 'concepts_for_filters', 'filters_over_constrained', 'normalize_semantic_filters']