"""収支計算ロジック（設計書 6.3）。

profit_amount = payout_count * exchange_rate_used
              - (cash_investment + saved_ball_used * exchange_rate_used)

獲得・使用とも「換金レート」に統一する（7.7 参照）。
端数は四捨五入して整数円に丸める（6.3「端数の扱い」参照）。
"""


def calculate_profit(
    cash_investment: int,
    saved_ball_used: int,
    payout_count: int,
    exchange_rate_used: float,
) -> int:
    income = payout_count * exchange_rate_used
    cost = cash_investment + saved_ball_used * exchange_rate_used
    return round(income - cost)


def calculate_lending_reference(saved_ball_used: int, lending_rate_used: float) -> int:
    """参考指標：貯玉使用分を現金換算した場合の投資額（6.6）。保存はしない、表示専用。"""
    return round(saved_ball_used * lending_rate_used)
