#!/usr/bin/env python3
"""
eco_analysis.py — 经济数据摘要生成器

读取已有的 eco_data/ + sse_etf_data/ + data_stock/ 数据，
如果本地没有（如 GitHub Actions 环境），则通过 akshare 实时抓取。

输出：
  - news/reports/eco_YYYY-MM-DD.md（人类可读报告）
  - stdout（由 news_intelligence.py 捕获注入 prompt）
"""

import os, json, re, sys
from datetime import datetime, timedelta
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
ECO_DIR = os.path.join(PROJECT_DIR, "eco_data")
SSE_DIR = os.path.join(PROJECT_DIR, "sse_etf_data")
STOCK_DIR = os.path.join(PROJECT_DIR, "data_stock")
CRYPTO_DIR = os.path.join(PROJECT_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# ============================================================
# 宏观数据读取（双模式：本地CSV > akshare实时）
# ============================================================

def read_csv(name, path, col_map=None):
    """安全读取 CSV，返回最新行 dict。"""
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, encoding='utf-8')
        if df.empty:
            return None
        row = df.tail(1).to_dict('records')[0]
        if col_map:
            row = {col_map.get(k, k): v for k, v in row.items()}
        return row
    except Exception:
        return None


def fetch_akshare(symbol_func, params=None):
    """通过 akshare 实时抓取（用于 GitHub Actions 环境）。"""
    try:
        import akshare as ak
        func = getattr(ak, symbol_func)
        if params:
            df = func(**params)
        else:
            df = func()
        if df is not None and not df.empty:
            return df.tail(1).to_dict('records')[0]
    except Exception:
        pass
    return None


def get_macro_snapshot():
    """读取所有宏观指标的最新值（优先本地 CSV，无则 akshare 实时抓）。"""
    # 先试本地 CSV
    csv_files = {
        "CPI": os.path.join(ECO_DIR, "CPI.csv"),
        "PPI": os.path.join(ECO_DIR, "PPI.csv"),
        "PMI": os.path.join(ECO_DIR, "PMI.csv"),
        "M1": os.path.join(ECO_DIR, "M1.csv"),
        "M2": os.path.join(ECO_DIR, "M2.csv"),
        "LPR": os.path.join(ECO_DIR, "LPR.csv"),
        "DR007": os.path.join(ECO_DIR, "dr007_history.csv"),
        "Shibor": os.path.join(ECO_DIR, "Shibor.csv"),
        "国债收益率": os.path.join(ECO_DIR, "国债收益率.csv"),
        "中美利差": os.path.join(ECO_DIR, "中美利差.csv"),
        "社融增量": os.path.join(ECO_DIR, "社会融资规模增量.csv"),
        "社融存量": os.path.join(ECO_DIR, "社会融资规模存量.csv"),
        "北向资金": os.path.join(ECO_DIR, "北向资金.csv"),
        "两融余额": os.path.join(ECO_DIR, "融资融券余额.csv"),
        "A股成交额": os.path.join(ECO_DIR, "A股成交额.csv"),
        "工业增加值": os.path.join(ECO_DIR, "规模以上工业增加值.csv"),
        "PE": os.path.join(ECO_DIR, "全市场PE.csv"),
        "PB": os.path.join(ECO_DIR, "全市场PB.csv"),
        "企业贷款占比": os.path.join(ECO_DIR, "企业中长期贷款占比.csv"),
    }

    result = {}
    for name, path in csv_files.items():
        row = read_csv(name, path)
        if row:
            result[name] = row

    # 如果本地没有数据，尝试 akshare 实时抓取（GitHub Actions 环境）
    if not result:
        print("  > 未找到本地宏观数据，尝试 akshare 实时抓取...")
        try:
            import akshare as ak

            # LPR
            try:
                df = ak.macro_china_lpr()
                if df is not None and not df.empty:
                    row = df.tail(1).to_dict('records')[0]
                    result["LPR"] = {"LPR1Y": row.get("LPR1Y", ""), "LPR5Y": row.get("LPR5Y", "")}
            except:
                pass

            # Shibor（近似 DR007）
            try:
                df = ak.macro_china_shibor_all()
                if df is not None and not df.empty:
                    row = df.tail(1).to_dict('records')[0]
                    result["Shibor"] = row
                    # 用隔夜 Shibor 近似 DR007
                    if "隔夜" in row:
                        result["DR007"] = {"DR007": row["隔夜"]}
            except:
                pass

            # CPI
            try:
                df = ak.macro_china_cpi_yearly()
                if df is not None and not df.empty:
                    row = df.tail(1).to_dict('records')[0]
                    cpi_val = row.get('cpi', row.get('CPI', row.get('cpi_yearly', None)))
                    if cpi_val:
                        result["CPI"] = {"CPI": float(str(cpi_val).replace('%',''))/100 if '%' in str(cpi_val) else float(cpi_val)/100}
            except:
                pass

            # PMI
            try:
                df = ak.macro_china_pmi()
                if df is not None and not df.empty:
                    row = df.tail(1).to_dict('records')[0]
                    pmi_val = row.get('制造业采购经理人指数', row.get('pmi', None))
                    if pmi_val:
                        result["PMI"] = {"PMI": float(str(pmi_val).replace('%',''))/100 if '%' in str(pmi_val) else float(pmi_val)}
            except:
                pass

            # M2
            try:
                df = ak.macro_china_money_supply()
                if df is not None and not df.empty:
                    row = df.tail(1).to_dict('records')[0]
                    m2_val = row.get('m2', row.get('M2', row.get('m2_yearly', None)))
                    col = [c for c in row.keys() if 'm2' in c.lower() or 'M2' in c]
                    if col:
                        result["M2"] = {"M2同比增速": float(str(row[col[0]]).replace('%',''))/100}
            except:
                pass

            print(f"  > akshare 成功获取 {len(result)} 个宏观指标")
        except Exception as e:
            print(f"  > akshare 宏观抓取失败: {e}")

    return result


def describe_macro(macro):
    """将宏观数据转为简洁的文本摘要。"""
    lines = []

    # 利率
    dr007 = macro.get("DR007", {})
    lpr = macro.get("LPR", {})
    if dr007:
        val = dr007.get("DR007", "")
        lines.append(f"DR007={(val if isinstance(val,str) else f'{val:.2f}')}%")
    if lpr:
        lines.append(f"LPR1Y={lpr.get('LPR1Y','')}% LPR5Y={lpr.get('LPR5Y','')}%")

    # 通胀
    cpi = macro.get("CPI", {})
    ppi = macro.get("PPI", {})
    if cpi:
        v = cpi.get("CPI", 0)
        if isinstance(v, (int, float)):
            lines.append(f"CPI={v*100:.1f}%")
    if ppi:
        v = ppi.get("PPI", 0)
        if isinstance(v, (int, float)):
            lines.append(f"PPI={'+' if v>=0 else ''}{v*100:.1f}%")

    # 货币
    m1 = macro.get("M1", {})
    m2 = macro.get("M2", {})
    if m1:
        v = m1.get("M1同比增速", 0)
        if isinstance(v, (int, float)):
            lines.append(f"M1={'+' if v>=0 else ''}{v*100:.1f}%")
    if m2:
        v = m2.get("M2同比增速", 0)
        if isinstance(v, (int, float)):
            lines.append(f"M2={'+' if v>=0 else ''}{v*100:.1f}%")

    # 经济
    pmi = macro.get("PMI", {})
    ind = macro.get("工业增加值", {})
    if pmi:
        v = pmi.get("PMI", 0)
        if isinstance(v, (int, float)):
            lines.append(f"PMI={v*100:.1f}")
    if ind:
        v = ind.get("规模以上工业增加值同比增速", 0)
        if isinstance(v, (int, float)):
            lines.append(f"工业增加值={'+' if v>=0 else ''}{v*100:.1f}%")

    # 资金
    north = macro.get("北向资金", {})
    margin = macro.get("两融余额", {})
    if north:
        v = north.get("北向资金（亿元）", "")
        lines.append(f"北向={v}亿" if not isinstance(v, float) else f"北向={v:.0f}亿")
    if margin:
        v = margin.get("融资融券余额（亿元）", "")
        lines.append(f"两融={v}亿" if not isinstance(v, float) else f"两融={v:.0f}亿")

    # 债券
    spread = macro.get("中美利差", {})
    if spread:
        cn10 = spread.get("中国10年", "")
        us10 = spread.get("美国10年", "")
        diff = spread.get("中美10年利差", "")
        if cn10 and us10:
            lines.append(f"CN10Y={cn10}% US10Y={us10}% 利差={diff}%")

    return " | ".join(lines)


# ============================================================
# ETF 数据读取
# ============================================================

# 关注的核心 ETF
TARGET_ETF = {
    "510300": "沪深300",
    "588000": "科创50",
    "510050": "上证50",
    "159949": "创业板50",
    "159919": "沪深300ETF(嘉实)",
    "512100": "中证1000",
    "159845": "中证1000(另一个)",
}

# 美股指数（GitHub Actions 时用 akshare）
US_INDEX = {
    "SPY": "标普500",
    "QQQ": "纳斯达克",
    "BTC-USD": "比特币",
}


def get_etf_prices():
    """读取 ETF 价格变化（优先本地，无则 akshare）。"""
    result = {}
    has_local = False

    for code, name in TARGET_ETF.items():
        path = os.path.join(STOCK_DIR, f"{code}_Klines.csv")
        if not os.path.exists(path):
            continue
        has_local = True
        try:
            df = pd.read_csv(path, encoding='utf-8')
            if df.empty:
                continue
            recent = df.tail(5)
            if len(recent) >= 2:
                cur = recent.iloc[-1]['close']
                prev = recent.iloc[0]['close']
                change = (cur - prev) / prev * 100
                result[name] = {"price": f"{cur:.2f}", "chg_5d": f"{change:+.1f}%"}
        except Exception:
            pass

    # 本地无数据时用 akshare
    if not has_local:
        print("  > 尝试 akshare 拉取指数数据...")
        try:
            import akshare as ak
            indices = [
                ("sh000300", "沪深300"),
                ("sh000688", "科创50"),
                ("sh000001", "上证指数"),
                ("sh000016", "上证50"),
                ("sz399006", "创业板指"),
                ("sh000905", "中证500"),
            ]
            for symbol, name in indices:
                try:
                    idx = ak.stock_zh_index_daily_em(symbol=symbol)
                    if idx is not None and len(idx) >= 2:
                        r = idx.tail(5)
                        cur = r.iloc[-1]['close']
                        prev = r.iloc[0]['close']
                        result[name] = {"chg_5d": f"{(cur-prev)/prev*100:+.1f}%"}
                        # 也尝试加入美股指数
                except:
                    pass
            # 美股
            try:
                us_idx = ak.stock_us_index_daily_em(symbol="spx")
                if us_idx is not None and len(us_idx) >= 2:
                    r = us_idx.tail(5)
                    result["标普500"] = {"chg_5d": f"{(r.iloc[-1]['close']-r.iloc[0]['close'])/r.iloc[0]['close']*100:+.1f}%"}
            except:
                pass
            print(f"  > akshare 获取 {len(result)} 个指数数据")
        except Exception as e:
            print(f"  > akshare 指数抓取失败: {e}")

    return result


def get_btc_snapshot():
    """读取 BTC 日线数据获取涨跌幅（优先本地，无则 akshare）。"""
    btc_path = os.path.join(CRYPTO_DIR, "BTC_factors.csv")
    if os.path.exists(btc_path):
        try:
            df = pd.read_csv(btc_path)
            if 'close' in df.columns and len(df) >= 2:
                recent = df.tail(5)
                chg_1d = (recent.iloc[-1]['close'] - recent.iloc[-2]['close']) / recent.iloc[-2]['close'] * 100
                chg_5d = (recent.iloc[-1]['close'] - recent.iloc[0]['close']) / recent.iloc[0]['close'] * 100
                return {"price": f"{recent.iloc[-1]['close']:.2f}", "chg_1d": f"{chg_1d:+.2f}%", "chg_5d": f"{chg_5d:+.2f}%"}
        except Exception:
            pass

    # 本地无数据时用 akshare
    try:
        import akshare as ak
        crypto_df = ak.crypto_hist(symbol="BTC-USD")
        if crypto_df is not None and len(crypto_df) >= 2:
            crypto_df = crypto_df.tail(5)
            cur = crypto_df.iloc[-1]['close']
            prev_1d = crypto_df.iloc[-2]['close']
            prev_5d = crypto_df.iloc[0]['close']
            return {
                "price": f"{cur:.2f}",
                "chg_1d": f"{(cur-prev_1d)/prev_1d*100:+.2f}%",
                "chg_5d": f"{(cur-prev_5d)/prev_5d*100:+.2f}%",
            }
    except Exception:
        pass
    return None


# ============================================================
# DeepSeek API 调用
# ============================================================

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"


def call_deepseek(macro_text: str, etf_data: dict, btc_data: dict) -> dict:
    """将宏观+ETF数据发给 DeepSeek，获取经济分析报告。"""
    if not DEEPSEEK_API_KEY:
        print("  > 未设置 DEEPSEEK_API_KEY，跳过 API 调用")
        return {}

    from openai import OpenAI

    # 格式化数据
    data_lines = ["## 宏观数据"]
    data_lines.append(macro_text)
    data_lines.append("")
    data_lines.append("## 市场指数（近5日涨跌幅）")
    for name, info in etf_data.items():
        p = f" {info.get('price','')}" if info.get('price') else ""
        data_lines.append(f"- {name}:{p} {info['chg_5d']}")
    if btc_data:
        data_lines.append(f"\n## 比特币")
        data_lines.append(f"- 价格: {btc_data['price']}")
        data_lines.append(f"- 1日: {btc_data['chg_1d']}")
        data_lines.append(f"- 5日: {btc_data['chg_5d']}")
    data_text = "\n".join(data_lines)

    prompt = f"""你是一名宏观策略研究员，基于以下经济数据进行系统性分析。

请分析：流动性（资金松紧）、信用周期、经济基本面、资金行为、当前核心矛盾、对股市/加密的影响。

要求：
- 不要逐条复述数据
- 做跨指标联动分析，识别背离关系
- 强调边际变化而不是绝对值
- 输出用以下格式，**不要用 JSON**，用 Markdown

## 宏观周期判断
（扩张/复苏/过热/滞胀/收缩/企稳震荡）

## 流动性
（宽松/中性/收紧 + 一句话理由）

## 经济状态
（结论 + 一句话理由）

## 资金面
（结论 + 一句话理由）

## 核心矛盾
（1-3个当前最关键的背离或冲突）

## 对市场的影响
- 对BTC方向性判断
- 对A股方向性判断
- 对美股方向性判断
- 对利率/债市判断

## 一句话总结

【经济数据】
{data_text}
"""

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL, timeout=120)
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        print("  > API 分析成功")
        return {"analysis": content}
    except Exception as e:
        print(f"  > API 调用失败: {e}")
        return {"analysis": f"API 调用失败: {e}"}


def main():
    print("\n[经济数据分析]")
    data = build_eco_json()

    # 先输出原始数据 JSON 到 stdout
    json_str = json.dumps(data, ensure_ascii=False)
    print(json_str)

    # 调 DeepSeek 做分析
    result = call_deepseek(data["macro"], data["etf"] or {}, data["btc"] or {})

    # 保存为 markdown 报告
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"eco_{datetime.now().strftime('%Y-%m-%d')}.md")

    lines = ["# 经济分析报告\n"]
    lines.append(f"> 生成时间: {data['date']}\n")
    lines.append("---\n")

    if result.get("analysis"):
        lines.append(result["analysis"])
    else:
        lines.append("## 原始数据（API 未执行）\n")
        lines.append(f"宏观: {data['macro']}\n")
        lines.append(f"BTC: {data['btc']}\n")
        lines.append(f"指数: {data['etf']}\n")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  > 报告已保存: {report_path}")

    # 输出摘要（供 news_intelligence 注入）
    summary = f"【经济分析摘要】{result.get('analysis','')[:200]}..." if result.get('analysis') else ""
    print(f"\n[ECO_SUMMARY]{summary}[/ECO_SUMMARY]")
