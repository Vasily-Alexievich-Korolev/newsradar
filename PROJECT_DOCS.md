# News Program — 每日新闻情报系统

自动抓取宏观经济数据 + 全球新闻，通过 DeepSeek 生成每日经济分析和新闻简报，并构建静态网站。
由 Windows 定时任务每天 06:00 自动运行，完成后推送到远程仓库。不依赖 GitHub Actions。

---

## 一、项目结构

```
news_program/
│
├── .github/workflows/
│   └── daily-news.yml        ← GitHub Actions 工作流（交易日 06:00 自动触发）
│
├── data_fetch/               ← 12 个数据抓取脚本（update_all_eco.py 统一调度）
│   ├── update_all_eco.py     ← 主控脚本，依次运行所有 fetcher
│   ├── DR007_get.py          ← 银行间 7 天回购利率
│   ├── shibor_fetcher.py     ← Shibor 各期限利率
│   ├── bond_yield_fetcher.py ← 中国国债收益率曲线
│   ├── margin_balance_fetcher.py  ← 融资融券余额
│   ├── south_bound_fetcher.py     ← 港股通南向资金
│   ├── cn_us_spread_fetcher.py    ← 中美 10 年国债利差
│   ├── turnover_fetcher.py        ← A 股日成交额
│   ├── account_fetcher.py         ← 新增投资者开户数（月频）
│   ├── market_valuation_fetcher.py ← 全市场 PE / PB 估值
│   ├── update_etf_share.py         ← 上交所 ETF 日份额
│   └── update_etf_kline.py         ← 核心 ETF 日 K 线
│
├── news/                     ← 分析引擎
│   ├── eco_analysis.py       ← 宏观数据分析 + DeepSeek 经济报告
│   ├── news_intelligence.py  ← RSS 新闻抓取 + DeepSeek 每日简报
│   ├── build_static_site.py  ← 生成 HTML 静态网站
│   ├── events.json           ← 事件记忆库（持久化跨日追踪）
│   ├── reports/              ← 生成的 Markdown 报告
│   │   ├── eco_YYYY-MM-DD.md       ← 经济分析报告
│   │   └── briefing_YYYY-MM-DD.md  ← 每日新闻简报
│   └── static_site/          ← build_static_site.py 的输出（部署到 gh-pages）
│
├── eco_data/                 ← 宏观经济历史数据（CSV，已持久化到 git）
├── sse_etf_data/             ← 上交所 ETF 份额日数据（CSV）
├── data_stock/               ← A 股核心 ETF 日 K 线（CSV）
├── data/                     ← 项目数据（CSV）
├── news_data/                ← RSS 缓存（从新闻源抓取的原始数据）
│
└── .gitignore
```

---

## 二、数据流向

```
                   ┌──────────────────────────────┐
                   │  GitHub Actions (06:00 CST)   │
                   │  .github/workflows/daily-news.yml │
                   └──────┬───────────────────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 1: 安装依赖      │
              │  pip install ...       │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 2: 抓取 12 项数据  │
              │  python data_fetch/     │
              │  update_all_eco.py      │
              │                         │
              │  ┌─────────────────┐    │
              │  │ 9 个宏观 fetcher │    │  → eco_data/*.csv
              │  │ DR007 / Shibor  │    │
              │  │ 国债 / 两融     │    │
              │  │ 南向 / 中美利差 │    │
              │  │ 成交额 / 开户   │    │
              │  │ PE / PB        │    │
              │  └─────────────────┘    │
              │  ┌─────────────────┐    │
              │  │ ETF 日份额      │    │  → sse_etf_data/*.csv
              │  │ ETF 日 K 线     │    │  → data_stock/*_Klines.csv
              │  └─────────────────┘    │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 3: 经济分析      │
              │  python news/          │
              │  eco_analysis.py       │
              │  → 读取 eco_data/      │  → news/reports/eco_*.md
              │  → DeepSeek 分析       │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 4: 新闻简报      │
              │  python news/          │
              │  news_intelligence.py  │
              │  → RSS 抓取新闻        │
              │  → 读取 eco_*.md       │  → news/reports/briefing_*.md
              │  → DeepSeek 综合分析   │  → news/events.json 更新
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 5: 构建静态站    │
              │  python news/          │
              │  build_static_site.py  │  → news/static_site/ (HTML)
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 6: git commit    │
              │  + push 回 main 分支   │
              │  → 持久化 CSV + 报告   │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  Step 7: 部署 Pages   │
              │  gh-pages 分支        │  → https://xxx.github.io/repo/
              └───────────────────────┘
```

---

## 三、各脚本详解

### 3.1 数据抓取（data_fetch/）

所有 fetcher 均采用**增量更新**模式：
1. 读取已有 CSV（如果有）
2. 确定缺失日期范围
3. 仅抓取缺失的数据
4. 合并去重后保存

#### `update_all_eco.py` — 主控脚本
- 依次运行全部 12 个 fetcher（每个最长 5 分钟超时）
- 异常隔离：一个失败不影响其他
- 汇总打印执行结果和数据文件大小
- 通过 `PYTHONIOENCODING=utf-8` 环境变量确保跨平台兼容

#### 9 个宏观数据 fetcher

| 脚本 | 数据源 | 输出文件 | 频率 |
|------|--------|----------|:----:|
| `DR007_get.py` | 中国外汇交易中心 API | `eco_data/dr007_history.csv` | 日 |
| `shibor_fetcher.py` | akshare → Shibor | `eco_data/Shibor.csv` | 日 |
| `bond_yield_fetcher.py` | akshare → ChinaBond | `eco_data/国债收益率.csv` | 日 |
| `margin_balance_fetcher.py` | akshare → 沪深交易所 | `eco_data/融资融券余额.csv` | 日 |
| `south_bound_fetcher.py` | akshare → 东方财富 | `eco_data/南向资金.csv` | 日 |
| `cn_us_spread_fetcher.py` | akshare → 中美国债 | `eco_data/中美利差.csv` | 日 |
| `turnover_fetcher.py` | akshare → 上证指数 | `eco_data/A股成交额.csv` | 日 |
| `account_fetcher.py` | akshare → 东方财富 | `eco_data/新开户数.csv` | 月 |
| `market_valuation_fetcher.py` | akshare → legulegu | `eco_data/全市场PE.csv`, `全市场PB.csv` | 日 |

关键技术点：
- 所有 fetcher 都可以脱离虚拟环境独立运行（`pip install` 后直接 `python xxx.py`）
- `bond_yield_fetcher.py` 使用分块抓取（每块 350 天绕开 API 限制）
- `DR007_get.py` 直接从央行 API 获取，不依赖 akshare
- `market_valuation_fetcher.py` 依赖 `py_mini_racer`（JS 引擎）解析 legulegu 的验证码
- **⚠ 版本锁**：`market_valuation_fetcher.py` 使用了 akshare 内部模块路径 `akshare.stock_feature.stock_a_pe_and_pb`（非公开 API），akshare 重构可能导致导入失败。建议在 `requirements.txt` 或 CI 中锁定 akshare 版本。当前已知兼容版本：akshare >= 1.14

#### 3 个补充数据 fetcher

| 脚本 | 数据源 | 输出文件 | 频率 |
|------|--------|----------|:----:|
| `update_etf_share.py` | 上交所 SSE API | `sse_etf_data/sse_etf_*.csv` | 日 |
| `update_etf_kline.py` | akshare → 东方财富 | `data_stock/*_Klines.csv` | 日 |

`update_etf_kline.py` 抓取 6 只核心 ETF：上证50(510050)、沪深300(510300)、中证500(510500)、中证1000(512100)、科创50(588000)、创业板指(sz399006)。

### 3.2 经济分析（news/eco_analysis.py）

**流程：**
1. 读取 `eco_data/` 下的所有 CSV 文件，获取最新一条记录
2. 也尝试读取 ETF 数据（`data_stock/`）
3. 如果没有本地数据，用 akshare 实时抓取
4. 将所有数据打包发给 DeepSeek API，要求分析：
   - 宏观周期判断（扩张/复苏/过热/滞胀/收缩/企稳震荡）
   - 流动性判断
   - 经济状态
   - 资金面
   - 核心矛盾（背离或冲突）
   - 对 A股/美股/债市的影响
5. 输出 Markdown 报告到 `news/reports/eco_YYYY-MM-DD.md`

**关键逻辑：**
- `get_macro_snapshot()` — 读取所有宏观指标的最新值
- `describe_macro()` — 转为文本摘要
- `call_deepseek()` — 调 DeepSeek API 生成分析
- 如果 `DEEPSEEK_API_KEY` 未设置，跳过 API 调用只输出原始数据

### 3.3 新闻简报（news/news_intelligence.py）

**流程：**
1. 抓取 22 个 RSS 新闻源（世界/政治/财经/科技分类）
2. 读取 `news/reports/eco_*.md` 获取经济分析摘要
3. 读取 `news/events.json` 获取追踪中的重大事件
4. 全部发给 DeepSeek API 生成结构化简报：
   - 每日四维简报（政治/经济/科技）
   - 长尾效应分析
   - 水面下的隐藏信号
5. 更新 `events.json`（新增事件、更新已有事件状态）
6. 输出到 `news/reports/briefing_YYYY-MM-DD.md`

**事件记忆库（events.json）：**
跨日持久化，追踪重大事件的演化。结构：
```json
{
  "events": {
    "event_id": {
      "title": "事件标题",
      "first_seen": "2026-06-20",
      "last_updated": "2026-06-28",
      "status": "ongoing|resolved|escalated",
      "evolutions": ["day1 变化", "day2 变化"]
    }
  }
}
```

### 3.4 静态站点生成（news/build_static_site.py）

- 读取 `news/reports/` 下的 `briefing_*.md` 和 `eco_*.md`
- 读取 `news/events.json`
- 生成完整的 HTML 静态站点到 `news/static_site/`
- 包含页面：首页、简报列表、简报详情、经济分析列表、经济分析详情

---

## 四、本地运行方式

**入口脚本：** `run_news_pipeline.py`

**命令行参数：**

| 参数 | 作用 |
|------|------|
| 无参数 | 完整运行：抓数据 → 分析 → 推送 → 关机 |
| `--no-shutdown` | 跑完后不关机 |
| `--skip-fetch` | 跳过数据抓取（已有数据时加速） |
| `--skip-ai` | 跳过 AI 分析（调试时使用） |

**示例：**
```bash
# 完整运行
python run_news_pipeline.py

# 仅构建静态站 + 推送（不抓数据、不调 AI）
python run_news_pipeline.py --skip-fetch --skip-ai --no-shutdown
```

**Python 环境：**
- Python 3.13.12 (managed: `C:\Users\Vasily_A_K\.workbuddy\binaries\python\versions\3.13.12\python.exe`)
- pip 安装：`akshare pandas requests py_mini_racer python-dateutil openai feedparser beautifulsoup4 lxml`

**触发：**
- 定时：交易日 北京时间 06:00（UTC 22:00 前一天，周日至周四）
- 手动：`workflow_dispatch`

**权限：**
- `contents: write` — 提交 CSV 和报告回主分支
- `pages: write` — 部署静态站
- `id-token: write` — Pages 部署认证

**步骤：**
| 步骤 | 命令 | 作用 |
|:----:|------|------|
| 1 | actions/checkout@v4 | 检出代码 |
| 2 | setup-python@v5 | 设置 Python 3.11 |
| 3 | apt-get install libicu-dev | py_mini_racer 系统依赖 |
| 4 | pip install ... | 安装 9 个 Python 包 |
| 5 | `python data_fetch/update_all_eco.py` | 抓取 12 项数据 |
| 6 | `python news/eco_analysis.py` | 经济分析（DeepSeek） |
| 7 | `python news/news_intelligence.py` | 新闻简报（DeepSeek） |
| 8 | `python news/build_static_site.py` | 构建 HTML 站点 |
| 9 | git commit + push | 持久化 CSV 和报告 |
| 10 | peaceiris/actions-gh-pages | 部署到 gh-pages |

**仓库秘密（需手动配置）：**
- `DEEPSEEK_API_KEY` — DeepSeek API 密钥（Settings → Secrets and variables → Actions）

---

## 五、依赖

```
# 系统依赖
libicu-dev                    (py_mini_racer 需要)

# Python 包
akshare                       (A 股/宏观数据)
pandas                        (数据处理)
requests                      (HTTP)
py_mini_racer                 (JS 引擎，用于 legulegu)
python-dateutil               (日期处理)
openai                        (DeepSeek API)
feedparser                    (RSS 解析)
beautifulsoup4                (HTML 解析)
lxml                          (XML 解析)
```

---

## 六、本地运行方式

```bash
# 安装依赖
pip install akshare pandas requests py_mini_racer python-dateutil openai feedparser beautifulsoup4 lxml

# 方式 1：单独跑数据抓取
python data_fetch/update_all_eco.py

# 方式 2：单独跑经济分析（需要 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY=sk-xxxx
python news/eco_analysis.py

# 方式 3：单独跑新闻简报（需要 DEEPSEEK_API_KEY）
python news/news_intelligence.py

# 方式 4：构建静态站
python news/build_static_site.py
```

**Windows 编码注意：** 如果终端出现乱码，先设置：
```cmd
set PYTHONIOENCODING=utf-8
```

---

## 七、远程存储位置

| 数据 | 远程分支 | 路径 |
|------|:--------:|------|
| 宏观经济 CSV | `main` | `eco_data/*.csv` |
| ETF 份额 | `main` | `sse_etf_data/*.csv` |
| ETF K 线 | `main` | `data_stock/*_Klines.csv` |
| RSS 缓存 | 不持久化 | `news_data/`（每次重新抓） |
| 经济分析报告 | `main` | `news/reports/eco_*.md` |
| 新闻简报 | `main` | `news/reports/briefing_*.md` |
| 事件记忆库 | `main` | `news/events.json` |
| 静态网站 | `gh-pages` | `news/static_site/` → GitHub Pages |

---

## 八、定时任务

Windows Task Scheduler 每天 06:00 自动运行完整管线。

**手动导入（需执行一次）：**
1. 按 `Win+R` 输入 `taskschd.msc`
2. 右侧点 **导入任务** → 选择 `NewsRadar_task.xml`
3. 确认用户账号，点确定

**或直接用命令行导入（管理员终端）：**
```cmd
schtasks /Create /XML "D:\Python_Program\news_program\NewsRadar_task.xml" /TN "NewsRadar\DailyPipeline"
```
2. 本地测试：按第六节步骤依次运行
