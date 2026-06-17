from __future__ import annotations
from app.analytics.context import location_descriptor
from app.analytics.insights import InsightResult
from app.analytics.narration import narrate
from app.analytics.quality import DataQualityReport
from app.planning.plan import AnalyticalPlan

def compose(plan: AnalyticalPlan, insight: InsightResult, quality: DataQualityReport | None=None) -> str:
    if not insight.metrics and (not insight.records) and (not insight.rankings) and (not insight.trends):
        if insight.summary and 'No data' in insight.summary:
            return _maybe_prefix(plan, insight.summary)
    text = narrate(plan, insight)
    if quality and quality.has_issues():
        text = f'{text}\n\n{quality.note()}'
    return _maybe_prefix(plan, text)

def _maybe_prefix(plan: AnalyticalPlan, text: str) -> str:
    loc = location_descriptor(plan)
    if loc and loc.lower() not in text.lower():
        return f'At {loc}: {text}'
    return text