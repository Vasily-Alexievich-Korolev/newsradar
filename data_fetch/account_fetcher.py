"""
A 股新增投资者开户数自动抓取工具

从东方财富获取 A 股新增投资者账户数（月度数据）。
增量更新到 eco_data/新开户数.csv

数据来源：akshare -> stock_account_statistics_em()
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "新开户数.csv")


def load_existing():
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m"))
    return df, existing_dates


def fetch_account_data():
    """抓取 A 股账户统计数据"""
    import akshare as ak

    print("正在抓取 A 股账户统计数据...")
    df = ak.stock_account_statistics_em()

    # 保存-读取以解决中文列名编码问题
    tmp = os.path.join(BASE_DIR, ".tmp_acct.csv")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    df = pd.read_csv(tmp, encoding="utf-8-sig")
    os.remove(tmp)

    # 重命名关键列（列名来自实际 CSV 输出确认）
    df = df.rename(columns={
        "数据日期": "time",
        "新增投资者-数量": "新增投资者(万户)",
        "新增投资者-环比": "新增投资者环比(%)",
        "新增投资者-同比": "新增投资者同比(%)",
        "期末投资者-总量": "期末投资者(万户)",
        "期末投资者-A股账户": "A股账户(万户)",
        "期末投资者-B股账户": "B股账户(万户)",
        "沪深总市值": "沪深总市值(亿)",
        "上证指数-收盘": "上证收盘",
        "上证指数-涨跌幅": "上证涨跌幅(%)",
    })

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    print(f"  抓取成功，共 {len(df)} 条记录")
    print(f"  最新: {df['time'].max().strftime('%Y-%m')}")
    print(f"  新增投资者: {df.iloc[-1]['新增投资者(万户)']} 万户")

    return df


def incremental_update():
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个月")

    new_df = fetch_account_data()
    new_records = new_df[~new_df["time"].dt.strftime("%Y-%m").isin(existing_dates)]

    if len(new_records) == 0:
        print("\n无需更新，所有月份已有数据。")
        return existing_df

    combined = pd.concat([existing_df, new_records], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n保存完成: {OUTPUT_CSV}")
    print(f"总计 {len(combined)} 条记录，新增 {len(new_records)} 条")
    print(f"最新: {combined['time'].max().strftime('%Y-%m')}")

    return combined


def auto_update():
    return incremental_update()


if __name__ == "__main__":
    auto_update()
