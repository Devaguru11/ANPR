from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class BusinessConceptDef:
    id: str
    description: str
    primary_tables: tuple[str, ...]
    metric: str
    related_columns: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
BUSINESS_CONCEPTS: dict[str, BusinessConceptDef] = {'plate_reads': BusinessConceptDef(id='plate_reads', description='Distinct plate identifications — unique ANPR reads where a plate number was recognized. Counts unique vehicle_num values, not every camera sighting row.', primary_tables=('vehicle_events',), metric='plate_reads', related_columns=('vehicle_num', 'camera_id', 'created_at'), examples=('plate reads', 'plates read', 'distinct plates', 'plates identified', 'plates seen today', 'count distinct plates'), negative_examples=('anpr detections', 'detection events', 'every capture', 'vehicles captured', 'unique vehicles', 'cars seen')), 'vehicle_detections': BusinessConceptDef(id='vehicle_detections', description='Raw ANPR detection events — every camera sighting row in vehicle_events, including repeat passes of the same plate. Use when the user means detections, captures, sightings, or camera triggers rather than unique plates.', primary_tables=('vehicle_events',), metric='detections', related_columns=('vehicle_num', 'camera_id', 'created_at'), examples=('anpr detections', 'detection events', 'detections today', 'camera captures', 'sightings', 'camera triggers', 'every detection'), negative_examples=('distinct plates', 'unique vehicles', 'plate reads', 'tickets issued', 'violations')), 'vehicles': BusinessConceptDef(id='vehicles', description='Distinct vehicles observed — unique plates seen in a period, emphasizing unique vehicle count rather than total detection rows or raw event volume.', primary_tables=('vehicle_events',), metric='vehicles', related_columns=('vehicle_num',), examples=('how many vehicles', 'vehicles captured', 'vehicles seen', 'cars seen', 'unique vehicles', 'distinct vehicles', 'unique cars'), negative_examples=('anpr detections', 'detection events', 'plate reads', 'every sighting', 'camera triggers')), 'violations': BusinessConceptDef(id='violations', description='Traffic violation events — offences detected in traffic_violations such as no-helmet, wrong route, triple riding. The violation occurred; issuance is separate.', primary_tables=('traffic_violations', 'vehicle_events'), metric='violations', related_columns=('violation_type', 'event_id'), examples=('violations', 'offences', 'infractions', 'no helmet violations', 'traffic violations', 'violation events'), negative_examples=('challans issued', 'tickets issued', 'penalties issued', 'plate reads', 'anpr detections')), 'challans': BusinessConceptDef(id='challans', description='Issued challans, tickets, or penalty notices — enforcement workflow output tracked in violation_ticket_flags and tickets, not raw violation detection.', primary_tables=('violation_ticket_flags', 'traffic_violations'), metric='challans', related_columns=('challan_id', 'flag', 'violation_id'), examples=('challans issued', 'tickets issued', 'penalties issued', 'how many challans', 'how many tickets', 'issued tickets'), negative_examples=('violations detected', 'offences detected', 'violation events', 'plate reads', 'anpr detections')), 'camera_activity': BusinessConceptDef(id='camera_activity', description='Camera or site activity volume — how busy a camera is, throughput, or which camera/location had the most activity.', primary_tables=('vehicle_events', 'cameras', 'camera'), metric='cameras', related_columns=('camera_id',), examples=('camera activity', 'most active camera', 'busiest camera', 'which camera had the most activity', 'busiest site', 'camera throughput'), negative_examples=('violations', 'challans', 'watchlist hits', 'distinct plates')), 'watchlist_hits': BusinessConceptDef(id='watchlist_hits', description='Watchlist rule matches — plates or vehicles that matched configured LPR watchlist criteria and require review or alerting.', primary_tables=('vehicle_events',), metric='watchlist_hits', related_columns=('vehicle_num', 'camera_id'), examples=('watchlist hits', 'watchlist matches', 'watchlist alerts', 'lpr watchlist'), negative_examples=('violations', 'challans', 'plate reads', 'detection volume'))}

def concept_names() -> list[str]:
    return list(BUSINESS_CONCEPTS.keys())

def default_concept() -> str:
    return 'violations'

def get_concept(concept_id: str) -> BusinessConceptDef:
    return BUSINESS_CONCEPTS.get(concept_id, BUSINESS_CONCEPTS[default_concept()])

def concept_to_metric(concept_id: str) -> str:
    return get_concept(concept_id).metric

def registry_prompt() -> str:
    lines = ['Canonical business concepts — return 2-3 ranked candidates:']
    for concept in BUSINESS_CONCEPTS.values():
        tables = ', '.join(concept.primary_tables)
        lines.append(f'- {concept.id}: {concept.description} [tables: {tables}]')
        if concept.examples:
            lines.append(f"  examples: {'; '.join(concept.examples[:4])}")
        if concept.negative_examples:
            lines.append(f"  not: {'; '.join(concept.negative_examples[:3])}")
    return '\n'.join(lines)