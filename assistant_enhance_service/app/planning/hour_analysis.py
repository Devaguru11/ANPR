from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any
HOUR_RANKING_PHRASES: tuple[str, ...] = ('hour with most violations', 'hour with the most violations', 'hour with most', 'most violations by hour', 'violations by hour', 'busiest hour', 'busiest time of day', 'peak hour', 'hourly peak', 'highest hour', 'which hour', 'what hour', 'top hour', 'by hour', 'per hour')
_HOUR_RANKING_RE = re.compile('\\b(?:peak\\s+hour|busiest\\s+hour|highest\\s+hour|top\\s+hour|hourly\\s+peak|which\\s+hour|what\\s+hour|hour\\s+with\\s+(?:the\\s+)?most(?:\\s+violations)?|most\\s+violations\\s+by\\s+hour|violations\\s+by\\s+hour|busiest\\s+time\\s+of\\s+day)\\b', re.I)

def question_requests_hour_ranking(question: str) -> bool:
    q = question.lower().strip()
    if not q:
        return False
    if _HOUR_RANKING_RE.search(q):
        return True
    return any((phrase in q for phrase in HOUR_RANKING_PHRASES))

@dataclass
class HourAnalysisPriority:
    applied: bool
    prior_objective: str | None
    prior_dimension: str | None
    objective: str
    dimension: str

    def to_debug_dict(self) -> dict[str, Any]:
        return {'hour_dimension_explicit': self.applied, 'prior_objective': self.prior_objective, 'prior_dimension': self.prior_dimension, 'applied_objective': self.objective, 'applied_dimension': self.dimension}

def apply_hour_ranking_priority(*, question: str, objective: str, dimension: str | None, has_record_detail_evidence: bool=False) -> tuple[str, str | None, HourAnalysisPriority | None]:
    if has_record_detail_evidence or not question_requests_hour_ranking(question):
        return (objective, dimension, None)
    priority = HourAnalysisPriority(applied=True, prior_objective=objective, prior_dimension=dimension, objective='ranking', dimension='hour')
    return ('ranking', 'hour', priority)
__all__ = ['HOUR_RANKING_PHRASES', 'HourAnalysisPriority', 'apply_hour_ranking_priority', 'question_requests_hour_ranking']