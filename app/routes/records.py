"""記録入力／編集フォーム（5.2）と、日別の記録一覧。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services import saved_ball_ledger
from ..services.profit_calculator import calculate_lending_reference, calculate_profit
from ..services.saved_ball_realization import recalculate_shop_ledger

bp = Blueprint("records", __name__, url_prefix="/records")


def _save_record(db, record_id: int | None, form) -> int:
    shop_id = int(form["shop_id"])
    machine_id = int(form["machine_id"])
    play_date = form["play_date"]
    cash_investment = int(form.get("cash_investment") or 0)
    saved_ball_used = int(form.get("saved_ball_used") or 0)
    payout_count = int(form.get("payout_count") or 0)
    saved_ball_earned = int(form.get("saved_ball_earned") or 0)
    memo = form.get("memo", "").strip() or None
    machine_number = form.get("machine_number", "").strip() or None

    if saved_ball_earned > payout_count:
        raise ValueError("貯玉獲得数が回収枚数を超えています。")

    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    exchange_rate_used = shop["exchange_rate"]
    lending_rate_used = shop["lending_rate"]

    manual_profit = form.get("manual_profit_amount")
    if manual_profit not in (None, ""):
        profit_amount = int(manual_profit)
        profit_is_manual = 1
    else:
        profit_amount = calculate_profit(cash_investment, saved_ball_used, payout_count, exchange_rate_used)
        profit_is_manual = 0

    old_shop_id = None
    if record_id is None:
        cur = db.execute(
            """
            INSERT INTO records
                (play_date, shop_id, machine_id, machine_number, cash_investment, saved_ball_used,
                 payout_count, saved_ball_earned, exchange_rate_used, lending_rate_used,
                 profit_amount, profit_is_manual, memo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (play_date, shop_id, machine_id, machine_number, cash_investment, saved_ball_used,
             payout_count, saved_ball_earned, exchange_rate_used, lending_rate_used,
             profit_amount, profit_is_manual, memo),
        )
        record_id = cur.lastrowid
    else:
        old_shop_id = db.execute("SELECT shop_id FROM records WHERE id = ?", (record_id,)).fetchone()["shop_id"]
        db.execute(
            """
            UPDATE records SET
                play_date = ?, shop_id = ?, machine_id = ?, machine_number = ?, cash_investment = ?,
                saved_ball_used = ?, payout_count = ?, saved_ball_earned = ?, exchange_rate_used = ?,
                lending_rate_used = ?, profit_amount = ?, profit_is_manual = ?, memo = ?,
                updated_at = datetime('now','localtime')
            WHERE id = ?
            """,
            (play_date, shop_id, machine_id, machine_number, cash_investment, saved_ball_used,
             payout_count, saved_ball_earned, exchange_rate_used, lending_rate_used,
             profit_amount, profit_is_manual, memo, record_id),
        )

    saved_ball_ledger.sync_record_transactions(
        db, record_id, shop_id, play_date, saved_ball_used, saved_ball_earned, exchange_rate_used
    )
    db.commit()

    recalculate_shop_ledger(db, shop_id)
    if old_shop_id is not None and old_shop_id != shop_id:
        recalculate_shop_ledger(db, old_shop_id)

    return record_id


@bp.route("/new", methods=["GET", "POST"])
def new():
    db = get_db()
    if request.method == "POST":
        try:
            _save_record(db, None, request.form)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("records.new", date=request.form.get("play_date")))
        flash("記録を保存しました。")
        return redirect(url_for("calendar.index"))

    shops = db.execute("SELECT * FROM shops ORDER BY name").fetchall()
    machines = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    default_date = request.args.get("date", "")
    return render_template(
        "records/form.html", record=None, shops=shops, machines=machines,
        default_date=default_date, active_nav="calendar",
    )


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
def edit(record_id: int):
    db = get_db()
    if request.method == "POST":
        try:
            _save_record(db, record_id, request.form)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("records.edit", record_id=record_id))
        flash("記録を更新しました。")
        return redirect(url_for("calendar.index"))

    record = db.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    shops = db.execute("SELECT * FROM shops ORDER BY name").fetchall()
    machines = db.execute("SELECT * FROM machines ORDER BY name").fetchall()

    lending_reference = calculate_lending_reference(record["saved_ball_used"], record["lending_rate_used"])
    adjustments = db.execute(
        "SELECT * FROM record_realization_adjustments WHERE record_id = ? ORDER BY created_at DESC",
        (record_id,),
    ).fetchall()

    return render_template(
        "records/form.html", record=record, shops=shops, machines=machines,
        default_date=record["play_date"], lending_reference=lending_reference,
        adjustments=adjustments, active_nav="calendar",
    )


@bp.route("/<int:record_id>/delete", methods=["POST"])
def delete(record_id: int):
    db = get_db()
    record = db.execute("SELECT shop_id FROM records WHERE id = ?", (record_id,)).fetchone()
    saved_ball_ledger.delete_record_transactions(db, record_id)
    db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    db.commit()
    if record:
        recalculate_shop_ledger(db, record["shop_id"])
    flash("記録を削除しました。")
    return redirect(url_for("calendar.index"))


@bp.route("/day/<date>")
def day(date: str):
    db = get_db()
    records = db.execute(
        """
        SELECT r.*, s.name AS shop_name, m.name AS machine_name
        FROM records r
        JOIN shops s ON s.id = r.shop_id
        JOIN machines m ON m.id = r.machine_id
        WHERE r.play_date = ?
        ORDER BY r.id
        """,
        (date,),
    ).fetchall()
    return render_template("records/day.html", date=date, records=records, active_nav="calendar")
