"""
中国国债收益率曲线自动抓取工具

从中国债券信息网（ChinaBond）获取国债收益率曲线数据，
增量更新到 eco_data/国债收益率.csv

数据来源：bond_china_yield (akshare -> chinabond.com.cn)
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")

# CSV 路径（相对于工作目录 Scripts/）
OUTPUT_CSV = "eco_data/国债收益率.csv"

# 关键期限列表（与现有 CSV 对齐）
KEY_TERMS = ["3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"]


def load_existing():
    """读取已有 CSV"""
    if not os.path.exists(OUTPUT_CSV):
        return pd.DataFrame(), set()
    df = pd.read_csv(OUTPUT_CSV)
    df["time"] = pd.to_datetime(df["time"])
    existing_dates = set(df["time"].dt.strftime("%Y-%m-%d"))
    return df, existing_dates


def fetch_bond_yield(start_date, end_date):
    """
    抓取一个时间段内的国债收益率数据

    Parameters
    ----------
    start_date : str, 格式 "YYYYMMDD"
    end_date : str, 格式 "YYYYMMDD"
    """
    import akshare as ak

    df = ak.bond_china_yield(start_date=start_date, end_date=end_date)

    # 过滤出"国债国债收益率曲线"行
    gov_bond = df[df.iloc[:, 0].str.contains("国债", na=False)].copy()

    if len(gov_bond) == 0:
        print(f"  {start_date}~{end_date}: 未找到国债数据")
        return pd.DataFrame()

    # 标准化列名: 第2列是日期，后续是期限收益率
    col_map = {gov_bond.columns[1]: "time"}
    for term in KEY_TERMS:
        if term in gov_bond.columns:
            col_map[term] = term

    gov_bond = gov_bond.rename(columns=col_map)
    gov_bond = gov_bond[["time"] + [t for t in KEY_TERMS if t in gov_bond.columns]]

    gov_bond["time"] = pd.to_datetime(gov_bond["time"])
    for term in KEY_TERMS:
        if term in gov_bond.columns:
            gov_bond[term] = pd.to_numeric(gov_bond[term], errors="coerce")

    return gov_bond.sort_values("time").reset_index(drop=True)


def iter_fetch(full_start, full_end, chunk_days=350):
    """
    由于 API 限制（一次最多查约1年），分块抓取

    Parameters
    ----------
    full_start : str, "YYYY-MM-DD"
    full_end : str, "YYYY-MM-DD"
    chunk_days : int, 每块最大天数（留余量避免刚好1年边界问题）
    """
    start_dt = datetime.strptime(full_start, "%Y-%m-%d")
    end_dt = datetime.strptime(full_end, "%Y-%m-%d")

    chunks = []
    current = start_dt
    while current < end_dt:
        chunk_end = min(current + timedelta(days=chunk_days), end_dt)
        s = current.strftime("%Y%m%d")
        e = chunk_end.strftime("%Y%m%d")
        print(f"  抓取区间: {s} ~ {e}")
        chunk = fetch_bond_yield(s, e)
        if len(chunk) > 0:
            chunks.append(chunk)
        current = chunk_end + timedelta(days=1)

    if not chunks:
        return pd.DataFrame()

    full = pd.concat(chunks, ignore_index=True)
    full = full.drop_duplicates(subset=["time"])
    full = full.sort_values("time").reset_index(drop=True)
    return full


def incremental_update():
    """增量更新"""
    existing_df, existing_dates = load_existing()
    print(f"已有数据: {len(existing_df)} 条, 覆盖 {len(existing_dates)} 个交易日")

    # 确定抓取范围：已有数据的最早日期 → 今天
    if len(existing_df) > 0:
        start = existing_df["time"].min().strftime("%Y-%m-%d")
    else:
        # 默认过去半年
        start = (datetime.today() - timedelta(days=180)).strftime("%Y-%m-%d")

    end = datetime.today().strftime("%Y-%m-%d")

    print(f"抓取范围: {start} ~ {end}")
    new_df = iter_fetch(start, end)

    if len(new_df) == 0:
        print("抓取失败，无数据返回")
        return existing_df

    # 筛选缺失日期
    new_records = new_df[~new_df["time"].dt.strftime("%Y-%m-%d").isin(existing_dates)]

    if len(new_records) == 0:
        print("\n无需更新，所有日期已有数据。")
        return existing_df

    # 合并
    combined = pd.concat([existing_df, new_records], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    # 补齐 2 年和 10年-2年 期限差（已有数据包含这些计算列）
    if "2年" not in combined.columns:
        # 用 3年 和 1年 插值估算 2年
        combined["2年"] = combined.apply(
            lambda r: round((r.get("1年", 0) + r.get("3年", 0)) / 2, 2)
            if pd.notna(r.get("1年")) and pd.notna(r.get("3年"))
            else None,
            axis=1,
        )
    else:
        # 已有 2年 列但新数据可能为空，补上估算值
        combined["2年"] = combined.apply(
            lambda r: round((r["1年"] + r["3年"]) / 2, 2)
            if pd.isna(r["2年"]) and pd.notna(r["1年"]) and pd.notna(r["3年"])
            else r["2年"],
            axis=1,
        )
    if "10年-2年" not in combined.columns:
        combined["10年-2年"] = combined.apply(
            lambda r: round(r.get("10年", 0) - r.get("2年", 0), 2)
            if pd.notna(r.get("10年")) and pd.notna(r.get("2年"))
            else None,
            axis=1,
        )
    else:
        combined["10年-2年"] = combined.apply(
            lambda r: round(r["10年"] - r["2年"], 2)
            if pd.isna(r["10年-2年"]) and pd.notna(r["10年"]) and pd.notna(r["2年"])
            else r["10年-2年"],
            axis=1,
        )

    # 保存
    cols = ["time"] + KEY_TERMS + ["2年", "10年-2年"]
    cols = [c for c in cols if c in combined.columns]
    combined[cols].to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n保存完成: {OUTPUT_CSV}")
    print(f"总计 {len(combined)} 条记录，新增 {len(new_records)} 条")
    print(f"最新: {combined['time'].max().strftime('%Y-%m-%d')}")

    return combined


def auto_update():
    """一键更新"""
    return incremental_update()


if __name__ == "__main__":
    auto_update()
