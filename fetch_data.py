# -*- coding: utf-8 -*-
"""
サイト用データ生成 : コア3資産・配当株・暗号資産の価格／1年高値からの下落率／
利回りを data.json と data.js に書き出す。GitHub Actions が定期実行する。
"""
from __future__ import annotations
import json, datetime, os

import pandas as pd
import yfinance as yf

# コア3資産（毎月2万円・4:4:2・再投資）
TICKERS = ["1489.T", "2559.T", "1540.T"]

# 余剰資金で買い足す配当株（1株から手をつけやすい銘柄）。
DIVIDEND = {
    "1489.T": "日経高配当株50 ETF",
    "9432.T": "NTT",
    "2914.T": "JT",
    "8058.T": "三菱商事",
    "8766.T": "東京海上",
}

# 暗号資産（円建て）。超ハイリスク・別枠・NISA対象外・利益は雑所得課税。
CRYPTO = {
    "BTC-JPY": "ビットコイン",
    "ETH-JPY": "イーサリアム",
}
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
    n = len(closes)
    ma20 = float(closes.tail(min(20, n)).mean())

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
        "drawdown": round((price / hi - 1) * 100, 1),
        "vs_ma": round((price / ma20 - 1) * 100, 1),
        "yield_pct": yield_pct,
        "adjusted": adjusted,
        "days_since_jump": n if adjusted else None,
    }


def _price_metrics(tk: str) -> dict | None:
    """価格・1年高値からの下落率・直近5日変化・配当利回り。"""
    t = yf.Ticker(tk)
    closes = t.history(period="1y")["Close"].dropna()
    if len(closes) < 30:
        return None
    jumps = closes.pct_change().abs()
    big = jumps[jumps > 0.4]
    if len(big) > 0:
        closes = closes.loc[big.index[-1]:]
        if len(closes) < 10:
            return None
    price = float(closes.iloc[-1])
    hi = float(closes.max())
    ret5 = (price / float(closes.iloc[-6]) - 1) * 100 if len(closes) > 6 else 0.0
    yield_pct = None
    divs = t.dividends
    if len(divs) > 0:
        cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
        last12 = divs[divs.index >= cutoff]
        if len(last12) > 0:
            yield_pct = round(float(last12.sum()) / price * 100, 2)
    return {
        "code": tk.replace(".T", ""),
        "price": round(price, 1),
        "drawdown": round((price / hi - 1) * 100, 1),
        "ret5": round(ret5, 1),
        "yield_pct": yield_pct,
        "plunge": ret5 <= -7.0,
    }


def fetch_dividend(tk: str, name: str) -> dict | None:
    try:
        m = _price_metrics(tk)
        if m is None:
            return None
        m["name"] = name
        return m
    except Exception:
        return None


def fetch_crypto(tk: str, name: str) -> dict | None:
    """暗号資産（円建て）。1年高値からの下落率・25日平均比・直近7日変化。"""
    try:
        h = yf.Ticker(tk).history(period="1y")["Close"].dropna()
        if len(h) < 30:
            return None
        price = float(h.iloc[-1])
        hi = float(h.max())
        ma25 = float(h.tail(25).mean())
        ret7 = (price / float(h.iloc[-8]) - 1) * 100 if len(h) > 8 else 0.0
        return {
            "code": tk.replace("-JPY", ""),
            "name": name,
            "price": round(price),
            "high1y": round(hi),
            "drawdown": round((price / hi - 1) * 100, 1),
            "vs_ma": round((price / ma25 - 1) * 100, 1),
            "ret7": round(ret7, 1),
        }
    except Exception:
        return None


def main():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    dividend = [d for tk, nm in DIVIDEND.items() if (d := fetch_dividend(tk, nm))]
    dividend.sort(key=lambda d: d["drawdown"])   # 安い順
    crypto = [c for tk, nm in CRYPTO.items() if (c := fetch_crypto(tk, nm))]
    data = {
        "updated": datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M"),
        "assets": {tk: fetch_one(tk) for tk in TICKERS},
        "dividend": dividend,
        "crypto": crypto,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    js_path = os.path.join(os.path.dirname(OUT), "data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.SITE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";")
    print("wrote", OUT, "and", js_path)
    for tk, a in data["assets"].items():
        print(f"  core {tk}: {a.get('price')} / DD {a.get('drawdown')}%")
    for d in dividend:
        print(f"  配当 {d['name']}({d['code']}): {d['price']}円 DD{d['drawdown']}% 利回り{d['yield_pct']}%")


if __name__ == "__main__":
    main()
