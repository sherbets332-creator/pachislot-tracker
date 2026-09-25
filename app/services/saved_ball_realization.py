"""貯玉換金のFIFOロット会計・実現差額調整（設計書 6.5・7.9）。

- 'earn'（獲得）および 'adjust'（残高を増やす補正）の各行を「ロット」として扱う。
- 'use' / 'cashout' / 'adjust'（残高を減らす補正）は、ロットを獲得順（FIFO）に消費する。
- 'cashout'（実際に現金を受け取る換金）のときだけ、当初の計算価値と実受取額の差額を、
  消費した中で最も古いロットに全額割り当てる（ルール(b)。7.9参照）。
  差額はそのロットの獲得元記録の `realized_adjustment_total` に加算する。
- 'use' や 'adjust' は消費順（どのロットが残るか）には影響するが、差額調整はトリガーしない。
- 獲得元の記録がないロット（'adjust'起源）が対象になった場合、差額はどの記録にも
  割り当てず、`record_realization_adjustments.record_id = NULL` として記録する。

店舗の貯玉台帳が変わるたび（cashout/adjustの追加・編集・削除、記録のsaved_ball_used／
saved_ball_earnedの変更、記録の削除）に、対象店舗の台帳全体を最初から再計算する
（差分更新ではなく全再計算方式。理由は7.9参照）。
"""
import sqlite3
from collections import deque
from dataclasses import dataclass


@dataclass
class Lot:
    record_id: int | None
    remaining: int
    rate: float


def recalculate_shop_ledger(db: sqlite3.Connection, shop_id: int) -> None:
    """対象店舗の貯玉台帳をFIFOで最初から再計算し、実現差額調整を作り直す。"""

    # 1. 既存の調整履歴を削除し、対象記録の実現差額を0にリセットする
    db.execute("DELETE FROM record_realization_adjustments WHERE shop_id = ?", (shop_id,))
    db.execute(
        "UPDATE records SET realized_adjustment_total = 0 WHERE shop_id = ?",
        (shop_id,),
    )

    # 2. 台帳を時系列（同日はid）順に読み込む
    transactions = db.execute(
        """
        SELECT * FROM saved_ball_transactions
        WHERE shop_id = ?
        ORDER BY transaction_date ASC, id ASC
        """,
        (shop_id,),
    ).fetchall()

    lots: deque[Lot] = deque()

    for tx in transactions:
        ttype = tx["transaction_type"]

        if ttype == "earn":
            lots.append(Lot(record_id=tx["record_id"], remaining=tx["ball_count"], rate=tx["exchange_rate_used"]))

        elif ttype == "adjust" and tx["ball_count"] > 0:
            # 獲得元の記録がない新しいロット（初期残高登録など）
            lots.append(Lot(record_id=None, remaining=tx["ball_count"], rate=tx["exchange_rate_used"]))

        elif ttype == "use" or (ttype == "adjust" and tx["ball_count"] < 0):
            qty = tx["ball_count"] if ttype == "use" else abs(tx["ball_count"])
            _consume_lots(lots, qty)

        elif ttype == "cashout":
            qty = tx["ball_count"]
            consumed = _consume_lots(lots, qty)
            _apply_cashout_realization(db, shop_id, tx, consumed)

    db.commit()


def _consume_lots(lots: "deque[Lot]", qty: int) -> list[tuple[Lot, int]]:
    """ロットを古い順に消費し、(消費したロット, 消費枚数) のリストを返す。

    実際の残高は保存前のフォームバリデーションで不足しないことを前提とするが、
    万一不足している場合は在庫がある分だけ消費する（防御的な実装）。
    """
    consumed: list[tuple[Lot, int]] = []
    remaining_qty = qty
    while remaining_qty > 0 and lots:
        lot = lots[0]
        take = min(lot.remaining, remaining_qty)
        if take <= 0:
            lots.popleft()
            continue
        lot.remaining -= take
        remaining_qty -= take
        consumed.append((lot, take))
        if lot.remaining <= 0:
            lots.popleft()
    return consumed


def _apply_cashout_realization(
    db: sqlite3.Connection,
    shop_id: int,
    cashout_tx: sqlite3.Row,
    consumed: list[tuple["Lot", int]],
) -> None:
    if not consumed:
        return

    calculated_total = sum(round(qty * lot.rate) for lot, qty in consumed)
    diff = (cashout_tx["cash_amount"] or 0) - calculated_total

    for i, (lot, qty) in enumerate(consumed):
        calculated_value = round(qty * lot.rate)
        # ルール(b): 差額は最古のロット（先頭= i == 0）にのみ全額割り当てる
        adjustment_amount = diff if i == 0 else 0

        db.execute(
            """
            INSERT INTO record_realization_adjustments
                (shop_id, record_id, cashout_transaction_id, consumed_ball_count,
                 calculated_value, adjustment_amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (shop_id, lot.record_id, cashout_tx["id"], qty, calculated_value, adjustment_amount),
        )

        if adjustment_amount != 0 and lot.record_id is not None:
            db.execute(
                "UPDATE records SET realized_adjustment_total = realized_adjustment_total + ? WHERE id = ?",
                (adjustment_amount, lot.record_id),
            )
