# -*- coding: utf-8 -*-
"""
サイト用データ生成 : 3銘柄の価格・1年高値からの下落率・分配金利回りを
data.json に書き出す。GitHub Actions が毎営業日の取引終了後に自動実行する。
"""
from __future__ import annotations
import json, datetime, os

import pandas as pd
import yfinance as yf

TICKERS = ["1489.T", "2559.T", "1540.T"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def fetch_one(tk: str) -> dict:
    t = yf.Ticker(tk)
    h = t.history(period="1y")
    closes = h["Close"].dropna()
    if len(closes) < 10:
        return {"ok": False}

    # 分割・データ異常（1日で±40%超の飛び）があれば、その日以降だけで判定する
    jumps = closes.pct_change().abs()
    big = jumps[jumps > 0.4]
    adjusted = False
    if len(big) > 0:
        closes = closes.loc[big.index[-1]:]
        adjusted = True

    price = float(closes.iloc[-1])
    hi = float(closes.max())
    drawdown = (price / hi - 1) * 100  # 高値からの下落率（マイナス値）

    n = len(closes)
    ma20 = float(closes.tail(min(20, n)).mean())
    vs_ma = (price / ma20 - 1) * 100

    # 直近1年の分配金合計 → いま買った場合の利回り（分割調整中は計算しない）
    yield_pct = None
    if not adjusted:
        divs = t.dividends
        if len(divs) > 0:
            cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
            last12 = divs[divs.index >= cutoff]
            if len(last12) > 0:
                yield_pct = round(float(last12.sum()) / price * 100, 2)

    return {
        "ok": True,
        "price": round(price, 1),
        "high1y": round(hi, 1),
        "drawdown": round(drawdown, 1),
        "vs_ma": round(vs_ma, 1),
        "yield_pct": yield_pct,
        "adjusted": adjusted,            # 分割等でデータ調整中フラグ
        "days_since_jump": n if adjusted else None,
    }


def main():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    data = {
        "updated": datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M"),
        "assets": {tk: fetch_one(tk) for tk in TICKERS},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)
    for tk, a in data["assets"].items():
        if a.get("ok"):
            print(f"  {tk}: {a['price']}円 / 1年高値から {a['drawdown']}% / "
                  f"利回り {a['yield_pct']}% / 調整中={a['adjusted']}")
        else:
            print(f"  {tk}: 取得失敗")


if __name__ == "__main__":
    main()
