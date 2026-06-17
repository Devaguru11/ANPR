from __future__ import annotations
import re
from dataclasses import dataclass
from app.planning.plan import AnalyticalPlan
_LISTING_SCOPE_KINDS = frozenset({'all', 'single', 'sample', 'first_n', 'latest_n'})
_RECORD_LISTING_PHRASES = ('vehicle numbers', 'vehicle number', 'plate reads', 'plate numbers', 'show records', 'show details', 'those records', 'list them', 'ending with', 'ending in')

@dataclass(frozen=True)
class RetrievalScopeSpec:
    kind: str = 'default'
    count: int | None = None

    @classmethod
    def parse(cls, raw: str | None) -> RetrievalScopeSpec:
        if not raw or raw == 'default':
            return cls(kind='default')
        value = str(raw).strip().lower()
        if value == 'all':
            return cls(kind='all')
        if value == 'single':
            return cls(kind='single', count=1)
        if value == 'sample':
            return cls(kind='sample', count=5)
        for (pattern, kind) in (('^first_(\\d+)$', 'first_n'), ('^latest_(\\d+)$', 'latest_n'), ('^top_(\\d+)$', 'top_n'), ('^sample_(\\d+)$', 'sample')):
            m = re.match(pattern, value)
            if m:
                return cls(kind=kind, count=int(m.group(1)))
        return cls(kind='default')

    def to_label(self) -> str:
        if self.kind in ('default', 'all', 'single'):
            return self.kind
        if self.kind == 'sample':
            if self.count in (None, 5):
                return 'sample'
            return f'sample_{self.count}'
        if self.kind in ('first_n', 'latest_n', 'top_n') and self.count is not None:
            prefix = {'first_n': 'first', 'latest_n': 'latest', 'top_n': 'top'}[self.kind]
            return f'{prefix}_{self.count}'
        return 'default'

def apply_retrieval_scope(plan: AnalyticalPlan, raw_scope: str | None) -> None:
    spec = RetrievalScopeSpec.parse(raw_scope)
    if spec.kind == 'all':
        plan.limit = None
        if plan.query_mode == 'record_listing':
            plan.sort = {'field': 've.created_at', 'direction': 'ASC'}
        return
    if spec.kind == 'single':
        plan.limit = 1
        if plan.query_mode == 'record_listing':
            plan.sort = {'field': 've.created_at', 'direction': 'DESC'}
        elif plan.query_mode in ('top_n', 'ranking', 'grouped_analysis'):
            plan.sort = {'field': 'total', 'direction': 'DESC'}
        return
    if spec.kind == 'first_n':
        plan.limit = spec.count or 10
        if plan.query_mode == 'record_listing':
            plan.sort = {'field': 've.created_at', 'direction': 'ASC'}
        return
    if spec.kind == 'latest_n':
        plan.limit = spec.count or 10
        plan.sort = {'field': 've.created_at', 'direction': 'DESC'}
        return
    if spec.kind == 'top_n':
        plan.limit = spec.count or 1
        plan.sort = {'field': 'total', 'direction': 'DESC'}
        return
    if spec.kind == 'sample':
        plan.limit = spec.count or 5
        plan.sort = {'field': 've.created_at', 'direction': 'DESC'}
        return
    if plan.user_objective == 'record_detail':
        plan.limit = plan.limit if plan.limit is not None else 10
        plan.sort = plan.sort or {'field': 've.created_at', 'direction': 'DESC'}
    elif plan.user_objective == 'ranking':
        plan.limit = plan.limit if plan.limit is not None else 1
        plan.sort = plan.sort or {'field': 'total', 'direction': 'DESC'}
    elif plan.user_objective == 'trend':
        plan.limit = plan.limit if plan.limit is not None else 30

def sql_limit_clause(limit: int | None) -> str:
    return '' if limit is None else f' LIMIT {limit}'

def infer_listing_scope_from_question(question: str) -> str | None:
    q = question.lower()
    if re.search('\\b(?:give(?:\\s+me)?|show|list)\\s+(?:me\\s+)?all\\b', q) or re.search('\\ball\\s+(?:vehicle|plate|records?)\\b', q):
        return 'all'
    match = re.search('\\bfirst\\s+(\\d+)\\b', q)
    if match:
        return f'first_{match.group(1)}'
    match = re.search('\\blatest\\s+(\\d+)\\b', q)
    if match:
        return f'latest_{match.group(1)}'
    if re.search('\\bshow\\s+one\\s+example\\b', q):
        return 'single'
    return None

def signals_record_listing_intent(question: str) -> bool:
    from app.planning.objective_evidence import has_record_detail_evidence
    return has_record_detail_evidence(question)