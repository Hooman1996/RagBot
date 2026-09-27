"""Aggregate-only metrics for the existing browser analytics dashboard.

The query writer stores naive UTC timestamps. All boundaries sent to PostgreSQL
are therefore naive UTC, and only aggregate result rows leave this module.
"""

from datetime import datetime, time, timedelta, timezone


ANALYTICS_CONTRACT_VERSION = "main-analytics/v3"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
HOURS = [f"{hour:02d}:00" for hour in range(24)]
DEPTH_LABELS = ["1", "2–4", "5–9", "10+"]
DURATION_LABELS = ["<2 s", "2–5 s", "5–10 s", "10–20 s", "20+ s"]


def _rows(cursor, sql, params):
    cursor.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _one(cursor, sql, params):
    return _rows(cursor, sql, params)[0]


def aggregate_analytics(db_manager, days, now=None):
    if days not in (7, 14, 30):
        raise ValueError("days must be 7, 14, or 30")
    snapshot = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    end = snapshot.replace(tzinfo=None)
    today = datetime.combine(snapshot.date(), time.min)
    start = today - timedelta(days=days - 1)
    week_start = today - timedelta(days=6)
    prior_week_start = week_start - timedelta(days=7)

    conn = db_manager.get_connection()
    try:
        # The endpoint has no writes. This also protects manual audits against
        # accidentally introducing a write as the SQL evolves.
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor() as cursor:
            summary = _one(cursor, """
                SELECT COUNT(*) AS total_queries,
                       COUNT(DISTINCT user_id) AS active_users,
                       COUNT(*) FILTER (WHERE is_helpful = 1) AS helpful,
                       COUNT(*) FILTER (WHERE is_helpful = 0) AS unhelpful,
                       COUNT(*) FILTER (WHERE is_helpful IS NULL) AS no_feedback,
                       COUNT(*) FILTER (WHERE is_helpful IS NOT NULL AND is_helpful NOT IN (0, 1)) AS other_feedback,
                       COUNT(*) FILTER (WHERE chat_session_id IS NULL) AS without_session,
                       COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                       COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                       COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                       COUNT(*) FILTER (WHERE status IS NULL OR status NOT IN ('completed', 'pending', 'failed')) AS other_status,
                       COUNT(*) FILTER (WHERE status = 'completed' AND completed_at IS NOT NULL
                                                AND completed_at >= created_at) AS measured,
                       AVG(EXTRACT(EPOCH FROM completed_at - created_at)) FILTER
                           (WHERE status = 'completed' AND completed_at IS NOT NULL
                                  AND completed_at >= created_at) AS avg_seconds,
                       COUNT(*) FILTER (WHERE status = 'completed' AND completed_at >= created_at
                                                AND completed_at - created_at < INTERVAL '2 seconds') AS duration_0,
                       COUNT(*) FILTER (WHERE status = 'completed' AND completed_at >= created_at
                                                AND completed_at - created_at >= INTERVAL '2 seconds'
                                                AND completed_at - created_at < INTERVAL '5 seconds') AS duration_1,
                       COUNT(*) FILTER (WHERE status = 'completed' AND completed_at >= created_at
                                                AND completed_at - created_at >= INTERVAL '5 seconds'
                                                AND completed_at - created_at < INTERVAL '10 seconds') AS duration_2,
                       COUNT(*) FILTER (WHERE status = 'completed' AND completed_at >= created_at
                                                AND completed_at - created_at >= INTERVAL '10 seconds'
                                                AND completed_at - created_at < INTERVAL '20 seconds') AS duration_3,
                       COUNT(*) FILTER (WHERE status = 'completed' AND completed_at >= created_at
                                                AND completed_at - created_at >= INTERVAL '20 seconds') AS duration_4
                  FROM queries
                 WHERE created_at >= %s AND created_at < %s
            """, (start, end))

            daily = _rows(cursor, """
                SELECT created_at::date AS day, COUNT(*) AS queries,
                       COUNT(DISTINCT user_id) AS users
                  FROM queries
                 WHERE created_at >= %s AND created_at < %s
                 GROUP BY created_at::date ORDER BY day
            """, (start, end))

            depth = _one(cursor, """
                WITH per_session AS (
                    SELECT chat_session_id, COUNT(*) AS n
                      FROM queries
                     WHERE created_at >= %s AND created_at < %s
                       AND chat_session_id IS NOT NULL
                     GROUP BY chat_session_id
                )
                SELECT COUNT(*) FILTER (WHERE n = 1) AS depth_0,
                       COUNT(*) FILTER (WHERE n BETWEEN 2 AND 4) AS depth_1,
                       COUNT(*) FILTER (WHERE n BETWEEN 5 AND 9) AS depth_2,
                       COUNT(*) FILTER (WHERE n >= 10) AS depth_3,
                       COUNT(*) AS sessions
                  FROM per_session
            """, (start, end))

            activity = _rows(cursor, """
                SELECT EXTRACT(ISODOW FROM created_at)::int AS weekday,
                       EXTRACT(HOUR FROM created_at)::int AS hour,
                       COUNT(*) AS queries
                  FROM queries
                 WHERE created_at >= %s AND created_at < %s
                 GROUP BY 1, 2
            """, (start, end))

            weekly = _rows(cursor, """
                SELECT EXTRACT(ISODOW FROM created_at)::int AS weekday,
                       (created_at >= %s) AS current_week,
                       COUNT(*) AS queries
                  FROM queries
                 WHERE created_at >= %s AND created_at < %s
                 GROUP BY 1, 2
            """, (week_start, prior_week_start, end))

            documents = _one(cursor, """
                SELECT COUNT(*) AS indexed FROM documents
                 WHERE processing_status = 'completed'
            """, ())
        conn.rollback()
    finally:
        conn.close()

    by_day = {row["day"]: row for row in daily}
    dates = [start.date() + timedelta(days=i) for i in range(days)]
    labels = [day.isoformat() for day in dates]
    matrix = [[0] * 24 for _ in range(7)]
    for row in activity:
        matrix[int(row["weekday"]) - 1][int(row["hour"])] = int(row["queries"])
    week_current, week_previous = [0] * 7, [0] * 7
    for row in weekly:
        target = week_current if row["current_week"] else week_previous
        target[int(row["weekday"]) - 1] = int(row["queries"])

    total = int(summary["total_queries"])
    completed = int(summary["completed"])
    measured = int(summary["measured"])
    helpful = int(summary["helpful"])
    unhelpful = int(summary["unhelpful"])
    states = [(name, int(summary[name])) for name in ("completed", "pending", "failed", "other_status")]
    states = [("other" if name == "other_status" else name, count)
              for name, count in states if count]
    return {
        "meta": {
            "contract_version": ANALYTICS_CONTRACT_VERSION,
            "days": days, "timezone": "UTC",
            "start": start.isoformat() + "Z", "end": end.isoformat() + "Z",
            "weekly_independent": True,
            "weekly_start": week_start.isoformat() + "Z",
            "weekly_previous_start": prior_week_start.isoformat() + "Z",
        },
        "kpis": {
            "total_queries": total,
            "active_users": int(summary["active_users"]),
            "avg_completion_seconds": round(float(summary["avg_seconds"]), 2) if measured else None,
            "completion_measured": measured,
            "completed_queries": completed,
            "rated_responses": helpful + unhelpful,
            "documents_indexed": int(documents["indexed"]),
        },
        "queries_per_day": {"labels": labels, "data": [int(by_day.get(day, {}).get("queries", 0)) for day in dates], "total": total},
        "users_per_day": {"labels": labels, "data": [int(by_day.get(day, {}).get("users", 0)) for day in dates], "query_total": total},
        "feedback_outcomes": {
            "labels": ["Helpful", "Unhelpful", "No feedback"],
            "data": [helpful, unhelpful, int(summary["no_feedback"])],
            "rated_responses": helpful + unhelpful,
            "total_queries": total,
            "other_values": int(summary["other_feedback"]),
        },
        "conversation_depth": {
            "labels": DEPTH_LABELS,
            "data": [int(depth[f"depth_{i}"]) for i in range(4)],
            "sessions": int(depth["sessions"]),
            "queries_without_session": int(summary["without_session"]),
        },
        "completion_duration": {
            "labels": DURATION_LABELS,
            "data": [int(summary[f"duration_{i}"]) for i in range(5)],
            "measured": measured, "completed": completed,
            "excluded_completed": completed - measured,
            "unavailable_reason": None if measured else "No completed queries with valid timestamps",
        },
        "query_states": {"labels": [name for name, _ in states],
                         "data": [count for _, count in states], "total": total},
        "heatmap": {"weekdays": WEEKDAYS, "hours": HOURS,
                    "matrix": matrix, "weekday_totals": [sum(row) for row in matrix],
                    "total": total},
        "weekly_comparison": {
            "labels": WEEKDAYS, "current": week_current, "previous": week_previous,
            "current_total": sum(week_current), "previous_total": sum(week_previous),
        },
    }
