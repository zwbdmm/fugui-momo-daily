import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
DEFAULT_OUT_DIR = SKILL_DIR / "output"
DEFAULT_STOCKS_FILE = SKILL_DIR / "references" / "default-stocks.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate the dividend summary first, then the stock analysis report.")
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
    return parser.parse_args()


def run_step(script_name: str, extra_args: list[str]):
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *extra_args]
    subprocess.run(cmd, check=True)


def main():
    args = parse_args()
    shared_args = [
        "--date",
        args.date,
        "--out-dir",
        args.out_dir,
        "--stocks-file",
        args.stocks_file,
    ]
    run_step("generate_dividend_summary.py", shared_args)
    run_step("generate_stock_analysis_report.py", [*shared_args, "--version", args.version])
    print("DONE")


if __name__ == "__main__":
    main()
