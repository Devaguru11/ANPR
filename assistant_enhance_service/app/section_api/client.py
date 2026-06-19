"""
section_api/client.py
---------------------
HTTP client that calls the existing Node.js REST API endpoints.
These are the same endpoints the frontend dashboard sections use,
so data is always consistent with what appears on screen.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base() -> str:
    """Node server base URL (no trailing slash)."""
    return settings.node_server_url.rstrip("/")


def _headers() -> dict[str, str]:
    """Auth header for internal service-to-service calls."""
    return {"X-Internal-Key": settings.internal_api_key}


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(20.0)


def _ymd_today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _ymd_n_days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Time-range preset → (from_date, to_date) resolver
# The assistant_enhance_service uses its own time_range dicts; we flatten them
# to plain YYYY-MM-DD strings that the Node endpoints accept.
# ---------------------------------------------------------------------------

def resolve_date_range(time_range: dict[str, Any] | None) -> tuple[str, str]:
    """Convert a temporal resolution dict to (from_date, to_date) strings."""
    if not time_range:
        to = _ymd_today()
        frm = _ymd_n_days_ago(30)
        return frm, to

    preset = time_range.get("preset", "last_30_days")
    today = _ymd_today()

    if preset == "specific_date":
        frm = str(time_range.get("start") or time_range.get("date") or today)[:10]
        to = str(time_range.get("end") or frm)[:10]
        return frm, to

    if preset == "today":
        return today, today

    if preset == "yesterday":
        y = _ymd_n_days_ago(1)
        return y, y

    if preset == "this_week":
        now = datetime.utcnow()
        frm = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return frm, today

    if preset == "this_month":
        frm = datetime.utcnow().replace(day=1).strftime("%Y-%m-%d")
        return frm, today

    if preset == "last_month":
        now = datetime.utcnow()
        first_this = now.replace(day=1)
        last_m_end = first_this - timedelta(days=1)
        last_m_start = last_m_end.replace(day=1)
        return last_m_start.strftime("%Y-%m-%d"), last_m_end.strftime("%Y-%m-%d")

    if preset == "last_7_days":
        return _ymd_n_days_ago(7), today

    if preset == "last_5_days":
        return _ymd_n_days_ago(5), today

    # default: last_30_days
    return _ymd_n_days_ago(30), today


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

async def fetch_violations_summary(
    from_date: str,
    to_date: str,
    camera_id: str | None = None,
    plate: str | None = None,
) -> dict[str, Any]:
    """GET /api/dashboard/violations-summary — total + by-type breakdown."""
    params: dict[str, str] = {"from": from_date, "to": to_date}
    if camera_id:
        params["cameraId"] = camera_id
    if plate:
        params["plate"] = plate

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/violations-summary",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_violations_by_camera(
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    """GET /api/dashboard/overview — includes trafficViolationsByCamera."""
    params: dict[str, str] = {"from": from_date, "to": to_date}
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/overview",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_range_stats(
    from_date: str,
    to_date: str,
    vehicle_type: str | None = None,
    camera_id: str | None = None,
) -> dict[str, Any]:
    """GET /api/dashboard/range-stats — total detections + by vehicle type."""
    params: dict[str, str] = {"from": from_date, "to": to_date}
    if vehicle_type:
        params["vehicleType"] = vehicle_type
    if camera_id:
        params["cameraId"] = camera_id

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/range-stats",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_overview(
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    """GET /api/dashboard/overview — high-level dashboard summary."""
    params: dict[str, str] = {"from": from_date, "to": to_date}
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/overview",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_violations_list(
    from_date: str,
    to_date: str,
    violation_type: str | None = None,
    camera_id: str | None = None,
    plate: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    """GET /api/dashboard/violations — paginated violation records."""
    params: dict[str, Any] = {
        "from": from_date,
        "to": to_date,
        "page": page,
        "pageSize": page_size,
    }
    if violation_type:
        params["type"] = violation_type
    if camera_id:
        params["cameraId"] = camera_id
    if plate:
        params["plate"] = plate

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/violations",
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_recidivism(limit: int = 10) -> dict[str, Any]:
    """GET /api/dashboard/violations-recidivism — repeat offenders this month."""
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/violations-recidivism",
            params={"limit": limit},
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_captured_counts() -> dict[str, Any]:
    """GET /api/dashboard/captured — today/week/month vehicle capture counts."""
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.get(
            f"{_base()}/api/dashboard/captured",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()
