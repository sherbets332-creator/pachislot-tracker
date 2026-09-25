"""記録入力／編集フォーム（5.2）と、日別の記録一覧。"""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services import saved_ball_ledger
from ..services.profit_calculator import calculate_lending_reference, calculate_profit
from ..services.saved_ball_realization import recalculate_shop_ledger
from ..services.validation import (
    ValidationError,
    check_balance_never_negative,
    parse_int,
    require_date,
    to_half_width,
)

bp = Blueprint("records", __name__, url_prefix="/records")


def _save_record(db, record_id: int | None, form) -> int:
    play_date = require_date(form, "play_date", "日付")
    shop_id = parse_int(form, "shop_id", "店舗", minimum=1)
    machine_id = parse_int(form, "machine_id", "機種", minimum=1)
    cash_investment = parse_int(form, "cash_investment", "現金投資", required=False, minimum=0)
    saved_ball_used = parse_int(form, "saved_ball_used", "貯玉使用枚数", required=False, minimum=0)
    payout_count = parse_int(form, "payout_count", "回収枚数", required=False, minimum=0)
    saved_ball_earned = parse_int(form, "saved_ball_earned", "貯玉獲得数", required=False, minimum=0)
    memo = form.get("memo", "").strip() or None
    machine_number = form.get("machine_number", "").strip() or None

    if saved_ball_earned > payout_count:
        raise ValidationError("貯玉獲得数が回収枚数を超えています。")

    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if shop is None:
        raise ValidationError("選択した店舗が見つかりません。")
    machine = db.execute("SELECT id FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if machine is None:
        raise ValidationError("選択した機種が見つかりません。")
    exchange_rate_used = shop["exchange_rate"]
    lending_rate_used = shop["lending_rate"]

    # この記録の use/earn を除いた台帳に、新しい値の use/earn を反映して
    # 残高が一度でもマイナスにならないかを検証する。
    # 編集で貯玉獲得数を減らしただけ（saved_ball_used自体は0）でも、それより後の
    # 別記録の使用分が足りなくなることがあるため、used/earned どちらか一方だけでなく
    # 常にチェックする（record_idがNoneの新規作成でも、他記録との整合性確認を兼ねる）。
    proposed = []
    if saved_ball_used > 0:
        proposed.append((play_date, "use", saved_ball_used))
    if saved_ball_earned > 0:
        proposed.append((play_date, "earn", saved_ball_earned))
    check_balance_never_negative(db, shop_id, proposed, exclude_record_id=record_id)

    manual_profit = form.get("manual_profit_amount")
    if manual_profit not in (None, ""):
        try:
            profit_amount = int(to_half_width(manual_profit.strip()))
        except ValueError:
            raise ValidationError("手動入力の収支金額には整数を入力してください。") from None
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
        except sqlite3.IntegrityError:
            flash("入力内容がルールを満たしていないため保存できませんでした。数値を見直してください。")
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
        except sqlite3.IntegrityError:
            flash("入力内容がルールを満たしていないため保存できませんでした。数値を見直してください。")
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
    if record is None:
        flash("記録が見つかりませんでした。")
        return redirect(url_for("calendar.index"))

    try:
        # この記録の use/earn を丸ごと取り除いた場合に、他の記録・換金・調整が
        # 使っている分が足りなくなって残高がマイナスにならないかを確認する。
        check_balance_never_negative(db, record["shop_id"], [], exclude_record_id=record_id)
    except ValidationError:
        flash(
            "この記録が獲得した貯玉は、すでに他の記録の使用や換金で使われているため削除できません。"
            "先にそちらの記録・換金・残高調整を編集または削除してください。"
        )
        return redirect(url_for("records.edit", record_id=record_id))

    saved_ball_ledger.delete_record_transactions(db, record_id)
    db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    db.commit()
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
