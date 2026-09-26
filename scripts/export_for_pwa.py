"""Flask版（SQLite）のデータを、PWA版がインポートできるJSON形式に書き出す。

PWA版（pachislot-tracker-pwa）は record_realization_adjustments テーブルを
持たない設計（表示のたびにその場でFIFO計算をやり直す）なので、ここでは書き出さない。
records.realized_adjustment_total も同じ理由で書き出さない（PWA側で自動的に再計算される）。

実行:
    venv\\Scripts\\python scripts\\export_for_pwa.py [出力先パス]

出力先を省略した場合は、実行したディレクトリに pachislot-export-YYYY-MM-DD.json を作る。
"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pachislot.db"

EXPORT_VERSION = 1


def export_shops(db: sqlite3.Connection) -> list[dict]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "exchange_rate": r["exchange_rate"],
            "lending_rate": r["lending_rate"],
            "address": r["address"],
            "memo": r["memo"],
            "is_archived": r["is_archived"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in db.execute("SELECT * FROM shops")
    ]


def export_machines(db: sqlite3.Connection) -> list[dict]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "maker": r["maker"],
            "memo": r["memo"],
            "is_archived": r["is_archived"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in db.execute("SELECT * FROM machines")
    ]


def export_records(db: sqlite3.Connection) -> list[dict]:
    return [
        {
            "id": r["id"],
            "play_date": r["play_date"],
            "shop_id": r["shop_id"],
            "machine_id": r["machine_id"],
            "machine_number": r["machine_number"],
            "cash_investment": r["cash_investment"],
            "saved_ball_used": r["saved_ball_used"],
            "payout_count": r["payout_count"],
            "saved_ball_earned": r["saved_ball_earned"],
            "exchange_rate_used": r["exchange_rate_used"],
            "lending_rate_used": r["lending_rate_used"],
            "profit_amount": r["profit_amount"],
            "profit_is_manual": r["profit_is_manual"],
            "memo": r["memo"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            # realized_adjustment_total はPWA側で保存しないので含めない
        }
        for r in db.execute("SELECT * FROM records")
    ]


def export_saved_ball_transactions(db: sqlite3.Connection) -> list[dict]:
    return [
        {
            "id": r["id"],
            "shop_id": r["shop_id"],
            "record_id": r["record_id"],
            "transaction_date": r["transaction_date"],
            "transaction_type": r["transaction_type"],
            "ball_count": r["ball_count"],
            "cash_amount": r["cash_amount"],
            "exchange_rate_used": r["exchange_rate_used"],
            "memo": r["memo"],
            "created_at": r["created_at"],
        }
        for r in db.execute("SELECT * FROM saved_ball_transactions")
    ]


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(f"pachislot-export-{date.today().isoformat()}.json")

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    data = {
        "exported_at": date.today().isoformat(),
        "version": EXPORT_VERSION,
        "shops": export_shops(db),
        "machines": export_machines(db),
        "records": export_records(db),
        "saved_ball_transactions": export_saved_ball_transactions(db),
    }
    db.close()

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"書き出し完了: {output_path}")
    for key in ("shops", "machines", "records", "saved_ball_transactions"):
        print(f"  {key}: {len(data[key])}件")


if __name__ == "__main__":
    main()
