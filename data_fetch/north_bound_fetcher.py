"""
北向资金（陆股通）自动抓取工具

从东方财富 datacenter API 获取北向资金（沪股通 + 深股通）历史数据，
增量更新到 eco_data/北向资金.csv

数据来源：东方财富 datacenter API
"""

import os
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "北向资金.csv")

API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def fetch_all_pages():
    """通过分页获取全部记录"""
    headers = {"User-Agent": "Mozilla/5.0"}
    all_data = []
    for page in range(1, 10):
        params = {
            "reportName": "RPT_NORTH_ACCUM_NETBUY",
            "columns": "TRADE_DATE,ACCUM_NETBUY_H,ACCUM_NETBUY_S,ACCUM_NETBUY_AMT",
            "filter": '(DATE_TYPE_CODE="001")',
            "pageNumber": page,
            "pageSize": 500,
            "sortTypes": "-1",
            "sortColumns": "TRADE_DATE",
            "source": "WEB", "client": "WEB",
        }
        r = requests.get(API_URL, params=params, headers=headers, timeout=15)
        data = r.json()
        if not data.get("success"):
            print(f"  Page {page}: API 返回异常，跳过")
            break
        records = data["result"]["data"]
        if not records:
            break
        all_data.extend(records)
    df = pd.DataFrame(all_data)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["TRADE_DATE"])
    df["北向资金(亿)"] = df["ACCUM_NETBUY_AMT"]
    df = df[["time", "北向资金(亿)"]].sort_values("time").reset_index(drop=True)
    return df


def load_existing():
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", parse_dates=["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def incremental_update():
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    print("正在抓取北向资金数据...")
    new_df = fetch_all_pages()
    if new_df.empty:
        print("  未获取到数据")
        return existing_df
    print(f"  抓取成功，共 {len(new_df)} 条记录")
    print(f"  日期范围: {new_df['time'].min().strftime('%Y-%m-%d')} ~ {new_df['time'].max().strftime('%Y-%m-%d')}")

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
    return incremental_update()


if __name__ == "__main__":
    df = auto_update()
    if len(df) > 0:
        last = df.iloc[-1]
        print(f"\n最新北向资金: {last['time'].strftime('%Y-%m-%d')}")
        print(f"  累计净买额: {last['北向资金(亿)']:.2f} 亿")
        print(f"\n  [!] 注意：该接口数据仅更新到 2024-08-16")
        print(f"  2024年后的北向资金逐日汇总暂无可用的公开 API")
