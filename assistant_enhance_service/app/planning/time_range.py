from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any

def time_clause(tr: dict[str, Any], column: str='ve.created_at') -> str:
    preset = tr.get('preset', 'last_30_days')
    now = datetime.utcnow()
    if preset == 'specific_date':
        start = tr.get('start') or tr.get('date')
        if start:
            day = str(start)[:10]
            end = tr.get('end', day)
            end_day = str(end)[:10]
            start_dt = f'{day} 00:00:00'
            if end_day == day:
                end_dt = (datetime.strptime(day, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                return f"{column} >= '{start_dt}' AND {column} < '{end_dt}'"
            end_dt = f'{end_day} 23:59:59'
            return f"{column} >= '{start_dt}' AND {column} <= '{end_dt}'"
    if preset == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif preset == 'yesterday':
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return f"{column} >= '{start:%Y-%m-%d %H:%M:%S}' AND {column} < '{end:%Y-%m-%d %H:%M:%S}'"
    elif preset == 'this_week':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif preset == 'last_month':
        first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = (first - timedelta(days=1)).replace(day=1)
        end = first
        return f"{column} >= '{start:%Y-%m-%d %H:%M:%S}' AND {column} < '{end:%Y-%m-%d %H:%M:%S}'"
    elif preset == 'this_month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif preset == 'last_7_days':
        start = now - timedelta(days=7)
    elif preset == 'last_5_days':
        start = now - timedelta(days=5)
    else:
        start = now - timedelta(days=30)
    return f"{column} >= '{start:%Y-%m-%d %H:%M:%S}'"

def month_bounds() -> tuple[datetime, datetime, datetime]:
    now = datetime.utcnow()
    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = this_month
    last_month_start = (this_month - timedelta(days=1)).replace(day=1)
    return (this_month, last_month_start, last_month_end)