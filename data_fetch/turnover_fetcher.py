"""
A 股成交额历史自动抓取工具

从东方财富获取上证指数日线（含成交额），作为全市场情绪指标。
增量更新到 eco_data/A股成交额.csv

数据来源：akshare -> stock_zh_index_daily_em(symbol="sh000001")
"""

import os
import pandas as pd
from datetime import datetime, timedelta

OUTPUT_CSV = "eco_data/A股成交额.csv"


def load_existing():
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def fetch_turnover_data():
    """抓取上证指数含成交额日线数据"""
    import akshare as ak

    print("正在抓取上证指数日线（含成交额）...")
    df = ak.stock_zh_index_daily_em(symbol="sh000001")

    df = df.rename(columns={
        "date": "time",
        "open": "开盘",
        "close": "收盘",
        "high": "最高",
        "low": "最低",
        "volume": "成交量(手)",
        "amount": "成交额(元)",
    })

    df["time"] = pd.to_datetime(df["time"])
    # 成交额从元转为亿元
    df["成交额(亿)"] = (df["成交额(元)"] / 1e8).round(2)
    df = df.sort_values("time").reset_index(drop=True)

    print(f"  抓取成功，共 {len(df)} 条记录")
    print(f"  最新日期: {df['time'].max().strftime('%Y-%m-%d')}")
    print(f"  成交额: {df.iloc[-1]['成交额(亿)']} 亿")

    return df


def incremental_update():
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    new_df = fetch_turnover_data()
    new_records = new_df[~new_df["time"].dt.strftime("%Y-%m-%d").isin(existing_dates)]

    if len(new_records) == 0:
        print("\n无需更新，所有日期已有数据。")
        return existing_df

    combined = pd.concat([existing_df, new_records], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    # 只保留关键列
    keep_cols = ["time", "收盘", "成交额(亿)", "成交量(手)", "开盘", "最高", "最低"]
    keep_cols = [c for c in keep_cols if c in combined.columns]
    combined[keep_cols].to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n保存完成: {OUTPUT_CSV}")
    print(f"总计 {len(combined)} 条记录，新增 {len(new_records)} 条")
    print(f"最新: {combined['time'].max().strftime('%Y-%m-%d')}")

    return combined


def auto_update():
    return incremental_update()


if __name__ == "__main__":
    auto_update()
