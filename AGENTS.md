# AGENTS.md

このリポジトリは、複数のAIコーディングツール(Claude / MulmoClaude、Codex CLI など)から
並行して触られることがあります。作業を始める前に必ずこのファイルを読んでください。

## プロジェクト概要

パチスロの収支・貯玉を記録する個人用Webアプリ(Flask + SQLite)。ローカルPCで動かす前提で、
サーバー公開や複数人利用は想定していない。姉妹プロジェクトとして、iPhone単体で完結する
PWA版(`../pachislot-tracker-pwa`)が別リポジトリで開発中。こちらのFlask版は
**動作確認済みの仕様書・バックアップとして維持する**(積極的な新機能開発の主戦場はPWA版)。

設計の経緯はメインのワークスペース側の設計書にまとまっている:
`artifacts/documents/2026/09/pachislot-tracker-design-e6a657b4b3cd431e.md`
(このリポジトリには含まれていない。ワークスペースのファイルなので直接は読めないことが多い)

## 絶対に守ってほしい設計ルール

- **収支計算式**: `profit_amount = payout_count * exchange_rate_used - (cash_investment + saved_ball_used * exchange_rate_used)`
  貯玉の獲得・使用は両方とも「換金レート」に統一する(貸出レートは参考表示専用、収支計算には使わない)
- **貯玉台帳**(`saved_ball_transactions`): earn/use/cashout/adjustの4種別。adjustのみball_countが符号付き
- **貯玉換金のFIFOロット会計**(`app/services/saved_ball_realization.py`): 換金時の計算価値と実受取額の差額は、
  消費した中で**最も古いロットにのみ全額割り当てる**(ルール(b))。use/adjustは消費順に影響するが差額調整はトリガーしない
- **貯玉残高は絶対にマイナスにしない**: 記録の新規/編集/削除、換金、残高調整のいずれでも、
  保存前に`app/services/validation.py`の`check_balance_never_negative`相当のチェックを必ず通すこと
- **店舗・機種マスタ**: 記録・貯玉履歴がある場合は削除禁止、アーカイブ(`is_archived`)のみ可。
  履歴が無ければ完全削除可

## 開発・テストの進め方

- Pythonは `venv/Scripts/python.exe` を使う(グローバル環境にはインストールしない)
- 自動テストフレームワークは無い。機能追加時は、Flaskの test_client を使った使い捨てスクリプトで
  実際にシナリオを動かして検証し、**検証が終わったらそのスクリプトは削除する**（リポジトリに残さない）
- DBスキーマを変更したら、`app/db.py`の`ensure_schema_migrations`に既存DB向けの
  マイグレーション処理を追加すること(`CREATE TABLE IF NOT EXISTS`は既存DBの列追加には効かない)

## Git運用（重要・過去にインシデントあり）

- **`git add -A`する前に必ず`git status`で中身を確認すること**。過去に，このリポジトリと
  姉妹リポジトリ(pachislot-tracker-pwa)の両方で、想定外のファイル（実データを含むDBバックアップや
  無関係なツールの生成物）が`.gitignore`の抜け穴によりステージされそうになったことがある
- 個人データ(実店舗名、実際の収支記録など)を**絶対にcommitしない**。`data/`ディレクトリは
  丸ごと`.gitignore`されている(本番DB・バックアップ用)
- commitの作者メールは、このリポジトリでは既にGitHubのnoreplyアドレスに設定済み。
  変更しないこと(実メールアドレスの露出を避けるため)
- Claude/MulmoClaude経由でcommitする場合は、コミットメッセージの最後に
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` を付ける(セッション側の指示による)。
  Codex経由の場合はCodex自身の規約に従ってよい
- リポジトリはPublic。公開して問題ないことを常に意識する(個人情報・秘密情報を含めない)

## ディレクトリ構成

```
app/
  routes/       Flaskのルート（画面・エンドポイント）
  services/     ビジネスロジック（profit_calculator, saved_ball_ledger, saved_ball_realization, validation, csv_import）
  templates/    Jinja2テンプレート
  db.py         DB接続・スキーマ初期化・マイグレーション
schema.sql      DDL
scripts/        開発用の単発スクリプト（export_for_pwa.py、scrape_pworld.js相当のPython版など）
data/           本番DB・バックアップ（.gitignore対象、リポジトリには含まれない）
```
