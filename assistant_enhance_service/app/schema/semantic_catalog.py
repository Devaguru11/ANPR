from __future__ import annotations
from typing import Any
from sqlalchemy import text
from app.db.pool import Database
from app.schema.discovery import SchemaCatalog
from app.planning.business_concepts import BUSINESS_CONCEPTS
TABLE_DESCRIPTIONS: dict[str, str] = {'vehicle_events': 'Raw ANPR detections and plate reads from cameras. Each row is a vehicle sighting with plate number, camera, timestamp, and vehicle attributes.', 'traffic_violations': 'Traffic violation events linked to vehicle detections via event_id. Includes violation type (e.g. NO_HELMET, WRONG_ROUTE).', 'violation_ticket_flags': 'Challan and ticket workflow flags for violations. Links violations to issued challans/tickets.', 'cameras': 'Registered camera devices and their metadata.', 'camera': 'Camera/site configuration and display names.', 'sites': 'Physical site locations where cameras are deployed.', 'tickets': 'Ticket/challan records in the enforcement workflow.'}
SAMPLE_COLUMNS: dict[str, list[str]] = {'vehicle_events': ['vehicle_num', 'camera_id', 'vehicle_type'], 'traffic_violations': ['violation_type'], 'violation_ticket_flags': ['flag']}

def _relevant_tables(catalog: SchemaCatalog) -> list[str]:
    names: set[str] = set()
    for concept in BUSINESS_CONCEPTS.values():
        names.update(concept.primary_tables)
    names.update(SAMPLE_COLUMNS.keys())
    return sorted((n for n in names if n in catalog.tables))

def _semantic_layer_filtered(catalog: SchemaCatalog, tables: list[str]) -> str:
    from app.schema.discovery import SEMANTIC_HINTS
    lines = ['=== SEMANTIC SCHEMA (relevant tables) ===']
    for tname in tables:
        table = catalog.tables[tname]
        lines.append(f'\n{tname}:')
        for col in table.columns[:20]:
            meaning = SEMANTIC_HINTS.get(col.name) or col.comment or f'{col.name} ({col.data_type})'
            lines.append(f'  {col.name}: {meaning}')
        if len(table.columns) > 20:
            lines.append(f'  ... ({len(table.columns) - 20} more columns)')
    return '\n'.join(lines)

class SchemaSemanticCatalog:

    def __init__(self, catalog: SchemaCatalog, db: Database) -> None:
        self.catalog = catalog
        self.db = db
        self._samples: dict[str, dict[str, list[str]]] = {}

    def refresh_samples(self) -> None:
        samples: dict[str, dict[str, list[str]]] = {}
        for (table, columns) in SAMPLE_COLUMNS.items():
            if table not in self.catalog.tables:
                continue
            samples[table] = {}
            for col in columns:
                try:
                    rows = self.db.query_all(f"SELECT DISTINCT `{col}` AS v FROM `{table}` WHERE `{col}` IS NOT NULL AND `{col}` <> '' LIMIT 5")
                    samples[table][col] = [str(r.get('v')) for r in rows if r.get('v') is not None]
                except Exception:
                    samples[table][col] = []
        self._samples = samples

    def to_prompt(self) -> str:
        tables = _relevant_tables(self.catalog)
        lines = [_semantic_layer_filtered(self.catalog, tables), '', '=== TABLE MEANINGS ===']
        for tname in tables:
            desc = TABLE_DESCRIPTIONS.get(tname)
            if desc:
                lines.append(f'{tname}: {desc}')
        if self._samples:
            lines.append('\n=== SAMPLE VALUES (illustrative) ===')
            for (table, cols) in self._samples.items():
                for (col, values) in cols.items():
                    if values:
                        lines.append(f"{table}.{col}: {', '.join(values[:5])}")
        lines.append('\n=== RELATIONSHIPS ===')
        for tname in tables:
            table = self.catalog.tables[tname]
            for fk in table.foreign_keys:
                lines.append(f"{tname}.{fk['column']} -> {fk['ref_table']}.{fk['ref_col']}")
        return '\n'.join(lines)

    def sample_lines(self) -> list[str]:
        lines: list[str] = []
        for (table, cols) in self._samples.items():
            for (col, values) in cols.items():
                if values:
                    lines.append(f"{table}.{col}: {', '.join(values[:5])}")
        return lines