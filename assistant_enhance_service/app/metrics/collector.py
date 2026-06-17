from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any

@dataclass
class LatencyMetrics:
    llm_ms: float = 0
    sql_ms: float = 0
    entity_ms: float = 0
    analytics_ms: float = 0
    total_ms: float = 0
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {'llm_latency_ms': self.llm_ms, 'sql_latency_ms': self.sql_ms, 'entity_resolution_latency_ms': self.entity_ms, 'analytics_latency_ms': self.analytics_ms, 'total_latency_ms': self.total_ms, 'request_counts': self.counts}

class MetricsCollector:

    def __init__(self) -> None:
        self._totals: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    def record(self, name: str, ms: float) -> None:
        self._totals[name] = self._totals.get(name, 0) + ms
        self._counts[name] = self._counts.get(name, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        return {'totals_ms': self._totals, 'counts': self._counts, 'averages_ms': {k: self._totals[k] / self._counts[k] for k in self._counts if self._counts[k]}}

class Timer:

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000