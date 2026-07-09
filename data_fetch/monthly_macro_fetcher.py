"""
月度宏观指标批量抓取工具

从 akshare 一次性抓取所有月度频率的宏观经济指标，
增量更新到 eco_data/ 下的对应 CSV 文件。

覆盖指标：CPI, PPI, PMI, M1/M2, 社会融资规模

数据来源：akshare -> 国家统计局 / 中国人民银行 / 东方财富
"""

import os
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ECO_DIR = os.path.join(BASE_DIR, "eco_data")
os.makedirs(ECO_DIR, exist_ok=True)

# 指标配置：{ 文件名: (akshare函数名, 列映射) }
INDICATORS = {
    "CPI": {
        "output": os.path.join(ECO_DIR, "CPI.csv"),
        "func": "macro_china_cpi_yearly",
        "date_col": "日期",
        "value_col": "现值",
    },
    "PPI": {
        "output": os.path.join(ECO_DIR, "PPI.csv"),
        "func": "macro_china_ppi_yearly",
        "date_col": "日期",
        "value_col": "全部工业品",
    },
    "PMI": {
        "output": os.path.join(ECO_DIR, "PMI.csv"),
        "func": "macro_china_pmi",
        "date_col": "月份",
        "value_col": "制造业-指数",
    },
    "M1": {
        "output": os.path.join(ECO_DIR, "M1.csv"),
        "func": "macro_china_money_supply",
        "date_col": "月份",
        "value_col": "货币(M1)-数量(亿元)",
    },
    "M2": {
        "output": os.path.join(ECO_DIR, "M2.csv"),
        "func": "macro_china_money_supply",
        "date_col": "月份",
        "value_col": "货币和准货币(M2)-数量(亿元)",
    },
    "社融增量": {
        "output": os.path.join(ECO_DIR, "社会融资规模增量.csv"),
        "func": "macro_china_shrzgm",
        "date_col": "月份",
        "value_col": "社会融资规模增量",
    },
    "社融存量": {
        "output": os.path.join(ECO_DIR, "社会融资规模存量.csv"),
        "func": "macro_china_shrzgm",
        "date_col": "月份",
        "value_col": "社会融资规模存量",
    },
}


def load_existing(path):
    """读取已有 CSV，返回 (DataFrame, 已有日期集合)。解析失败则视为空。"""
    if not os.path.exists(path):
        return pd.DataFrame(), set()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        if df.empty:
            return df, set()
        date_col = df.columns[0]
        dates = set(df[date_col].astype(str).str.strip())
        return df, dates
    except Exception:
        print(f"(警告: CSV 损坏，从 {os.path.basename(path)} 重新抓取)")
        return pd.DataFrame(), set()


def fetch_and_merge(indicator_name, config):
    """抓取单个指标并合并去重。"""
    print(f"\n  [{indicator_name}] ", end="")

    try:
        import akshare as ak
        func = getattr(ak, config["func"])
        raw = func()
    except ImportError:
        print("akshare 不可用，跳过")
        return
    except Exception as e:
        print(f"抓取失败: {e}")
        return

    if raw is None or raw.empty:
        print("无数据返回")
        return

    # 加载已有数据
    existing_df, existing_dates = load_existing(config["output"])

    # 处理不同函数返回的列名
    date_col = config["date_col"]
    value_col = config["value_col"]

    # 查找实际列名（精确匹配优先，模糊匹配取第一个）
    actual_date = None
    actual_value = None
    for c in raw.columns:
        if date_col in str(c):
            actual_date = c
    # value_col: 精确等值匹配，不行再模糊（取第一个匹配）
    exact_matches = [c for c in raw.columns if str(c).strip() == str(value_col).strip()]
    if exact_matches:
        actual_value = exact_matches[0]
    else:
        for c in raw.columns:
            if value_col in str(c):
                actual_value = c
                break

    if actual_date is None:
        actual_date = raw.columns[0]
    if actual_value is None:
        actual_value = raw.columns[-1]

    # 提取日期和值
    out = pd.DataFrame()
    out["date"] = raw[actual_date].astype(str).str.strip()
    out[indicator_name] = pd.to_numeric(raw[actual_value], errors="coerce")

    # 去重：只保留新日期
    new_rows = out[~out["date"].isin(existing_dates)]
    if new_rows.empty:
        print("已是最新（无新数据）")
        return

    # 合并保存
    if not existing_df.empty:
        combined = pd.concat([existing_df, new_rows], ignore_index=True)
    else:
        combined = new_rows

    # 确保 date 列全是字符串，避免 sort_values 类型混合报错
    combined["date"] = combined["date"].astype(str).str.strip()
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    combined = combined.sort_values("date")
    combined.to_csv(config["output"], index=False, encoding="utf-8-sig")
    print(f"新增 {len(new_rows)} 行 → 总计 {len(combined)} 行")


def main():
    print("=" * 50)
    print("  月度宏观指标批量更新")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    for name, config in INDICATORS.items():
        try:
            fetch_and_merge(name, config)
        except Exception as e:
            import traceback
            print(f"\n  [{name}] 未捕获异常: {e}")
            traceback.print_exc()

    # 汇总
    print("\n" + "=" * 50)
    print("  数据文件大小:")
    for name, config in INDICATORS.items():
        if os.path.exists(config["output"]):
            kb = os.path.getsize(config["output"]) / 1024
            print(f"    {name:<10s} {kb:>8.1f} KB")
        else:
            print(f"    {name:<10s}  (缺失)")
    print("=" * 50)


if __name__ == "__main__":
    main()
