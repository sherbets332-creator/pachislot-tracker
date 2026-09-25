"""店舗情報（5.4）：店舗マスタ管理・貯玉残高・貯玉換金・残高調整。"""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services import saved_ball_ledger
from ..services.saved_ball_realization import recalculate_shop_ledger
from ..services.validation import (
    ValidationError,
    check_balance_never_negative,
    parse_int,
    require_date,
    require_text,
)

bp = Blueprint("shops", __name__, url_prefix="/shops")


def _parse_rate(form, field: str, label: str) -> float:
    raw = (form.get(field) or "").strip()
    if raw == "":
        raise ValidationError(f"{label}を入力してください。")
    try:
        value = float(raw)
    except ValueError:
        raise ValidationError(f"{label}には数値を入力してください。") from None
    if value <= 0:
        raise ValidationError(f"{label}は0より大きい値を入力してください。")
    return value


def _save_shop(db, shop_id: int | None, form) -> None:
    name = require_text(form, "name", "店舗名")
    exchange_rate = _parse_rate(form, "exchange_rate", "換金レート")
    lending_rate = _parse_rate(form, "lending_rate", "貸し出しレート")
    address = form.get("address", "").strip() or None
    memo = form.get("memo", "").strip() or None

    try:
        if shop_id is None:
            db.execute(
                """
                INSERT INTO shops (name, exchange_rate, lending_rate, address, memo)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, exchange_rate, lending_rate, address, memo),
            )
        else:
            db.execute(
                """
                UPDATE shops SET name = ?, exchange_rate = ?, lending_rate = ?, address = ?, memo = ?,
                    updated_at = datetime('now','localtime')
                WHERE id = ?
                """,
                (name, exchange_rate, lending_rate, address, memo, shop_id),
            )
        db.commit()
    except sqlite3.IntegrityError:
        raise ValidationError("その店舗名はすでに登録されています。") from None


@bp.route("/")
def index():
    db = get_db()
    shops = db.execute("SELECT * FROM shops ORDER BY name").fetchall()
    balances = {s["id"]: saved_ball_ledger.get_balance(db, s["id"]) for s in shops}
    return render_template("shops/index.html", shops=shops, balances=balances, active_nav="shops")


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        db = get_db()
        try:
            _save_shop(db, None, request.form)
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("shops.new"))
        flash("店舗を登録しました。")
        return redirect(url_for("shops.index"))
    return render_template("shops/form.html", shop=None, active_nav="shops")


@bp.route("/<int:shop_id>/edit", methods=["GET", "POST"])
def edit(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if request.method == "POST":
        try:
            _save_shop(db, shop_id, request.form)
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("shops.edit", shop_id=shop_id))
        flash("店舗情報を更新しました。")
        return redirect(url_for("shops.index"))
    return render_template("shops/form.html", shop=shop, active_nav="shops")


@bp.route("/<int:shop_id>")
def detail(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    balance = saved_ball_ledger.get_balance(db, shop_id)
    ledger = saved_ball_ledger.get_ledger(db, shop_id)
    balance_history = saved_ball_ledger.get_balance_history(db, shop_id)
    chart_labels = [d for d, _ in balance_history]
    chart_values = [v for _, v in balance_history]
    adjustments = db.execute(
        """
        SELECT rra.*, m.name AS machine_name, r.play_date AS record_play_date
        FROM record_realization_adjustments rra
        LEFT JOIN records r ON r.id = rra.record_id
        LEFT JOIN machines m ON m.id = r.machine_id
        WHERE rra.shop_id = ?
        ORDER BY rra.created_at DESC, rra.id DESC
        """,
        (shop_id,),
    ).fetchall()
    return render_template(
        "shops/detail.html",
        shop=shop,
        balance=balance,
        ledger=ledger,
        adjustments=adjustments,
        chart_labels=chart_labels,
        chart_values=chart_values,
        active_nav="shops",
    )


@bp.route("/<int:shop_id>/cashout", methods=["GET", "POST"])
def cashout(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if request.method == "POST":
        try:
            transaction_date = require_date(request.form, "transaction_date", "日付")
            ball_count = parse_int(request.form, "ball_count", "換金枚数", minimum=1)
            cash_amount = parse_int(request.form, "cash_amount", "受取現金額", minimum=0)
            check_balance_never_negative(db, shop_id, [(transaction_date, "cashout", ball_count)])

            db.execute(
                """
                INSERT INTO saved_ball_transactions
                    (shop_id, transaction_date, transaction_type, ball_count, cash_amount, memo)
                VALUES (?, ?, 'cashout', ?, ?, ?)
                """,
                (
                    shop_id,
                    transaction_date,
                    ball_count,
                    cash_amount,
                    request.form.get("memo", "").strip() or None,
                ),
            )
            db.commit()
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("shops.cashout", shop_id=shop_id))
        except sqlite3.IntegrityError:
            flash("入力内容がルールを満たしていないため保存できませんでした。数値を見直してください。")
            return redirect(url_for("shops.cashout", shop_id=shop_id))

        recalculate_shop_ledger(db, shop_id)
        flash("貯玉換金を記録しました。")
        return redirect(url_for("shops.detail", shop_id=shop_id))

    balance = saved_ball_ledger.get_balance(db, shop_id)
    return render_template("shops/cashout_form.html", shop=shop, balance=balance, active_nav="shops")


@bp.route("/<int:shop_id>/adjust", methods=["GET", "POST"])
def adjust(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if request.method == "POST":
        try:
            transaction_date = require_date(request.form, "transaction_date", "日付")
            ball_count = parse_int(request.form, "ball_count", "調整枚数")
            if ball_count == 0:
                raise ValidationError("調整枚数は0以外の値を入力してください。")
            if ball_count < 0:
                check_balance_never_negative(db, shop_id, [(transaction_date, "adjust", ball_count)])

            db.execute(
                """
                INSERT INTO saved_ball_transactions
                    (shop_id, transaction_date, transaction_type, ball_count, exchange_rate_used, memo)
                VALUES (?, ?, 'adjust', ?, ?, ?)
                """,
                (
                    shop_id,
                    transaction_date,
                    ball_count,
                    shop["exchange_rate"] if ball_count > 0 else None,
                    request.form.get("memo", "").strip() or None,
                ),
            )
            db.commit()
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("shops.adjust", shop_id=shop_id))
        except sqlite3.IntegrityError:
            flash("入力内容がルールを満たしていないため保存できませんでした。数値を見直してください。")
            return redirect(url_for("shops.adjust", shop_id=shop_id))

        recalculate_shop_ledger(db, shop_id)
        flash("残高調整を記録しました。")
        return redirect(url_for("shops.detail", shop_id=shop_id))

    balance = saved_ball_ledger.get_balance(db, shop_id)
    return render_template("shops/adjust_form.html", shop=shop, balance=balance, active_nav="shops")


@bp.route("/<int:shop_id>/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
def edit_transaction(shop_id: int, tx_id: int):
    """貯玉換金（cashout）・残高調整（adjust）の履歴を編集する。

    earn/use は記録（records）に紐づいて自動生成される行なので、ここでは扱わない
    （該当の記録を編集してもらう）。
    """
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    tx = db.execute(
        "SELECT * FROM saved_ball_transactions WHERE id = ? AND shop_id = ?",
        (tx_id, shop_id),
    ).fetchone()
    if tx is None or tx["transaction_type"] not in ("cashout", "adjust"):
        flash("編集できない履歴です。")
        return redirect(url_for("shops.detail", shop_id=shop_id))

    if request.method == "POST":
        try:
            transaction_date = require_date(request.form, "transaction_date", "日付")
            if tx["transaction_type"] == "cashout":
                ball_count = parse_int(request.form, "ball_count", "換金枚数", minimum=1)
                cash_amount = parse_int(request.form, "cash_amount", "受取現金額", minimum=0)
                check_balance_never_negative(
                    db, shop_id, [(transaction_date, "cashout", ball_count)],
                    exclude_transaction_id=tx_id,
                )
                db.execute(
                    """
                    UPDATE saved_ball_transactions
                    SET transaction_date = ?, ball_count = ?, cash_amount = ?, memo = ?
                    WHERE id = ?
                    """,
                    (transaction_date, ball_count, cash_amount,
                     request.form.get("memo", "").strip() or None, tx_id),
                )
            else:  # adjust
                ball_count = parse_int(request.form, "ball_count", "調整枚数")
                if ball_count == 0:
                    raise ValidationError("調整枚数は0以外の値を入力してください。")
                if ball_count < 0:
                    check_balance_never_negative(
                        db, shop_id, [(transaction_date, "adjust", ball_count)],
                        exclude_transaction_id=tx_id,
                    )
                db.execute(
                    """
                    UPDATE saved_ball_transactions
                    SET transaction_date = ?, ball_count = ?, exchange_rate_used = ?, memo = ?
                    WHERE id = ?
                    """,
                    (
                        transaction_date, ball_count,
                        shop["exchange_rate"] if ball_count > 0 else None,
                        request.form.get("memo", "").strip() or None, tx_id,
                    ),
                )
            db.commit()
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("shops.edit_transaction", shop_id=shop_id, tx_id=tx_id))
        except sqlite3.IntegrityError:
            flash("入力内容がルールを満たしていないため保存できませんでした。数値を見直してください。")
            return redirect(url_for("shops.edit_transaction", shop_id=shop_id, tx_id=tx_id))

        recalculate_shop_ledger(db, shop_id)
        flash("履歴を更新しました。")
        return redirect(url_for("shops.detail", shop_id=shop_id))

    balance = saved_ball_ledger.get_balance(db, shop_id)
    template = "shops/cashout_form.html" if tx["transaction_type"] == "cashout" else "shops/adjust_form.html"
    return render_template(template, shop=shop, balance=balance, transaction=tx, active_nav="shops")


@bp.route("/<int:shop_id>/transactions/<int:tx_id>/delete", methods=["POST"])
def delete_transaction(shop_id: int, tx_id: int):
    db = get_db()
    tx = db.execute(
        "SELECT * FROM saved_ball_transactions WHERE id = ? AND shop_id = ?",
        (tx_id, shop_id),
    ).fetchone()
    if tx is None or tx["transaction_type"] not in ("cashout", "adjust"):
        flash("削除できない履歴です。")
        return redirect(url_for("shops.detail", shop_id=shop_id))

    try:
        # この行を取り除いた場合に、他の使用・換金・調整が足りなくなって
        # 残高がマイナスにならないかを確認する
        # （cashout削除・マイナスadjust削除は残高を増やすだけなので必ず通るが、
        #   プラスadjustの削除は既に使われている可能性があるためチェックが必要）。
        check_balance_never_negative(db, shop_id, [], exclude_transaction_id=tx_id)
    except ValidationError:
        flash("この履歴を削除すると貯玉残高がマイナスになるため削除できません。")
        return redirect(url_for("shops.detail", shop_id=shop_id))

    # cashout行はrecord_realization_adjustments.cashout_transaction_idから参照されている
    # ことがあるため、先にその調整履歴（対象店舗分）をクリアしてから削除する
    # （recalculate_shop_ledgerが直後に全て作り直すので、消えても問題ない）。
    db.execute("DELETE FROM record_realization_adjustments WHERE shop_id = ?", (shop_id,))
    db.execute("UPDATE records SET realized_adjustment_total = 0 WHERE shop_id = ?", (shop_id,))
    db.execute("DELETE FROM saved_ball_transactions WHERE id = ?", (tx_id,))
    db.commit()
    recalculate_shop_ledger(db, shop_id)
    flash("履歴を削除しました。")
    return redirect(url_for("shops.detail", shop_id=shop_id))
