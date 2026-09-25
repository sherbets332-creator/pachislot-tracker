"""機種情報（5.5）：機種マスタの一覧・登録・編集。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("machines", __name__, url_prefix="/machines")


@bp.route("/")
def index():
    db = get_db()
    machines = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    return render_template("machines/index.html", machines=machines, active_nav="machines")


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        db = get_db()
        db.execute(
            "INSERT INTO machines (name, maker, memo) VALUES (?, ?, ?)",
            (request.form["name"].strip(), request.form.get("maker", "").strip() or None,
             request.form.get("memo", "").strip() or None),
        )
        db.commit()
        flash("機種を登録しました。")
        return redirect(url_for("machines.index"))
    return render_template("machines/form.html", machine=None, active_nav="machines")


@bp.route("/<int:machine_id>/edit", methods=["GET", "POST"])
def edit(machine_id: int):
    db = get_db()
    machine = db.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if request.method == "POST":
        db.execute(
            "UPDATE machines SET name = ?, maker = ?, memo = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (request.form["name"].strip(), request.form.get("maker", "").strip() or None,
             request.form.get("memo", "").strip() or None, machine_id),
        )
        db.commit()
        flash("機種を更新しました。")
        return redirect(url_for("machines.index"))
    return render_template("machines/form.html", machine=machine, active_nav="machines")
