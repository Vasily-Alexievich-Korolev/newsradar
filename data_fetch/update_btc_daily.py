#!/usr/bin/env python3
"""
update_btc_daily.py — BTC/ETH/SOL 等主流币 1d K线增量抓取

从 Binance API 抓取主流币种日线数据，增量更新到 data/ 目录。
不依赖本地旧版脚本，纯 requests，可在 GitHub Actions 直接运行。

数据来源: Binance API (https://api.binance.com)
"""

import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 主流币种列表
SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "PEPEUSDT",
]

INTERVAL = "1d"
LIMIT = 1000

BINANCE_API = "https://api.binance.com/api/v3/klines"


def fetch_klines(symbol, start_time=None, end_time=None):
    """从 Binance 抓取 K 线数据"""
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": LIMIT,
    }
    if start_time:
        params["startTime"] = int(start_time)
    if end_time:
        params["endTime"] = int(end_time)

    resp = requests.get(BINANCE_API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()

    rows = []
    for k in data:
        rows.append({
            "open_time": datetime.fromtimestamp(k[0] / 1000),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": datetime.fromtimestamp(k[6] / 1000),
            "quote_volume": float(k[7]),
            "trades": int(k[8]),
        })
    df = pd.DataFrame(rows)
    df = df.sort_values("open_time").reset_index(drop=True)
    return df


def update_symbol(symbol):
    """增量更新单币种日线数据"""
    filename = os.path.join(DATA_DIR, f"{symbol}_history_{INTERVAL}.csv")

    if os.path.exists(filename):
        old_df = pd.read_csv(filename, parse_dates=["open_time", "close_time"])
        last_open = int(old_df["open_time"].iloc[-1].timestamp() * 1000)
        print(f"  > 已有数据: {len(old_df)} 条, 最新: {old_df['open_time'].iloc[-1]}")
        # 从最后一条之后开始拉
        new_df = fetch_klines(symbol, start_time=last_open + 1)
    else:
        print(f"  > 无历史数据，从头抓取最近 365 天...")
        start = int((time.time() - 365 * 86400) * 1000)
        new_df = fetch_klines(symbol, start_time=start)
        old_df = pd.DataFrame()

    if new_df.empty:
        print("  > 无新数据")
        return old_df if not old_df.empty else pd.DataFrame()

    # 去重合并
    combined = pd.concat([old_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["open_time"])
    combined = combined.sort_values("open_time").reset_index(drop=True)

    os.makedirs(DATA_DIR, exist_ok=True)
    combined.to_csv(filename, index=False)
    print(f"  > 保存: {len(combined)} 条 (新增 {len(combined) - len(old_df)} 条)")
    print(f"  > 最新: {combined['open_time'].iloc[-1].strftime('%Y-%m-%d')}  close={combined['close'].iloc[-1]:.2f}")
    return combined


def main():
    print("=" * 50)
    print("  主流币种 1d K线数据抓取")
    print(f"  币种: {', '.join(SYMBOLS)}")
    print("=" * 50)

    success = 0
    for i, symbol in enumerate(SYMBOLS, 1):
        print(f"\n[{i}/{len(SYMBOLS)}] {symbol}")
        try:
            update_symbol(symbol)
            success += 1
        except Exception as e:
            print(f"  [FAIL] 失败: {e}")
        time.sleep(0.5)  # 避免请求过快

    print(f"\n完成: {success}/{len(SYMBOLS)} 成功")


if __name__ == "__main__":
    main()
