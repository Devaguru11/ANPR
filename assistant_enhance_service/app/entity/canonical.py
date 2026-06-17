from __future__ import annotations
import re
from typing import Any
from app.entity.cache import KNOWN_CAMERA_NAMES
_CAMERA_ID_RE = re.compile('^AEYE_\\d+$', re.I)
VIOLATION_LABELS = {'NO_HELMET': 'no-helmet', 'WRONG_ROUTE': 'wrong-route', 'WRONG_PARKING': 'wrong-parking', 'TRIPLE_RIDING': 'triple-riding'}

def is_camera_id(value: Any) -> bool:
    if value is None:
        return False
    return bool(_CAMERA_ID_RE.match(str(value).strip()))

def display_for_camera(camera_id: Any, camera_names: dict[str, str] | None=None) -> str:
    cid = str(camera_id).strip()
    if not cid:
        return ''
    names = camera_names or KNOWN_CAMERA_NAMES
    mapped = names.get(cid)
    if mapped and (not is_camera_id(mapped)):
        return mapped
    return cid if not is_camera_id(cid) else cid

def _first_human_name(*candidates: Any) -> str | None:
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text and (not is_camera_id(text)):
            return text
    return None

def normalize_entity_scope(scope: dict[str, Any] | None, *, camera_names: dict[str, str] | None=None) -> dict[str, Any]:
    if not scope:
        return {}
    names = camera_names or KNOWN_CAMERA_NAMES
    out = dict(scope)
    cam_id = out.get('camera_id')
    human = _first_human_name(out.get('display_name'), out.get('display'), out.get('location'))
    if cam_id:
        cid = str(cam_id).strip()
        if not human:
            human = display_for_camera(cid, names)
        if is_camera_id(human):
            human = display_for_camera(cid, names)
        out['camera_id'] = cid
        out['display_name'] = human
        out['display'] = human
        if not human or is_camera_id(str(out.get('location', ''))):
            out['location'] = human
        elif is_camera_id(str(out.get('location', ''))):
            out['location'] = human
    elif out.get('location'):
        loc = str(out['location']).strip()
        if is_camera_id(loc):
            cid = loc
            human = display_for_camera(cid, names)
            out['camera_id'] = cid
            out['location'] = human
            out['display'] = human
            out['display_name'] = human
        else:
            out['display_name'] = loc
            out.setdefault('display', loc)
            if not out.get('camera_id'):
                for (cid, name) in names.items():
                    if name.lower() == loc.lower():
                        out['camera_id'] = cid
                        break
    if out.get('display_name') and is_camera_id(str(out['display_name'])):
        cid = str(out.get('camera_id') or out['display_name'])
        out['display_name'] = display_for_camera(cid, names)
        out['display'] = out['display_name']
        out['location'] = out['display_name']
        out['camera_id'] = cid
    return out

def merge_entity_scope(current: dict[str, Any], incoming: dict[str, Any], *, camera_names: dict[str, str] | None=None) -> dict[str, Any]:
    merged = dict(current or {})
    for (key, val) in (incoming or {}).items():
        if val is None:
            continue
        if key in ('location', 'display', 'display_name') and is_camera_id(val):
            if key == 'camera_id' or not merged.get('camera_id'):
                merged['camera_id'] = str(val)
            continue
        if key == 'camera_id':
            merged['camera_id'] = str(val)
            human = _first_human_name(incoming.get('display_name'), incoming.get('display'), incoming.get('location'))
            if human:
                merged['display_name'] = human
                merged['display'] = human
                merged['location'] = human
            continue
        merged[key] = val
    return normalize_entity_scope(merged, camera_names=camera_names)

def user_facing_label(value: Any, plan: Any | None=None, *, scope: dict[str, Any] | None=None, camera_names: dict[str, str] | None=None, allow_internal: bool=False) -> str:
    if value is None or value == '':
        return 'Unknown'
    text = str(value).strip()
    if allow_internal:
        return text
    names = camera_names or KNOWN_CAMERA_NAMES
    entity_scope = normalize_entity_scope(scope or (getattr(plan, 'entity_scope', None) if plan is not None else None) or {}, camera_names=names)
    if entity_scope.get('camera_id') and text == str(entity_scope['camera_id']):
        human = _first_human_name(entity_scope.get('display_name'), entity_scope.get('display'), entity_scope.get('location'))
        if human:
            return human
    if is_camera_id(text):
        mapped = display_for_camera(text, names)
        if mapped != text:
            return mapped
    if text in VIOLATION_LABELS:
        return VIOLATION_LABELS[text]
    if text.isupper() and '_' in text:
        return text
    return text.replace('_', ' ').title() if '_' in text else text

def location_display(scope: dict[str, Any] | None, *, plan: Any | None=None, camera_names: dict[str, str] | None=None, allow_internal: bool=False) -> str:
    entity_scope = normalize_entity_scope(scope or (getattr(plan, 'entity_scope', None) if plan is not None else None) or {}, camera_names=camera_names)
    human = _first_human_name(entity_scope.get('display_name'), entity_scope.get('display'), entity_scope.get('location'))
    if human:
        return human
    if allow_internal and entity_scope.get('camera_id'):
        return str(entity_scope['camera_id'])
    return ''

def debug_entity_fields(scope: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_entity_scope(scope)
    display = _first_human_name(normalized.get('display_name'), normalized.get('display'), normalized.get('location'))
    return {'display_entity': display, 'canonical_entity': display, 'internal_identifier': normalized.get('camera_id'), 'entity_scope': normalized}
__all__ = ['KNOWN_CAMERA_NAMES', 'debug_entity_fields', 'display_for_camera', 'is_camera_id', 'location_display', 'merge_entity_scope', 'normalize_entity_scope', 'user_facing_label']