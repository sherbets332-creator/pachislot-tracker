"""貯玉台帳（saved_ball_transactions）の同期・残高計算（設計書 6.4）。

- 記録（records）の保存に伴う 'earn' / 'use' 行の自動生成・同期
- 店舗ごとの現在残高の計算
  現在の貯玉残高 = SUM(earn) - SUM(use) - SUM(cashout) + SUM(adjust)   ※ adjustは符号付き
"""
import sqlite3


def sync_record_transactions(
    db: sqlite3.Connection,
    record_id: int,
    shop_id: int,
    play_date: str,
    saved_ball_used: int,
    saved_ball_earned: int,
    exchange_rate_used: float,
) -> None:
    """記録保存時に、その記録に紐づく 'use' / 'earn' 行を作り直す。

    既存の紐づく行をいったん削除してから、現在の値に基づいて作り直す
    （記録の編集で値が変わった場合も整合性が保てる）。
    """
    db.execute(
        "DELETE FROM saved_ball_transactions WHERE record_id = ? AND transaction_type IN ('use', 'earn')",
        (record_id,),
    )
    if saved_ball_used > 0:
        db.execute(
            """
            INSERT INTO saved_ball_transactions
                (shop_id, record_id, transaction_date, transaction_type, ball_count)
            VALUES (?, ?, ?, 'use', ?)
            """,
            (shop_id, record_id, play_date, saved_ball_used),
        )
    if saved_ball_earned > 0:
        db.execute(
            """
            INSERT INTO saved_ball_transactions
                (shop_id, record_id, transaction_date, transaction_type, ball_count, exchange_rate_used)
            VALUES (?, ?, ?, 'earn', ?, ?)
            """,
            (shop_id, record_id, play_date, saved_ball_earned, exchange_rate_used),
        )


def delete_record_transactions(db: sqlite3.Connection, record_id: int) -> None:
    """記録削除時に、紐づく 'use' / 'earn' 行を削除する。"""
    db.execute(
        "DELETE FROM saved_ball_transactions WHERE record_id = ? AND transaction_type IN ('use', 'earn')",
        (record_id,),
    )


def get_balance(db: sqlite3.Connection, shop_id: int) -> int:
    row = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type = 'earn'    THEN ball_count END), 0)
          - COALESCE(SUM(CASE WHEN transaction_type = 'use'     THEN ball_count END), 0)
          - COALESCE(SUM(CASE WHEN transaction_type = 'cashout' THEN ball_count END), 0)
          + COALESCE(SUM(CASE WHEN transaction_type = 'adjust'  THEN ball_count END), 0)
              AS balance
        FROM saved_ball_transactions
        WHERE shop_id = ?
        """,
        (shop_id,),
    ).fetchone()
    return int(row["balance"] or 0)


def get_ledger(db: sqlite3.Connection, shop_id: int) -> list[sqlite3.Row]:
    """店舗の貯玉増減履歴を時系列で取得する（記録の機種名も一緒に）。"""
    return db.execute(
        """
        SELECT
            sbt.*,
            r.play_date AS record_play_date,
            m.name AS machine_name
        FROM saved_ball_transactions sbt
        LEFT JOIN records r ON r.id = sbt.record_id
        LEFT JOIN machines m ON m.id = r.machine_id
        WHERE sbt.shop_id = ?
        ORDER BY sbt.transaction_date, sbt.id
        """,
        (shop_id,),
    ).fetchall()
