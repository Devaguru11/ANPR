from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any
from rapidfuzz import fuzz
from app.db.pool import Database
KNOWN_CAMERA_NAMES: dict[str, str] = {'AEYE_1': 'Highway', 'AEYE_2': 'Luvers', 'AEYE_3': 'Market', 'AEYE_4': 'Baliwag', 'AEYE_5': 'Chowking', 'AEYE_6': 'Bridge'}

@dataclass
class EntityCache:
    camera_ids: list[str] = field(default_factory=list)
    camera_names: dict[str, str] = field(default_factory=dict)
    violation_types: list[str] = field(default_factory=list)
    vehicle_types: list[str] = field(default_factory=list)
    vehicle_categories: list[str] = field(default_factory=list)
    sites: list[str] = field(default_factory=list)
    last_refresh: float = 0.0

class EntityDiscovery:

    def __init__(self, db: Database, refresh_seconds: int=300) -> None:
        self.db = db
        self.refresh_seconds = refresh_seconds
        self.cache = EntityCache()
        self.refresh()

    def maybe_refresh(self) -> None:
        if time.time() - self.cache.last_refresh > self.refresh_seconds:
            self.refresh()

    def refresh(self) -> None:
        try:
            cams = [self._clean(r[0]) for r in self.db.query_all('SELECT DISTINCT camera_id FROM vehicle_events WHERE camera_id IS NOT NULL LIMIT 500') if r[0]]
        except Exception:
            cams = []
        ids = list(dict.fromkeys(cams))
        names = {c: c for c in ids}
        names.update(KNOWN_CAMERA_NAMES)
        names.update(self._discover_camera_labels())

        def distinct(sql: str, fallback: list[str]) -> list[str]:
            try:
                rows = self.db.query_all(sql)
                return [self._clean(r[0]) for r in rows if r[0]]
            except Exception:
                return fallback
        self.cache = EntityCache(camera_ids=ids, camera_names=names, violation_types=distinct('SELECT DISTINCT violation_type FROM traffic_violations WHERE violation_type IS NOT NULL LIMIT 100', ['WRONG_ROUTE', 'NO_HELMET', 'TRIPLE_RIDING', 'WRONG_PARKING']), vehicle_types=distinct('SELECT DISTINCT vehicle_type FROM vehicle_events WHERE vehicle_type IS NOT NULL LIMIT 100', []), vehicle_categories=distinct('SELECT DISTINCT vehicle_category FROM vehicle_events WHERE vehicle_category IS NOT NULL LIMIT 100', []), sites=list(set(names.values())), last_refresh=time.time())

    def _discover_camera_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for sql in ('SELECT camera_id, name FROM cameras WHERE camera_id IS NOT NULL LIMIT 500', 'SELECT unique_id, name FROM camera WHERE unique_id IS NOT NULL LIMIT 500'):
            try:
                for row in self.db.query_all(sql):
                    if len(row) >= 2 and row[0] and row[1]:
                        labels[self._clean(row[0])] = self._clean(row[1])
            except Exception:
                continue
        return labels

    @staticmethod
    def _clean(v: Any) -> str:
        return str(v).replace('\x00', '').strip() if v else ''

    def _location_phrase(self, text: str) -> str:
        import re
        m = re.search('\\b(?:at|for|in|from)\\s+([A-Za-z0-9][A-Za-z0-9 _-]{1,40})', text, re.I)
        if m:
            return m.group(1).strip()
        m = re.search('\\b(AEYE_\\d+)\\b', text, re.I)
        if m:
            return m.group(1)
        stripped = text.strip()
        if len(stripped.split()) <= 3:
            return stripped
        return text

    def resolve_location(self, text: str) -> tuple[dict | None, float, list]:
        self.maybe_refresh()
        phrase = self._location_phrase(text)
        log: list[dict[str, Any]] = []
        phrase_l = phrase.lower()
        for (cid, name) in self.cache.camera_names.items():
            if name.lower() == phrase_l:
                return ({'camera_id': cid, 'location': name, 'display': name}, 1.0, [{'type': 'camera', 'value': cid, 'display': name, 'confidence': 1.0, 'source': 'exact_name'}])
        scored: dict[str, tuple[float, str]] = {}
        for cid in self.cache.camera_ids:
            name = self.cache.camera_names.get(cid, cid)
            best_for_cam = 0.0
            for candidate in (cid, name, f'{name} ({cid})'):
                score = max(fuzz.ratio(phrase.lower(), candidate.lower()), fuzz.partial_ratio(phrase.lower(), candidate.lower())) / 100.0
                best_for_cam = max(best_for_cam, score)
            if best_for_cam >= 0.72:
                log.append({'type': 'camera', 'value': cid, 'display': name, 'confidence': best_for_cam})
                scored[cid] = (best_for_cam, name)
        if not scored:
            return (None, 0.0, sorted(log, key=lambda x: x['confidence'], reverse=True)[:5])
        top_score = max((v[0] for v in scored.values()))
        matched = [cid for (cid, (score, _)) in scored.items() if score >= max(0.72, top_score - 0.08)]
        matched.sort(key=lambda c: scored[c][0], reverse=True)
        names = [scored[c][1] for c in matched]
        best_score = top_score
        if len(matched) == 1:
            best = {'camera_id': matched[0], 'location': names[0], 'display': names[0]}
        else:
            best = {'camera_id': matched, 'location': phrase, 'display': ', '.join(names[:3])}
        return (best, best_score, sorted(log, key=lambda x: x['confidence'], reverse=True)[:5])

    def display_name(self, camera_id: Any) -> str:
        self.maybe_refresh()
        cid = self._clean(camera_id)
        if not cid:
            return ''
        return self.cache.camera_names.get(cid, cid)

    def enrich_camera_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.maybe_refresh()
        for row in rows:
            cid = row.get('camera_id')
            if cid is not None:
                row['site_name'] = self.display_name(cid)
        return rows

    def camera_name_map(self) -> dict[str, str]:
        self.maybe_refresh()
        return dict(self.cache.camera_names)

    def to_prompt(self) -> str:
        self.maybe_refresh()
        return f"Cameras: {', '.join((f'{self.display_name(c)}' for c in self.cache.camera_ids))}\nViolation types: {', '.join(self.cache.violation_types)}\nVehicle types: {', '.join(self.cache.vehicle_types)}"