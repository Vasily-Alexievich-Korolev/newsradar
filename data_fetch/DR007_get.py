import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date


URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-dlrp/PrDlyBltn"


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.chinamoney.com.cn/chinese/mtdexdaily/?tab=2",
    "X-Requested-With": "XMLHttpRequest"
}


def load_existing(output_csv):
    """读取已有的 CSV 数据，返回 (DataFrame, 已有日期集合)"""
    if not os.path.exists(output_csv):
        return pd.DataFrame(), set()
    df = pd.read_csv(output_csv)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def fetch_dr007_by_date(date_str):
    """
    抓取指定日期的 DR007 数据

    Parameters
    ----------
    date_str : str
        日期，例如 "2026-05-19"

    Returns
    -------
    dict or None
    """

    payload = {
        "lang": "en",
        "indexType": "markInterBankVOList",
        "searchDate": date_str,
        "publishedTime": "2200"
    }

    try:

        resp = requests.post(
            URL,
            headers=HEADERS,
            data=payload,
            timeout=10
        )

        resp.raise_for_status()

        data = resp.json()

        records = data.get("records", [])

        for row in records:

            if row.get("instrmntCd") == "DR007":

                return {
                    "time": date_str,
                    "DR007": float(row["wghtdAvgRepoRate"])
                }

    except Exception as e:

        print(f"{date_str} 抓取失败: {e}")

    return None


def fetch_dr007_history(
    start_date,
    end_date,
    output_csv="eco_data/dr007_history.csv"
):
    """
    批量抓取 DR007 历史数据（支持增量更新）

    会读取已有 CSV，只抓取缺失日期，合并后保存。

    Parameters
    ----------
    start_date : str
        开始日期，例如 "2025-01-01"

    end_date : str
        结束日期，例如 "2026-06-28"

    output_csv : str
        输出 CSV 文件名（相对于工作目录）
    """

    # 读取已有数据
    existing_df, existing_dates = load_existing(output_csv)
    print(f"已有数据: {len(existing_df)} 条, 已覆盖 {len(existing_dates)} 个交易日")

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    new_results = []

    current = start

    while current <= end:

        date_str = current.strftime("%Y-%m-%d")

        # 跳过已有数据
        if date_str in existing_dates:
            print(f" 跳过已有: {date_str}")
            current += timedelta(days=1)
            continue

        print(f" 正在抓取: {date_str}")

        result = fetch_dr007_by_date(date_str)

        if result is not None:

            new_results.append(result)

            print(f"  -> {result}")

        current += timedelta(days=1)

    if not new_results:
        print(f"\n无需更新，所有日期已有数据。")
        return existing_df

    new_df = pd.DataFrame(new_results)
    new_df["time"] = pd.to_datetime(new_df["time"])

    # 合并新旧数据
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["time"])
    merged = merged.sort_values("time").reset_index(drop=True)

    # 保存
    merged.to_csv(output_csv, index=False)

    print(f"\n保存完成: {output_csv}")
    print(f"总计 {len(merged)} 条记录，新增 {len(new_results)} 条")

    return merged


def auto_update(output_csv="eco_data/dr007_history.csv", lookback_days=45):
    """
    自动增量更新：从已有最早日期到今天，扫描缺失日期

    Parameters
    ----------
    output_csv : str
        输出 CSV 文件路径

    lookback_days : int
        如果无已有数据，从多少天前开始抓取
    """
    existing_df, _ = load_existing(output_csv)

    if len(existing_df) > 0:
        start = existing_df["time"].min().strftime("%Y-%m-%d")
    else:
        start = (datetime.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    end = datetime.today().strftime("%Y-%m-%d")

    print(f"自动增量更新: {start} ~ {end}")
    return fetch_dr007_history(start, end, output_csv)


if __name__ == "__main__":

    df = auto_update()
    print(f"\n最新 DR007: {df.iloc[-1]['DR007']} ({df.iloc[-1]['time'].strftime('%Y-%m-%d')})")