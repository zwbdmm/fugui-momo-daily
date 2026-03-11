# fugui-momo-daily

A Python project for generating Markdown-based **dividend summaries** and **low-volatility stock analysis reports** for a configurable CN/HK stock pool.

The repository packages a repeatable workflow for collecting dividend data, fetching current and historical prices, calculating yield-related metrics, and producing two report files that can be used in research, monitoring, or publishing pipelines.

## Features

- Generate a consolidated dividend summary in Markdown
- Generate a versioned stock analysis report in Markdown
- Support configurable stock pools through JSON
- Support both A-share and Hong Kong stock symbols
- Use dedicated data-source rules for dividends, prices, and moving averages
- Keep output generation scriptable and repeatable

## Output

By default, the project generates two Markdown files under `output/`:

1. `股票分红信息整合总表_YYYY-MM-DD.md`
2. `股票分析表格_版本11_YYYY-MM-DD.md`

Sample output files are included in this repository for reference.

## Repository Structure

```text
.
├─ README.md
├─ SKILL.md
├─ requirements.txt
├─ .gitignore
├─ references/
│  ├─ default-stocks.json
│  └─ source-rules.md
├─ scripts/
│  ├─ generate_dividend_summary.py
│  ├─ generate_stock_analysis_report.py
│  └─ refresh_full_report.py
└─ output/
```

## Requirements

- Python 3.10+

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Configure the stock pool

Edit `references/default-stocks.json`.

Example:

```json
[
  {"name": "招商银行", "code": "600036", "prefix": "sh"},
  {"name": "中信建投证券", "code": "06066", "prefix": "hk"}
]
```

Field meanings:

- `name`: display name
- `code`: stock code
- `prefix`: market prefix such as `sh`, `sz`, or `hk`

### 2. Run the full workflow

```bash
python scripts/refresh_full_report.py --date 2026-03-07 --version 11
```

### 3. Run only the dividend summary

```bash
python scripts/generate_dividend_summary.py --date 2026-03-07
```

### 4. Run only the stock analysis report

```bash
python scripts/generate_stock_analysis_report.py --date 2026-03-07 --version 11
```

### 5. Override stock pool or output directory

```bash
python scripts/refresh_full_report.py \
  --date 2026-03-07 \
  --version 11 \
  --stocks-file references/default-stocks.json \
  --out-dir output
```

## Data Sources

The detailed rule set is documented in `references/source-rules.md`.

Current source stack:

- **Dividend details**: 同花顺 F10 bonus pages
- **Current prices**: 腾讯财经 quote API
- **A-share historical prices / moving averages**: Baostock
- **Hong Kong historical prices / moving averages**: 东方财富 historical k-line API

## Method Notes

- Dividend attribution is based on the **ex-dividend year**, not the report year
- The `2024` annual dividend yield is calculated by summing **per-event yield values** using the close price on each ex-dividend date
- The moving-average checks in section 2 follow the fixed rules documented in `references/source-rules.md`
- The three trend arrows shown after the current price are derived from the **last four completed daily closes**, not from the live quote

## Use Cases

This repository is suitable for:

- Dividend-focused stock tracking
- Low-volatility stock screening workflows
- Markdown-based reporting pipelines
- Scheduled report generation
- Further extension into larger research automation systems

## Disclaimer

This repository is provided for data organization, research support, and report generation only.

It does **not** constitute investment advice. Always verify data independently before making investment decisions.
