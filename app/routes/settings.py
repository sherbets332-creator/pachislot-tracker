"""その他メニュー（雛形）：現状はCSVインポートへの入口のみ。"""
from flask import Blueprint, render_template

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/")
def index():
    return render_template("settings/index.html", active_nav="other")
