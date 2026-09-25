-- パチスロ収支管理Webアプリ DBスキーマ
-- 設計書: artifacts/documents/2026/09/pachislot-tracker-design-e6a657b4b3cd431e.md
--
-- 注意：SQLiteは既定で外部キー制約が無効なので、アプリ側の接続時に
--   PRAGMA foreign_keys = ON;
-- を必ず実行すること（app/db.py で設定する）。

PRAGMA foreign_keys = ON;

-- =========================================================
-- shops（店舗マスタ）
-- =========================================================
CREATE TABLE IF NOT EXISTS shops (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    exchange_rate       REAL    NOT NULL DEFAULT 20.0,   -- 換金レート（円／枚）
    lending_rate        REAL    NOT NULL DEFAULT 20.0,   -- 貸し出しレート（円／枚、参考指標）
    address             TEXT,
    memo                TEXT,
    external_source_url TEXT,                            -- 将来：スクレイピング対象URL
    external_source_id  TEXT,                            -- 将来：取得元サイトでの店舗識別子
    is_archived         INTEGER NOT NULL DEFAULT 0,       -- 1=アーカイブ済み（一覧・選択肢からは隠すが、記録は残す）
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (exchange_rate > 0),
    CHECK (lending_rate > 0),
    CHECK (is_archived IN (0, 1))
);

-- =========================================================
-- machines（機種マスタ）
-- =========================================================
CREATE TABLE IF NOT EXISTS machines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    maker       TEXT,
    memo        TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,       -- 1=アーカイブ済み（一覧・選択肢からは隠すが、記録は残す）
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (is_archived IN (0, 1))
);

-- =========================================================
-- records（収支記録）※メインテーブル
-- =========================================================
CREATE TABLE IF NOT EXISTS records (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    play_date                   TEXT    NOT NULL,              -- YYYY-MM-DD
    shop_id                     INTEGER NOT NULL REFERENCES shops(id),
    machine_id                  INTEGER NOT NULL REFERENCES machines(id),
    machine_number              TEXT,
    cash_investment              INTEGER NOT NULL DEFAULT 0,    -- 現金投資（円）
    saved_ball_used              INTEGER NOT NULL DEFAULT 0,    -- 貯玉使用枚数
    payout_count                 INTEGER NOT NULL DEFAULT 0,    -- 回収枚数（＝出玉）
    saved_ball_earned            INTEGER NOT NULL DEFAULT 0,    -- 貯玉獲得数
    exchange_rate_used           REAL    NOT NULL,              -- 換金レートのスナップショット
    lending_rate_used            REAL    NOT NULL,              -- 貸し出しレートのスナップショット
    profit_amount                INTEGER NOT NULL,              -- 収支金額（当初計算値。手動上書き可）
    profit_is_manual             INTEGER NOT NULL DEFAULT 0,    -- 0=自動計算／1=手動上書き
    realized_adjustment_total    INTEGER NOT NULL DEFAULT 0,    -- 実現差額調整の累計（6.5）
    memo                         TEXT,
    source                       TEXT    NOT NULL DEFAULT 'manual',  -- 'manual' / 'scrape'（将来）
    external_ref                 TEXT    UNIQUE,                -- 将来：取込元の一意キー
    created_at                   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at                   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (cash_investment >= 0),
    CHECK (saved_ball_used >= 0),
    CHECK (payout_count >= 0),
    CHECK (saved_ball_earned >= 0),
    CHECK (saved_ball_earned <= payout_count),
    CHECK (profit_is_manual IN (0, 1)),
    CHECK (source IN ('manual', 'scrape'))
);

CREATE INDEX IF NOT EXISTS idx_records_play_date  ON records(play_date);
CREATE INDEX IF NOT EXISTS idx_records_shop_id    ON records(shop_id);
CREATE INDEX IF NOT EXISTS idx_records_machine_id ON records(machine_id);

-- =========================================================
-- saved_ball_transactions（貯玉増減履歴／台帳）
-- =========================================================
CREATE TABLE IF NOT EXISTS saved_ball_transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id             INTEGER NOT NULL REFERENCES shops(id),
    record_id           INTEGER REFERENCES records(id),   -- earn/useは必ず紐づく。cashout/adjustは常にNULL
    transaction_date    TEXT    NOT NULL,                 -- YYYY-MM-DD
    transaction_type    TEXT    NOT NULL CHECK (transaction_type IN ('earn', 'use', 'cashout', 'adjust')),
    ball_count          INTEGER NOT NULL,                 -- earn/use/cashoutは正の値、adjustのみ符号付き
    cash_amount         INTEGER,                          -- cashoutの場合のみ、実際の受取額（円）
    exchange_rate_used  REAL,                              -- earn／adjust(+)のロット評価レート（6.5）
    memo                TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (
        (transaction_type != 'adjust' AND ball_count > 0)
        OR (transaction_type = 'adjust' AND ball_count != 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_sbt_shop_id          ON saved_ball_transactions(shop_id);
CREATE INDEX IF NOT EXISTS idx_sbt_transaction_date ON saved_ball_transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_sbt_record_id        ON saved_ball_transactions(record_id);

-- =========================================================
-- record_realization_adjustments（換金差額調整履歴）
-- 店舗の貯玉台帳をFIFOで再計算するたびに、対象店舗分を全削除してから作り直す監査ログ（6.5）
-- =========================================================
CREATE TABLE IF NOT EXISTS record_realization_adjustments (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id                 INTEGER NOT NULL REFERENCES shops(id),
    record_id               INTEGER REFERENCES records(id),  -- 獲得元の記録がないロット由来ならNULL
    cashout_transaction_id  INTEGER NOT NULL REFERENCES saved_ball_transactions(id),
    consumed_ball_count     INTEGER NOT NULL,
    calculated_value        INTEGER NOT NULL,
    adjustment_amount       INTEGER NOT NULL,
    created_at               TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_rra_shop_id                ON record_realization_adjustments(shop_id);
CREATE INDEX IF NOT EXISTS idx_rra_record_id               ON record_realization_adjustments(record_id);
CREATE INDEX IF NOT EXISTS idx_rra_cashout_transaction_id  ON record_realization_adjustments(cashout_transaction_id);
