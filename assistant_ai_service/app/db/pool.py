from __future__ import annotations
from contextlib import contextmanager
from typing import Any, Generator
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Result
from sqlalchemy.pool import QueuePool
from app.config import settings

def _url() -> str:
    user = quote_plus(settings.db_user)
    password = quote_plus(settings.db_password)
    host = settings.db_host
    return f'mysql+mysqlconnector://{user}:{password}@{host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4'

class Database:

    def __init__(self) -> None:
        self.engine: Engine = create_engine(_url(), poolclass=QueuePool, pool_size=5, max_overflow=2, pool_pre_ping=True)

    @contextmanager
    def connect(self) -> Generator[Any, None, None]:
        conn = self.engine.connect()
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, sql: str, params: dict | None=None) -> tuple[list[str], list[tuple]]:
        with self.connect() as conn:
            conn.execute(text(f'SET SESSION MAX_EXECUTION_TIME={settings.sql_timeout_seconds * 1000}'))
            result: Result = conn.execute(text(sql), params or {})
            cols = list(result.keys())
            rows = result.fetchmany(settings.sql_max_rows)
            return (cols, [tuple(r) for r in rows])

    def query_all(self, sql: str, params: dict | None=None) -> list[tuple]:
        (_, rows) = self.execute(sql, params)
        return rows