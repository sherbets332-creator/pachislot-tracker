"""開発用の起動スクリプト。

ローカル環境での動作を想定しているため、Flaskの開発サーバーをそのまま使う。
PC・スマホの両方から同一LAN内でアクセスできるよう host='0.0.0.0' で待ち受ける。
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
