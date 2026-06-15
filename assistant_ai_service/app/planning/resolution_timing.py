from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ResolutionTiming:
    phases: dict[str, float] = field(default_factory=dict)
    cache_hit: bool = False

    def start(self, name: str) -> float:
        return time.perf_counter()

    def stop(self, name: str, started: float) -> None:
        self.phases[name] = round((time.perf_counter() - started) * 1000, 2)

    def to_dict(self) -> dict[str, Any]:
        total = round(sum(self.phases.values()), 2)
        return {'cache_hit': self.cache_hit, 'phases_ms': dict(self.phases), 'total_ms': total}