"""
融资融券（双融）余额自动抓取工具

从东方财富数据中心获取沪深两市融资融券数据，
合并计算沪深合计余额，增量更新到 eco_data/融资融券余额.csv

数据来源：东方财富 -> akshare (macro_china_market_margin_sh / macro_china_market_margin_sz)
"""

import os
import pandas as pd
from datetime import datetime

# CSV 路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "融资融券余额.csv")


def load_existing():
    """读取已有 CSV"""
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def fetch_margin_data():
    """抓取沪深两市融资融券数据"""
    import akshare as ak

    print("正在抓取上交所融资融券数据...")
    sh = ak.macro_china_market_margin_sh()
    sh = sh.rename(columns={"日期": "time", "融资融券余额": "SH_余额"})
    sh["time"] = pd.to_datetime(sh["time"])

    print("正在抓取深交所融资融券数据...")
    sz = ak.macro_china_market_margin_sz()
    sz = sz.rename(columns={"日期": "time", "融资融券余额": "SZ_余额"})
    sz["time"] = pd.to_datetime(sz["time"])

    # 合并沪深
    merged = pd.merge(sh[["time", "SH_余额"]], sz[["time", "SZ_余额"]], on="time", how="inner")
    merged["融资融券余额（亿元）"] = ((merged["SH_余额"] + merged["SZ_余额"]) / 1e8).round(0).astype(int)
    merged = merged.sort_values("time").reset_index(drop=True)

    print(f"  沪深合并成功，共 {len(merged)} 条记录")
    print(f"  最新日期: {merged['time'].max().strftime('%Y-%m-%d')}")
    print(f"  最新余额: {merged.iloc[-1]['融资融券余额（亿元）']} 亿元")

    return merged[["time", "融资融券余额（亿元）"]]


def incremental_update():
    """增量更新：仅补充缺失日期"""
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    # 抓取全量源头数据
    new_df = fetch_margin_data()

    # 过滤出缺失的日期
    new_records = new_df[~new_df["time"].dt.strftime("%Y-%m-%d").isin(existing_dates)]

    if len(new_records) == 0:
        print("\n无需更新，所有日期已有数据。")
        return existing_df

    # 合并新旧
    combined = pd.concat([existing_df, new_records], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    # 保存
    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n保存完成: {OUTPUT_CSV}")
    print(f"总计 {len(combined)} 条记录，新增 {len(new_records)} 条")

    return combined


def auto_update():
    """一键更新"""
    return incremental_update()


if __name__ == "__main__":
    df = auto_update()
    if len(df) > 0:
        print(f"\n最新融资融券余额: {df.iloc[-1]['融资融券余额（亿元）']} 亿元 ({df.iloc[-1]['time'].strftime('%Y-%m-%d')})")
