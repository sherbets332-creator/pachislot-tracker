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


# schema.sql に列を追加したとき、既存のDBファイルには自動では反映されない
# （CREATE TABLE IF NOT EXISTS は既存テーブルをスキップするため）。
# マイグレーションツールを入れるほどの規模ではないので、ここに
# (テーブル名, 列名, 追加用DDL) を足していく簡易な自己修復方式にする。
_COLUMN_MIGRATIONS = [
    ("shops", "is_archived", "ALTER TABLE shops ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"),
    ("machines", "is_archived", "ALTER TABLE machines ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"),
]


def ensure_schema_migrations() -> None:
    """起動時に呼び、既存DBに不足している列があれば追加する（テーブルがまだ無ければ何もしない）。"""
    db = get_db()
    existing_tables = {
        row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    changed = False
    for table, column, ddl in _COLUMN_MIGRATIONS:
        if table not in existing_tables:
            continue
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            db.execute(ddl)
            changed = True
    if changed:
        db.commit()


@click.command("init-db")
def init_db_command() -> None:
    """`flask init-db` — DBファイルをschema.sqlから初期化する。"""
    init_db()
    click.echo("データベースを初期化しました。")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
