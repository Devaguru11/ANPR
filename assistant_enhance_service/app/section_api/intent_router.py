"""
section_api/intent_router.py
-----------------------------
Lightweight, rule-based intent classifier.
No LLM call needed — uses keyword scoring to determine which section
(and therefore which REST endpoint) to use for a given question.

Also extracts query parameters (date range, vehicle type, camera, plate).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Intent enum
# ---------------------------------------------------------------------------

class SectionIntent(StrEnum):
    VIOLATIONS_SUMMARY   = "violations_summary"    # how many violations?
    VIOLATIONS_BY_CAMERA = "violations_by_camera"  # rank locations / busiest cameras
    VIOLATIONS_LIST      = "violations_list"        # show violation records
    PLATE_READS          = "plate_reads"            # how many vehicles / detections?
    OVERVIEW             = "overview"               # general summary / situation
    RECIDIVISM           = "recidivism"             # repeat offenders
    CAMERA_STATUS        = "camera_status"          # cameras online / uptime
    UNKNOWN              = "unknown"                # fall back to LLM SQL path


# ---------------------------------------------------------------------------
# Keyword scoring tables
# Each entry: (regex_pattern, score)
# Score is additive; winner is highest total.
# ---------------------------------------------------------------------------

_INTENT_SIGNALS: dict[SectionIntent, list[tuple[str, float]]] = {
    SectionIntent.VIOLATIONS_SUMMARY: [
        (r"\bviolation", 2.5),
        (r"\bviolat\b|\bviolated\b|\bviolators\b", 1.5),
        (r"\boffence|\boffense|\binfraction", 1.5),
        (r"\bno.helmet|\bhelmet", 2.5),
        (r"\bno.seatbelt|\bseatbelt", 2.5),
        (r"\bspeeding|\bover.speed", 1.5),
        (r"\bwrong.way|\bwrong.lane|\bcounterflow", 1.5),
        (r"\bno.plate|\bmissing.plate", 1.5),
        (r"\bhow.many.violation", 3.0),
        (r"\bviolation.count|\bcount.violation", 2.5),
        (r"\btotal.violation|\bviolation.total", 2.5),
        (r"\bhow.many.were.violated|\bhow.many.did.we.get", 2.5),
        (r"\bbetween\b.*\bviolation|\bviolation.*\bbetween\b", 2.5),
        (r"\bbreakdown.of.violation|\bviolation.breakdown", 2.5),
        (r"\bviolation.by.type|\btype.of.violation", 2.0),
        (r"\brecorded.*violation|\bviolation.*recorded", 2.5),
        (r"\bget.this.month|\bget.on|\bget.between", 1.5),
    ],
    SectionIntent.VIOLATIONS_BY_CAMERA: [
        (r"\brank.location|\brank.camera|\brank.site", 5.0),
        (r"\bbusiest.camera|\bbusiest.location|\bbusiest.site", 5.0),
        (r"\btop.location|\btop.camera|\btop.site", 4.0),
        (r"\bviolation.*by.camera|\bviolation.*by.location|\bviolation.*by.site", 4.0),
        (r"\bwhich.camera.*violation|\bwhich.location.*violation|\bwhich.site.*violation", 3.5),
        (r"\bmost.violation.*camera|\bmost.violation.*location", 3.5),
        (r"\brank.*violation|\bviolation.*rank", 4.0),
        (r"\bviolation.count.*location|\blocation.*violation.count", 3.5),
        (r"\bbusiest.*violation|\bviolation.*busiest", 3.5),
    ],

    SectionIntent.VIOLATIONS_LIST: [
        (r"\bshow.violations|\blist.violations|\bsee.violations", 2.5),
        (r"\bviolation.record|\brecent.violation", 2.0),
        (r"\bshow.offence|\blist.offence", 2.0),
        (r"\bshow.me.violation|\bgive.me.violation", 2.0),
    ],
    SectionIntent.PLATE_READS: [
        (r"\bvehicle.detect|\bdetect.*vehicle", 2.0),
        (r"\bplate.read|\bread.*plate", 2.0),
        (r"\bhow.many.vehicle|\bhow.many.car|\bhow.many.motor|\bhow.many.bike|\bhow.many.truck|\bhow.many.bus", 2.5),
        (r"\bvehicle.count|\bcount.vehicle|\bcount.detect", 2.0),
        (r"\bdetect.*today|\btoday.*detect", 1.5),
        (r"\bdetect.*month|\bmonth.*detect", 1.5),
        (r"\bdetect.*june|\bdetect.*may|\bdetect.*april", 1.5),
        (r"\bmotorcycle|\bbike\b", 1.5),
        (r"\bprivate.vehicle|\bpublic.vehicle|\bcommercial.vehicle", 1.5),
        (r"\btotal.vehicle|\bvehicle.total", 2.0),
        (r"\bhow.many.were.detected", 2.5),
        (r"\bplate.analytics|\bplate.read.analytics", 2.5),
    ],
    SectionIntent.OVERVIEW: [
        (r"\bsummary\b", 2.0),
        (r"\boverview\b", 2.5),
        (r"\bsituation\b", 2.0),
        (r"\bgive.me.a.summary|\bgive.a.summary", 2.5),
        (r"\bgeneral.report|\bbriefing\b", 2.0),
        (r"\bhow.is.everything|\bhow.things.are", 1.5),
        (r"\bwhat.is.happening|\bwhat.happened", 1.5),
        (r"\btoday.situation|\bthis.month.situation", 2.0),
        (r"\bpeak.hour|\bpeak.time|\bpeak.period", 1.5),
        (r"\bbusiest.hour|\bbusiest.day", 1.5),
        (r"\bunique.plate|\bunique.vehicle", 1.5),
        (r"\btotal.read|\bplate.capture", 1.5),
    ],
    SectionIntent.RECIDIVISM: [
        (r"\brepeat.offender|\brepeat.violator|\brecidiv", 3.0),
        (r"\bmultiple.violation|\bmore.than.once", 2.0),
        (r"\bfrequent.violator|\bserial.offender", 2.5),
        (r"\bplate.*multiple.*violation|\bvehicle.*multiple.*violation", 2.0),
    ],
    SectionIntent.CAMERA_STATUS: [
        (r"\bcamera.online|\bonline.camera|\bcameras.live", 3.0),
        (r"\bcamera.uptime|\buptime\b", 3.0),
        (r"\bcamera.status|\bstatus.*camera", 2.5),
        (r"\bhow.many.camera|\bwhich.camera.*online|\bcamera.*offline", 2.0),
    ],
}


# ---------------------------------------------------------------------------
# Vehicle type mapping (question keywords → Node API vehicleType param)
# ---------------------------------------------------------------------------

_VEHICLE_TYPE_KEYWORDS: list[tuple[str, str]] = [
    (r"\bmotorcycle|\bbike\b|\bmotor\b", "BIKE"),
    (r"\bcar\b|\bprivate.vehicle|\bsedан", "CAR"),
    (r"\btruck\b|\bloading.vehicle|\bheavy.vehicle", "TRUCK"),
    (r"\bbus\b|\bpublic.utility|\bminibus", "BUS"),
    (r"\bminivan|\bminitruck|\bfv\b", "MINITRUCK"),
    (r"\bauto\b|\btricycle", "AUTO"),
]

_VIOLATION_TYPE_KEYWORDS: list[tuple[str, str]] = [
    (r"\bno.helmet|\bhelmet", "NO_HELMET"),
    (r"\bno.seatbelt|\bseatbelt", "NO_SEATBELT"),
    (r"\bspeeding|\bover.speed|\bexcess.speed", "SPEEDING"),
    (r"\bwrong.way|\bwrong.route|\bcounterflow|\bwrong.lane", "WRONG_ROUTE"),
    (r"\bno.plate|\bmissing.plate|\bno.number.plate", "NO_PLATE"),
    (r"\boverloading|\boverload", "OVERLOADING"),
    (r"\btriple.riding|\btriple.ride|\bthree.riding", "TRIPLE_RIDING"),
    (r"\bwrong.parking|\billegal.parking|\bparking", "WRONG_PARKING"),
]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent: SectionIntent
    confidence: float
    vehicle_type: str | None = None
    violation_type: str | None = None
    camera_id: str | None = None
    plate: str | None = None
    scores: dict[str, float] = field(default_factory=dict)


def classify_intent(
    question: str,
    time_range: dict[str, Any] | None = None,
) -> IntentResult:
    """
    Score the question against all intent keyword tables.
    Returns the winning intent + confidence (0.0 – 1.0).
    Confidence ≥ 0.75 triggers the section API path;
    lower scores fall back to the existing LLM SQL pipeline.
    """
    q = question.lower()

    scores: dict[SectionIntent, float] = {intent: 0.0 for intent in SectionIntent}

    for intent, signals in _INTENT_SIGNALS.items():
        for pattern, score in signals:
            if re.search(pattern, q):
                scores[intent] += score

    # Remove UNKNOWN from scoring competition
    ranked = sorted(
        [(intent, s) for intent, s in scores.items() if intent != SectionIntent.UNKNOWN],
        key=lambda x: x[1],
        reverse=True,
    )

    if not ranked or ranked[0][1] == 0.0:
        return IntentResult(
            intent=SectionIntent.UNKNOWN,
            confidence=0.0,
            scores={k.value: v for k, v in scores.items()},
        )

    winner, winner_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # Confidence: scaled by how dominant the winner is
    # - max raw score for a single intent is typically ~8–10
    # - any match with score > 0 gets a minimum confidence of 0.35
    MAX_EXPECTED = 7.0
    raw_conf = min(winner_score / MAX_EXPECTED, 1.0)
    separation = winner_score - runner_score
    separation_bonus = min(separation / 4.0, 0.2)
    confidence = min(raw_conf + separation_bonus, 1.0)
    # Ensure any non-zero winner always meets basic threshold
    if winner_score > 0 and confidence < 0.35:
        confidence = 0.35

    # Extract extra parameters
    vehicle_type = _extract_vehicle_type(q)
    violation_type = _extract_violation_type(q)
    plate = _extract_plate(q)

    return IntentResult(
        intent=winner,
        confidence=confidence,
        vehicle_type=vehicle_type,
        violation_type=violation_type,
        plate=plate,
        scores={k.value: v for k, v in scores.items()},
    )


# ---------------------------------------------------------------------------
# Parameter extractors
# ---------------------------------------------------------------------------

def _extract_vehicle_type(q: str) -> str | None:
    for pattern, vtype in _VEHICLE_TYPE_KEYWORDS:
        if re.search(pattern, q):
            return vtype
    return None


def _extract_violation_type(q: str) -> str | None:
    for pattern, vtype in _VIOLATION_TYPE_KEYWORDS:
        if re.search(pattern, q):
            return vtype
    return None


_PLATE_PATTERN = re.compile(r"\b([A-Z]{2,3}[\s\-]?\d{1,4}[A-Z]?)\b", re.IGNORECASE)


def _extract_plate(q: str) -> str | None:
    m = _PLATE_PATTERN.search(q)
    if m:
        return m.group(1).upper().replace(" ", "").replace("-", "")
    return None
