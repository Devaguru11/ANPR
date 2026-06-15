from __future__ import annotations
import json
from typing import Any
from app.planning.business_concepts import BUSINESS_CONCEPTS
from app.schema.semantic_catalog import TABLE_DESCRIPTIONS, SchemaSemanticCatalog

class BusinessConceptCatalog:

    def __init__(self, schema_semantic: SchemaSemanticCatalog) -> None:
        self.concepts: dict[str, str] = {cid: concept.description for (cid, concept) in BUSINESS_CONCEPTS.items()}
        self._compact_prompt = self._build_compact(schema_semantic)
        self._json_blob = json.dumps(self.concepts, ensure_ascii=False)

    def _build_compact(self, schema_semantic: SchemaSemanticCatalog) -> str:
        lines = ['=== BUSINESS CONCEPT CATALOG ===']
        for (cid, concept) in BUSINESS_CONCEPTS.items():
            tables = ', '.join(concept.primary_tables)
            lines.append(f'{cid}: {concept.description} [tables: {tables}]')
            if concept.examples:
                lines.append(f'  + {concept.examples[0]}')
            if concept.negative_examples:
                lines.append(f'  - not: {concept.negative_examples[0]}')
        lines.append('\n=== TABLE SUMMARIES ===')
        for (tname, desc) in TABLE_DESCRIPTIONS.items():
            lines.append(f'{tname}: {desc}')
        samples = schema_semantic.sample_lines()
        if samples:
            lines.append('\n=== SAMPLE VALUES ===')
            lines.extend(samples)
        return '\n'.join(lines)

    def compact_prompt(self) -> str:
        return self._compact_prompt

    def resolver_prompt(self) -> str:
        lines = ['=== BUSINESS CONCEPTS ===']
        for (cid, concept) in BUSINESS_CONCEPTS.items():
            lines.append(f'{cid}: {concept.description}')
            if concept.examples:
                lines.append(f'  e.g. {concept.examples[0]}')
        return '\n'.join(lines)

    def to_dict(self) -> dict[str, str]:
        return dict(self.concepts)

    def token_estimate(self) -> int:
        return max(1, len(self._compact_prompt) // 4)