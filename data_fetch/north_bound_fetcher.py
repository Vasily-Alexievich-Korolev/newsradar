"""
北向资金（陆股通）每日成交额自动抓取工具

从东方财富 datacenter API 获取北向资金每日成交额数据，
增量更新到 eco_data/北向资金.csv

数据来源：RPT_MUTUAL_DEALAMT（东方财富 datacenter）
"""

import os
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(BASE_DIR, "eco_data", "北向资金.csv")
API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

REPORT = "RPT_MUTUAL_DEALAMT"
COLUMNS = (
    "TRADE_DATE,"
    "NF_DEAL_AMT,SSC_DEAL_AMT,SSC_QUOTA_BALANCE,SSC_DEAL_NUM,"
    "ST_DEAL_AMT,ST_QUOTA_BALANCE,ST_DEAL_NUM,"
    "SCI_INDEX_PRICE,SCI_INDEX_RATE,SZC_INDEX_PRICE,SZC_INDEX_RATE"
)


def fetch_all_pages():
    """分页获取全部北向成交额记录"""
    headers = {"User-Agent": "Mozilla/5.0"}
    all_data = []
    for page in range(1, 10):
        params = {
            "reportName": REPORT,
            "columns": COLUMNS,
            "filter": "",  # 全量
            "pageNumber": page,
            "pageSize": 500,
            "sortTypes": "-1",
            "sortColumns": "TRADE_DATE",
            "source": "WEB", "client": "WEB",
        }
        r = requests.get(API_URL, params=params, headers=headers, timeout=15)
        data = r.json()
        if not data.get("success"):
            break
        records = data["result"]["data"]
        if not records:
            break
        all_data.extend(records)

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)

    # 数值列：API 原始单位是 万元，÷100 得 亿元
    for col in ["NF_DEAL_AMT", "SSC_DEAL_AMT", "ST_DEAL_AMT"]:
        df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0

    df["time"] = pd.to_datetime(df["TRADE_DATE"])
    df["SCI_INDEX_RATE"] = pd.to_numeric(df["SCI_INDEX_RATE"], errors="coerce")
    df["SZC_INDEX_RATE"] = pd.to_numeric(df["SZC_INDEX_RATE"], errors="coerce")

    out = pd.DataFrame({
        "time": df["time"],
        "北向成交总额(亿)": df["NF_DEAL_AMT"],
        "沪股通成交额(亿)": df["SSC_DEAL_AMT"],
        "沪股通余额": df["SSC_QUOTA_BALANCE"],
        "沪股通笔数": df["SSC_DEAL_NUM"],
        "深股通成交额(亿)": df["ST_DEAL_AMT"],
        "深股通余额": df["ST_QUOTA_BALANCE"],
        "深股通笔数": df["ST_DEAL_NUM"],
        "上证指数": df["SCI_INDEX_PRICE"],
        "上证涨跌幅(%)": df["SCI_INDEX_RATE"],
        "深证成指": df["SZC_INDEX_PRICE"],
        "深证涨跌幅(%)": df["SZC_INDEX_RATE"],
    })
    return out.sort_values("time").reset_index(drop=True)


def load_existing():
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig", parse_dates=["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def incremental_update():
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    print("正在抓取北向资金成交额数据...")
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
        print(f"  北向成交总额: {last['北向成交总额(亿)']:.2f} 亿")
        print(f"  沪股通: {last['沪股通成交额(亿)']:.2f} 亿")
        print(f"  深股通: {last['深股通成交额(亿)']:.2f} 亿")
