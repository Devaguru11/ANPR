from __future__ import annotations
from app.planning.dimensions import filters_to_sql, group_expressions
from app.planning.metrics import get_metric
from app.planning.plan import AnalyticalPlan
from app.planning.retrieval_scope import sql_limit_clause
from app.planning.time_range import month_bounds, time_clause

class SQLBuilder:
    _ORDER_ALIASES = {'date': 'period', 'day': 'period', 'week': 'period', 'month': 'period', 'hour': 'period', 've.created_at': 've.created_at', 'total': 'total', 'period': 'period'}

    def _order_column(self, field: str) -> str:
        return self._ORDER_ALIASES.get(field, field if field in ('total', 'period') else 'total')

    def build(self, plan: AnalyticalPlan) -> str:
        mode = plan.query_mode
        if mode == 'record_listing':
            return self._record_listing(plan)
        if mode == 'comparison' and plan.compare_to:
            return self._comparison(plan)
        if mode == 'growth_analysis':
            return self._growth_analysis(plan)
        if mode in ('trend_analysis', 'grouped_analysis', 'top_n', 'bottom_n', 'ranking', 'anomaly_detection'):
            return self._grouped(plan)
        return self._count(plan)

    def _where(self, plan: AnalyticalPlan, *, include_time: bool=True) -> str:
        parts = ['1=1']
        if include_time and plan.time_range:
            clause = time_clause(plan.time_range)
            if clause:
                parts.append(clause)
        parts.extend(filters_to_sql(plan.filters))
        return ' AND '.join(parts)

    def _count(self, plan: AnalyticalPlan) -> str:
        if plan.metric == 'challans':
            where = self._where(plan)
            return f'SELECT COUNT(DISTINCT vtf.challan_id) AS total FROM violation_ticket_flags vtf JOIN traffic_violations tv ON vtf.violation_id = tv.violation_id JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE vtf.challan_id IS NOT NULL AND {where} LIMIT 1'
        metric = get_metric(plan.metric)
        where = self._where(plan)
        if metric.requires_violation_join:
            return f'SELECT {metric.count_expression} AS total FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {where} LIMIT 1'
        return f'SELECT {metric.count_expression} AS total FROM vehicle_events ve WHERE {where} LIMIT 1'

    def _grouped(self, plan: AnalyticalPlan) -> str:
        metric = get_metric(plan.metric)
        dims = plan.group_by or plan.dimensions or ['date']
        groups = group_expressions(dims)
        if not groups:
            return self._count(plan)
        select_parts = [f'{expr} AS {alias}' for (expr, alias) in groups]
        group_cols = [expr for (expr, _) in groups]
        order = self._order_column(plan.sort.get('field', 'total'))
        direction = plan.sort.get('direction', 'DESC')
        if order not in ('total', 'period') and groups:
            order = 'total'
        limit = plan.limit or 365
        where = self._where(plan)
        if metric.requires_violation_join:
            select_sql = ', '.join(select_parts) + f', {metric.count_expression} AS total'
            return f"SELECT {select_sql} FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {where} GROUP BY {', '.join(group_cols)} ORDER BY {order} {direction}{sql_limit_clause(limit)}"
        select_sql = ', '.join(select_parts) + f', {metric.count_expression} AS total'
        return f"SELECT {select_sql} FROM vehicle_events ve WHERE {where} GROUP BY {', '.join(group_cols)} ORDER BY {order} {direction}{sql_limit_clause(limit)}"

    def _record_listing(self, plan: AnalyticalPlan) -> str:
        metric = get_metric(plan.metric)
        where = self._where(plan)
        order = plan.sort.get('field') or 've.created_at'
        if order == 'total':
            order = 've.created_at'
        direction = plan.sort.get('direction', 'DESC')
        limit_clause = sql_limit_clause(plan.limit)
        cols = ', '.join((f've.{c}' if c != 'violation_type' else 'tv.violation_type' for c in metric.record_columns))
        if metric.requires_violation_join:
            return f'SELECT {cols} FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {where} ORDER BY {order} {direction}{limit_clause}'
        return f'SELECT ve.vehicle_num, ve.camera_id, ve.created_at FROM vehicle_events ve WHERE {where} ORDER BY {order} {direction}{limit_clause}'

    def _growth_analysis(self, plan: AnalyticalPlan) -> str:
        metric = get_metric(plan.metric)
        dims = plan.group_by or plan.dimensions or ['camera']
        groups = group_expressions(dims)
        if not groups:
            groups = [('ve.camera_id', 'camera_id')]
        (entity_expr, entity_alias) = groups[0]
        current = time_clause(plan.time_range or {'preset': 'this_month'})
        previous = time_clause(plan.compare_to or {'preset': 'last_month'})
        base = self._where(plan, include_time=False)
        limit = plan.limit or 10
        cur_expr = f'SUM(CASE WHEN {current} THEN 1 ELSE 0 END)'
        prev_expr = f'SUM(CASE WHEN {previous} THEN 1 ELSE 0 END)'
        if metric.requires_violation_join:
            return f'SELECT {entity_expr} AS {entity_alias}, {cur_expr} AS current_count, {prev_expr} AS previous_count, ({cur_expr} - {prev_expr}) AS delta FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {base} GROUP BY {entity_expr} HAVING current_count > previous_count ORDER BY delta DESC LIMIT {limit}'
        return f'SELECT {entity_expr} AS {entity_alias}, {cur_expr} AS current_count, {prev_expr} AS previous_count, ({cur_expr} - {prev_expr}) AS delta FROM vehicle_events ve WHERE {base} GROUP BY {entity_expr} HAVING current_count > previous_count ORDER BY delta DESC LIMIT {limit}'

    def _comparison(self, plan: AnalyticalPlan) -> str:
        metric = get_metric(plan.metric)
        base = self._where(plan, include_time=False)
        current = time_clause(plan.time_range or {'preset': 'this_month'})
        previous = time_clause(plan.compare_to or {'preset': 'last_month'})
        if metric.requires_violation_join:
            return f"SELECT 'current_period' AS period, {metric.count_expression} AS total FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {base} AND {current} UNION ALL SELECT 'previous_period' AS period, {metric.count_expression} AS total FROM traffic_violations tv JOIN vehicle_events ve ON tv.event_id = ve.event_id WHERE {base} AND {previous}"
        return f"SELECT 'current_period' AS period, {metric.count_expression} AS total FROM vehicle_events ve WHERE {base} AND {current} UNION ALL SELECT 'previous_period' AS period, {metric.count_expression} AS total FROM vehicle_events ve WHERE {base} AND {previous}"