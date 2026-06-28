"""
全市场 PE/PB 估值自动抓取工具

从 legulegu.com（乐股）获取上证指数/深证成指等全市场 PE/PB 估值数据。
增量更新到 eco_data/全市场PE.csv 和 eco_data/全市场PB.csv

注：akshare 的 stock_market_pe_lg/pb_lg 有日期解析 bug，此处直接调用底层 API。
"""

import os
import requests
import pandas as pd
from datetime import datetime
import py_mini_racer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from akshare.stock_feature.stock_a_pe_and_pb import hash_code, get_cookie_csrf
except ImportError:
    hash_code = None
    get_cookie_csrf = None

# 配置：上证/深证/创业板 的市场 ID
MARKETS = {
    "上证": {
        "market_id": "1", "index_code": "1",
        "pe_url": "https://legulegu.com/stockdata/shanghaiPE",
        "pb_url": "https://legulegu.com/stockdata/shanghaiPB",
    },
    "深证": {
        "market_id": "2", "index_code": "2",
        "pe_url": "https://legulegu.com/stockdata/shenzhenPE",
        "pb_url": "https://legulegu.com/stockdata/shenzhenPB",
    },
    "创业板": {
        "market_id": "4", "index_code": "4",
        "pe_url": "https://legulegu.com/stockdata/cybPE",
        "pb_url": "https://legulegu.com/stockdata/cybPB",
    },
}


def _get_token():
    """获取 legulegu API token"""
    if hash_code is None:
        raise ImportError("需要 akshare 的 hash_code")
    js = py_mini_racer.MiniRacer()
    js.eval(hash_code)
    return js.call("hex", datetime.now().date().isoformat()).lower()


def _fetch_api(endpoint, market_id, referer_url):
    """通用 legulegu API 调用"""
    url = f"https://legulegu.com/api/stock-data/{endpoint}"
    token = _get_token()
    params = {"token": token, "marketId": market_id}
    cookie_args = get_cookie_csrf(url=referer_url)
    r = requests.get(url, params=params, **cookie_args, timeout=15)
    r.raise_for_status()
    data = r.json()
    items = data.get("data", [])
    return items


def fetch_pe_data(market="上证"):
    """抓取指定市场的 PE 数据"""
    market_info = MARKETS[market]
    items = _fetch_api("market-pe", market_info["market_id"], market_info["pe_url"])
    df = pd.DataFrame(items)[["date", "close", "pe"]]

    # 兼容处理日期格式（字符串 / 毫秒时间戳）
    def parse_date(d):
        if isinstance(d, (int, float)):
            return pd.to_datetime(d, unit="ms", utc=True).tz_convert("Asia/Shanghai")
        return pd.to_datetime(d)

    df["date"] = df["date"].apply(parse_date)
    df = df.rename(columns={"date": "time", "close": "指数", "pe": "市盈率"})
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df


def fetch_pb_data(market="上证"):
    """抓取指定市场的 PB 数据（API 参数为 indexCode）"""
    market_info = MARKETS[market]
    url = "https://legulegu.com/api/stockdata/index-basic-pb"
    token = _get_token()
    params = {"token": token, "indexCode": market_info["index_code"]}
    cookie_args = get_cookie_csrf(url=market_info["pb_url"])
    r = requests.get(url, params=params, **cookie_args, timeout=15)
    r.raise_for_status()
    data = r.json()
    items = data.get("data", [])
    df = pd.DataFrame(items)[["date", "close", "addPb", "pb", "middlePb"]]

    def parse_date(d):
        if isinstance(d, (int, float)):
            return pd.to_datetime(d, unit="ms", utc=True).tz_convert("Asia/Shanghai")
        return pd.to_datetime(d)

    df["date"] = df["date"].apply(parse_date)
    df = df.rename(columns={
        "date": "time", "close": "指数",
        "addPb": "平均市净率", "pb": "加权市净率",
        "middlePb": "中位数市净率",
    })
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df


def auto_update_pe():
    """增量更新 PE CSV"""
    output = os.path.join(BASE_DIR, "eco_data", "全市场PE.csv")
    existing_dates = set()

    if os.path.exists(output):
        old = pd.read_csv(output)
        existing_dates = set(old["time"])
        print(f"已有 PE 数据: {len(old)} 条, 覆盖 {len(existing_dates)} 个交易日")
    else:
        print("无已有 PE 数据，新建")

    new = fetch_pe_data()
    new_dates = set(new["time"].dt.strftime("%Y-%m-%d"))
    missing = new[~new["time"].dt.strftime("%Y-%m-%d").isin(existing_dates)]

    if len(missing) == 0:
        print("PE 无需更新")
        return

    combined = pd.concat([pd.read_csv(output) if os.path.exists(output) else pd.DataFrame(), missing], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    combined.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"PE 保存完成: {output}, 总计 {len(combined)} 条, 新增 {len(missing)} 条")
    print(f"  最新: {combined.iloc[-1]['time']}, PE={combined.iloc[-1]['市盈率']}")


def auto_update_pb():
    """增量更新 PB CSV"""
    output = os.path.join(BASE_DIR, "eco_data", "全市场PB.csv")
    existing_dates = set()

    if os.path.exists(output):
        old = pd.read_csv(output)
        existing_dates = set(old["time"])
        print(f"已有 PB 数据: {len(old)} 条, 覆盖 {len(existing_dates)} 个交易日")
    else:
        print("无已有 PB 数据，新建")

    new = fetch_pb_data()
    new_dates = set(new["time"].dt.strftime("%Y-%m-%d"))
    missing = new[~new["time"].dt.strftime("%Y-%m-%d").isin(existing_dates)]

    if len(missing) == 0:
        print("PB 无需更新")
        return

    combined = pd.concat([pd.read_csv(output) if os.path.exists(output) else pd.DataFrame(), missing], ignore_index=True)
    combined = combined.drop_duplicates(subset=["time"])
    combined = combined.sort_values("time").reset_index(drop=True)

    combined.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"PB 保存完成: {output}, 总计 {len(combined)} 条, 新增 {len(missing)} 条")
    print(f"  最新: {combined.iloc[-1]['time']}, 平均PB={combined.iloc[-1]['平均市净率']}")


if __name__ == "__main__":
    print("=== 全市场 PE ===")
    auto_update_pe()
    print()
    print("=== 全市场 PB ===")
    auto_update_pb()
