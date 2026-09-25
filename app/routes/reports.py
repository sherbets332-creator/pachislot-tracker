"""収支分析（5.3）：月別・機種別・店舗別集計など。

雛形段階につき、まずは基本的な集計クエリをそのまま表示する簡易版。
表示用収支は `profit_amount + realized_adjustment_total`（6.5）を使う。
"""
from flask import Blueprint, render_template

from ..db import get_db

bp = Blueprint("reports", __name__, url_prefix="/reports")

DISPLAY_PROFIT = "(profit_amount + realized_adjustment_total)"


@bp.route("/")
def index():
    db = get_db()

    yearly = db.execute(
        f"""
        SELECT substr(play_date, 1, 4) AS y,
               SUM({DISPLAY_PROFIT}) AS total,
               COUNT(*) AS play_count
        FROM records
        GROUP BY y
        ORDER BY y DESC
        """
    ).fetchall()

    monthly = db.execute(
        f"""
        SELECT substr(play_date, 1, 7) AS ym,
               SUM({DISPLAY_PROFIT}) AS total,
               COUNT(*) AS play_count
        FROM records
        GROUP BY ym
        ORDER BY ym DESC
        LIMIT 12
        """
    ).fetchall()

    by_machine = db.execute(
        f"""
        SELECT m.name AS machine_name,
               SUM({DISPLAY_PROFIT}) AS total,
               COUNT(*) AS play_count,
               AVG({DISPLAY_PROFIT}) AS avg_profit
        FROM records r JOIN machines m ON m.id = r.machine_id
        GROUP BY r.machine_id
        ORDER BY total DESC
        """
    ).fetchall()

    by_shop = db.execute(
        f"""
        SELECT s.name AS shop_name,
               SUM({DISPLAY_PROFIT}) AS total,
               COUNT(*) AS play_count
        FROM records r JOIN shops s ON s.id = r.shop_id
        GROUP BY r.shop_id
        ORDER BY total DESC
        """
    ).fetchall()

    cashout_by_shop = db.execute(
        """
        SELECT s.name AS shop_name, SUM(sbt.cash_amount) AS total_cashout
        FROM saved_ball_transactions sbt
        JOIN shops s ON s.id = sbt.shop_id
        WHERE sbt.transaction_type = 'cashout'
        GROUP BY sbt.shop_id
        """
    ).fetchall()

    other_adjustments = db.execute(
        """
        SELECT s.name AS shop_name, SUM(rra.adjustment_amount) AS total
        FROM record_realization_adjustments rra
        JOIN shops s ON s.id = rra.shop_id
        WHERE rra.record_id IS NULL
        GROUP BY rra.shop_id
        """
    ).fetchall()

    return render_template(
        "reports/index.html",
        yearly=yearly, monthly=monthly, by_machine=by_machine, by_shop=by_shop,
        cashout_by_shop=cashout_by_shop, other_adjustments=other_adjustments,
        active_nav="reports",
    )
