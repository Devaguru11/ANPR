from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from app.analytics.composer import compose
from app.analytics.dataset import classify_dataset
from app.analytics.insights import InsightResult, analyze
from app.planning.modes import dataset_type_for_mode
from app.planning.plan import AnalyticalPlan

@dataclass
class AnalyticsResult:
    summary: str = ''
    composed_answer: str = ''
    dataset_type: str = ''
    metrics: dict[str, Any] = field(default_factory=dict)
    trends: list[dict] = field(default_factory=list)
    comparisons: list[dict] = field(default_factory=list)
    rankings: list[dict] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    data_quality: dict[str, Any] = field(default_factory=dict)
    grounded: bool = True

class AnalyticsEngine:

    def run(self, plan: AnalyticalPlan | dict, columns: list[str], rows: list[tuple], camera_names: dict[str, str] | None=None) -> AnalyticsResult:
        analytical = plan if isinstance(plan, AnalyticalPlan) else AnalyticalPlan.from_dict(plan)
        expected_type = dataset_type_for_mode(analytical.query_mode)
        dataset_type = classify_dataset(analytical.query_mode, columns, rows)
        if dataset_type == 'empty':
            dataset_type = expected_type if rows else 'empty'
        insight: InsightResult = analyze(dataset_type, columns, rows, camera_names, plan=analytical)
        composed = compose(analytical, insight, insight.data_quality)
        dq = {}
        if insight.data_quality:
            dq = {'issues': insight.data_quality.issues, 'missing_plates': insight.data_quality.missing_plates, 'total_rows': insight.data_quality.total_rows}
        return AnalyticsResult(summary=insight.summary, composed_answer=composed, dataset_type=dataset_type, metrics=insight.metrics, trends=insight.trends, comparisons=insight.comparisons, rankings=insight.rankings, records=insight.records, insights=insight.insights, data_quality=dq, grounded=True)