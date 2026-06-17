from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from sqlalchemy import text
from app.db.pool import Database

@dataclass
class ColumnMeta:
    name: str
    data_type: str
    column_key: str
    comment: str = ''

@dataclass
class TableMeta:
    name: str
    columns: list[ColumnMeta] = field(default_factory=list)
    foreign_keys: list[dict[str, str]] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)

@dataclass
class SchemaCatalog:
    database: str
    tables: dict[str, TableMeta] = field(default_factory=dict)

    def table_names(self) -> list[str]:
        return sorted(self.tables.keys())

    def to_prompt(self) -> str:
        lines: list[str] = []
        for name in self.table_names():
            t = self.tables[name]
            cols = ', '.join((f'{c.name}({c.data_type})' for c in t.columns))
            lines.append(f'TABLE {name}: {cols}')
            if t.foreign_keys:
                fks = '; '.join((f"{fk['column']}->{fk['ref_table']}.{fk['ref_col']}" for fk in t.foreign_keys))
                lines.append(f'  FK: {fks}')
        return '\n'.join(lines)
SEMANTIC_HINTS: dict[str, str] = {'camera_id': 'Physical camera/site where ANPR detections occur (e.g. AEYE_5 = Chowking)', 'vehicle_num': 'Normalized vehicle plate number', 'violation_type': 'Traffic violation: WRONG_ROUTE, NO_HELMET, TRIPLE_RIDING, WRONG_PARKING', 'vehicle_type': 'CAR, TRUCK, BIKE, MINITRUCK, BUS, AUTO, ELECTRIC, etc.', 'event_id': 'Links vehicle_events to traffic_violations', 'created_at': 'Wall-clock datetime of record storage'}

def semantic_layer(catalog: SchemaCatalog) -> str:
    lines = ['=== SEMANTIC SCHEMA ===']
    for (tname, table) in catalog.tables.items():
        lines.append(f'\n{tname}:')
        for col in table.columns:
            meaning = SEMANTIC_HINTS.get(col.name) or col.comment or f'{col.name} ({col.data_type})'
            lines.append(f'  {col.name}: {meaning}')
    return '\n'.join(lines)

class SchemaDiscovery:

    def __init__(self, db: Database) -> None:
        self.db = db

    def discover(self, database: str) -> SchemaCatalog:
        catalog = SchemaCatalog(database=database)
        with self.db.connect() as conn:
            tables = conn.execute(text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=:db AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"), {'db': database}).fetchall()
            for (tname,) in tables:
                tm = TableMeta(name=tname)
                cols = conn.execute(text('SELECT COLUMN_NAME, DATA_TYPE, COLUMN_KEY, COLUMN_COMMENT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t ORDER BY ORDINAL_POSITION'), {'db': database, 't': tname}).fetchall()
                for (cname, dtype, ckey, comment) in cols:
                    tm.columns.append(ColumnMeta(cname, dtype, ckey or '', comment or ''))
                fks = conn.execute(text('SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND REFERENCED_TABLE_NAME IS NOT NULL'), {'db': database, 't': tname}).fetchall()
                for (col, ref_t, ref_c) in fks:
                    tm.foreign_keys.append({'column': col, 'ref_table': ref_t, 'ref_col': ref_c})
                idx = conn.execute(text("SELECT DISTINCT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:t AND INDEX_NAME!='PRIMARY'"), {'db': database, 't': tname}).fetchall()
                tm.indexes = [r[0] for r in idx]
                catalog.tables[tname] = tm
        return catalog