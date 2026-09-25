"""カレンダー（ホーム）画面（5.1）。"""
import calendar as calendar_module
from datetime import date

from flask import Blueprint, render_template, request

from ..db import get_db

bp = Blueprint("calendar", __name__)


@bp.route("/")
def index():
    today = date.today()
    year = request.args.get("year", type=int, default=today.year)
    month = request.args.get("month", type=int, default=today.month)

    db = get_db()
    rows = db.execute(
        """
        SELECT play_date, SUM(profit_amount + realized_adjustment_total) AS total
        FROM records
        WHERE play_date LIKE ?
        GROUP BY play_date
        """,
        (f"{year:04d}-{month:02d}-%",),
    ).fetchall()
    daily_totals = {r["play_date"]: r["total"] for r in rows}

    month_total = sum(daily_totals.values())

    cal = calendar_module.Calendar(firstweekday=6)  # 日曜始まり
    raw_weeks = cal.monthdayscalendar(year, month)

    weeks = []
    for raw_week in raw_weeks:
        week = []
        for day in raw_week:
            if day == 0:
                week.append(None)
            else:
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                week.append({
                    "day": day,
                    "date_str": date_str,
                    "total": daily_totals.get(date_str),
                    "is_today": date_str == today.isoformat(),
                })
        weeks.append(week)

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    return render_template(
        "calendar/index.html",
        year=year, month=month, weeks=weeks,
        month_total=month_total, today=today.isoformat(),
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        active_nav="calendar",
    )
