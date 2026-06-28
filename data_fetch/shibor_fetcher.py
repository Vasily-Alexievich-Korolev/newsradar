"""
Shibor 利率自动抓取工具

从 akshare 获取 Shibor（上海银行间同业拆放利率）历史数据。
增量更新到 eco_data/Shibor.csv

数据来源：akshare -> macro_china_shibor_all()
"""

import os
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "Shibor.csv")


def load_existing():
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def fetch_shibor_data():
    """抓取 Shibor 历史数据"""
    import akshare as ak

    print("正在抓取 Shibor 数据...")
    df = ak.macro_china_shibor_all()

    # 保存-读取以正确加载中文列名（避免终端编码问题）
    tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".tmp_shibor.csv")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    df = pd.read_csv(tmp_path, encoding="utf-8-sig")
    os.remove(tmp_path)

    # 重命名列 - 列名来自实际CSV输出确认
    df = df.rename(columns={
        "日期": "time",
        "O/N-定价": "隔夜",
        "1W-定价": "1周",
        "2W-定价": "2周",
        "1M-定价": "1月",
        "3M-定价": "3月",
        "6M-定价": "6月",
        "9M-定价": "9月",
        "1Y-定价": "1年",
    })

    # 只保留日期和利率列（去掉涨跌幅）
    keep_cols = ["time", "隔夜", "1周", "2周", "1月", "3月", "6月", "9月", "1年"]
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols]

    df["time"] = pd.to_datetime(df["time"])
    for col in keep_cols[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("time").reset_index(drop=True)

    print(f"  抓取成功，共 {len(df)} 条记录")
    latest_rate = df.iloc[-1, 1]
    print(f"  最新日期: {df.iloc[-1]['time'].strftime('%Y-%m-%d')}, 隔夜: {latest_rate}%")

    return df


def incremental_update():
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    new_df = fetch_shibor_data()
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
    auto_update()
