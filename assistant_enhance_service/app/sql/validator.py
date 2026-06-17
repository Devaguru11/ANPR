from __future__ import annotations
import re
from dataclasses import dataclass
import sqlparse
from app.schema.discovery import SchemaCatalog
WRITE_RE = re.compile('\\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|MERGE|REPLACE\\s+INTO)\\b', re.I)

@dataclass
class ValidationResult:
    ok: bool
    sql: str = ''
    errors: list[str] | None = None

class SQLValidator:

    def __init__(self, schema: SchemaCatalog, max_rows: int=10000) -> None:
        self.schema = schema
        self.max_rows = max_rows

    def validate(self, sql: str) -> ValidationResult:
        s = sql.strip().rstrip(';')
        if not s:
            return ValidationResult(False, errors=['Empty SQL'])
        if WRITE_RE.search(s):
            return ValidationResult(False, errors=['Write operation forbidden'])
        if not re.match('^\\s*(SELECT|WITH)\\b', s, re.I):
            return ValidationResult(False, errors=['SELECT only'])
        if re.search("'\\s*\\[", s) or re.search("\\]\\s*'", s):
            return ValidationResult(False, errors=['Invalid list literal in SQL'])
        if not re.search('\\bLIMIT\\b', s, re.I):
            s = f'{s}\nLIMIT {self.max_rows}'
        tables = set(re.findall('\\b(?:FROM|JOIN)\\s+`?(\\w+)`?', s, re.I))
        known = {t.lower() for t in self.schema.table_names()}
        bad = [t for t in tables if t.lower() not in known]
        if bad:
            return ValidationResult(False, errors=[f'Unknown table: {t}' for t in bad])
        return ValidationResult(True, sql=s)