#!/usr/bin/env python3
"""
eco_analysis.py — 经济数据摘要生成器

读取已有的 eco_data/ + sse_etf_data/ + data_stock/ 数据，
如果本地 CSV 不存在，则通过 akshare 实时抓取。

输出：
  - news/reports/eco_YYYY-MM-DD.md（人类可读报告）
  - stdout（由 news_intelligence.py 捕获注入 prompt）
"""

import os, json, re, sys
from datetime import datetime, timedelta
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# 加载 .env（项目根目录下的密钥文件）
env_path = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()
ECO_DIR = os.path.join(PROJECT_DIR, "eco_data")
SSE_DIR = os.path.join(PROJECT_DIR, "sse_etf_data")
STOCK_DIR = os.path.join(PROJECT_DIR, "data_stock")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# ============================================================
# 宏观数据读取（双模式：本地CSV > akshare实时）
# ============================================================

def read_csv(name, path, col_map=None):
    """安全读取 CSV，返回最新行 dict。"""
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        if df.empty:
            return None
        row = df.tail(1).to_dict('records')[0]
        if col_map:
            row = {col_map.get(k, k): v for k, v in row.items()}
        return row
    except Exception:
        return None


def read_csv_history(path, n=6):
    """读取 CSV 最近 n 行 DataFrame，用于计算 delta 和均值。"""
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        if df.empty or len(df) < 2:
            return None
        return df.tail(n)
    except Exception:
        return None


def fetch_akshare(symbol_func, params=None):
    """通过 akshare 实时抓取（本地 CSV 缺失时的备用方案）。"""
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

    # 如果本地没有数据，尝试 akshare 实时抓取（备用方案）
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

    # 为每条指标附加 delta（环比变化率）和 5 期均值
    for name, path in csv_files.items():
        if name not in result:
            continue
        hist = read_csv_history(path, n=6)
        if hist is None:
            continue
        val_cols = [c for c in hist.columns if c.lower() not in ('date', '日期', '月份', '时间', 'time')]
        if not val_cols:
            continue
        col = val_cols[-1]
        try:
            vals = hist[col].apply(lambda x: float(str(x).replace('%','').replace(',','').replace('+','')))
            latest = vals.iloc[-1]
            prev = vals.iloc[-2]
            if prev != 0:
                result[name]["_delta"] = f"{(latest - prev) / abs(prev) * 100:+.1f}%"
            if len(vals) >= 5:
                result[name]["_mean5"] = f"{vals.tail(5).mean():.2f}"
        except:
            pass

    return result


def describe_macro(macro):
    """将宏观数据转为机构级结构化摘要（含 delta 和趋势）。"""
    sections = []

    # ── 利率 ──
    dr007 = macro.get("DR007", {})
    shibor = macro.get("Shibor", {})
    lpr = macro.get("LPR", {})
    bond = macro.get("国债收益率", {})
    rate_parts = []
    if dr007:
        v = _value("DR007", dr007)
        rate_parts.append(f"DR007={safe_fmt(v)}% Δ{_delta(dr007)}")
    if shibor:
        for k in ['隔夜', '1周']:
            if k in shibor:
                rate_parts.append(f"Shibor{k}={shibor[k]}")
    if lpr:
        rate_parts.append(f"LPR1Y={lpr.get('LPR1Y','')}% LPR5Y={lpr.get('LPR5Y','')}%")
    if bond:
        v = bond.get("中国10年", bond.get("10年", ""))
        if v:
            rate_parts.append(f"CN10Y={v}%")
    if rate_parts:
        sections.append("【利率】" + " | ".join(rate_parts))

    # ── 通胀 ──
    cpi = macro.get("CPI", {})
    ppi = macro.get("PPI", {})
    if cpi or ppi:
        parts = []
        if cpi: parts.append(f"CPI={_val_pct('CPI', cpi)} Δ{_delta(cpi)}")
        if ppi: parts.append(f"PPI={_val_pct('PPI', ppi)} Δ{_delta(ppi)}")
        sections.append("【通胀】" + " | ".join(parts))

    # ── 货币信用 ──
    m1 = macro.get("M1", {})
    m2 = macro.get("M2", {})
    social_inc = macro.get("社融增量", {})
    social_stock = macro.get("社融存量", {})
    loan = macro.get("企业贷款占比", {})
    money_parts = []
    if m1: money_parts.append(f"M1={_val_pct_raw(m1)} Δ{_delta(m1)}")
    if m2: money_parts.append(f"M2={_val_pct_raw(m2)} Δ{_delta(m2)}")
    if social_inc: money_parts.append(f"社融增量={_val_raw(social_inc)}亿")
    if social_stock: money_parts.append(f"社融存量={_val_raw(social_stock)}亿")
    if money_parts:
        sections.append("【货币信用】" + " | ".join(money_parts))

    # ── 经济动能 ──
    pmi = macro.get("PMI", {})
    ind = macro.get("工业增加值", {})
    econ_parts = []
    if pmi: econ_parts.append(f"PMI={_val_pct('PMI', pmi)} Δ{_delta(pmi)}")
    if ind: econ_parts.append(f"工业增加值={_val_pct_raw(ind)}")
    if econ_parts:
        sections.append("【经济动能】" + " | ".join(econ_parts))

    # ── 资金面 ──
    north = macro.get("北向资金", {})
    margin = macro.get("两融余额", {})
    turnover = macro.get("A股成交额", {})
    cap_parts = []
    if north: cap_parts.append(f"北向={_val_raw(north)}亿")
    if margin: cap_parts.append(f"两融={_val_raw(margin)}亿")
    if turnover: cap_parts.append(f"成交额={_val_raw(turnover)}亿")
    if cap_parts:
        sections.append("【资金面】" + " | ".join(cap_parts))

    # ── 利差 ──
    spread = macro.get("中美利差", {})
    if spread:
        cn = spread.get("中国10年", "")
        us = spread.get("美国10年", "")
        diff = spread.get("中美10年利差", "")
        if cn and us:
            sections.append(f"【利差】CN10Y={cn}% US10Y={us}% 利差={diff}%")

    # ── 估值 ──
    pe = macro.get("PE", {})
    pb = macro.get("PB", {})
    val_parts = []
    if pe: val_parts.append(f"PE={_val_raw(pe)}")
    if pb: val_parts.append(f"PB={_val_raw(pb)}")
    if val_parts:
        sections.append("【估值】" + " | ".join(val_parts))

    return "\n".join(sections) if sections else "无宏观数据"


# ── 辅助函数 ──
def _value(key, d):
    for k, v in d.items():
        if key.lower() in k.lower():
            try: return float(str(v).replace('%','').replace(',',''))
            except: return v
    return None

def _delta(d):
    return d.get("_delta", "").replace("+", "↑").replace("-", "↓") if "_delta" in d else ""

def _val_pct(key, d):
    v = _value(key, d)
    if v is None: return "N/A"
    return f"{v:.1f}%" if abs(v) < 100 else f"{v:.0f}"

def _val_pct_raw(d):
    for k, v in d.items():
        if k.startswith("_"): continue
        try: return f"{float(str(v).replace('%','').replace('+','')):.1f}%"
        except: return str(v)
    return "N/A"

def _val_raw(d):
    for k, v in d.items():
        if k.startswith("_"): continue
        try: return f"{float(str(v).replace(',','')):.0f}"
        except: return str(v)
    return "N/A"

def safe_fmt(v):
    if v is None: return "N/A"
    try: return f"{float(v):.2f}"
    except: return str(v)


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

# 美股指数（本地 CSV 缺失时用 akshare）
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
            df = pd.read_csv(path, encoding='utf-8-sig')
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


# ============================================================
# DeepSeek API 调用
# ============================================================

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = "https://api.deepseek.com"


def call_deepseek(macro_text: str, etf_data: dict) -> dict:
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
    data_text = "\n".join(data_lines)

    prompt = f"""你是一名宏观策略研究员，需要基于以下宏观经济数据进行系统性分析，并给出可交易的市场判断。

# 分析目标
1. 宏观经济处于：扩张 / 复苏 / 过热 / 滞胀 / 收缩 / 企稳震荡 哪一阶段
2. 流动性环境（宽松 / 中性 / 收紧）
3. 信用周期（扩张 / 收缩 / 见底 / 见顶）
4. 风险偏好（上升 / 下降 / 中性）
5. 对股市的方向性影响（偏多 / 偏空 / 震荡）

# 分析要求
- **绝对禁止逐条复述数据**！如果你只是把数据复述一遍，你的输出毫无价值
- 做"跨指标联动分析"——把利率、通胀、货币、资金面串成因果链
- 重点识别背离关系（如宽松流动性+收缩信用 = 什么信号？）
- 强调边际变化（数据中的 Δ ↑↓ 箭头）而不是绝对值
- 区分领先指标（社融、北向资金）vs 滞后指标（CPI）
- 每个结论必须有 1-2 句因果链推导

# 输出格式（严格遵循）

## 1. 宏观周期判断
（只给一个阶段，后面跟 2-3 句基于数据的因果推导）

## 2. 流动性分析
（结论 + 因果链：DR007/M2/LPR 互相印证了什么？）

## 3. 信用周期
（结论 + 因果链：社融和M2的缺口说明什么？）

## 4. 经济基本面
（结论 + 因果链：PMI/CPI 联合指向什么状态？）

## 5. 资金面
（结论 + 因果链：北向/两融/成交量反映什么风险偏好？）

## 6. 核心矛盾（最重要！）
指出 2-3 个最关键的背离或冲突，例如：
- 矛盾1: （流动性指标A）宽松 vs （信用指标B）收缩 → 意味着什么
- 矛盾2: ...
- 矛盾3: ...

## 7. 市场结论
- 对A股：方向判断 + 风格偏好（大盘/小盘、成长/价值）+ 依据
- 对美股：方向判断 + 依据
- 对利率/债市：方向判断 + 依据
- 最大风险来源

## 8. 一句话总结
（格式：当前市场处于 X 阶段，流动性 Y，核心矛盾是 Z，短期关注 A）

---
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


def build_eco_json():
    """组装完整的宏观经济快照 JSON（宏观 + ETF）。"""
    macro = get_macro_snapshot()
    macro_text = describe_macro(macro) if macro else "无宏观数据"
    etf = get_etf_prices()

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "macro": macro_text,
        "etf": etf,
    }


def main():
    print("\n[经济数据分析]")
    data = build_eco_json()

    # 先输出原始数据 JSON 到 stdout
    json_str = json.dumps(data, ensure_ascii=False)
    print(json_str)

    # 调 DeepSeek 做分析
    result = call_deepseek(data["macro"], data["etf"] or {})

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
        lines.append(f"指数: {data['etf']}\n")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  > 报告已保存: {report_path}")

    # 输出摘要（供 news_intelligence 注入）
    summary = f"【经济分析摘要】{result.get('analysis','')[:200]}..." if result.get('analysis') else ""
    print(f"\n[ECO_SUMMARY]{summary}[/ECO_SUMMARY]")

if __name__ == '__main__':
    main()