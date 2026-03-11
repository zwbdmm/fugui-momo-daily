import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import baostock as bs
import pandas as pd
import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_OUT_DIR = SKILL_DIR / "output"
DEFAULT_STOCKS_FILE = SKILL_DIR / "references" / "default-stocks.json"

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_EM_KLINE_CACHE = {}


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a Markdown stock analysis report.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Archive date, format YYYY-MM-DD")
    parser.add_argument("--version", default="11", help="Report version, default 11")
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Output directory (default: skill-local output/)",
    )
    parser.add_argument(
        "--stocks-file",
        default=str(DEFAULT_STOCKS_FILE),
        help="JSON file describing the stock pool",
    )
    parser.add_argument(
        "--dividend-report",
        default=None,
        help="Path to the dividend summary; defaults to the same-date file in out-dir",
    )
    return parser.parse_args()


def load_stocks(path: str):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("stocks file must be a non-empty JSON array")
    required = {"name", "code", "prefix"}
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"invalid stock entry at index {idx}: {item!r}")
        item["code"] = str(item["code"])
        item["prefix"] = str(item["prefix"]).lower()
    return data


def is_missing(v) -> bool:
    return v is None or pd.isna(v)


def format_money(v):
    return f"{v:.2f}元" if not is_missing(v) else "-"


def format_pct(v):
    return f"{v * 100:.2f}%" if not is_missing(v) else "-"


def rolling_last(series: pd.Series, window: int):
    if len(series) < window:
        return None
    value = series.rolling(window).mean().iloc[-1]
    if pd.isna(value):
        return None
    return round(float(value), 2)


def format_dividend_code(prefix: str, code: str) -> str:
    if prefix == "hk":
        return f"HK{code.lstrip('0')}"
    return f"{prefix}{code}"


def format_report_code(prefix: str, code: str) -> str:
    if prefix == "hk":
        return f"HK{code.lstrip('0')}"
    return f"{prefix}{code}"


def fetch_price(prefix: str, code: str):
    text = requests.get(f"https://qt.gtimg.cn/q={prefix}{code}", timeout=15).content.decode("utf-8", errors="ignore")
    m = re.search(r'="([^"]+)"', text)
    if not m:
        raise RuntimeError(f"price parse failed: {prefix}{code}")
    parts = m.group(1).split("~")
    return float(parts[3])


def arrow_symbol(curr: float, prev: float) -> str:
    if curr > prev:
        return "↑"
    if curr < prev:
        return "↓"
    return "→"


def recent_trend_symbols(prefix: str, code: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    closes = []

    if prefix == "hk":
        daily = fetch_em_klines(code, 101, 0, start.replace("-", ""), today.replace("-", ""))
        for item in daily:
            parts = item.split(",")
            closes.append(float(parts[2]))
    else:
        rs = bs.query_history_k_data_plus(
            f"{prefix}.{code}",
            "date,close",
            start_date=start,
            end_date=today,
            frequency="d",
            adjustflag="3",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        closes = [float(row[1]) for row in rows]

    if len(closes) < 4:
        return "→→→"

    recent = closes[-4:]
    arrows = [
        arrow_symbol(recent[1], recent[0]),
        arrow_symbol(recent[2], recent[1]),
        arrow_symbol(recent[3], recent[2]),
    ]
    return "".join(arrows)


def fetch_em_klines(code: str, klt: int, fqt: int, beg: str, end: str):
    key = (code, klt, fqt, beg, end)
    if key in _EM_KLINE_CACHE:
        return _EM_KLINE_CACHE[key]
    secid = f"116.{code.zfill(5)}"
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt={klt}&fqt={fqt}&beg={beg}&end={end}"
    )
    resp = requests.get(url, timeout=20, headers=_HEADERS)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    klines = data.get("klines") or []
    _EM_KLINE_CACHE[key] = klines
    return klines


def fetch_ma(prefix: str, code: str):
    end_date = datetime.now().strftime("%Y-%m-%d")
    if prefix == "hk":
        daily = fetch_em_klines(code, 101, 1, "20240101", end_date.replace("-", ""))
        weekly = fetch_em_klines(code, 102, 1, "20240101", end_date.replace("-", ""))
        monthly = fetch_em_klines(code, 103, 1, "20150101", end_date.replace("-", ""))
        if not daily:
            raise RuntimeError(f"hk daily data empty: {code}")
        if not weekly:
            raise RuntimeError(f"hk weekly data empty: {code}")
        if not monthly:
            raise RuntimeError(f"hk monthly data empty: {code}")
        dclose = pd.Series([float(item.split(",")[2]) for item in daily])
        wclose = pd.Series([float(item.split(",")[2]) for item in weekly])
        mclose = pd.Series([float(item.split(",")[2]) for item in monthly])
        return {
            "ma250": rolling_last(dclose, 250),
            "ma120": rolling_last(dclose, 120),
            "ma60": rolling_last(dclose, 60),
            "ma60w": rolling_last(wclose, 60),
            "ma30w": rolling_last(wclose, 30),
            "ma20w": rolling_last(wclose, 20),
            "ma60m": rolling_last(mclose, 60),
            "ma20m": rolling_last(mclose, 20),
        }

    baocode = f"{prefix}.{code}"
    rs = bs.query_history_k_data_plus(
        baocode,
        "date,close",
        start_date="2024-01-01",
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )
    daily = []
    while rs.error_code == "0" and rs.next():
        daily.append(rs.get_row_data())
    if not daily:
        raise RuntimeError(f"daily data empty: {baocode}")
    ddf = pd.DataFrame(daily, columns=rs.fields)
    dclose = ddf["close"].astype(float)

    rsw = bs.query_history_k_data_plus(
        baocode,
        "date,close",
        start_date="2024-01-01",
        end_date=end_date,
        frequency="w",
        adjustflag="2",
    )
    weekly = []
    while rsw.error_code == "0" and rsw.next():
        weekly.append(rsw.get_row_data())
    if not weekly:
        raise RuntimeError(f"weekly data empty: {baocode}")
    wdf = pd.DataFrame(weekly, columns=rsw.fields)
    wclose = wdf["close"].astype(float)

    rsm = bs.query_history_k_data_plus(
        baocode,
        "date,close",
        start_date="2015-01-01",
        end_date=end_date,
        frequency="m",
        adjustflag="2",
    )
    monthly = []
    while rsm.error_code == "0" and rsm.next():
        monthly.append(rsm.get_row_data())
    if not monthly:
        raise RuntimeError(f"monthly data empty: {baocode}")
    mdf = pd.DataFrame(monthly, columns=rsm.fields)
    mclose = mdf["close"].astype(float)

    return {
        "ma250": rolling_last(dclose, 250),
        "ma120": rolling_last(dclose, 120),
        "ma60": rolling_last(dclose, 60),
        "ma60w": rolling_last(wclose, 60),
        "ma30w": rolling_last(wclose, 30),
        "ma20w": rolling_last(wclose, 20),
        "ma60m": rolling_last(mclose, 60),
        "ma20m": rolling_last(mclose, 20),
    }


def near(a: float, b: float, tol: float = 0.0027):
    return abs(a - b) / b <= tol


def price_at_or_below(price: float, line_value: float, tol: float = 0.0027):
    return price <= line_value * (1 + tol)


def line_at_or_below(value: float, line_value: float, tol: float = 0.0027):
    if is_missing(value) or is_missing(line_value):
        return False
    return value <= line_value * (1 + tol)


def parse_dividend_summary(path: Path):
    text = path.read_text(encoding="utf-8")
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| 股票 | 代码 | 现价 | 2026至今除息日"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 12:
            continue
        rows.append(
            {
                "name": parts[0],
                "code": parts[1],
                "price": parts[2],
                "y2026_dates": parts[3],
                "y2026_div": parts[4],
                "y2026_yield": parts[5],
                "y2025_dates": parts[6],
                "y2025_div": parts[7],
                "y2025_yield": parts[8],
                "y2024_dates": parts[9],
                "y2024_div": parts[10],
                "y2024_yield": parts[11],
            }
        )
    return {row["code"]: row for row in rows}


def remark_price_vs_line(price, line_value, label):
    threshold = line_value * 1.0027
    if price <= line_value:
        return f"价格低于或等于{label}，满足条件"
    if price <= threshold:
        return f"价格高于{label}，但在0.27%以内，满足条件"
    return f"价格高于{label}且超过0.27%，不满足条件"


def remark_near(a, b, higher_label, lower_label):
    diff = (a - b) / b
    if abs(diff) <= 0.0027:
        return f"{higher_label}接近{lower_label}，满足条件"
    if a > b:
        return f"{higher_label}明显高于{lower_label}"
    return f"{higher_label}低于{lower_label}"


def remark_cycle_state(value, line_value, cycle_label):
    if is_missing(value) or is_missing(line_value):
        return "数据不足"
    if value <= line_value * 1.0027:
        return f"{cycle_label}休息"
    return f"{cycle_label}干活"


def main():
    args = parse_args()
    stocks = load_stocks(args.stocks_file)
    out_dir = Path(args.out_dir)
    dividend_report = Path(args.dividend_report) if args.dividend_report else out_dir / f"股票分红信息整合总表_{args.date}.md"
    if not dividend_report.exists():
        raise FileNotFoundError(f"dividend report not found: {dividend_report}")

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")

    try:
        dividend_map = parse_dividend_summary(dividend_report)
        rows = []
        for s in stocks:
            price = round(fetch_price(s["prefix"], s["code"]), 2)
            ma = fetch_ma(s["prefix"], s["code"])
            trend = recent_trend_symbols(s["prefix"], s["code"])
            rows.append(
                {
                    "name": s["name"],
                    "code": format_report_code(s["prefix"], s["code"]),
                    "div_code": format_dividend_code(s["prefix"], s["code"]),
                    "price": price,
                    "trend": trend,
                    **ma,
                }
            )
    finally:
        bs.logout()

    judgement_250 = []
    judgement_120_60 = []
    judgement_30w_20w = []
    judgement_price_60w = []
    judgement_20w_60w = []
    judgement_20m_60m = []

    for r in rows:
        j250 = price_at_or_below(r["price"], r["ma250"])
        j120 = near(r["ma120"], r["ma60"])
        j30 = near(r["ma30w"], r["ma20w"])
        j60wp = price_at_or_below(r["price"], r["ma60w"])
        j2060 = line_at_or_below(r["ma20w"], r["ma60w"])
        j20m60m = line_at_or_below(r["ma20m"], r["ma60m"])
        r["j250"] = j250
        r["j120"] = j120
        r["j30"] = j30
        r["j60wp"] = j60wp
        r["j2060"] = j2060
        r["j20m60m"] = j20m60m
        r["score"] = int(j250) + int(j120) + int(j30) + int(j60wp) + int(j2060) + int(j20m60m)

        judgement_250.append(
            {
                "name": r["name"],
                "price": r["price"],
                "ma250": r["ma250"],
                "diff": (r["price"] - r["ma250"]) / r["ma250"],
                "ok": j250,
                "remark": remark_price_vs_line(r["price"], r["ma250"], "250日均线"),
            }
        )
        judgement_120_60.append(
            {
                "name": r["name"],
                "ma120": r["ma120"],
                "ma60": r["ma60"],
                "diff": abs(r["ma120"] - r["ma60"]) / r["ma60"],
                "ok": j120,
                "remark": remark_near(r["ma120"], r["ma60"], "120日", "60日"),
            }
        )
        judgement_30w_20w.append(
            {
                "name": r["name"],
                "ma30w": r["ma30w"],
                "ma20w": r["ma20w"],
                "diff": abs(r["ma30w"] - r["ma20w"]) / r["ma20w"],
                "ok": j30,
                "remark": remark_near(r["ma30w"], r["ma20w"], "30周", "20周"),
            }
        )
        judgement_price_60w.append(
            {
                "name": r["name"],
                "price": r["price"],
                "ma60w": r["ma60w"],
                "diff": (r["price"] - r["ma60w"]) / r["ma60w"],
                "ok": j60wp,
                "remark": remark_price_vs_line(r["price"], r["ma60w"], "60周均线"),
            }
        )
        judgement_20w_60w.append(
            {
                "name": r["name"],
                "ma20w": r["ma20w"],
                "ma60w": r["ma60w"],
                "diff": None if is_missing(r["ma20w"]) or is_missing(r["ma60w"]) else (r["ma20w"] - r["ma60w"]) / r["ma60w"],
                "ok": j2060,
                "remark": remark_cycle_state(r["ma20w"], r["ma60w"], "小周期"),
            }
        )
        judgement_20m_60m.append(
            {
                "name": r["name"],
                "ma20m": r["ma20m"],
                "ma60m": r["ma60m"],
                "diff": None if is_missing(r["ma20m"]) or is_missing(r["ma60m"]) else (r["ma20m"] - r["ma60m"]) / r["ma60m"],
                "ok": j20m60m,
                "remark": remark_cycle_state(r["ma20m"], r["ma60m"], "大周期"),
            }
        )

    ranked = sorted(rows, key=lambda x: (-x["score"], abs(x["price"] - x["ma250"]) / x["ma250"]))
    now = datetime.now()
    now_cn = f"{now.year}年{now.month}月{now.day}日 {now:%H:%M}"

    lines = []
    lines.append(f"# 股票分析表格 - 版本{args.version}")
    lines.append("")
    lines.append(f"**更新时间：** {now_cn}  ")
    lines.append(f"**股票池文件：** `{Path(args.stocks_file).name}`  ")
    lines.append(f"**样本数量：** {len(stocks)}  ")
    lines.append("**重要说明：**")
    lines.append("- **均线部分**：A 股使用 Baostock 前复权数据；港股使用东财前复权日/周/月 K 线。")
    lines.append("- **现价部分**：使用腾讯财经接口。")
    lines.append("- **分红部分**：主分红 source 为同花顺 F10 分红页，支持表来自同日期生成的股息率整合总表。")
    lines.append("- **箭头说明**：当前价格后面的 3 个箭头按“从早到近”展示最近 3 个交易日走势；上涨记 `↑`，下跌记 `↓`，持平记 `→`。")
    lines.append("- **判定标准**：章节 2 统一展示偏差率；2.5 / 2.6 使用“附近及以下”逻辑，即指标值 ≤ 长周期均线 × 1.0027 视为满足。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 一、股票数据汇总（{len(stocks)}只）")
    lines.append("")
    lines.append("| 股票代码 | 股票名称 | 当前价格 | 250日均线 | 120日均线 | 60日均线 | 60周均线 | 30周均线 | 20周均线 | 60月均线 | 20月均线 |")
    lines.append("|---------|---------|---------|----------|----------|---------|---------|---------|---------|---------|---------|")
    for r in rows:
        lines.append(f"| {r['code']} | {r['name']} | {format_money(r['price'])} {r['trend']} | {format_money(r['ma250'])} | {format_money(r['ma120'])} | {format_money(r['ma60'])} | {format_money(r['ma60w'])} | {format_money(r['ma30w'])} | {format_money(r['ma20w'])} | {format_money(r['ma60m'])} | {format_money(r['ma20m'])} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 二、均线关系判断")
    lines.append("")
    lines.append("### 1. 250日价格/低（股价 ≤ 250日均线 × 1.0027）")
    lines.append("")
    lines.append("| 股票名称 | 当前价格 | 250日均线 | 偏差率 | 是否满足 | 备注 |")
    lines.append("|---------|---------|----------|--------|---------|------|")
    for j in judgement_250:
        lines.append(f"| {j['name']} | {format_money(j['price'])} | {format_money(j['ma250'])} | {format_pct(j['diff'])} | {'✅ Y' if j['ok'] else '❌ N'} | {j['remark']} |")
    lines.append("")
    lines.append("**说明：** 这里的“250日价格/低”定义为：股价只要**低于250日均线**，或者**高于250日均线但不超过0.27%**，都算满足条件；表中的偏差率按 `(当前价格 - 250日均线) / 250日均线` 展示。")

    lines.append("")
    lines.append("### 2. 120日在60日低（|MA120 - MA60| / MA60 ≤ 0.0027）")
    lines.append("")
    lines.append("| 股票名称 | 120日均线 | 60日均线 | 偏差率 | 是否满足 | 备注 |")
    lines.append("|---------|----------|---------|--------|---------|------|")
    for j in judgement_120_60:
        lines.append(f"| {j['name']} | {format_money(j['ma120'])} | {format_money(j['ma60'])} | {format_pct(j['diff'])} | {'✅ Y' if j['ok'] else '❌ N'} | {j['remark']} |")
    lines.append("")
    lines.append("**说明：** 判断条件为120日均线与60日均线的绝对偏差不超过0.27%。")

    lines.append("")
    lines.append("### 3. 30周在20周附近（|MA30W - MA20W| / MA20W ≤ 0.0027）")
    lines.append("")
    lines.append("| 股票名称 | 30周均线 | 20周均线 | 偏差率 | 是否满足 | 备注 |")
    lines.append("|---------|---------|---------|--------|---------|------|")
    for j in judgement_30w_20w:
        lines.append(f"| {j['name']} | {format_money(j['ma30w'])} | {format_money(j['ma20w'])} | {format_pct(j['diff'])} | {'✅ Y' if j['ok'] else '❌ N'} | {j['remark']} |")
    lines.append("")
    lines.append("**说明：** 判断条件为30周均线与20周均线的绝对偏差不超过0.27%。")

    lines.append("")
    lines.append("### 4. 当前股价在60周线附近或者以下（股价 ≤ 60周均线 × 1.0027）")
    lines.append("")
    lines.append("| 股票名称 | 当前价格 | 60周均线 | 偏差率 | 是否满足 | 备注 |")
    lines.append("|---------|---------|---------|--------|---------|------|")
    for j in judgement_price_60w:
        lines.append(f"| {j['name']} | {format_money(j['price'])} | {format_money(j['ma60w'])} | {format_pct(j['diff'])} | {'✅ Y' if j['ok'] else '❌ N'} | {j['remark']} |")
    lines.append("")
    lines.append("**说明：** 这里的“60周线附近或者以下”定义为：股价只要**低于60周均线**，或者**高于60周均线但不超过0.27%**，都算满足条件；表中的偏差率按 `(当前价格 - 60周均线) / 60周均线` 展示。")

    lines.append("")
    lines.append("### 5. 20周线是不是在60周线附近及以下（20周线 ≤ 60周线 × 1.0027）")
    lines.append("")
    lines.append("| 股票名称 | 20周均线 | 60周均线 | 偏差率 | 是否满足 | 备注 |")
    lines.append("|---------|---------|---------|--------|---------|------|")
    for j in judgement_20w_60w:
        lines.append(f"| {j['name']} | {format_money(j['ma20w'])} | {format_money(j['ma60w'])} | {format_pct(j['diff'])} | {'✅ Y' if j['ok'] else '❌ N'} | {j['remark']} |")
    lines.append("")
    lines.append("**说明：** 判断条件为20周线在60周线附近及以下；若 20周线 ≤ 60周线 × 1.0027，则记为“小周期休息”，否则记为“小周期干活”。")

    lines.append("")
    lines.append("### 6. 20月线是不是在60月线附近及以下（20月线 ≤ 60月线 × 1.0027）")
    lines.append("")
    lines.append("| 股票名称 | 20月均线 | 60月均线 | 偏差率 | 是否满足 | 备注 |")
    lines.append("|---------|---------|---------|--------|---------|------|")
    for j in judgement_20m_60m:
        lines.append(f"| {j['name']} | {format_money(j['ma20m'])} | {format_money(j['ma60m'])} | {format_pct(j['diff'])} | {'✅ Y' if j['ok'] else '❌ N'} | {j['remark']} |")
    lines.append("")
    lines.append("**说明：** 判断条件为20月线在60月线附近及以下；若 20月线 ≤ 60月线 × 1.0027，则记为“大周期休息”，否则记为“大周期干活”。")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 三、分红与股息率汇总（{len(stocks)}只，同日刷新）")
    lines.append("")
    lines.append("> 口径说明：")
    lines.append("> - `2026至今股息率` = 2026年至今已除息分红累计 ÷ 10 ÷ 当前价")
    lines.append("> - `2025全年股息率` = 2025年内已除息分红累计 ÷ 10 ÷ 当前价")
    lines.append("> - `2024全年股息率` = 2024年每次分红分别 ÷ 当次除息日收盘价，再把单次股息率相加")
    lines.append("> - 年度归属按 **除权除息日** 所在年份划分，不按报告期年份划分")
    lines.append("")
    lines.append("| 股票 | 代码 | 现价 | 2026至今除息日 | 2026至今分红(10股) | 2026至今股息率 | 2025全年除息日 | 2025全年分红(10股) | 2025全年股息率 | 2024全年除息日 | 2024全年分红(10股) | 2024全年股息率 |")
    lines.append("|---|---|---:|---|---:|---:|---|---:|---:|---|---:|---:|")
    for s in stocks:
        key = format_dividend_code(s["prefix"], s["code"])
        d = dividend_map[key]
        lines.append(f"| {d['name']} | {d['code']} | {d['price']} | {d['y2026_dates']} | {d['y2026_div']} | {d['y2026_yield']} | {d['y2025_dates']} | {d['y2025_div']} | {d['y2025_yield']} | {d['y2024_dates']} | {d['y2024_div']} | {d['y2024_yield']} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 四、综合观察（按技术条件满足数排序）")
    lines.append("")
    lines.append("| 排名 | 股票 | 代码 | 满足条件数 | 备注 |")
    lines.append("|---:|---|---|---:|---|")
    for i, r in enumerate(ranked, start=1):
        remarks = []
        if r.get("j250"):
            remarks.append("250日价格/低")
        if r.get("j120"):
            remarks.append("120日≈60日")
        if r.get("j30"):
            remarks.append("30周≈20周")
        if r.get("j60wp"):
            remarks.append("价格≤60周线*1.0027")
        if r.get("j2060"):
            remarks.append("20周≤60周*1.0027")
        if r.get("j20m60m"):
            remarks.append("20月≤60月*1.0027")
        lines.append(f"| {i} | {r['name']} | {r['code']} | {r['score']} | {'；'.join(remarks) if remarks else '暂无条件满足'} |")

    lines.append("")
    lines.append("### 重点结论")
    lines.append("")
    lines.append(f"- **当前技术条件满足数最高的股票**：{ranked[0]['name']}（{ranked[0]['score']} 项）。")
    lines.append(f"- **这版最重要的特点**：统一输出 {len(stocks)} 只股票的均线、分红与最近 3 日方向符号，并补入 20月 / 60月的大周期判断。")
    lines.append("- **这版的关键规则**：均线使用前复权口径；2.1 和 2.4 采用“低于均线或高于均线但不超过0.27%即满足”；2.5 / 2.6 采用“附近及以下”逻辑。")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 五、版本{args.version}的批判性结论")
    lines.append("")
    lines.append("- 当前版本把均线口径、分红口径和偏差率展示尽量统一，但仍然依赖外部数据源实时可用。")
    lines.append("- 如果需要更严谨的投资决策支持，可以继续追加综合评分、逐笔分红明细引用和更长周期的趋势观察。")
    lines.append("- 这个公开版 skill 默认使用可配置股票池，更适合作为模板二次修改，而不是直接绑定某个私有工作流。")
    lines.append("")
    lines.append(f"**这是基于 {len(stocks)} 只股票、按前复权均线与统一偏差率口径重算后的版本{args.version}。**")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"股票分析表格_版本{args.version}_{args.date}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("DONE")


if __name__ == "__main__":
    main()
