from __future__ import annotations
from dataclasses import dataclass
from typing import Any
TIME_PHRASES: tuple[tuple[str, str], ...] = (('last 30 days', 'last_30_days'), ('last 7 days', 'last_7_days'), ('last 5 days', 'last_5_days'), ('last month', 'last_month'), ('this month', 'this_month'), ('this week', 'this_week'), ('yesterday', 'yesterday'), ('today', 'today'))

def infer_explicit_time_preset(question: str) -> dict[str, Any] | None:
    q = question.lower()
    for (phrase, preset) in TIME_PHRASES:
        if phrase in q:
            return {'preset': preset}
    return None

def question_has_explicit_time(question: str) -> bool:
    from app.planning.temporal_resolver import TemporalResolver
    return TemporalResolver._question_mentions_time(question) or infer_explicit_time_preset(question) is not None

@dataclass
class TemporalOverrideResult:
    time_range: dict[str, Any]
    previous_time_range: dict[str, Any]
    new_time_range: dict[str, Any]
    override_applied: bool
    source: str

    def to_debug_dict(self) -> dict[str, Any]:
        return {'previous_time_range': self.previous_time_range, 'new_time_range': self.new_time_range, 'override_applied': self.override_applied, 'source': self.source}

def ensure_dict_time_range(val: Any) -> dict[str, Any]:
    if not val:
        return {}
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, str):
        return {'preset': val}
    return {}

def apply_temporal_precedence(question: str, *, proposed: dict[str, Any] | None=None, reference: dict[str, Any] | None=None, active: dict[str, Any] | None=None, partial_date: dict[str, Any] | None=None, inherit: bool=False, default: dict[str, Any] | None=None) -> TemporalOverrideResult:
    proposed_tr = ensure_dict_time_range(proposed)
    reference_tr = ensure_dict_time_range(reference)
    active_tr = ensure_dict_time_range(active)
    partial_date_tr = ensure_dict_time_range(partial_date)
    default_tr = ensure_dict_time_range(default) or {'preset': 'last_30_days'}

    prev = active_tr or proposed_tr or default_tr

    if partial_date_tr:
        new_tr = dict(partial_date_tr)
        return TemporalOverrideResult(time_range=new_tr, previous_time_range=prev, new_time_range=new_tr, override_applied=new_tr != prev, source='partial_date')
    explicit = infer_explicit_time_preset(question)
    if explicit:
        return TemporalOverrideResult(time_range=explicit, previous_time_range=prev, new_time_range=explicit, override_applied=True, source='explicit')
    if question_has_explicit_time(question) and proposed_tr.get('preset'):
        return TemporalOverrideResult(time_range=proposed_tr, previous_time_range=prev, new_time_range=proposed_tr, override_applied=proposed_tr != prev, source='explicit')
    if reference_tr and (not question_has_explicit_time(question)):
        return TemporalOverrideResult(time_range=reference_tr, previous_time_range=prev, new_time_range=reference_tr, override_applied=reference_tr != prev, source='reference')
    if inherit and active_tr and (not question_has_explicit_time(question)):
        return TemporalOverrideResult(time_range=active_tr, previous_time_range=prev, new_time_range=active_tr, override_applied=False, source='inherit')
    if proposed_tr.get('preset'):
        return TemporalOverrideResult(time_range=proposed_tr, previous_time_range=prev, new_time_range=proposed_tr, override_applied=proposed_tr != prev, source='proposed')
    return TemporalOverrideResult(time_range=default_tr, previous_time_range=prev, new_time_range=default_tr, override_applied=default_tr != prev, source='default')
__all__ = ['TIME_PHRASES', 'TemporalOverrideResult', 'apply_temporal_precedence', 'infer_explicit_time_preset', 'question_has_explicit_time']