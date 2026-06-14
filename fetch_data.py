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

# 監視リスト: 財務が比較的安定した大型・高配当株（個別株はあくまで「おまけ」）
WATCH = {
    "8306.T": "三菱UFJ",
    "8316.T": "三井住友FG",
    "8411.T": "みずほFG",
    "8058.T": "三菱商事",
    "8001.T": "伊藤忠商事",
    "8031.T": "三井物産",
    "2914.T": "JT",
    "9432.T": "NTT",
    "9433.T": "KDDI",
    "9434.T": "ソフトバンク",
    "4502.T": "武田薬品",
    "8766.T": "東京海上",
    "5108.T": "ブリヂストン",
    "7203.T": "トヨタ自動車",
    "1605.T": "INPEX",
    "8591.T": "オリックス",
}
# 配当＋株主優待ねらいの個別株（NISA外・特定口座向け）。
# 優待内容は変更・廃止されるため、各社IR/証券アプリで必ず最新を確認すること。
# (証券コード: (社名, 優待の概要, 優待に必要な株数の目安))
YUTAI = {
    "8267.T": ("イオン", "オーナーズカードで買物金額の3〜7%キャッシュバック", "100株"),
    "2503.T": ("キリンHD", "自社製品（ビール・飲料）など", "100株"),
    "9831.T": ("ヤマダHD", "店舗で使える買物優待券", "100株"),
    "8233.T": ("高島屋", "優待カード（10%割引・限度額あり）", "100株"),
    "9020.T": ("JR東日本", "運賃割引券・グループ優待券", "100株"),
    "2811.T": ("カゴメ", "自社製品の詰め合わせ", "100株"),
    "7164.T": ("全国保証", "QUOカード（高配当が魅力）", "100株"),
    "9202.T": ("ANA HD", "国内線の搭乗割引券", "100株"),
    "2579.T": ("コカ・コーラBJH", "自社製品（飲料）", "100株"),
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


def _price_metrics(tk: str) -> dict | None:
    """価格・1年高値からの下落率・直近5日変化・配当利回りを返す共通処理。"""
    t = yf.Ticker(tk)
    h = t.history(period="1y")
    closes = h["Close"].dropna()
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
    dd = (price / hi - 1) * 100
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
        "drawdown": round(dd, 1),
        "ret5": round(ret5, 1),
        "yield_pct": yield_pct,
        "plunge": ret5 <= -7.0,   # 5日で-7%超 = 普段より大きな下落
    }


def fetch_watch(tk: str, name: str) -> dict | None:
    """監視リスト用（高配当の大型株）。"""
    try:
        m = _price_metrics(tk)
        if m is None:
            return None
        m["name"] = name
        return m
    except Exception:
        return None


def fetch_yutai(tk: str, name: str, perk: str, shares: str) -> dict | None:
    """配当＋株主優待ねらいの個別株（NISA外向け）。"""
    try:
        m = _price_metrics(tk)
        if m is None:
            return None
        m["name"] = name
        m["perk"] = perk
        m["shares"] = shares
        return m
    except Exception:
        return None


def main():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    watch = [w for tk, nm in WATCH.items() if (w := fetch_watch(tk, nm))]
    watch.sort(key=lambda w: w["drawdown"])   # 下がっている順
    yutai = [y for tk, (nm, pk, sh) in YUTAI.items() if (y := fetch_yutai(tk, nm, pk, sh))]
    yutai.sort(key=lambda y: y["drawdown"])   # 下がっている順
    data = {
        "updated": datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M"),
        "assets": {tk: fetch_one(tk) for tk in TICKERS},
        "watch": watch,
        "yutai": yutai,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    # ファイルを直接ダブルクリックで開いても読めるよう、JS形式でも書き出す
    js_path = os.path.join(os.path.dirname(OUT), "data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.SITE_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";")
    print("wrote", OUT, "and", js_path)
    for tk, a in data["assets"].items():
        if a.get("ok"):
            print(f"  {tk}: {a['price']}円 / 1年高値から {a['drawdown']}% / "
                  f"利回り {a['yield_pct']}% / 調整中={a['adjusted']}")
        else:
            print(f"  {tk}: 取得失敗")


if __name__ == "__main__":
    main()
