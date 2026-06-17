from __future__ import annotations
import re
from typing import Any
from app.entity.cache import EntityDiscovery
from app.entity.canonical import normalize_entity_scope
from app.planning.semantic_model_registry import VEHICLE_CATEGORY_ALIASES, resolve_concept_from_text
VEHICLE_CATEGORY_MAP = VEHICLE_CATEGORY_ALIASES

class EntityResolver:

    def __init__(self, discovery: EntityDiscovery) -> None:
        self.discovery = discovery

    def resolve(self, question: str, previous_scope: dict[str, Any] | None, inherit: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        entities: dict[str, Any] = dict(previous_scope or {}) if inherit else {}
        resolutions: list[dict[str, Any]] = []
        (loc, score, log) = self.discovery.resolve_location(question)
        if loc:
            entities.update(loc)
            for item in log:
                resolutions.append({'entity_type': 'location', 'resolved_entity': item.get('value'), 'display': item.get('display'), 'confidence': item.get('confidence', score), 'source': item.get('source', 'fuzzy_match'), 'candidates': log[:5]})
        q_lower = question.lower()
        for vio in self.discovery.cache.violation_types:
            label = vio.lower().replace('_', ' ')
            if label in q_lower or vio.lower() in q_lower:
                entities['violation_type'] = vio
                resolutions.append({'entity_type': 'violation_type', 'resolved_entity': vio, 'confidence': 0.85, 'source': 'catalog_match', 'candidates': []})
                break
        semantic_entities = resolve_concept_from_text(question)
        semantic_concepts = semantic_entities.pop('semantic_concepts', None)
        if semantic_entities:
            for (key, val) in semantic_entities.items():
                entities[key] = val
                resolutions.append({'entity_type': key, 'resolved_entity': val, 'confidence': 0.9, 'source': 'semantic_model', 'candidates': []})
            if semantic_concepts:
                entities['semantic_concepts'] = semantic_concepts
        if not any((k in entities for k in ('vehicle_type', 'vehicle_category'))):
            for vt in self.discovery.cache.vehicle_types:
                if vt.lower() in q_lower:
                    entities['vehicle_type'] = vt
                    resolutions.append({'entity_type': 'vehicle_type', 'resolved_entity': vt, 'confidence': 0.85, 'source': 'catalog_match', 'candidates': []})
                    break
        suffix = self._plate_suffix(question)
        if suffix:
            entities['plate_suffix'] = suffix
            resolutions.append({'entity_type': 'plate_suffix', 'resolved_entity': suffix, 'confidence': 0.9, 'source': 'pattern', 'candidates': []})
        if inherit:
            for key in list(entities.keys()):
                if key not in ('camera_id', 'location', 'display', 'violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix'):
                    entities.pop(key, None)
        return (normalize_entity_scope(entities), resolutions)

    @staticmethod
    def _plate_suffix(question: str) -> str | None:
        m = re.search('(?:ending|ends)\\s+with\\s+(\\w+)', question, re.I)
        return m.group(1) if m else None

    def needs_clarification(self, resolutions: list[dict[str, Any]]) -> str | None:
        for item in resolutions:
            if item.get('entity_type') == 'location' and float(item.get('confidence', 1)) < 0.72:
                cands = item.get('candidates') or []
                if cands:
                    names = ', '.join((c.get('display', c.get('value')) for c in cands[:3]))
                    return f'I found multiple possible locations ({names}). Which one did you mean?'
        return None