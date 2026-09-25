"""店舗情報（5.4）：店舗マスタ管理・貯玉残高・貯玉換金・残高調整。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services import saved_ball_ledger
from ..services.saved_ball_realization import recalculate_shop_ledger

bp = Blueprint("shops", __name__, url_prefix="/shops")


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
        db.execute(
            """
            INSERT INTO shops (name, exchange_rate, lending_rate, address, memo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request.form["name"].strip(),
                float(request.form["exchange_rate"]),
                float(request.form["lending_rate"]),
                request.form.get("address", "").strip() or None,
                request.form.get("memo", "").strip() or None,
            ),
        )
        db.commit()
        flash("店舗を登録しました。")
        return redirect(url_for("shops.index"))
    return render_template("shops/form.html", shop=None, active_nav="shops")


@bp.route("/<int:shop_id>/edit", methods=["GET", "POST"])
def edit(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if request.method == "POST":
        db.execute(
            """
            UPDATE shops SET name = ?, exchange_rate = ?, lending_rate = ?, address = ?, memo = ?,
                updated_at = datetime('now','localtime')
            WHERE id = ?
            """,
            (
                request.form["name"].strip(),
                float(request.form["exchange_rate"]),
                float(request.form["lending_rate"]),
                request.form.get("address", "").strip() or None,
                request.form.get("memo", "").strip() or None,
                shop_id,
            ),
        )
        db.commit()
        flash("店舗情報を更新しました。")
        return redirect(url_for("shops.index"))
    return render_template("shops/form.html", shop=shop, active_nav="shops")


@bp.route("/<int:shop_id>")
def detail(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    balance = saved_ball_ledger.get_balance(db, shop_id)
    ledger = saved_ball_ledger.get_ledger(db, shop_id)
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
        active_nav="shops",
    )


@bp.route("/<int:shop_id>/cashout", methods=["GET", "POST"])
def cashout(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if request.method == "POST":
        db.execute(
            """
            INSERT INTO saved_ball_transactions
                (shop_id, transaction_date, transaction_type, ball_count, cash_amount, memo)
            VALUES (?, ?, 'cashout', ?, ?, ?)
            """,
            (
                shop_id,
                request.form["transaction_date"],
                int(request.form["ball_count"]),
                int(request.form["cash_amount"]),
                request.form.get("memo", "").strip() or None,
            ),
        )
        db.commit()
        recalculate_shop_ledger(db, shop_id)
        flash("貯玉換金を記録しました。")
        return redirect(url_for("shops.detail", shop_id=shop_id))
    return render_template("shops/cashout_form.html", shop=shop, active_nav="shops")


@bp.route("/<int:shop_id>/adjust", methods=["GET", "POST"])
def adjust(shop_id: int):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)).fetchone()
    if request.method == "POST":
        ball_count = int(request.form["ball_count"])
        db.execute(
            """
            INSERT INTO saved_ball_transactions
                (shop_id, transaction_date, transaction_type, ball_count, exchange_rate_used, memo)
            VALUES (?, ?, 'adjust', ?, ?, ?)
            """,
            (
                shop_id,
                request.form["transaction_date"],
                ball_count,
                shop["exchange_rate"] if ball_count > 0 else None,
                request.form.get("memo", "").strip() or None,
            ),
        )
        db.commit()
        recalculate_shop_ledger(db, shop_id)
        flash("残高調整を記録しました。")
        return redirect(url_for("shops.detail", shop_id=shop_id))
    return render_template("shops/adjust_form.html", shop=shop, active_nav="shops")
