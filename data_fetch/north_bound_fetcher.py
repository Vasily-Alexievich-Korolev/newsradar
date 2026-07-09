"""
北向资金（陆股通）自动抓取工具

从东方财富数据中心获取北向资金（沪股通 + 深股通）历史数据，
增量更新到 eco_data/北向资金.csv

数据来源：东方财富 -> akshare (stock_hsgt_hist_em)
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "北向资金.csv")


def load_existing():
    """读取已有 CSV"""
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
        return df, existing_dates
    return pd.DataFrame(), set()


def fetch_north_bound_data():
    """抓取北向资金历史数据（仅保留有汇总净买额的行）"""
    import akshare as ak

    print("正在抓取北向资金历史数据...")
    raw = ak.stock_hsgt_hist_em(symbol="北向资金")

    # 仅保留有每日净买额的行（stock_hsgt_hist_em 返回混合表：
    # 汇总行有 当日成交净买额，个股明细行没有）
    df = raw[raw["当日成交净买额"].notna()].copy()

    df = df.rename(columns={
        "日期": "time",
        "当日成交净买额": "当日净买额(亿)",
        "买入成交额": "买入成交额(亿)",
        "卖出成交额": "卖出成交额(亿)",
        "历史累计净买额": "历史累计净买额(亿)",
    })

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    print(f"  抓取成功，共 {len(df)} 条记录（汇总行）")
    print(f"  日期范围: {df['time'].min().strftime('%Y-%m-%d')} ~ {df['time'].max().strftime('%Y-%m-%d')}")
    print(f"  最新净买额: {df.iloc[-1]['当日净买额(亿)']} 亿")

    return df


def incremental_update():
    """增量更新：仅补充缺失日期"""
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    new_df = fetch_north_bound_data()
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

    return combined


def auto_update():
    """一键更新"""
    return incremental_update()


if __name__ == "__main__":
    df = auto_update()
    if len(df) > 0:
        print(f"\n最新北向资金: {df.iloc[-1]['time'].strftime('%Y-%m-%d')}")
        print(f"  当日净买额: {df.iloc[-1]['当日净买额(亿)']} 亿")
        print(f"  累计净买额: {df.iloc[-1]['历史累计净买额(亿)']} 亿")
