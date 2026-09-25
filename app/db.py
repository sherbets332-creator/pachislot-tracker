"""SQLite接続の管理。

設計書 2.1 のとおり、journal_mode=WAL と busy_timeout を設定し、
PC/スマホからの同時アクセスによる競合を緩和する。
"""
import sqlite3
from pathlib import Path

import click
from flask import current_app, g


def get_db() -> sqlite3.Connection:
    """リクエストスコープのDB接続を返す（Flask の g にキャッシュ）。"""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """schema.sql を読み込んでテーブルを作成する（既存テーブルはスキップ）。"""
    db = get_db()
    schema_path = Path(current_app.root_path).parent / "schema.sql"
    with schema_path.open(encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()


@click.command("init-db")
def init_db_command() -> None:
    """`flask init-db` — DBファイルをschema.sqlから初期化する。"""
    init_db()
    click.echo("データベースを初期化しました。")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
