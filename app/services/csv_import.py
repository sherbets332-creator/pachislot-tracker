"""過去記録のCSVインポート。

対応フォーマット（列名は完全一致で検出）:
    日付,店舗コード,店舗,メーカー,機種コード,機種,台番号,投資額,回収額,収支,メモ,稼働時間,時給

このアプリの記録は「投資額（円）」「回収枚数（枚）」を持ち、
  収支 = 回収枚数 * 換金レート - (投資額 + 貯玉使用枚数 * 換金レート)
で計算する（profit_calculator.py）。だがCSV側の「回収額」はすでに円換算済みの
値なので、回収枚数 = 回収額 / 換金レート として逆算し、アプリの計算式で
CSVの「収支」列と一致するか検証する。一致すれば自動計算の記録として取り込み、
一致しなければ（レートが違う等）CSVの収支をそのまま手動上書き値として取り込む
（回収額はメモに残す）。

店舗マスタ・機種マスタに無い名前は、その場で新規登録する（店舗は換金・貸出
レートともに20.0円/枚の初期値、店舗コードはexternal_source_idに保存）。
店舗名・機種名が空欄の行は「不明」という名前で登録する。

稼働時間・時給の列はこのアプリにデータ項目が無いため取り込まない。

既存の記録と (日付, 店舗名, 機種名) が一致する行は、二重登録を避けるため
スキップする（すでに手入力で貯玉情報まで含めて登録済みの記録を、CSVの
簡易な内容で上書き・重複登録してしまうのを防ぐ）。
"""
from __future__ import annotations

import csv
import datetime
import io
from dataclasses import dataclass, field

from .profit_calculator import calculate_profit
from .validation import to_half_width
from . import saved_ball_ledger

REQUIRED_COLUMNS = {"日付", "投資額", "回収額"}
UNKNOWN_SHOP_NAME = "不明"
UNKNOWN_MACHINE_NAME = "不明"
DEFAULT_EXCHANGE_RATE = 20.0
DEFAULT_LENDING_RATE = 20.0


class CsvFormatError(ValueError):
    """ファイル全体が期待するCSV形式ではない場合のエラー。"""


@dataclass
class RowError:
    line_no: int
    message: str


@dataclass
class ImportResult:
    total_rows: int = 0
    imported: int = 0
    errors: list[RowError] = field(default_factory=list)
    created_shops: list[str] = field(default_factory=list)
    created_machines: list[str] = field(default_factory=list)
    skipped_duplicates: list[str] = field(default_factory=list)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvFormatError("文字コードを判別できませんでした（UTF-8 または Shift_JIS のCSVに対応しています）。")


def _parse_date(raw: str) -> str:
    raw = raw.strip()
    for sep in ("/", "-"):
        parts = raw.split(sep)
        if len(parts) == 3:
            try:
                y, m, d = (int(p) for p in parts)
                return datetime.date(y, m, d).isoformat()
            except ValueError:
                pass
    raise ValueError(f"日付「{raw}」を解釈できません。")


def _parse_int(raw: str | None, default: int = 0) -> int:
    raw = to_half_width((raw or "").strip())
    if raw == "":
        return default
    return int(raw)


def _get_or_create_shop(db, cache: dict, name: str, shop_code: str | None, result: ImportResult):
    if name in cache:
        return cache[name]
    row = db.execute("SELECT * FROM shops WHERE name = ?", (name,)).fetchone()
    if row is None:
        db.execute(
            """
            INSERT INTO shops (name, exchange_rate, lending_rate, external_source_id)
            VALUES (?, ?, ?, ?)
            """,
            (name, DEFAULT_EXCHANGE_RATE, DEFAULT_LENDING_RATE, shop_code or None),
        )
        row = db.execute("SELECT * FROM shops WHERE name = ?", (name,)).fetchone()
        result.created_shops.append(name)
    cache[name] = row
    return row


def _get_or_create_machine(db, cache: dict, name: str, maker: str | None, result: ImportResult):
    if name in cache:
        return cache[name]
    row = db.execute("SELECT * FROM machines WHERE name = ?", (name,)).fetchone()
    if row is None:
        db.execute("INSERT INTO machines (name, maker) VALUES (?, ?)", (name, maker or None))
        row = db.execute("SELECT * FROM machines WHERE name = ?", (name,)).fetchone()
        result.created_machines.append(name)
    cache[name] = row
    return row


def _existing_keys(db) -> set[tuple[str, str]]:
    """既存の記録と重複インポートされないようにするための (日付, 店舗名) の一覧。

    機種名は突合キーに使わない。CSV側の機種名（正式名称）と、このアプリの機種マスタで
    ユーザーが登録した呼び名（略称など）が一致しない場合があり、それだと同じ記録を
    見分けられず重複登録してしまうため。1日に同じ店舗で複数回遊技した記録がCSVと
    アプリの両方にある場合はこの突合では区別できない点に注意。
    """
    rows = db.execute(
        """
        SELECT r.play_date AS play_date, s.name AS shop_name
        FROM records r
        JOIN shops s ON s.id = r.shop_id
        """
    ).fetchall()
    return {(row["play_date"], row["shop_name"]) for row in rows}


def import_records_csv(db, file_bytes: bytes) -> ImportResult:
    text = _decode(file_bytes)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise CsvFormatError(
            "CSVの列見出しが想定と異なります。「日付」「投資額」「回収額」の列を含むCSVを指定してください。"
        )

    result = ImportResult()
    shop_cache: dict[str, object] = {}
    machine_cache: dict[str, object] = {}
    existing_keys = _existing_keys(db)

    for line_no, row in enumerate(reader, start=2):
        result.total_rows += 1
        try:
            play_date = _parse_date(row.get("日付") or "")
            cash_investment = _parse_int(row.get("投資額"))
            payout_yen = _parse_int(row.get("回収額"))
            profit_expected_raw = row.get("収支")
            profit_expected = (
                _parse_int(profit_expected_raw) if (profit_expected_raw or "").strip() != ""
                else payout_yen - cash_investment
            )
            shop_name = (row.get("店舗") or "").strip() or UNKNOWN_SHOP_NAME
            shop_code = (row.get("店舗コード") or "").strip() or None
            machine_name = (row.get("機種") or "").strip() or UNKNOWN_MACHINE_NAME
            maker = (row.get("メーカー") or "").strip() or None
            machine_number = (row.get("台番号") or "").strip() or None
            memo = (row.get("メモ") or "").strip() or None

            if (play_date, shop_name) in existing_keys:
                result.skipped_duplicates.append(f"{play_date} {shop_name} / {machine_name}")
                continue

            shop = _get_or_create_shop(db, shop_cache, shop_name, shop_code, result)
            machine = _get_or_create_machine(db, machine_cache, machine_name, maker, result)

            exchange_rate_used = shop["exchange_rate"]
            lending_rate_used = shop["lending_rate"]

            payout_count = max(0, round(payout_yen / exchange_rate_used)) if exchange_rate_used else 0
            computed_profit = calculate_profit(cash_investment, 0, payout_count, exchange_rate_used)

            if computed_profit == profit_expected:
                profit_amount = computed_profit
                profit_is_manual = 0
            else:
                payout_count = 0
                profit_amount = profit_expected
                profit_is_manual = 1
                note = f"[取込時の回収額: {payout_yen}円]"
                memo = f"{memo}\n{note}" if memo else note

            cur = db.execute(
                """
                INSERT INTO records
                    (play_date, shop_id, machine_id, machine_number, cash_investment, saved_ball_used,
                     payout_count, saved_ball_earned, exchange_rate_used, lending_rate_used,
                     profit_amount, profit_is_manual, memo, source)
                VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, ?, ?, 'manual')
                """,
                (play_date, shop["id"], machine["id"], machine_number, cash_investment,
                 payout_count, exchange_rate_used, lending_rate_used,
                 profit_amount, profit_is_manual, memo),
            )
            saved_ball_ledger.sync_record_transactions(
                db, cur.lastrowid, shop["id"], play_date, 0, 0, exchange_rate_used
            )
        except (ValueError, KeyError) as e:
            result.errors.append(RowError(line_no, str(e)))
            continue

        result.imported += 1

    db.commit()
    return result
