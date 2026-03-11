# 富贵momo日报（fugui-momo-daily）

一个用于生成 **红利汇总** 与 **低波股票分析报告** 的 Python 项目，面向可配置的 A 股 / 港股股票池输出 Markdown 报告。

这个仓库提供了一套可重复执行的流程：抓取分红数据、获取当前价格与历史价格、计算股息率与均线相关指标，并最终生成两份可直接查看或继续加工的 Markdown 文件。

## 项目特性

- 生成 Markdown 格式的分红汇总表
- 生成 Markdown 格式的股票分析报告
- 通过 JSON 配置股票池
- 同时支持 A 股与港股
- 将分红、现价、历史价格、均线等数据处理流程脚本化
- 适合手动执行，也适合集成到自动化任务中

## 输出内容

默认会在 `output/` 目录下生成两份文件：

1. `股票分红信息整合总表_YYYY-MM-DD.md`
2. `股票分析表格_版本11_YYYY-MM-DD.md`

仓库中已附带示例输出，便于快速查看生成结果的格式。

## 仓库结构

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

## 环境要求

- Python 3.10 及以上

安装依赖：

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 配置股票池

编辑 `references/default-stocks.json`。

示例：

```json
[
  {"name": "招商银行", "code": "600036", "prefix": "sh"},
  {"name": "中信建投证券", "code": "06066", "prefix": "hk"}
]
```

字段说明：

- `name`：显示名称
- `code`：股票代码
- `prefix`：市场前缀，例如 `sh`、`sz`、`hk`

### 2. 一键生成完整报告

```bash
python scripts/refresh_full_report.py --date 2026-03-07 --version 11
```

### 3. 仅生成分红汇总

```bash
python scripts/generate_dividend_summary.py --date 2026-03-07
```

### 4. 仅生成股票分析报告

```bash
python scripts/generate_stock_analysis_report.py --date 2026-03-07 --version 11
```

### 5. 指定股票池或输出目录

```bash
python scripts/refresh_full_report.py --date 2026-03-07 --version 11 --stocks-file references/default-stocks.json --out-dir output
```

## 数据来源

详细规则见 `references/source-rules.md`。

当前版本使用的数据来源如下：

- **分红明细**：同花顺 F10 bonus 页面
- **当前价格**：腾讯财经行情接口
- **A 股历史价格与均线**：Baostock
- **港股历史价格与均线**：东方财富历史 K 线接口

## 计算口径说明

- 分红归属按 **除权除息日 / 除净日所在年份** 计算，而不是按财报报告期年份计算
- `2024` 全年股息率按 **逐笔分红 ÷ 当次除息日收盘价** 后累计
- 分析报告中第 2 部分的均线判断，使用 `references/source-rules.md` 中定义的固定规则
- 当前价格后的 3 个方向箭头，来自 **最近 4 个已完成交易日收盘价** 推导出的 3 段方向变化，不混入实时价格

## 适用场景

- 红利类股票跟踪
- 低波股票观察与筛选
- Markdown 投研报告生成
- 定时日报 / 周报自动化
- 基于现有脚本继续扩展自己的研究流程

## 免责声明

本项目仅用于数据整理、研究辅助与报告生成。

**不构成任何投资建议。** 使用者应自行核验数据，并独立完成投资判断与决策。
