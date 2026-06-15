from __future__ import annotations
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
TIME_TOKENS = ('today', 'yesterday', 'tomorrow', 'this week', 'this month', 'last month', 'last week', 'last 7 days', 'last 30 days', 'this year', 'last year')

@dataclass
class CacheEntry:
    pattern: str
    payload: dict[str, Any]

class SemanticResolutionCache:

    def __init__(self, max_size: int=256, similarity_threshold: float=0.82) -> None:
        self.max_size = max_size
        self.similarity_threshold = similarity_threshold
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    @staticmethod
    def normalize_pattern(question: str) -> str:
        q = re.sub('\\s+', ' ', question.lower().strip())
        for token in TIME_TOKENS:
            q = q.replace(token, '{time}')
        q = re.sub('\\b\\d{1,2}(st|nd|rd|th)?\\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\b', '{date}', q)
        q = re.sub('\\b20\\d{2}-\\d{2}-\\d{2}\\b', '{date}', q)
        return q.strip()

    @staticmethod
    def similarity(a: str, b: str) -> float:
        if a == b:
            return 1.0
        wa = set(a.split())
        wb = set(b.split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)

    def lookup(self, question: str) -> dict[str, Any] | None:
        pattern = self.normalize_pattern(question)
        best: CacheEntry | None = None
        best_score = 0.0
        for entry in self._entries.values():
            score = self.similarity(pattern, entry.pattern)
            if score >= self.similarity_threshold and score > best_score:
                (best, best_score) = (entry, score)
        if best:
            self._entries.move_to_end(best.pattern)
            out = dict(best.payload)
            out['_cache_similarity'] = round(best_score, 3)
            return out
        return None

    def store(self, question: str, payload: dict[str, Any]) -> None:
        pattern = self.normalize_pattern(question)
        self._entries[pattern] = CacheEntry(pattern=pattern, payload=dict(payload))
        self._entries.move_to_end(pattern)
        while len(self._entries) > self.max_size:
            self._entries.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        return {'size': len(self._entries), 'max_size': self.max_size}