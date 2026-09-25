# パチスロ収支管理Webアプリ

設計書：`artifacts/documents/2026/09/pachislot-tracker-design-e6a657b4b3cd431e.md`（メインのワークスペース側）

## セットアップ（初回のみ）

venvは作成済み・Flaskはインストール済みです。DBを初期化する場合：

```
cd C:\Users\sherb\mulmoclaude\github\pachislot-tracker
venv\Scripts\python -m flask --app run.py init-db
```

別PCで新しくcloneした場合は、先に `python -m venv venv` → `venv\Scripts\pip install -r requirements.txt` でvenvを作り直してから上記を実行する。

## 起動方法

```
cd C:\Users\sherb\mulmoclaude\github\pachislot-tracker
venv\Scripts\python run.py
```

デスクトップの `Mulmo_Start.bat` / `Mulmo_End.bat` を使う場合は、起動時に自動で `git pull`、終了時に自動で `git push`（コミット済みの分のみ）される。

`http://localhost:5000/` （同一LAN内のスマホからは `http://<PCのIPアドレス>:5000/`）でアクセスできます。

## 現状の実装状況（雛形）

- ✅ 店舗マスタ・機種マスタのCRUD
- ✅ 記録の新規登録・編集・削除（収支自動計算、プレビュー、貯玉獲得数⇔回収枚数の連動）
- ✅ カレンダー（月間表示、日ごとの収支、日別記録一覧）
- ✅ 貯玉台帳（獲得・使用・換金・残高調整）と残高計算
- ✅ 貯玉換金のFIFOロット会計・実現差額調整（設計書6.5）
- ✅ 収支分析（月別・機種別・店舗別の簡易集計）
- ✅ スマホでのカレンダー左右スワイプ月切り替え（/calendar/fragment API＋先読みキャッシュ）
- ✅ 入力バリデーションの強化（貯玉残高が保存後にマイナスになる操作をブロックするなど）
- ✅ 収支推移グラフ（月別＋累計）・貯玉残高推移グラフ（Chart.js、CDN経由）
- ⬜ スクレイピング設定画面（プレースホルダのみ、未実装）
