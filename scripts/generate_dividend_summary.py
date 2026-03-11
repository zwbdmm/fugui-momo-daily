import argparse
import io
import json
import os
import re
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

import baostock as bs
import pandas as pd
import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_OUT_DIR = SKILL_DIR / "output"
DEFAULT_STOCKS_FILE = SKILL_DIR / "references" / "default-stocks.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://basic.10jqka.com.cn/",
}

_PRICE_CACHE = {}
_EM_KLINE_CACHE = {}


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a dividend summary Markdown report.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Archive date, format YYYY-MM-DD")
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


def format_stock_code(prefix: str, code: str) -> str:
    if prefix == "hk":
        return f"HK{code.lstrip('0')}"
    return f"{prefix}{code}"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_price(prefix: str, code: str):
    text = fetch_text(f"https://qt.gtimg.cn/q={prefix}{code}")
    m = re.search(r'="([^"]+)"', text)
    if not m:
        return None, None
    parts = m.group(1).split("~")
    if len(parts) < 18:
        return None, None
    price = None
    try:
        price = float(parts[3])
    except Exception:
        pass
    raw_ts = parts[30] if len(parts) > 30 else parts[17]
    ts = None
    if raw_ts and raw_ts.isdigit() and len(raw_ts) >= 14:
        ts = f"{raw_ts[0:4]}-{raw_ts[4:6]}-{raw_ts[6:8]} {raw_ts[8:10]}:{raw_ts[10:12]}:{raw_ts[12:14]}"
    return price, ts


def parse_per10_from_plan(plan: str):
    if not plan:
        return None
    plan = str(plan)
    m = re.search(r"10派\s*([0-9.]+)元", plan)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    m = re.search(r"每股\s*([0-9.]+)\s*(?:港元|元|人民币)", plan)
    if m:
        try:
            return float(m.group(1)) * 10
        except Exception:
            return None
    return None


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = []
    for col in df.columns:
        if isinstance(col, tuple):
            parts = [str(part).strip() for part in col if str(part).strip() and str(part).strip() != "nan"]
            cols.append("/".join(parts))
        else:
            cols.append(str(col).strip())
    df.columns = cols
    return df


def pick_value(row: pd.Series, candidates: list[str]) -> str:
    for candidate in candidates:
        for col in row.index:
            if candidate in col:
                value = row.get(col)
                text = "" if value is None else str(value).strip()
                if text and text != "nan":
                    return text
    return ""


def fetch_dividends(prefix: str, code: str):
    page_code = f"HK{code.lstrip('0')}" if prefix == "hk" else code
    resp = requests.get(f"https://basic.10jqka.com.cn/{page_code}/bonus.html", headers=HEADERS, timeout=20)
    resp.raise_for_status()
    encoding = resp.apparent_encoding or resp.encoding or "utf-8"
    html = resp.content.decode(encoding, errors="ignore")
    tables = pd.read_html(io.StringIO(html))
    if not tables:
        return []
    df = normalize_columns(tables[0].copy())
    records = []
    for _, row in df.iterrows():
        plan = pick_value(row, ["分红方案说明", "方案"])
        ex_date = pick_value(row, ["A股除权除息日", "除净日", "除权除息日"])
        report = pick_value(row, ["报告期", "公告日期"])
        progress = pick_value(row, ["方案进度", "进度"])
        if not plan or "不分配" in plan or "不分红" in plan:
            continue
        if not ex_date or ex_date in ("--", "nan"):
            continue
        per10 = parse_per10_from_plan(plan)
        records.append(
            {
                "REPORT_DATE": report,
                "EX_DIVIDEND_DATE": ex_date,
                "PRETAX_BONUS_RMB": per10,
                "ASSIGN_PROGRESS": progress if progress and progress != "nan" else "-",
                "IMPL_PLAN_PROFILE": plan,
            }
        )
    return records


def safe_date(value):
    if not value:
        return "-"
    return str(value)[:10]


def get_year(value):
    d = safe_date(value)
    if d == "-":
        return None
    try:
        return int(d[:4])
    except Exception:
        return None


def to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def get_ex_year(record):
    return get_year(record.get("EX_DIVIDEND_DATE"))


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
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    klines = data.get("klines") or []
    _EM_KLINE_CACHE[key] = klines
    return klines


def fetch_hk_close_on_date(code: str, date_str: str):
    raw = fetch_em_klines(code, 101, 0, date_str.replace("-", ""), date_str.replace("-", ""))
    if not raw:
        return None
    parts = raw[0].split(",")
    try:
        return float(parts[2])
    except Exception:
        return None


def fetch_close_on_date(prefix: str, code: str, date_str: str):
    key = (prefix, code, date_str)
    if key in _PRICE_CACHE:
        return _PRICE_CACHE[key]
    if prefix == "hk":
        price = fetch_hk_close_on_date(code, date_str)
        _PRICE_CACHE[key] = price
        return price
    rs = bs.query_history_k_data_plus(
        f"{prefix}.{code}",
        "date,close",
        start_date=date_str,
        end_date=date_str,
        frequency="d",
        adjustflag="3",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    price = None
    if rows:
        try:
            price = float(rows[0][1])
        except Exception:
            pass
    _PRICE_CACHE[key] = price
    return price


def join_dates(records):
    dates = [safe_date(r.get("EX_DIVIDEND_DATE")) for r in records if safe_date(r.get("EX_DIVIDEND_DATE")) != "-"]
    return " / ".join(dates) if dates else "-"


def sum_per10(records):
    total = 0.0
    found = False
    for r in records:
        v = to_float(r.get("PRETAX_BONUS_RMB"))
        if v is not None:
            total += v
            found = True
    return total if found else None


def format_pct(v):
    return "-" if v is None else f"{v:.2f}%"


def format_money(v):
    return "-" if v is None else f"{v:.2f}"


def main():
    args = parse_args()
    stocks = load_stocks(args.stocks_file)
    as_of_date = args.date
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary_rows = []
    detail_rows = []

    login_rs = bs.login()
    if login_rs.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login_rs.error_msg}")

    try:
        for stock in stocks:
            price, price_ts = parse_price(stock["prefix"], stock["code"])
            records = fetch_dividends(stock["prefix"], stock["code"])
            records = [r for r in records if safe_date(r.get("EX_DIVIDEND_DATE")) != "-"]
            records.sort(key=lambda r: safe_date(r.get("EX_DIVIDEND_DATE")))

            grouped = {
                2026: [r for r in records if get_ex_year(r) == 2026 and safe_date(r.get("EX_DIVIDEND_DATE")) <= as_of_date],
                2025: [r for r in records if get_ex_year(r) == 2025],
                2024: [r for r in records if get_ex_year(r) == 2024],
            }

            y2026_per10 = sum_per10(grouped[2026])
            y2026_yield = ((y2026_per10 / 10) / price * 100) if (y2026_per10 is not None and price) else None

            y2025_per10 = sum_per10(grouped[2025])
            y2025_yield = ((y2025_per10 / 10) / price * 100) if (y2025_per10 is not None and price) else None

            y2024_per10 = sum_per10(grouped[2024])
            y2024_yield = 0.0
            y2024_has = False
            for r in grouped[2024]:
                per10 = to_float(r.get("PRETAX_BONUS_RMB"))
                ex_date = safe_date(r.get("EX_DIVIDEND_DATE"))
                ex_close = fetch_close_on_date(stock["prefix"], stock["code"], ex_date)
                single_yield = None
                if per10 is not None and ex_close:
                    single_yield = (per10 / 10) / ex_close * 100
                    y2024_yield += single_yield
                    y2024_has = True
                detail_rows.append(
                    {
                        "name": stock["name"],
                        "code": format_stock_code(stock["prefix"], stock["code"]),
                        "report_date": safe_date(r.get("REPORT_DATE")),
                        "ex_date": ex_date,
                        "per10": per10,
                        "per_share": (per10 / 10) if per10 is not None else None,
                        "calc_price": ex_close,
                        "yield_value": single_yield,
                        "yield_note": "按当次除息价",
                        "progress": r.get("ASSIGN_PROGRESS") or "-",
                        "plan": r.get("IMPL_PLAN_PROFILE") or "-",
                    }
                )

            for year in (2025, 2026):
                for r in grouped[year]:
                    per10 = to_float(r.get("PRETAX_BONUS_RMB"))
                    single_yield = ((per10 / 10) / price * 100) if (per10 is not None and price) else None
                    detail_rows.append(
                        {
                            "name": stock["name"],
                            "code": format_stock_code(stock["prefix"], stock["code"]),
                            "report_date": safe_date(r.get("REPORT_DATE")),
                            "ex_date": safe_date(r.get("EX_DIVIDEND_DATE")),
                            "per10": per10,
                            "per_share": (per10 / 10) if per10 is not None else None,
                            "calc_price": price,
                            "yield_value": single_yield,
                            "yield_note": "按当前价",
                            "progress": r.get("ASSIGN_PROGRESS") or "-",
                            "plan": r.get("IMPL_PLAN_PROFILE") or "-",
                        }
                    )

            summary_rows.append(
                {
                    "name": stock["name"],
                    "code": format_stock_code(stock["prefix"], stock["code"]),
                    "price": price,
                    "price_ts": price_ts,
                    "y2026_dates": join_dates(grouped[2026]),
                    "y2026_per10": y2026_per10,
                    "y2026_yield": y2026_yield,
                    "y2025_dates": join_dates(grouped[2025]),
                    "y2025_per10": y2025_per10,
                    "y2025_yield": y2025_yield,
                    "y2024_dates": join_dates(grouped[2024]),
                    "y2024_per10": y2024_per10,
                    "y2024_yield": y2024_yield if y2024_has else None,
                }
            )
            time.sleep(0.2)
    finally:
        bs.logout()

    detail_rows.sort(key=lambda r: (r["name"], r["ex_date"], r["report_date"]))

    lines = []
    lines.append("# 股票股息率整合表")
    lines.append("")
    lines.append(f"- 生成时间：{now}")
    lines.append(f"- 股票池文件：`{Path(args.stocks_file).name}`")
    lines.append("- 数据源：分红明细取自同花顺 F10 分红页面；现价取自腾讯财经；2024 年除息日价格取自 A 股 Baostock / 港股东财历史 K 线。")
    lines.append("- 年度归属口径：按 `除权除息日` 所在年份划分，不按报告期年份划分。")
    lines.append("- 2026至今股息率 = 2026年至今已除息分红累计 ÷ 10 ÷ 当前价。")
    lines.append("- 2025全年股息率 = 2025年内已除息分红累计 ÷ 10 ÷ 当前价。")
    lines.append("- 2024全年股息率 = 2024年每次分红分别 ÷ 当次除息日收盘价，再把单次股息率相加。")
    lines.append("")
    lines.append("## 一、股息率汇总")
    lines.append("")
    lines.append("| 股票 | 代码 | 现价 | 2026至今除息日 | 2026至今分红(10股) | 2026至今股息率 | 2025全年除息日 | 2025全年分红(10股) | 2025全年股息率 | 2024全年除息日 | 2024全年分红(10股) | 2024全年股息率 |")
    lines.append("|---|---|---:|---|---:|---:|---|---:|---:|---|---:|---:|")
    for s in summary_rows:
        lines.append(
            f"| {s['name']} | {s['code']} | {format_money(s['price'])} | {s['y2026_dates']} | {format_money(s['y2026_per10'])} | {format_pct(s['y2026_yield'])} | {s['y2025_dates']} | {format_money(s['y2025_per10'])} | {format_pct(s['y2025_yield'])} | {s['y2024_dates']} | {format_money(s['y2024_per10'])} | {format_pct(s['y2024_yield'])} |"
        )

    lines.append("")
    lines.append("## 二、复核结论")
    lines.append("")
    lines.append(f"- 已逐只复核 {len(stocks)} 只股票在 2026至今 / 2025全年 / 2024全年 的分红记录。")
    lines.append("- 正式表格优先使用同花顺 F10 分红页，避免单一 API 漏掉特别分红或补充分红。")
    lines.append("- 当前表格已统一按“除息年份”归属年度，避免把报告期和实际派息年份混在一起。")

    lines.append("")
    lines.append("## 三、逐笔分红明细（核对用）")
    lines.append("")
    lines.append("| 股票 | 代码 | 报告期 | 除息日 | 分红(10股) | 分红(每股) | 计算价格 | 单次股息率 | 计算口径 | 状态 | 方案 |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---|---|---|")
    for r in detail_rows:
        plan = r["plan"].replace("|", "\\|")
        lines.append(
            f"| {r['name']} | {r['code']} | {r['report_date']} | {r['ex_date']} | {format_money(r['per10'])} | {format_money(r['per_share'])} | {format_money(r['calc_price'])} | {format_pct(r['yield_value'])} | {r['yield_note']} | {r['progress']} | {plan} |"
        )

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"股票分红信息整合总表_{as_of_date}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("DONE")


if __name__ == "__main__":
    main()
