"""
section_api/narrator.py
-----------------------
Converts structured JSON from Node REST API responses into
plain-English answers for the Data Assistant chat.

All functions are pure (no I/O, no LLM) — they take the JSON data
and return a human-readable string.
"""
from __future__ import annotations

from typing import Any

from app.section_api.intent_router import IntentResult, SectionIntent

# ---------------------------------------------------------------------------
# Violation type → human label
# ---------------------------------------------------------------------------

_VIOLATION_LABELS: dict[str, str] = {
    "NO_HELMET": "No Helmet",
    "NO_SEATBELT": "No Seatbelt",
    "SPEEDING": "Speeding",
    "WRONG_WAY": "Wrong Way / Counterflow",
    "NO_PLATE": "Missing Plate",
    "OVERLOADING": "Overloading",
}

# Vehicle type → label
_VEHICLE_LABELS: dict[str, str] = {
    "CAR": "cars",
    "TRUCK": "trucks",
    "BIKE": "motorcycles",
    "MINITRUCK": "mini-trucks",
    "BUS": "buses",
    "AUTO": "auto/tricycles",
}


def _fmt_date_range(from_date: str, to_date: str) -> str:
    if from_date == to_date:
        return f"on {_fmt_date(from_date)}"
    return f"from {_fmt_date(from_date)} to {_fmt_date(to_date)}"


def _fmt_date(d: str) -> str:
    """'2026-06-14' → '14 Jun 2026'"""
    try:
        from datetime import datetime
        return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        return d


def _n(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Narrators — one per intent
# ---------------------------------------------------------------------------

def narrate(
    intent: SectionIntent,
    data: dict[str, Any],
    ir: IntentResult,
    from_date: str,
    to_date: str,
) -> str:
    """Route to the correct narrator based on intent."""
    try:
        if intent == SectionIntent.VIOLATIONS_SUMMARY:
            return _narrate_violations_summary(data, ir, from_date, to_date)
        if intent == SectionIntent.VIOLATIONS_BY_CAMERA:
            return _narrate_violations_by_camera(data, ir, from_date, to_date)
        if intent == SectionIntent.VIOLATIONS_LIST:
            return _narrate_violations_list(data, ir, from_date, to_date)
        if intent == SectionIntent.PLATE_READS:
            return _narrate_plate_reads(data, ir, from_date, to_date)
        if intent == SectionIntent.OVERVIEW:
            return _narrate_overview(data, ir, from_date, to_date)
        if intent == SectionIntent.RECIDIVISM:
            return _narrate_recidivism(data, from_date, to_date)
        if intent == SectionIntent.CAMERA_STATUS:
            return _narrate_camera_status(data)
    except Exception:
        pass
    return "I was able to fetch the data but could not summarise it. Please try rephrasing."


# ---------------------------------------------------------------------------

def _narrate_violations_summary(
    data: dict[str, Any],
    ir: IntentResult,
    from_date: str,
    to_date: str,
) -> str:
    total = _n(data.get("total"))
    when = _fmt_date_range(from_date, to_date)
    by_type: dict[str, int] = {k: _n(v) for k, v in (data.get("byType") or {}).items()}

    if total == 0:
        return f"There were no violations recorded {when}."

    # If a specific type was requested
    if ir.violation_type and ir.violation_type in by_type:
        label = _VIOLATION_LABELS.get(ir.violation_type, ir.violation_type)
        count = by_type[ir.violation_type]
        return f"There were **{count:,}** *{label}* violations {when}."

    lines = [f"There were **{total:,}** total violations {when}."]

    # Breakdown by type (non-zero only)
    active = [(k, v) for k, v in by_type.items() if v > 0]
    if active:
        active.sort(key=lambda x: x[1], reverse=True)
        breakdown = ", ".join(
            f"{_VIOLATION_LABELS.get(k, k)}: {v:,}" for k, v in active
        )
        lines.append(f"Breakdown — {breakdown}.")

    return "\n".join(lines)


def _narrate_violations_by_camera(
    data: dict[str, Any],
    ir: IntentResult,
    from_date: str,
    to_date: str,
) -> str:
    when = _fmt_date_range(from_date, to_date)
    by_camera: list[dict] = data.get("trafficViolationsByCamera") or []

    if not by_camera:
        return f"No violation data by location was found {when}."

    total_viol = _n(data.get("trafficViolationCount"))
    lines = []
    if total_viol:
        lines.append(f"There were **{total_viol:,}** total violations {when}.")
    lines.append("\n**Locations ranked by violation count:**")

    for i, cam in enumerate(by_camera[:10], 1):
        name = cam.get("name") or cam.get("camera_id") or "Unknown"
        count = _n(cam.get("total"))
        lines.append(f"{i}. {name} — {count:,} violations")

    return "\n".join(lines)


def _narrate_violations_list(
    data: dict[str, Any],
    ir: IntentResult,
    from_date: str,
    to_date: str,
) -> str:
    when = _fmt_date_range(from_date, to_date)
    total = _n(data.get("total"))
    rows: list[dict] = data.get("rows") or []

    if total == 0 or not rows:
        return f"No violation records found {when}."

    lines = [f"Found **{total:,}** violation records {when}."]
    lines.append("")
    for row in rows[:10]:
        plate = row.get("plate") or "(no plate)"
        cam = row.get("cameraName") or row.get("cameraId") or "?"
        vtype = _VIOLATION_LABELS.get(row.get("violationType", ""), row.get("violationType", ""))
        det = row.get("detectedAt") or ""
        lines.append(f"- **{plate}** at {cam} — {vtype} — {det}")

    if total > 10:
        lines.append(f"- … and {total - 10:,} more")

    return "\n".join(lines)


def _narrate_plate_reads(
    data: dict[str, Any],
    ir: IntentResult,
    from_date: str,
    to_date: str,
) -> str:
    when = _fmt_date_range(from_date, to_date)
    total = _n(data.get("total"))
    by_type: dict[str, int] = {k: _n(v) for k, v in (data.get("byType") or {}).items()}

    if total == 0:
        return f"No vehicle detections were recorded {when}."

    # Specific vehicle type requested
    if ir.vehicle_type and ir.vehicle_type in by_type:
        label = _VEHICLE_LABELS.get(ir.vehicle_type, ir.vehicle_type.lower())
        count = by_type[ir.vehicle_type]
        return f"There were **{count:,}** {label} detected {when}."

    lines = [f"There were **{total:,}** total vehicle detections {when}."]

    # Show type breakdown
    active = [(k, v) for k, v in by_type.items() if v > 0]
    if active:
        active.sort(key=lambda x: x[1], reverse=True)
        breakdown_parts = [
            f"{_VEHICLE_LABELS.get(k, k.lower())}: {v:,}" for k, v in active
        ]
        lines.append("By type — " + ", ".join(breakdown_parts) + ".")

    # Top camera
    cameras: list[dict] = data.get("cameras") or []
    if cameras:
        top = cameras[0]
        name = top.get("name") or top.get("camera_id") or "?"
        cnt = _n(top.get("total"))
        lines.append(f"Busiest camera: **{name}** with {cnt:,} detections.")

    return "\n".join(lines)


def _narrate_overview(
    data: dict[str, Any],
    ir: IntentResult,
    from_date: str,
    to_date: str,
) -> str:
    when = _fmt_date_range(from_date, to_date)
    total_reads = _n(data.get("totalReads"))
    unique_plates = _n(data.get("uniquePlates"))
    total_violations = _n(data.get("trafficViolationCount"))
    cameras_online = _n(data.get("camerasOnline"))
    cameras_deployed = _n(data.get("camerasDeployed"))
    uptime_pct = data.get("cameraUptimePercent")

    by_violation = data.get("trafficViolationsByType") or {}
    busiest_camera = data.get("busiestCamera") or {}
    peak = data.get("peakInterval") or {}

    lines = [f"**Situation Report — {_fmt_date_range(from_date, to_date).replace('from ', '').capitalize()}**", ""]

    if total_reads:
        lines.append(f"📷 **{total_reads:,}** total plate reads ({unique_plates:,} unique plates)")

    if total_violations:
        lines.append(f"⚠️  **{total_violations:,}** traffic violations detected")
        active_viol = [(k, _n(v)) for k, v in by_violation.items() if _n(v) > 0]
        if active_viol:
            active_viol.sort(key=lambda x: x[1], reverse=True)
            breakdown = ", ".join(
                f"{_VIOLATION_LABELS.get(k, k)}: {v:,}" for k, v in active_viol
            )
            lines.append(f"   Breakdown — {breakdown}")
    else:
        lines.append("✅ No traffic violations recorded in this period.")

    if busiest_camera.get("name"):
        cam_name = busiest_camera["name"]
        cam_reads = _n(busiest_camera.get("reads"))
        lines.append(f"🏆 Busiest camera: **{cam_name}** ({cam_reads:,} reads)")

    if peak.get("bucket"):
        peak_bucket = peak["bucket"]
        peak_total = _n(peak.get("total"))
        if peak_total:
            lines.append(f"⏰ Peak period: **{peak_bucket}** with {peak_total:,} reads")

    if cameras_deployed:
        uptime_str = f" ({uptime_pct:.0f}% uptime)" if isinstance(uptime_pct, (int, float)) else ""
        lines.append(f"📡 Cameras: **{cameras_online}/{cameras_deployed}** online{uptime_str}")

    return "\n".join(lines)


def _narrate_recidivism(
    data: dict[str, Any],
    from_date: str,
    to_date: str,
) -> str:
    repeat_count = _n(data.get("repeatPlates"))
    rows: list[dict] = data.get("rows") or []

    when = _fmt_date_range(from_date, to_date)

    if repeat_count == 0:
        return f"No repeat offenders found {when}."

    lines = [
        f"There are **{repeat_count:,}** plates with multiple violations {when}.",
        "",
        "**Top repeat offenders:**",
    ]

    for row in rows[:10]:
        plate = row.get("plate") or "(no plate)"
        count = _n(row.get("violationCount"))
        type_count = _n(row.get("typeCount"))
        latest = row.get("latestDetectedAt") or ""
        latest_type = _VIOLATION_LABELS.get(
            row.get("latestType", ""), row.get("latestType", "")
        )
        lines.append(
            f"- **{plate}** — {count} violations ({type_count} type{'s' if type_count != 1 else ''})"
            + (f", latest: {latest_type} at {latest}" if latest else "")
        )

    return "\n".join(lines)


def _narrate_camera_status(data: dict[str, Any]) -> str:
    cameras_online = _n(data.get("camerasOnline"))
    cameras_deployed = _n(data.get("camerasDeployed"))
    cameras_live = _n(data.get("camerasLive"))
    uptime_pct = data.get("cameraUptimePercent")

    if not cameras_deployed:
        return "No camera data available."

    uptime_str = ""
    if isinstance(uptime_pct, (int, float)):
        uptime_str = f" ({uptime_pct:.0f}% average uptime)"

    lines = [
        f"📡 **{cameras_online}/{cameras_deployed}** cameras are currently online{uptime_str}.",
    ]
    if cameras_live:
        lines.append(f"🔴 **{cameras_live}** cameras are streaming live.")

    by_camera: list[dict] = data.get("cameraUptimeByCamera") or []
    if by_camera:
        offline = [c for c in by_camera if not c.get("isOnline")]
        if offline:
            names = [c.get("name") or c.get("cameraId", "?") for c in offline[:5]]
            lines.append(f"Offline: {', '.join(names)}" + (" and more." if len(offline) > 5 else "."))

    return "\n".join(lines)
