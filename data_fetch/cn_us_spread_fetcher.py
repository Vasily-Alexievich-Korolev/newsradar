"""
中美利差自动抓取工具

从 akshare 获取中美国债收益率对比数据，计算中美利差。
增量更新到 eco_data/中美利差.csv

数据来源：akshare -> bond_zh_us_rate()
"""

import os
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "中美利差.csv")


def load_existing():
    """读取已有 CSV"""
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def fetch_spread_data():
    """抓取中美利差数据"""
    import akshare as ak

    print("正在抓取中美利率对比数据...")
    df = ak.bond_zh_us_rate()

    # 重命名列
    df = df.rename(columns={
        "日期": "time",
        "中国国债收益率2年": "中国2年",
        "中国国债收益率5年": "中国5年",
        "中国国债收益率10年": "中国10年",
        "中国国债收益率30年": "中国30年",
        "中国国债收益率10年-2年": "中国10-2年",
        "美国国债收益率2年": "美国2年",
        "美国国债收益率5年": "美国5年",
        "美国国债收益率10年": "美国10年",
        "美国国债收益率30年": "美国30年",
        "美国国债收益率10年-2年": "美国10-2年",
    })

    # 只保留需要的中美核心期限列
    keep_cols = ["time"] + [c for c in df.columns if "中国" in c or "美国" in c]
    df = df[keep_cols]

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    # 计算核心利差
    df["中美10年利差"] = (df["中国10年"] - df["美国10年"]).round(4)
    df["中美2年利差"] = (df["中国2年"] - df["美国2年"]).round(4)
    df["中美5年利差"] = (df["中国5年"] - df["美国5年"]).round(4)

    print(f"  抓取成功，共 {len(df)} 条记录")
    print(f"  最新日期: {df['time'].max().strftime('%Y-%m-%d')}")
    print(f"  中美10年利差: {df.iloc[-1]['中美10年利差']}%")

    return df


def incremental_update():
    """增量更新"""
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    new_df = fetch_spread_data()
    new_records = new_df[~new_df["time"].dt.strftime("%Y-%m-%d").isin(existing_dates)]

    if len(new_records) == 0:
        print("\n无需更新，所有日期已有数据。")
        return existing_df

    combined = pd.concat([existing_df, new_records], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n保存完成: {OUTPUT_CSV}")
    print(f"总计 {len(combined)} 条记录，新增 {len(new_records)} 条")
    print(f"最新: {combined['time'].max().strftime('%Y-%m-%d')}")

    return combined


def auto_update():
    return incremental_update()


if __name__ == "__main__":
    df = auto_update()
    if len(df) > 0:
        print(f"\n最新中美利差 ({df.iloc[-1]['time'].strftime('%Y-%m-%d')}):")
        print(f"  中国10Y: {df.iloc[-1]['中国10年']}%")
        print(f"  美国10Y: {df.iloc[-1]['美国10年']}%")
        print(f"  利差: {df.iloc[-1]['中美10年利差']}%")
