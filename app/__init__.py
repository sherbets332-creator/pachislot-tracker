"""Flask アプリファクトリ。"""
from pathlib import Path

from flask import Flask

from . import db as db_module


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    data_dir = Path(app.root_path).parent / "data"
    data_dir.mkdir(exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY="dev",  # ローカル専用アプリのため簡易な値。将来的に環境変数化してもよい
        DATABASE_PATH=str(data_dir / "pachislot.db"),
    )

    if test_config is not None:
        app.config.update(test_config)

    @app.template_filter("commas")
    def commas_filter(value):
        """金額・枚数を3桁区切りで表示する（例: -49857 -> "-49,857"）。"""
        if value is None or value == "":
            return ""
        try:
            return f"{round(float(value)):,}"
        except (TypeError, ValueError):
            return value

    db_module.init_app(app)

    with app.app_context():
        db_module.ensure_schema_migrations()

    from .routes import calendar, machines, records, reports, shops

    app.register_blueprint(calendar.bp)
    app.register_blueprint(records.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(shops.bp)
    app.register_blueprint(machines.bp)

    return app
