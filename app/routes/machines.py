"""機種情報（5.5）：機種マスタの一覧・登録・編集。"""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..db import get_db
from ..services.validation import ValidationError, require_text

bp = Blueprint("machines", __name__, url_prefix="/machines")


def _save_machine(db, machine_id: int | None, form) -> None:
    name = require_text(form, "name", "機種名")
    maker = form.get("maker", "").strip() or None
    memo = form.get("memo", "").strip() or None

    try:
        if machine_id is None:
            db.execute(
                "INSERT INTO machines (name, maker, memo) VALUES (?, ?, ?)",
                (name, maker, memo),
            )
        else:
            db.execute(
                "UPDATE machines SET name = ?, maker = ?, memo = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (name, maker, memo, machine_id),
            )
        db.commit()
    except sqlite3.IntegrityError:
        raise ValidationError("その機種名はすでに登録されています。") from None


def _machine_has_history(db, machine_id: int) -> bool:
    row = db.execute("SELECT 1 FROM records WHERE machine_id = ?", (machine_id,)).fetchone()
    return row is not None


@bp.route("/")
def index():
    db = get_db()
    show_archived = request.args.get("show_archived") == "1"
    machines = db.execute(
        "SELECT * FROM machines WHERE is_archived = ? ORDER BY name",
        (1 if show_archived else 0,),
    ).fetchall()
    archived_count = db.execute("SELECT COUNT(*) AS c FROM machines WHERE is_archived = 1").fetchone()["c"]
    return render_template(
        "machines/index.html", machines=machines,
        show_archived=show_archived, archived_count=archived_count,
        active_nav="machines",
    )


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        db = get_db()
        try:
            _save_machine(db, None, request.form)
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("machines.new"))
        flash("機種を登録しました。")
        return redirect(url_for("machines.index"))
    return render_template("machines/form.html", machine=None, active_nav="machines")


@bp.route("/<int:machine_id>/edit", methods=["GET", "POST"])
def edit(machine_id: int):
    db = get_db()
    machine = db.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if request.method == "POST":
        try:
            _save_machine(db, machine_id, request.form)
        except ValidationError as e:
            flash(str(e))
            return redirect(url_for("machines.edit", machine_id=machine_id))
        flash("機種を更新しました。")
        return redirect(url_for("machines.index"))
    has_history = _machine_has_history(db, machine_id)
    return render_template("machines/form.html", machine=machine, has_history=has_history, active_nav="machines")


@bp.route("/<int:machine_id>/archive", methods=["POST"])
def archive(machine_id: int):
    db = get_db()
    db.execute(
        "UPDATE machines SET is_archived = 1, updated_at = datetime('now','localtime') WHERE id = ?",
        (machine_id,),
    )
    db.commit()
    flash("機種をアーカイブしました。一覧や記録入力の選択肢には出なくなりますが、記録は残ります。")
    return redirect(url_for("machines.index"))


@bp.route("/<int:machine_id>/unarchive", methods=["POST"])
def unarchive(machine_id: int):
    db = get_db()
    db.execute(
        "UPDATE machines SET is_archived = 0, updated_at = datetime('now','localtime') WHERE id = ?",
        (machine_id,),
    )
    db.commit()
    flash("機種を一覧に戻しました。")
    return redirect(url_for("machines.index", show_archived=1))


@bp.route("/<int:machine_id>/delete", methods=["POST"])
def delete_machine(machine_id: int):
    db = get_db()
    if _machine_has_history(db, machine_id):
        flash("この機種には記録があるため削除できません。アーカイブを使ってください。")
        return redirect(url_for("machines.edit", machine_id=machine_id))
    db.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
    db.commit()
    flash("機種を削除しました。")
    return redirect(url_for("machines.index"))
