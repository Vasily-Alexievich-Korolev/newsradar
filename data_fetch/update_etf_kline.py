#!/usr/bin/env python3
"""
update_etf_kline.py — 核心 ETF 日K线增量抓取

用 akshare 增量更新核心 ETF 的日K线数据，
保存到 data_stock/ 目录。

数据来源: akshare -> fund_etf_hist_sina / stock_zh_index_daily_em
"""

import os
import pandas as pd
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data_stock")
os.makedirs(DATA_DIR, exist_ok=True)

# 核心 ETF 列表（沪深交易所核心 ETF + eco_analysis.py 使用的）
CORE_ETF = {
    "510050": "上证50",
    "510300": "沪深300",
    "510500": "中证500",
    "512100": "中证1000",
    "588000": "科创50",
    "sz399006": "创业板指",   # 用指数代码替代159949 ETF
}


def fetch_etf_daily(symbol, name):
    """抓取单只 ETF 日K线（增量更新）"""
    filename = os.path.join(DATA_DIR, f"{symbol}_Klines.csv")

    # 读取已有数据
    if os.path.exists(filename):
        old_df = pd.read_csv(filename, encoding="utf-8")
        if not old_df.empty and "date" in old_df.columns:
            old_df["date"] = pd.to_datetime(old_df["date"])
            latest_date = old_df["date"].max()
            print(f"  > 已有: {len(old_df)} 条, 最新: {latest_date.strftime('%Y-%m-%d')}")
            need_fetch = False
        else:
            old_df = pd.DataFrame()
            latest_date = None
            need_fetch = True
    else:
        old_df = pd.DataFrame()
        latest_date = None
        need_fetch = True

    try:
        import akshare as ak

        # 判断交易所前缀
        if symbol.startswith("sz") or symbol.startswith("sh"):
            index_symbol = symbol
        else:
            index_symbol = f"sh{symbol}"

        df = ak.stock_zh_index_daily_em(symbol=index_symbol)

        if df is None or df.empty:
            # 尝试另一交易所
            if symbol.startswith("sz"):
                index_symbol = f"sh{symbol[2:]}"
            elif symbol.startswith("sh"):
                index_symbol = f"sz{symbol[2:]}"
            else:
                index_symbol = f"sz{symbol}"
            df = ak.stock_zh_index_daily_em(symbol=index_symbol)

        if df is None or df.empty:
            print(f"  > 抓取失败: {name}({symbol})")
            return old_df if not old_df.empty else pd.DataFrame()

        # 标准化列名
        df = df.rename(columns={
            "date": "date", "open": "open", "close": "close",
            "high": "high", "low": "low", "volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # 增量合并
        if not old_df.empty:
            combined = pd.concat([old_df, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["date"])
            combined = combined.sort_values("date").reset_index(drop=True)
        else:
            combined = df

        combined.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"  > 保存: {len(combined)} 条 (新增 {len(combined) - len(old_df)} 条)")
        print(f"  > 最新: {combined['date'].iloc[-1].strftime('%Y-%m-%d')}  close={combined['close'].iloc[-1]:.2f}")
        return combined

    except Exception as e:
        print(f"  > 失败: {e}")
        return old_df if not old_df.empty else pd.DataFrame()


def main():
    print("=" * 50)
    print("  核心 ETF 日K线增量抓取")
    print(f"  ETF: {len(CORE_ETF)} 只")
    print("=" * 50)

    success = 0
    for symbol, name in CORE_ETF.items():
        print(f"\n[{name}] ({symbol})")
        try:
            fetch_etf_daily(symbol, name)
            success += 1
        except Exception as e:
            print(f"  ✗ 异常: {e}")

    print(f"\n完成: {success}/{len(CORE_ETF)} 成功")


if __name__ == "__main__":
    main()
