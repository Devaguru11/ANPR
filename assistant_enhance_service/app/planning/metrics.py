from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MetricDef:
    name: str
    description: str
    base_table: str
    requires_violation_join: bool
    count_expression: str
    record_columns: tuple[str, ...]
METRICS: dict[str, MetricDef] = {'violations': MetricDef(name='violations', description='Traffic violation events', base_table='traffic_violations', requires_violation_join=True, count_expression='COUNT(*)', record_columns=('vehicle_num', 'camera_id', 'created_at', 'violation_type')), 'plate_reads': MetricDef(name='plate_reads', description='Vehicle detection / plate read events', base_table='vehicle_events', requires_violation_join=False, count_expression='COUNT(DISTINCT vehicle_num)', record_columns=('vehicle_num', 'camera_id', 'created_at')), 'detections': MetricDef(name='detections', description='Raw vehicle detection events', base_table='vehicle_events', requires_violation_join=False, count_expression='COUNT(*)', record_columns=('vehicle_num', 'camera_id', 'created_at')), 'vehicles': MetricDef(name='vehicles', description='Distinct vehicles observed', base_table='vehicle_events', requires_violation_join=False, count_expression='COUNT(DISTINCT vehicle_num)', record_columns=('vehicle_num', 'camera_id', 'created_at')), 'cameras': MetricDef(name='cameras', description='Camera-level activity', base_table='vehicle_events', requires_violation_join=False, count_expression='COUNT(*)', record_columns=('camera_id',)), 'challans': MetricDef(name='challans', description='Issued challans and tickets from violation workflow', base_table='violation_ticket_flags', requires_violation_join=True, count_expression='COUNT(DISTINCT vtf.challan_id)', record_columns=('violation_id', 'challan_id', 'created_at')), 'watchlist_hits': MetricDef(name='watchlist_hits', description='Watchlist rule matches on vehicle detections', base_table='vehicle_events', requires_violation_join=False, count_expression='COUNT(*)', record_columns=('vehicle_num', 'camera_id', 'created_at')), 'unique_violating_vehicles': MetricDef(name='unique_violating_vehicles', description='Distinct vehicles that committed violations', base_table='traffic_violations', requires_violation_join=True, count_expression='COUNT(DISTINCT ve.vehicle_num)', record_columns=('vehicle_num', 'camera_id', 'created_at', 'violation_type'))}

def metric_names() -> list[str]:
    return list(METRICS.keys())

def get_metric(name: str) -> MetricDef:
    return METRICS.get(name, METRICS['violations'])

def registry_prompt() -> str:
    return '\n'.join((f'- {m.name}: {m.description}' for m in METRICS.values()))