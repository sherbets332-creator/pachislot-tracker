"""フォーム入力の検証（保存前チェック）。

DBのCHECK制約（schema.sql）は最後の砦として残すが、そこで弾かれると
ユーザーには生の"IntegrityError"が見えてしまう。ここでは保存の手前で
分かりやすい日本語メッセージのエラーとして検出する。

貯玉残高が保存の結果マイナスになってしまうケース（設計書 6.4／これまでの
やり取りで「本来はアプリ側で保存できないエラーにする想定」としていた部分）も
ここでチェックする。
"""
from __future__ import annotations

import sqlite3

_FULLWIDTH_TO_HALFWIDTH = str.maketrans("０１２３４５６７８９－", "0123456789-")


class ValidationError(ValueError):
    """フォーム入力の検証エラー。ルート側でflashメッセージとして表示する。"""


def to_half_width(text: str) -> str:
    return text.translate(_FULLWIDTH_TO_HALFWIDTH)


def parse_int(form, field: str, label: str, *, required: bool = True, minimum: int | None = None) -> int:
    """フォームの値を整数として取り出す。全角数字にも対応する。"""
    raw = to_half_width((form.get(field) or "").strip())
    if raw == "":
        if required:
            raise ValidationError(f"{label}を入力してください。")
        return 0
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError(f"{label}には整数を入力してください。") from None
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label}は{minimum}以上で入力してください。")
    return value


def parse_float(form, field: str, label: str, *, minimum: float | None = None) -> float:
    raw = to_half_width((form.get(field) or "").strip())
    if raw == "":
        raise ValidationError(f"{label}を入力してください。")
    try:
        value = float(raw)
    except ValueError:
        raise ValidationError(f"{label}には数値を入力してください。") from None
    if minimum is not None and value <= minimum:
        raise ValidationError(f"{label}は{minimum}より大きい値を入力してください。")
    return value


def require_text(form, field: str, label: str) -> str:
    value = (form.get(field) or "").strip()
    if not value:
        raise ValidationError(f"{label}を入力してください。")
    return value


def require_date(form, field: str, label: str) -> str:
    raw = (form.get(field) or "").strip()
    if not raw:
        raise ValidationError(f"{label}を入力してください。")
    import datetime

    try:
        datetime.date.fromisoformat(raw)
    except ValueError:
        raise ValidationError(f"{label}の形式が正しくありません。") from None
    return raw


def check_balance_never_negative(
    db: sqlite3.Connection,
    shop_id: int,
    proposed: list[tuple[str, str, int]],
    *,
    exclude_record_id: int | None = None,
) -> None:
    """この変更を反映した場合に、貯玉残高が一度でもマイナスになるかを検証する。

    実際の貯玉残高はマイナスにはならない（持っている以上は使えない・換金できない）ため、
    保存前にここで弾く。

    proposed: (transaction_date, transaction_type, ball_count) のリスト。
      ball_count は 'adjust' のみ符号付き、それ以外（use/earn/cashout）は正の値。
    exclude_record_id: 記録の編集時、その記録が持つ既存の use/earn 行を計算から除外する
      （新しい値で作り直した proposed に置き換えるため）。
    """
    query = (
        "SELECT transaction_date, id, transaction_type, ball_count "
        "FROM saved_ball_transactions WHERE shop_id = ?"
    )
    params: list = [shop_id]
    if exclude_record_id is not None:
        query += " AND (record_id IS NULL OR record_id != ?)"
        params.append(exclude_record_id)
    rows = db.execute(query, params).fetchall()

    max_id = max((row["id"] for row in rows), default=0)
    sequence = [
        (row["transaction_date"], row["id"], row["transaction_type"], row["ball_count"])
        for row in rows
    ]
    for offset, (date_str, ttype, ball_count) in enumerate(proposed, start=1):
        sequence.append((date_str, max_id + offset, ttype, ball_count))
    sequence.sort(key=lambda item: (item[0], item[1]))

    balance = 0
    for date_str, _id, ttype, ball_count in sequence:
        if ttype == "earn":
            balance += ball_count
        elif ttype in ("use", "cashout"):
            balance -= ball_count
        elif ttype == "adjust":
            balance += ball_count  # 符号付きのためそのまま加算
        if balance < 0:
            raise ValidationError(
                f"貯玉残高が不足しています（{date_str}時点で残高が{balance}枚になります）。"
                "枚数を確認するか、日付を見直してください。"
            )
