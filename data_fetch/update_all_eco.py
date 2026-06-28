#!/usr/bin/env python3
"""
update_all_eco.py — 宏观经济数据一键更新主控脚本

依次运行所有 9 个宏观数据抓取脚本，支持增量更新。
在 GitHub Actions 环境中自动工作（无需虚拟环境）。

使用方式:
    python data_fetch/update_all_eco.py
"""

import subprocess
import sys
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# 抓取脚本列表（按稳定性排序，简单的先跑）
FETCHERS = [
    # 基础利率/货币类
    ("DR007 隔夜回购利率",          "DR007_get.py"),
    ("Shibor 利率",                 "shibor_fetcher.py"),
    ("中国国债收益率曲线",          "bond_yield_fetcher.py"),

    # 资金流向类
    ("融资融券余额",                "margin_balance_fetcher.py"),
    ("南向资金（港股通）",          "south_bound_fetcher.py"),
    ("中美利差",                    "cn_us_spread_fetcher.py"),

    # A股市场情绪类
    ("A股成交额（上证指数）",       "turnover_fetcher.py"),
    ("新增投资者开户数（月频）",    "account_fetcher.py"),

    # 全市场估值（依赖 py_mini_racer，可能出问题）
    ("全市场 PE/PB 估值",           "market_valuation_fetcher.py"),

    # 补充数据源
    ("BTC/ETH/SOL 日线价格",        "update_btc_daily.py"),
    ("上交所 ETF 份额",             "update_etf_share.py"),
    ("核心 ETF 日K线",              "update_etf_kline.py"),
]


def run_fetcher(display_name, script_name):
    """运行单个抓取脚本，返回 (成功?, 输出)"""
    script_path = os.path.join(BASE_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"  [WARN] 脚本不存在: {script_path}")
        return False, "FILE_NOT_FOUND"

    print(f"\n┌─ {display_name}")
    print(f"│  脚本: {script_name}")

    start = time.time()
    try:
        # 设置 UTF-8 编码避免 Windows 终端问题
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=PROJECT_DIR,
            capture_output=True,
            timeout=300,
            text=True,
            env=env,
        )
        elapsed = time.time() - start
        success = result.returncode == 0

        # 打印 stdout
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                print(f"│  {line}")

        # 打印 stderr（可能包含警告）
        if result.stderr.strip():
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    print(f"│  [stderr] {line}")

        if success:
            print(f"└─ [OK] 完成 ({elapsed:.1f}s)")
        else:
            print(f"└─ [FAIL] 失败 (exit code={result.returncode}, {elapsed:.1f}s)")

        return success, result.stdout

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"└─ [FAIL] 超时 ({elapsed:.1f}s)")
        return False, "TIMEOUT"
    except Exception as e:
        elapsed = time.time() - start
        print(f"└─ [FAIL] 异常: {e} ({elapsed:.1f}s)")
        return False, str(e)


def main():
    print("=" * 56)
    print("  宏观经济数据自动更新")
    print("  数据目录: eco_data/")
    print(f"  运行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 56)

    results = []
    for display_name, script_name in FETCHERS:
        ok, output = run_fetcher(display_name, script_name)
        results.append((display_name, ok))

    # 汇总
    print("\n" + "=" * 56)
    print("  执行汇总")
    print("=" * 56)
    success_count = 0
    fail_count = 0
    for name, ok in results:
        status = "[OK]" if ok else "[FAIL]"
        if ok:
            success_count += 1
        else:
            fail_count += 1
        print(f"  {status} {name}")

    print(f"\n  成功: {success_count}  |  失败: {fail_count}  |  总计: {len(results)}")

    # eco_data 目录文件大小
    eco_dir = os.path.join(PROJECT_DIR, "eco_data")
    if os.path.isdir(eco_dir):
        print("\n  数据文件大小:")
        for f in sorted(os.listdir(eco_dir)):
            if f.endswith(".csv"):
                fpath = os.path.join(eco_dir, f)
                size_kb = os.path.getsize(fpath) / 1024
                print(f"    {f:<25s} {size_kb:>8.1f} KB")

    print("=" * 56)
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
