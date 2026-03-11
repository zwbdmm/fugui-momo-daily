---
name: stock-analysis-report-public
description: Generate a reusable Markdown stock analysis report plus a supporting dividend summary for a configurable CN/HK stock pool. Use when preparing or maintaining an open-source stock-reporting skill, regenerating the report, changing the stock pool, adjusting moving-average rules, or packaging a shareable public version without private paths or personal workflow details.
---

# Stock Analysis Report Public

## Overview

Use this skill to generate two linked Markdown outputs from a configurable stock pool:
1. `股票分红信息整合总表_YYYY-MM-DD.md`
2. `股票分析表格_版本11_YYYY-MM-DD.md`

Keep the workflow deterministic by running the bundled scripts instead of rewriting one-off code.

## Quick Workflow

1. Read `references/source-rules.md` for the data-source stack, formulas, section-2 judgment rules, and public-sanitization notes.
2. Edit `references/default-stocks.json` if the stock pool should change.
3. Run `scripts/refresh_full_report.py` for the normal full refresh.
4. If only one layer changed, run the specific script directly:
   - `scripts/generate_dividend_summary.py`
   - `scripts/generate_stock_analysis_report.py`
5. Verify that the output files were written to the skill-local `output/` directory, unless `--out-dir` overrides it.
6. If logic changed, verify that the table wording still matches the implemented rule.
7. Before publishing, scan for hard-coded private paths, user IDs, cloud-drive folder names, doc links, or persona-specific wording.
8. Package the skill with `package_skill.py` after the public copy is validated.

## Commands

### Full refresh

```powershell
python scripts/refresh_full_report.py --date 2026-03-07 --version 11
```

### Full refresh with a custom stock list and output directory

```powershell
python scripts/refresh_full_report.py --date 2026-03-07 --version 11 --stocks-file references/default-stocks.json --out-dir output
```

### Only rebuild the dividend summary

```powershell
python scripts/generate_dividend_summary.py --date 2026-03-07
```

### Only rebuild the stock analysis report

```powershell
python scripts/generate_stock_analysis_report.py --date 2026-03-07 --version 11
```

## Non-obvious Rules

- Use **同花顺 F10 bonus.html** as the primary dividend-detail source for formal tables.
- Use **腾讯财经** for current prices.
- Use **Baostock 前复权** (`adjustflag="2"`) for A-share moving averages.
- Use **Baostock 不复权** (`adjustflag="3"`) for A-share 2024 ex-dividend-date close prices in the dividend-yield back-calculation.
- Use **东方财富港股历史 K 线** for Hong Kong moving averages and 2024 ex-date close prices, because Baostock does not cover Hong Kong equities.
- Chapter 1 appends **three recent direction arrows** after the current price; compute them from the **last four completed daily closes**, so the output always reflects the last three completed trading-day moves in chronological order. Use `↑` for up, `↓` for down, and `→` for flat; do not mix the live current price into the arrow calculation.
- Section **2.5** uses the asymmetric rule `MA20W <= MA60W * 1.0027` with the remark wording **小周期休息 / 小周期干活**.
- Section **2.6** uses `MA20M <= MA60M * 1.0027` with the remark wording **大周期休息 / 大周期干活**.
- Group dividends by **除权除息日年份** / **除净日年份**, not report year.
- Keep section 2 table display aligned: use **偏差率** columns consistently.
- For `2.1` and `2.4`, the pass logic is asymmetric: price below the line always passes; price slightly above the line also passes if within `0.27%`.
- Preserve raw tables in the report; do not collapse everything into prose summaries.
- Keep the public copy free of personal cloud-drive conventions, local NAS paths, chat IDs, and assistant persona signatures.

## Resources

### scripts/
- `generate_dividend_summary.py` — build the formal dividend summary Markdown file
- `generate_stock_analysis_report.py` — build the versioned stock analysis Markdown file
- `refresh_full_report.py` — run the dividend summary first, then the analysis report

### references/
- `source-rules.md` — source stack, formulas, section-2 rules, output-path guidance, and publication notes
- `default-stocks.json` — example stock pool; replace with your own list before production use
