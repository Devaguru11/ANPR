from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from app.llm.vllm_client import VLLMClient
from app.planning.conversation_state import load_previous_plan
from app.planning.dimensions import TIME_PRESETS
MONTH_ALIASES: dict[str, int] = {'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3, 'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9, 'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12}
RESOLVER_SYSTEM = 'You are a temporal context resolver for a traffic analytics assistant.\n\nYour ONLY job: resolve the TIME SCOPE for this question using conversation context.\nDo NOT choose objectives, dimensions, metrics, or filters.\n\nRules:\n- Relative dates inherit the active conversation timeframe and reporting period.\n- If discussion is in June 2026, "2nd June" → 2026-06-02 (not an arbitrary past year).\n- If no explicit date change, inherit the prior plan time_range.\n- Presets: today, yesterday, this_week, this_month, last_month, last_7_days, last_5_days, last_30_days\n- Specific dates use: {"preset":"specific_date", "start":"YYYY-MM-DD", "end":"YYYY-MM-DD"}\n  For a single day, start and end are the same date.\n\nReturn JSON only.'

@dataclass
class TemporalResolution:
    time_range: dict[str, Any] = field(default_factory=lambda : {'preset': 'last_30_days'})
    confidence: float = 0.5
    inherited: bool = False
    reasoning: str = ''
    resolution_tier: str = 'primary'
    previous_time_range: dict[str, Any] | None = None
    new_time_range: dict[str, Any] | None = None
    override_applied: bool = False
    override_source: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class TemporalResolver:
    HIGH = 0.75
    MEDIUM = 0.5

    def __init__(self, llm: VLLMClient) -> None:
        self.llm = llm

    async def resolve(self, question: str, conversation_context: str, previous_mem_plan: dict[str, Any] | None, mem_time_range: dict[str, Any] | None=None) -> TemporalResolution:
        previous = load_previous_plan(previous_mem_plan)
        active_tr = (previous.time_range if previous else None) or mem_time_range or {'preset': 'last_30_days'}
        reporting = self._reporting_period(active_tr, conversation_context)
        partial = self._resolve_partial_date(question, reporting)
        if partial:
            return TemporalResolution(time_range=partial, confidence=0.9, inherited=True, reasoning='deterministic partial date from conversation reporting period')
        primary = await self._pass(question, conversation_context, active_tr, reporting, tier='primary')
        inherit = previous is not None
        if primary.confidence >= self.HIGH:
            return self._normalize(primary, question, reporting, active_tr=active_tr, inherit=inherit)
        if primary.confidence >= self.MEDIUM:
            secondary = await self._pass(question, conversation_context, active_tr, reporting, tier='secondary', prior=primary)
            best = secondary if secondary.confidence >= primary.confidence else primary
            if best.confidence >= self.MEDIUM:
                return self._normalize(best, question, reporting, active_tr=active_tr, inherit=inherit)
            primary = best
        if not self._question_mentions_time(question):
            return TemporalResolution(time_range=dict(active_tr), confidence=0.6, inherited=True, reasoning='low confidence; inherited active conversation time_range')
        return self._normalize(primary, question, reporting, active_tr=active_tr, inherit=inherit)

    async def _pass(self, question: str, context: str, active_tr: dict[str, Any], reporting: dict[str, Any], *, tier: str, prior: TemporalResolution | None=None) -> TemporalResolution:
        extra = ''
        if tier == 'secondary' and prior:
            extra = f'\nPrior attempt: {json.dumps(prior.time_range)} (confidence {prior.confidence:.2f})\nRe-resolve using conversation reporting period.\n'
        user = f"""Question: {question}\n\nToday's date (UTC): {datetime.utcnow():%Y-%m-%d}\nActive conversation time_range: {json.dumps(active_tr)}\nReporting period context: {json.dumps(reporting)}\n\nConversation:\n{context[:2000]}\n{extra}\nReturn JSON: {{"time_range":{{...}}, "confidence":0.0-1.0, "inherited":true|false, "reasoning":"..."}}"""
        try:
            data = await self.llm.chat_json(RESOLVER_SYSTEM, user)
            return self._parse(data, tier=tier)
        except Exception:
            return TemporalResolution(time_range=dict(active_tr), confidence=0.4, inherited=True, reasoning='fallback: inherited active time_range', resolution_tier=tier)

    def _parse(self, data: dict[str, Any], *, tier: str) -> TemporalResolution:
        tr_raw = data.get('time_range')
        if isinstance(tr_raw, dict):
            tr = dict(tr_raw)
        elif isinstance(tr_raw, str):
            tr = {'preset': tr_raw}
        else:
            tr = {'preset': 'last_30_days'}
        conf = float(data.get('confidence', 0.7))
        conf = max(0.0, min(1.0, conf))
        return TemporalResolution(time_range=tr, confidence=conf, inherited=bool(data.get('inherited', False)), reasoning=str(data.get('reasoning', '')), resolution_tier=tier)

    def _normalize(self, resolution: TemporalResolution, question: str, reporting: dict[str, Any], *, active_tr: dict[str, Any] | None=None, inherit: bool=False) -> TemporalResolution:
        if inherit and active_tr and (not self._question_mentions_time(question)):
            resolution.time_range = dict(active_tr)
            resolution.inherited = True
            resolution.reasoning += '; inherited active time_range (normalize)'
            return resolution
        tr = dict(resolution.time_range)
        preset = tr.get('preset')
        if preset == 'specific_date' or tr.get('start') or tr.get('date'):
            start = tr.get('start') or tr.get('date')
            if start:
                day = self._apply_reporting_year(str(start)[:10], question, reporting)
                tr = {'preset': 'specific_date', 'start': day, 'end': self._apply_reporting_year(str(tr.get('end', day))[:10], question, reporting)}
                resolution.time_range = tr
                return resolution
        if preset in TIME_PRESETS:
            resolution.time_range = {'preset': preset}
            return resolution
        if preset not in (None, 'specific_date') and preset not in TIME_PRESETS:
            resolution.time_range = {'preset': 'last_30_days'}
            resolution.reasoning += '; normalized unknown preset'
        return resolution

    @staticmethod
    def _resolve_partial_date(question: str, reporting: dict[str, Any]) -> dict[str, Any] | None:
        q = question.lower()
        found_dates = []

        # Pattern 1: Day Month (e.g., "14 June", "14th June")
        for m in re.finditer('\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\\b', q):
            day = int(m.group(1))
            month_key = m.group(2)
            found_dates.append((m.start(), day, month_key))

        # Pattern 2: Month Day (e.g., "June 14th", "June 14")
        for m in re.finditer('\\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\\s+(\\d{1,2})(?:st|nd|rd|th)?\\b', q):
            month_key = m.group(1)
            day = int(m.group(2))
            found_dates.append((m.start(), day, month_key))

        if not found_dates:
            return None

        found_dates.sort(key=lambda x: x[0])

        def parse_single_match(day: int, month_key: str) -> str | None:
            month = MONTH_ALIASES.get(month_key) or MONTH_ALIASES.get(month_key[:3])
            if not month:
                return None
            year = reporting.get('conversation_year')
            if year is None:
                ref = reporting.get('reference_date')
                year = int(str(ref)[:4]) if ref else datetime.utcnow().year
            try:
                resolved = datetime(int(year), month, day)
                return resolved.strftime('%Y-%m-%d')
            except ValueError:
                return None

        if len(found_dates) >= 2:
            start_str = parse_single_match(found_dates[0][1], found_dates[0][2])
            end_str = parse_single_match(found_dates[1][1], found_dates[1][2])
            if start_str and end_str:
                return {'preset': 'specific_date', 'start': start_str, 'end': end_str}

        day_str = parse_single_match(found_dates[0][1], found_dates[0][2])
        if not day_str:
            return None
        return {'preset': 'specific_date', 'start': day_str, 'end': day_str}

    @staticmethod
    def _apply_reporting_year(date_str: str, question: str, reporting: dict[str, Any]) -> str:
        if len(date_str) < 10:
            return date_str
        year_in_question = re.search('\\b(20\\d{2})\\b', question)
        if year_in_question:
            return date_str
        context_year = reporting.get('conversation_year')
        if context_year is None:
            return date_str
        try:
            parts = date_str.split('-')
            (month, day) = (int(parts[1]), int(parts[2]))
            corrected = datetime(int(context_year), month, day)
            return corrected.strftime('%Y-%m-%d')
        except (ValueError, IndexError):
            return date_str

    @staticmethod
    def _question_mentions_time(question: str) -> bool:
        q = question.lower()
        if any((p in q for p in TIME_PRESETS)):
            return True
        if re.search('\\b\\d{1,2}(st|nd|rd|th)?\\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', q):
            return True
        if re.search('\\b(january|february|march|april|may|june|july|august|september|october|november|december)\\b', q):
            return True
        return any((w in q for w in ('today', 'yesterday', 'this week', 'this month', 'last month', 'last 7 days', 'last 30 days', 'last 5 days')))

    @staticmethod
    def _reporting_period(active_tr: dict[str, Any], context: str) -> dict[str, Any]:
        now = datetime.utcnow()
        period: dict[str, Any] = {'reference_date': now.strftime('%Y-%m-%d'), 'active_preset': active_tr.get('preset')}
        year_match = re.search('\\b(20\\d{2})\\b', context)
        if year_match:
            period['conversation_year'] = int(year_match.group(1))
        month_match = re.search('\\b(january|february|march|april|may|june|july|august|september|october|november|december)\\s+(20\\d{2})\\b', context.lower())
        if month_match:
            period['conversation_month'] = month_match.group(1)
            period['conversation_year'] = int(month_match.group(2))
        if active_tr.get('preset') == 'specific_date':
            start = active_tr.get('start') or active_tr.get('date')
            if start:
                period['active_date'] = str(start)[:10]
                period['conversation_year'] = int(str(start)[:4])
        return period