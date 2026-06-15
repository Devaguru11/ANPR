from __future__ import annotations
import re
from typing import Any
from app.entity.cache import EntityDiscovery
VEHICLE_CATEGORY_MAP = {'motorcycle': [5, 6], 'bike': [5, 6]}

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
        for vt in self.discovery.cache.vehicle_types:
            if vt.lower() in q_lower:
                entities['vehicle_type'] = vt
                resolutions.append({'entity_type': 'vehicle_type', 'resolved_entity': vt, 'confidence': 0.85, 'source': 'catalog_match', 'candidates': []})
                break
        for (label, cats) in VEHICLE_CATEGORY_MAP.items():
            if label in q_lower:
                entities['vehicle_category'] = cats
                resolutions.append({'entity_type': 'vehicle_category', 'resolved_entity': cats, 'confidence': 0.85, 'source': 'category_map', 'candidates': []})
                break
        suffix = self._plate_suffix(question)
        if suffix:
            entities['plate_suffix'] = suffix
            resolutions.append({'entity_type': 'plate_suffix', 'resolved_entity': suffix, 'confidence': 0.9, 'source': 'pattern', 'candidates': []})
        if inherit:
            for key in list(entities.keys()):
                if key not in ('camera_id', 'location', 'display', 'violation_type', 'vehicle_type', 'vehicle_category', 'plate_suffix'):
                    entities.pop(key, None)
        return (entities, resolutions)

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