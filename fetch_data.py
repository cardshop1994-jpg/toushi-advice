# -*- coding: utf-8 -*-
"""
サイト用データ生成 : 6資産（オルカン・1489・NTT・三菱商事・東京海上・金）と
暗号資産の価格／1年高値からの下落率／利回りを data.json と data.js に書き出す。
GitHub Actions が3時間おきに自動実行（無料）。
"""
from __future__ import annotations
import json, datetime, os

import pandas as pd
import yfinance as yf

# 6資産プラン：(ティッカー) -> (表示名, 目標比率)
# 4:4:2 = オルカン40 / 高配当40（4銘柄×10）/ 金20
PLAN = {
    "2559.T": ("オルカン（全世界株）", 0.40),
    "1489.T": ("日経高配当株50 ETF", 0.10),
    "9432.T": ("NTT", 0.10),
    "8058.T": ("三菱商事", 0.10),
    "8766.T": ("東京海上", 0.10),
    "1540.T": ("金（ゴールド）", 0.20),
}

# 暗号資産（円建て）。超ハイリスク・別枠・NISA対象外・利益は雑所得課税。
CRYPTO = {
    "BTC-JPY": "ビットコイン",
    "ETH-JPY": "イーサリアム",
}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def fetch_asset(tk: str) -> dict | None:
    t = yf.Ticker(tk)
    closes = t.history(period="1y")["Close"].dropna()
    if len(closes) < 10:
        return None
    # 分割・データ異常（1日で±40%超の飛び）はその日以降だけで判定
    jumps = closes.pct_change().abs()
    big = jumps[jumps > 0.4]
    adjusted = len(big) > 0
    if adjusted:
        closes = closes.loc[big.index[-1]:]
    price = float(closes.iloc[-1])
    hi = float(closes.max())
    n = len(closes)
    yield_pct = None
    if not adjusted:
        divs = t.dividends
        if len(divs) > 0:
            cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
            last12 = divs[divs.index >= cutoff]
            if len(last12) > 0:
                yield_pct = round(float(last12.sum()) / price * 100, 2)
    return {
        "code": tk.replace(".T", ""),
        "price": round(price, 1),
        "high1y": round(hi, 1),
        "drawdown": round((price / hi - 1) * 100, 1),
        "yield_pct": yield_pct,
        "adjusted": adjusted,
        "days_since_jump": n if adjusted else None,
    }


def fetch_crypto(tk: str, name: str) -> dict | None:
    try:
        h = yf.Ticker(tk).history(period="1y")["Close"].dropna()
        if len(h) < 30:
            return None
        price = float(h.iloc[-1]); hi = float(h.max()); ma25 = float(h.tail(25).mean())
        ret7 = (price / float(h.iloc[-8]) - 1) * 100 if len(h) > 8 else 0.0
        return {
            "code": tk.replace("-JPY", ""), "name": name, "price": round(price),
            "high1y": round(hi), "drawdown": round((price / hi - 1) * 100, 1),
            "vs_ma": round((price / ma25 - 1) * 100, 1), "ret7": round(ret7, 1),
        }
    except Exception:
        return None


def main():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    plan = []
    for tk, (name, target) in PLAN.items():
        try:
            a = fetch_asset(tk)
        except Exception:
            a = None
        if a:
            a["name"] = name
            a["target"] = target
            plan.append(a)
    crypto = [c for tk, nm in CRYPTO.items() if (c := fetch_crypto(tk, nm))]
    data = {
        "updated": datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M"),
        "plan": plan,
        "crypto": crypto,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(os.path.dirname(OUT), "data.js"), "w", encoding="utf-8") as f:
        f.write("window.SITE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";")
    print("wrote data.json and data.js")
    for a in plan:
        print(f"  {a['name']}({a['code']}): {a['price']}円 DD{a['drawdown']}% "
              f"利回り{a['yield_pct']} 目標{int(a['target']*100)}%")


if __name__ == "__main__":
    main()
