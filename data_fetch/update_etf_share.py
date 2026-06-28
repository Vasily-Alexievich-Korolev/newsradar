#!/usr/bin/env python3
"""
update_etf_share.py — 上交所 ETF 份额数据增量抓取

自动检测 sse_etf_data/ 目录的最新日期，补抓缺失的交易日。
数据来源: 上交所官网接口 (query.sse.com.cn)
"""

import requests
import pandas as pd
import re
import json
import time
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(BASE_DIR, "sse_etf_data")
os.makedirs(SAVE_DIR, exist_ok=True)

API_URL = "https://query.sse.com.cn/commonQuery.do"
HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0 Safari/537.36"
    ),
}
PAGE_SIZE = 100


def parse_jsonp(text):
    """解析 JSONP 响应"""
    match = re.search(r'^[^(]*\((.*)\)\s*$', text, re.S)
    if not match:
        raise ValueError("JSONP 解析失败")
    return json.loads(match.group(1))


def fetch_page(page_no, stat_date):
    """抓取单页数据"""
    callback = f"jsonpCallback{int(time.time() * 1000)}"
    params = {
        "jsonCallBack": callback,
        "isPagination": "true",
        "pageHelp.pageSize": PAGE_SIZE,
        "pageHelp.pageNo": page_no,
        "pageHelp.beginPage": page_no,
        "pageHelp.cacheSize": 1,
        "pageHelp.endPage": page_no,
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
        "STAT_DATE": stat_date,
        "_": int(time.time() * 1000),
    }
    resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return parse_jsonp(resp.text)


def fetch_one_day(stat_date):
    """抓取单日全部 ETF 份额数据"""
    all_rows = []
    page = 1
    while True:
        try:
            data = fetch_page(page, stat_date)
        except Exception as e:
            print(f"  > 第 {page} 页失败: {e}")
            break

        result = data.get("result")
        if not result:
            break

        all_rows.extend(result)
        if len(result) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.3)

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    filename = os.path.join(SAVE_DIR, f"sse_etf_{stat_date}.csv")
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"  > 保存: {filename} ({len(df)} 条)")
    return df


def get_existing_dates():
    """获取已有数据的日期列表"""
    dates = set()
    if not os.path.isdir(SAVE_DIR):
        return dates
    for f in os.listdir(SAVE_DIR):
        match = re.match(r"sse_etf_(\d{4}-\d{2}-\d{2})\.csv", f)
        if match:
            dates.add(match.group(1))
    return dates


def generate_trading_days(start, end):
    """生成交易日列表（周一至周五）"""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def main():
    print("=" * 50)
    print("  上交所 ETF 份额增量抓取")
    print("=" * 50)

    existing = get_existing_dates()
    print(f"已有: {len(existing)} 个交易日")

    # 确定抓取范围
    today = datetime.now()
    if existing:
        # 从已有最晚日期的次日开始
        latest = max(datetime.strptime(d, "%Y-%m-%d") for d in existing)
        start_date = latest + timedelta(days=1)
    else:
        start_date = today - timedelta(days=30)

    if start_date > today:
        print("\n✓ 数据已是最新，无需更新")
        return

    trading_days = generate_trading_days(start_date, today)
    # 去掉已有日期
    missing = [d for d in trading_days if d not in existing]

    if not missing:
        print("\n✓ 无需更新，所有日期已有数据")
        return

    print(f"缺失: {len(missing)} 个交易日 ({missing[0]} ~ {missing[-1]})")

    success = 0
    for stat_date in missing:
        print(f"\n- {stat_date}", end=" ")
        try:
            result = fetch_one_day(stat_date)
            if result is not None:
                success += 1
            else:
                print("  > 无数据")
        except Exception as e:
            print(f"  > 失败: {e}")
        time.sleep(1)

    print(f"\n\n完成: 成功 {success}/{len(missing)} 个交易日")


if __name__ == "__main__":
    main()
