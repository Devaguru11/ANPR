from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class DataQualityReport:
    issues: list[str] = field(default_factory=list)
    missing_plates: int = 0
    missing_vehicle_type: int = 0
    missing_violation_type: int = 0
    total_rows: int = 0

    def has_issues(self) -> bool:
        return bool(self.issues)

    def note(self) -> str | None:
        if not self.issues:
            return None
        return 'Data quality: ' + '; '.join(self.issues) + '.'

def assess(columns: list[str], rows: list[dict[str, Any]]) -> DataQualityReport:
    report = DataQualityReport(total_rows=len(rows))
    if not rows:
        return report
    for row in rows:
        plate = row.get('vehicle_num')
        if plate is not None and (not str(plate).strip()):
            report.missing_plates += 1
        if 'vehicle_type' in row and (not row.get('vehicle_type')):
            report.missing_vehicle_type += 1
        if 'violation_type' in row and (not row.get('violation_type')):
            report.missing_violation_type += 1
    if report.missing_plates:
        report.issues.append(f'{report.missing_plates} of {report.total_rows} records have missing plate numbers')
    if report.missing_vehicle_type:
        report.issues.append(f'{report.missing_vehicle_type} records missing vehicle type')
    if report.missing_violation_type:
        report.issues.append(f'{report.missing_violation_type} records missing violation type')
    return report