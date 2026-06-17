from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class SchemaRepresentation:
    filter_key: str
    value: Any
    priority: int = 1
    description: str = ''

    def matches_filter(self, filter_value: Any) -> bool:
        if filter_value is None:
            return False
        if isinstance(self.value, list):
            if not isinstance(filter_value, list):
                return False
            return sorted((str(v) for v in self.value)) == sorted((str(v) for v in filter_value))
        return str(filter_value).strip().lower() == str(self.value).strip().lower()

@dataclass(frozen=True)
class SemanticConcept:
    id: str
    canonical_meaning: str
    representations: tuple[SchemaRepresentation, ...]
    related_dimensions: tuple[str, ...] = ()
    related_metrics: tuple[str, ...] = ('violations',)
    aliases: tuple[str, ...] = ()

    def preferred_representation(self) -> SchemaRepresentation:
        return min(self.representations, key=lambda r: r.priority)

    def matching_filter_keys(self, filters: dict[str, Any]) -> list[tuple[str, SchemaRepresentation]]:
        hits: list[tuple[str, SchemaRepresentation]] = []
        for rep in self.representations:
            if rep.filter_key not in filters:
                continue
            if rep.matches_filter(filters[rep.filter_key]):
                hits.append((rep.filter_key, rep))
        return hits

    def alias_in_text(self, text: str) -> bool:
        q = text.lower()
        return any((alias in q for alias in self.aliases))
SEMANTIC_CONCEPTS: dict[str, SemanticConcept] = {'motorcycle': SemanticConcept(id='motorcycle', canonical_meaning='Two-wheeled motor vehicles (motorcycles and scooters)', representations=(SchemaRepresentation(filter_key='vehicle_category', value=[5, 6], priority=1, description='ANPR category codes for two-wheelers in this deployment'), SchemaRepresentation(filter_key='vehicle_type', value='motorcycle', priority=2, description='Literal vehicle_type label when present in catalog'), SchemaRepresentation(filter_key='vehicle_type', value='two_wheeler', priority=3, description='Alternate vehicle_type label'), SchemaRepresentation(filter_key='vehicle_type', value='two-wheeler', priority=3, description='Hyphenated two-wheeler label')), related_dimensions=('vehicle_type', 'vehicle_category', 'violation_type', 'hour', 'location', 'camera'), related_metrics=('violations', 'detections', 'vehicles'), aliases=('motorcycle', 'motorcycles', 'bike', 'bikes', 'two-wheeler', 'two wheeler', '2w', 'scooter')), 'no_helmet': SemanticConcept(id='no_helmet', canonical_meaning='Riding without a helmet (NO_HELMET violation)', representations=(SchemaRepresentation(filter_key='violation_type', value='NO_HELMET', priority=1, description='Canonical violation_type code'),), related_dimensions=('violation_type', 'location', 'camera', 'hour', 'date'), related_metrics=('violations',), aliases=('no helmet', 'no-helmet', 'without helmet', 'helmetless')), 'triple_riding': SemanticConcept(id='triple_riding', canonical_meaning='More than two riders on a two-wheeler (TRIPLE_RIDING)', representations=(SchemaRepresentation(filter_key='violation_type', value='TRIPLE_RIDING', priority=1, description='Canonical violation_type code'),), related_dimensions=('violation_type', 'location', 'camera'), related_metrics=('violations',), aliases=('triple riding', 'triple-riding', 'three on bike'))}
VEHICLE_CATEGORY_ALIASES: dict[str, list[int]] = {'motorcycle': [5, 6], 'bike': [5, 6]}

def concept_ids() -> list[str]:
    return list(SEMANTIC_CONCEPTS.keys())

def get_concept(concept_id: str) -> SemanticConcept | None:
    return SEMANTIC_CONCEPTS.get(concept_id)

def concepts_for_filters(filters: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for (concept_id, concept) in SEMANTIC_CONCEPTS.items():
        if concept.matching_filter_keys(filters):
            found.append(concept_id)
    return found

def concepts_from_text(text: str) -> list[str]:
    return [cid for (cid, concept) in SEMANTIC_CONCEPTS.items() if concept.alias_in_text(text)]

def resolve_concept_from_text(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    semantic_concepts: list[str] = []
    for concept_id in concepts_from_text(text):
        concept = SEMANTIC_CONCEPTS[concept_id]
        preferred = concept.preferred_representation()
        entities[preferred.filter_key] = preferred.value
        semantic_concepts.append(concept_id)
    if semantic_concepts:
        entities['semantic_concepts'] = semantic_concepts
    return entities

def registry_prompt() -> str:
    lines = ['Semantic business concepts (use canonical meaning; one representation per concept):']
    for concept in SEMANTIC_CONCEPTS.values():
        reps = ', '.join((f'{r.filter_key}={r.value!r} (priority {r.priority})' for r in concept.representations))
        lines.append(f"- {concept.id}: {concept.canonical_meaning}. Representations: {reps}. Dimensions: {', '.join(concept.related_dimensions)}. Metrics: {', '.join(concept.related_metrics)}.")
    return '\n'.join(lines)
__all__ = ['SchemaRepresentation', 'SemanticConcept', 'SEMANTIC_CONCEPTS', 'VEHICLE_CATEGORY_ALIASES', 'concept_ids', 'concepts_for_filters', 'concepts_from_text', 'get_concept', 'registry_prompt', 'resolve_concept_from_text']