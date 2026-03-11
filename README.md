# fugui-momo-daily

一个用于生成 **红利 / 低波股票日报与分红汇总 Markdown 报告** 的公开脚本仓库。

这个仓库面向两类用途：
- 直接把它当成一个可运行的 Python 项目，生成自己的股票分析报告
- 把它当成一个可复用的 OpenClaw Skill / 模板，继续改造成自己的自动化流程

## 这个仓库会生成什么

默认会生成两份 Markdown 文件：

1. `股票分红信息整合总表_YYYY-MM-DD.md`
2. `股票分析表格_版本11_YYYY-MM-DD.md`

默认输出目录是：
- `output/`

仓库里已经附带了一份示例输出，方便直接查看格式。

## 目录结构

```text
.
├─ README.md
├─ SKILL.md
├─ references/
│  ├─ default-stocks.json
│  └─ source-rules.md
├─ scripts/
│  ├─ generate_dividend_summary.py
│  ├─ generate_stock_analysis_report.py
│  └─ refresh_full_report.py
└─ output/
```

## 依赖环境

建议使用：
- Python 3.10+

常用依赖：
- `pandas`
- `requests`
- `baostock`
- `lxml`
- `html5lib`

可先这样安装：

```bash
pip install pandas requests baostock lxml html5lib
```

> 说明：
> - `pandas.read_html()` 在抓取同花顺分红页面时通常需要 `lxml` 或 `html5lib`
> - 如果后续你想把这个仓库做成正式开源项目，建议再补一个 `requirements.txt`

## 快速开始

### 1）修改股票池

编辑：

- `references/default-stocks.json`

示例格式：

```json
[
  {"name": "招商银行", "code": "600036", "prefix": "sh"},
  {"name": "中信建投证券", "code": "06066", "prefix": "hk"}
]
```

字段说明：
- `name`：股票名称
- `code`：股票代码
- `prefix`：市场前缀，A 股常见为 `sh` / `sz`，港股为 `hk`

### 2）一键刷新整套报告

```bash
python scripts/refresh_full_report.py --date 2026-03-07 --version 11
```

### 3）只生成分红汇总

```bash
python scripts/generate_dividend_summary.py --date 2026-03-07
```

### 4）只生成股票分析表

```bash
python scripts/generate_stock_analysis_report.py --date 2026-03-07 --version 11
```

### 5）指定自定义股票池或输出目录

```bash
python scripts/refresh_full_report.py --date 2026-03-07 --version 11 --stocks-file references/default-stocks.json --out-dir output
```

## 数据来源与规则

详细规则见：
- `references/source-rules.md`

当前公开版的大致数据栈如下：

### 分红明细
- **同花顺 F10 bonus 页面** 作为正式分红明细的主来源
- 用于抓逐笔分红、特别分红、补充分红

### 当前价格
- **腾讯财经** 行情接口

### 历史价格 / 均线
- A 股：**Baostock**
- 港股：**东方财富历史 K 线 API**

### 重要规则
- 分红归属按 **除权除息日 / 除净日年份**，不是按报告期年份
- `2024` 年股息率采用 **逐笔分红 ÷ 当次除息日收盘价** 后再累加
- 报告第 2 部分中的均线判断，使用仓库里已经固定好的规则
- 当前价格后面的 3 个方向箭头，来自 **最近 4 个已完成交易日收盘价** 的 3 段变化，而不是把实时价格混进去

## 适合谁用

这个仓库适合：
- 想自己维护一份红利 / 低波股票观察表的人
- 想把分红汇总和技术位置判断拆开维护的人
- 想做成定时任务、日报、自动化研究流水线的人
- 想基于公开脚本再二次开发的人

## 开源发布注意事项

这个仓库已经做过一轮公开化整理，但如果你继续二次发布，仍建议检查：

- 是否残留私人 NAS / 云盘路径
- 是否残留聊天 ID、用户 ID、文档 token
- 是否残留私有文档链接
- 是否把示例股票池误写成个人持仓池
- 是否保留了不适合公开的组织内流程描述

## 免责声明

本仓库仅用于：
- 数据整理
- 研究辅助
- 自动化报告生成

**不构成任何投资建议。** 市场有风险，使用者需自行核验数据并独立决策。

## 后续可改进项

如果你想把它继续打磨成更完整的开源项目，下一步比较值得补：

- `requirements.txt`
- `LICENSE`
- `.gitignore`
- GitHub Actions 定时刷新
- 更完整的异常处理与日志输出
- 输出示例截图 / 示例文档说明
