#!/usr/bin/env python3
"""
news_intelligence.py — 每日新闻情报系统

功能：
  1. 抓取 25 个新闻源（世界/政治/财经/科技/加密）
  2. 通过 DeepSeek API 单次分析：
     a) 每日四维简报（政治/经济/文化/科技）
     b) 追踪已有重大事件的演化
     c) 识别新事件及其潜在影响
     d) 长尾效应分析
     e) 水面下的隐藏信号
  3. 持久化事件记忆库（events.json）
  4. 输出结构化 Markdown 简报

用法：
  python news_intelligence.py

依赖（纯 Python 包，无 ML 模型）：
  pip install feedparser beautifulsoup4

作者：WorkBuddy
"""

import feedparser
import os
import json
import re
import time
import hashlib
import sys
import socket
import traceback
import atexit
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from openai import OpenAI
# 系统级配置
socket.setdefaulttimeout(10)
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# ============================================================
# 配置区
# ============================================================

# 加载 .env（项目根目录下的密钥文件）
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

# API Key 通过 .env 文件或环境变量设置
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("  ⚠ 未设置 DEEPSEEK_API_KEY，将跳过 AI 分析，仅生成 RSS 原始数据")
    print("    - 本地: 在 .env 中设置 DEEPSEEK_API_KEY=sk-xxx")
BASE_URL = "https://api.deepseek.com"

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DATA_DIR = os.path.join(BASE_DIR, "news_data")
EVENTS_DB_PATH = os.path.join(BASE_DIR, "news", "events.json")
REPORTS_DIR = os.path.join(BASE_DIR, "news", "reports")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# 旧新闻清理天数
NEWS_RETENTION_DAYS = 3

# 日志保留天数（自动清理更早的日志文件）
LOG_RETENTION_DAYS = 30


# ============================================================
# 日志功能：将全过程输出同时写入控制台和日志文件
# ============================================================

class _Tee:
    """把写入同时镜像到原始流（控制台）和日志文件；文件侧按行加时间戳前缀。"""

    def __init__(self, stream, logfile):
        self._stream = stream      # 原始 stdout/stderr（控制台）
        self._logfile = logfile    # 日志文件句柄
        self._buf = ""             # 行缓冲，用于给文件加时间戳

    def write(self, data):
        # 控制台原样输出
        try:
            self._stream.write(data)
        except Exception:
            pass
        # 文件按行加时间戳
        self._buf += data
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            ts = datetime.now().strftime("%H:%M:%S")
            self._logfile.write(f"[{ts}] {line}\n")
        try:
            self._logfile.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass
        try:
            self._logfile.flush()
        except Exception:
            pass

    def isatty(self):
        return getattr(self._stream, "isatty", lambda: False)()

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")


def _cleanup_old_logs():
    """清理超过保留期的旧日志文件。"""
    if not os.path.isdir(LOGS_DIR):
        return
    cutoff = time.time() - LOG_RETENTION_DAYS * 24 * 60 * 60
    for name in os.listdir(LOGS_DIR):
        if not name.endswith(".log"):
            continue
        path = os.path.join(LOGS_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except Exception:
            pass


def setup_logging():
    """启用日志：接管 stdout/stderr，所有输出镜像到 logs/ 下的按日文件。

    返回日志文件路径。可重复调用（幂等，不会二次包裹）。
    """
    if isinstance(sys.stdout, _Tee):
        return getattr(sys.stdout, "_log_path", None)

    os.makedirs(LOGS_DIR, exist_ok=True)
    _cleanup_old_logs()

    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOGS_DIR, f"news_intelligence_{today}.log")
    logfile = open(log_path, "a", encoding="utf-8")

    header = (
        "\n" + "=" * 70 + "\n"
        f"  运行开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  "
        f"(pid={os.getpid()})\n"
        + "=" * 70 + "\n"
    )
    logfile.write(header)
    logfile.flush()

    tee_out = _Tee(sys.stdout, logfile)
    tee_out._log_path = log_path
    sys.stdout = tee_out
    sys.stderr = _Tee(sys.stderr, logfile)

    # 进程退出时写收尾标记并关闭文件
    def _finalize():
        try:
            logfile.write(
                "-" * 70 + "\n"
                f"  运行结束: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                + "=" * 70 + "\n"
            )
            logfile.flush()
            logfile.close()
        except Exception:
            pass

    atexit.register(_finalize)
    return log_path

# ============================================================
# RSS 新闻源（全部保留）
# ============================================================

WORLD_SOURCES = [
    {'name': '纽约时报', 'url': 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'},
    {'name': '福克斯新闻', 'url': 'https://moxie.foxnews.com/google-publisher/world.xml'},
    {'name': '卫报', 'url': 'https://www.theguardian.com/world/rss'},
    {'name': '今日俄罗斯', 'url': 'https://www.rt.com/rss/news'},
    {'name': '联合早报', 'url': 'https://rsshub.rssforever.com/zaobao/realtime/china'},
]

POLITICS_SOURCES = [
    {'name': '福克斯新闻', 'url': 'https://moxie.foxnews.com/google-publisher/politics.xml'},
    {'name': 'BBC', 'url': 'https://feeds.bbci.co.uk/news/politics/rss.xml'},
    {'name': '中国新闻网', 'url': 'https://www.chinanews.com.cn/rss/china.xml'},
    {'name': '世界报', 'url': 'https://www.lemonde.fr/en/international/rss_full.xml'},
    {'name': '朝日新闻', 'url': 'https://www.asahi.com/rss/asahi/politics.rdf'},
    {'name': '新华社', 'url': 'http://www.xinhuanet.com/politics/news_politics.xml'},
]

FINANCE_SOURCES = [
    {'name': '纽约时报', 'url': 'https://rss.nytimes.com/services/xml/rss/nyt/Business.xml'},
    {'name': 'Investing', 'url': 'https://www.investing.com/rss/news.rss'},
    {'name': '福克斯新闻', 'url': 'https://moxie.foxbusiness.com/google-publisher/latest.xml'},
    {'name': 'BBC', 'url': 'https://feeds.bbci.co.uk/news/business/rss.xml'},
    {'name': '金融时报', 'url': 'https://www.ft.com/?format=rss'},
    {'name': '今日俄罗斯', 'url': 'https://www.rt.com/rss/business'},
    {'name': '中国新闻网', 'url': 'https://www.chinanews.com.cn/rss/finance.xml'},
    {'name': '世界报', 'url': 'https://www.lemonde.fr/en/economy/rss_full.xml'},
    {'name': '朝日新闻', 'url': 'https://www.asahi.com/rss/asahi/business.rdf'},
    {'name': '人民网财经', 'url': 'http://www.people.com.cn/rss/finance.xml'},
    {'name': '华尔街见闻', 'url': 'https://rsshub.rssforever.com/wallstreetcn/news/global'},
]

TECH_SOURCES = [
    {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/'},
    {'name': 'Ars Technica', 'url': 'https://feeds.arstechnica.com/arstechnica/index'},
    {'name': 'MIT Tech Review', 'url': 'https://www.technologyreview.com/feed/'},
]

CRYPTO_SOURCES = [
    {'name': 'CoinDesk', 'url': 'https://www.coindesk.com/arc/outboundfeeds/rss/'},
    {'name': 'CoinTelegraph', 'url': 'https://cointelegraph.com/rss'},
]

ALL_CATEGORIES = {
    "world": WORLD_SOURCES,
    "politics": POLITICS_SOURCES,
    "finance": FINANCE_SOURCES,
    "tech": TECH_SOURCES,
    "crypto": CRYPTO_SOURCES,
}

# ============================================================
# 工具函数
# ============================================================

def keep_first_two_sentences(text: str) -> str:
    """保留文本的前两句（中英文标点分句）。"""
    sentences = re.split(r'([。！？.!?])', text)
    full_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        full_sentences.append(sentences[i] + sentences[i + 1])
    first_two = full_sentences[:3]
    return ''.join(first_two).strip()


def clean_news_content(raw_html_or_text):
    """清洗新闻内容，剥离 HTML 标签。"""
    if not raw_html_or_text:
        return ""
    if '<' in raw_html_or_text and '>' in raw_html_or_text:
        try:
            soup = BeautifulSoup(raw_html_or_text, 'html.parser')
            for tag in soup.find_all(['img', 'a'], class_='em_handle_adv_close'):
                tag.decompose()
            for a_tag in soup.find_all('a', class_='keytip'):
                a_tag.replace_with(a_tag.text)
            clean_text = soup.get_text(separator='\n', strip=True)
            clean_text = re.sub(r'[\u3000\s]{2,}', ' ', clean_text)
            clean_text = re.sub(r'\n+', '\n', clean_text)
            return keep_first_two_sentences(clean_text)
        except Exception:
            return raw_html_or_text.strip()
    else:
        return raw_html_or_text.strip()


def sanitize_filename(text):
    """清洗字符串为安全文件名。"""
    s = re.sub(r'[^\w\s-]', '', text).strip()
    s = re.sub(r'[\s]+', '_', s)
    return s[:100]


# ============================================================
# 模块 1：RSS 新闻抓取
# ============================================================

def fetch_feed_with_retry(url, source_name, retries=2, delay=3):
    """带重试机制的 RSS 抓取（使用 urllib 确保超时生效）。"""
    import urllib.request
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
            feed = feedparser.parse(raw)
            return feed
        except Exception as e:
            err_msg = str(e)[:60]
            print(f"  > {source_name}: 失败 ({err_msg})", flush=True)
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def delete_old_news(days=NEWS_RETENTION_DAYS):
    """清理过期新闻文件。"""
    if not os.path.exists(NEWS_DATA_DIR):
        return 0
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    deleted_count = 0
    for root, dirs, files in os.walk(NEWS_DATA_DIR):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                if os.path.getmtime(file_path) < cutoff_time:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception:
                        pass
    if deleted_count > 0:
        print(f"  > 已清理 {deleted_count} 条旧新闻")
    return deleted_count


def fetch_news_by_category(sources, category):
    """抓取单类新闻，返回新闻列表（不存盘）。"""
    category_dir = os.path.join(NEWS_DATA_DIR, category)
    os.makedirs(category_dir, exist_ok=True)

    all_news = []
    for source in sources:
        source_name = source['name']
        feed_url = source['url']
        sanitized_name = sanitize_filename(source_name).lower()
        source_dir = os.path.join(category_dir, sanitized_name)
        os.makedirs(source_dir, exist_ok=True)

        feed = fetch_feed_with_retry(feed_url, source_name)
        if feed is None:
            continue
        # 当 feedparser 解析原始字节时没有 status 属性，通过是否有条目来判断
        if not feed.entries:
            continue

        for entry in feed.entries:
            try:
                title = entry.title if 'title' in entry else 'No Title'
                link = entry.link if 'link' in entry else 'No Link'
                raw_summary = entry.summary if 'summary' in entry else 'No Summary'
                summary = clean_news_content(raw_summary)

                news_item = {
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": entry.published if 'published' in entry else 'N/A',
                    "category": category,
                }
                all_news.append(news_item)

                # 仍保存到本地（复用旧文件结构）
                filename = sanitize_filename(title) + ".json"
                file_path = os.path.join(source_dir, filename)
                if not os.path.exists(file_path):
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(news_item, f, ensure_ascii=False, indent=4)

            except Exception:
                pass

        print(f"  > {source_name}: {len(feed.entries)} 条")

    return all_news


def fetch_all_news():
    """抓取所有分类新闻。"""
    print("\n[1/4] 抓取新闻...")
    delete_old_news()
    os.makedirs(NEWS_DATA_DIR, exist_ok=True)

    all_news = []
    for category, sources in ALL_CATEGORIES.items():
        print(f"\n--- {category.upper()} ---")
        news = fetch_news_by_category(sources, category)
        all_news.extend(news)

    print(f"\n  > 共抓取 {len(all_news)} 条新闻（含加密）")
    return all_news


# ============================================================
# 模块 2：事件记忆库
# ============================================================

def get_events_db():
    """读取事件记忆库，若不存在则初始化。"""
    if os.path.exists(EVENTS_DB_PATH):
        with open(EVENTS_DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "version": 2,
        "last_run": None,
        "events": [],
    }


def save_events_db(db):
    """保存事件记忆库。"""
    db["last_run"] = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(EVENTS_DB_PATH), exist_ok=True)
    with open(EVENTS_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def format_events_for_prompt(events_db):
    """将事件记忆库格式化为 LLM prompt 可读的文本。"""
    events = events_db.get("events", [])
    if not events:
        return "暂无追踪中的事件。"

    lines = ["当前追踪中的重大事件："]
    for e in events[-30:]:  # 最多取最近 30 条
        status_icon = {
            "active": "|",
            "escalating": "^",
            "resolving": "v",
            "resolved": "[OK]",
            "archived": ".",
        }.get(e.get("status", "active"), "?")

        last = e["daily_history"][-1] if e.get("daily_history") else {}
        lines.append(
            f"  [{status_icon}] {e['title']} "
            f"(状态:{e.get('status','?')} "
            f"| 风险:{e.get('tail_risk','?')} "
            f"| 首次:{e.get('first_detected','?')})"
        )
        if last:
            lines.append(f"      最近分析: {last.get('summary','')[:120]}")
    return "\n".join(lines)


# ============================================================
# 模块 3：DeepSeek API 分析引擎
# ============================================================

def build_analysis_prompt(news_list, events_db_text):
    """构造完整的分析 prompt。"""

    # 将新闻压缩成紧凑格式
    news_lines = []
    for n in news_list:
        summary = n.get("summary", "")[:200]
        news_lines.append(
            f"  [{n['category']}] [{n['source']}] {n['title']}\n"
            f"    {summary}"
        )
    news_text = "\n".join(news_lines)

    # 估算 token 数
    estimated_tokens = len(news_text) // 3 + 2000
    print(f"  > prompt 预估: ~{estimated_tokens} tokens（DeepSeek-V4 支持 1M 上下文，无需截断）")

    # 读取经济分析报告摘要
    eco_path = os.path.join(BASE_DIR, "news", "reports", f"eco_{datetime.now().strftime('%Y-%m-%d')}.md")
    eco_summary = ""
    if os.path.exists(eco_path):
        with open(eco_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 取前 600 字作为摘要
        eco_summary = content[:600]
        print("  > 已加载经济分析报告")

    prompt = f"""
你是首席市场情报分析师。你的任务是分析今日全球新闻，生成一份深度的每日情报简报。

输入包含三部分：
  1. 【经济分析报告】今日宏观/ETF/BTC 分析摘要
  2. 今日新闻摘要（按分类组织）
  3. 事件记忆库（追踪中的重大事件历史）

【经济分析报告摘要】
{eco_summary or "（暂无经济分析数据）"}

请严格按照以下 JSON 格式输出，不要包含任何其他文字：

{{
  "每日四维简报": {{
    "政治": {{
      "摘要": "1-2句话概括今日重要政治事件",
      "关键事件": ["事件1: 简述", "事件2: 简述"],
      "市场影响": "这些事件对全球市场的直接或间接影响"
    }},
    "经济": {{
      "摘要": "1-2句话概括今日重要经济/财经事件",
      "关键事件": ["事件1: 简述", "事件2: 简述"],
      "市场影响": "对股票/加密/外汇/大宗商品的具体影响"
    }},
    "文化": {{
      "摘要": "1-2句话概括今日重要文化/社会事件",
      "关键事件": ["事件1: 简述", "事件2: 简述"],
      "市场影响": "这些文化/社会趋势对相关行业的影响"
    }},
    "科技": {{
      "摘要": "1-2句话概括今日重要科技事件",
      "关键事件": ["事件1: 简述", "事件2: 简述"],
      "市场影响": "对科技股/加密/AI等行业的影响"
    }}
  }},
  "追踪事件更新": [
    {{
      "标题": "事件标题（与记忆库中一致）",
      "新动态": "今天有什么新发展",
      "状态变化": "相同/升级/缓解/解决",
      "更新评估": "对事件的最新判断"
    }}
  ],
  "新检测事件": [
    {{
      "标题": "事件标题",
      "分类": "politics/economy/culture/technology",
      "为何重要": "2-3句说明该事件的重要性和潜在的长期影响",
      "潜在影响资产": ["受影响的市场或资产类别"],
      "预估风险": "high/medium/low",
      "因果链": ["该事件可能的传导路径"]
    }}
  ],
  "长尾效应分析": [
    {{
      "事件": "具体事件",
      "起始时间": "如已持续多久",
      "影响链条": "该事件如何持续影响市场的分析",
      "未来展望": "接下来可能的发展方向和对市场的持续影响",
      "关注节点": "需要关注的里程碑事件或时间点"
    }}
  ],
  "水面下的信号": [
    {{
      "信号": "潜伏的叙事或二阶效应",
      "依据": "基于什么新闻内容推断的",
      "如果成立": "该信号可能怎样影响市场",
      "置信度": "high/medium/low"
    }}
  ]
}}

【事件记忆库】
{events_db_text}

【今日新闻】
{news_text}

请输出严格有效的 JSON（不要 markdown 代码块标记），确保中文输出。
"""

    return prompt


def call_deepseek_analysis(news_list, events_db_text):
    """调用 DeepSeek API 进行新闻分析。"""
    print("\n[2/4] 调用 DeepSeek API 分析新闻...")
    print("  > 新闻数量:", len(news_list))

    if not DEEPSEEK_API_KEY:
        print("  > 跳过 API 调用（无 API Key）")
        return None

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=BASE_URL, timeout=300)

    prompt = build_analysis_prompt(news_list, events_db_text)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=16384,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
            )
            content = response.choices[0].message.content

            # 尝试解析 JSON（LLM 可能在首尾加 ```json ... ```）
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)

            result = json.loads(content)
            print("  > API 分析成功")
            return result

        except json.JSONDecodeError:
            print(f"  > JSON 解析失败 (尝试 {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                print("  > 返回原始内容")
                return {"raw_text": content}
        except Exception as e:
            print(f"  > API 调用失败: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(5)

    return None


# ============================================================
# 模块 4：简报格式化 & 事件库更新
# ============================================================

def format_briefing(result, news_count):
    """将分析结果格式化为可读的 Markdown 简报。"""
    today = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# 每日情报简报 — {today}")
    lines.append(f"\n> 分析来源: 25 个新闻源（世界/政治/财经/科技/加密） | 今日新闻: {news_count} 条 | 分析引擎: DeepSeek")
    lines.append("\n---\n")

    # ---- 每日四维简报 ----
    briefing = result.get("每日四维简报", {})
    for dim_name, dim_data in briefing.items():
        lines.append(f"## [GLOBE] {dim_name}")
        lines.append(f"\n{dim_data.get('摘要', 'N/A')}\n")
        for evt in dim_data.get("关键事件", []):
            lines.append(f"- {evt}")
        lines.append(f"\n**市场影响**: {dim_data.get('市场影响', 'N/A')}")
        lines.append("\n---\n")

    # ---- 追踪事件更新 ----
    updates = result.get("追踪事件更新", [])
    if updates:
        lines.append("## [SYNC] 追踪事件更新")
        for u in updates:
            status_map = {"相同": "->", "升级": "^^", "缓解": "vv", "解决": "[OK]", "escalating": "^^", "resolving": "vv"}
            icon = status_map.get(u.get("状态变化", ""), "?")
            lines.append(f"\n### {icon} {u.get('标题', '未知')}")
            lines.append(f"- **新动态**: {u.get('新动态', 'N/A')}")
            lines.append(f"- **状态变化**: {u.get('状态变化', 'N/A')}")
            lines.append(f"- **更新评估**: {u.get('更新评估', 'N/A')}")
        lines.append("\n---\n")

    # ---- 新检测事件 ----
    new_events = result.get("新检测事件", [])
    if new_events:
        lines.append("## [NEW] 新检测事件")
        for e in new_events:
            risk_icon = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}
            icon = risk_icon.get(e.get("预估风险", ""), "[?]")
            lines.append(f"\n### {icon} {e.get('标题', '未知')}")
            lines.append(f"- **分类**: {e.get('分类', 'N/A')}")
            lines.append(f"- **为何重要**: {e.get('为何重要', 'N/A')}")
            lines.append(f"- **潜在影响资产**: {', '.join(e.get('潜在影响资产', []))}")
            lines.append(f"- **预估风险**: {e.get('预估风险', 'N/A')}")
            chain = e.get("因果链", [])
            if chain:
                lines.append("- **因果链**:")
                for c in chain:
                    lines.append(f"  - {c}")
        lines.append("\n---\n")

    # ---- 长尾效应 ----
    tails = result.get("长尾效应分析", [])
    if tails:
        lines.append("## [TAIL] 长尾效应分析")
        for t in tails:
            lines.append(f"\n### {t.get('事件', '未知')}")
            lines.append(f"- **起始时间**: {t.get('起始时间', 'N/A')}")
            lines.append(f"- **影响链条**: {t.get('影响链条', 'N/A')}")
            lines.append(f"- **未来展望**: {t.get('未来展望', 'N/A')}")
            lines.append(f"- **关注节点**: {t.get('关注节点', 'N/A')}")
        lines.append("\n---\n")

    # ---- 水面下的信号 ----
    signals = result.get("水面下的信号", [])
    if signals:
        lines.append("## [DEEP] 水面下的信号")
        for s in signals:
            conf_icon = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}
            icon = conf_icon.get(s.get("置信度", ""), "[?]")
            lines.append(f"\n### {icon} {s.get('信号', '未知')}")
            lines.append(f"- **依据**: {s.get('依据', 'N/A')}")
            lines.append(f"- **如果成立**: {s.get('如果成立', 'N/A')}")
            lines.append(f"- **置信度**: {s.get('置信度', 'N/A')}")
        lines.append("\n---\n")

    # ---- 脚注 ----
    lines.append(f"\n*简报生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("*数据来源: 纽约时报、福克斯新闻、BBC、卫报、金融时报、Investing、")
    lines.append("今日俄罗斯、联合早报、中国新闻网、世界报、朝日新闻、")
    lines.append("新华社、人民网财经、华尔街见闻、")
    lines.append("TechCrunch、Ars Technica、MIT Tech Review*")

    return "\n".join(lines)


def generate_event_id(title):
    """根据标题生成稳定的事件 ID。"""
    return hashlib.md5(title.encode('utf-8')).hexdigest()[:12]


def is_duplicate(new_title, existing_title):
    """判断两个标题是否指向同一事件（模糊匹配）。

    用于事件记忆库的去重：支持子串匹配与中文/英文 token 重叠度匹配。
    """
    # 快速检查：子串匹配（一个标题完全包含另一个）
    if new_title in existing_title or existing_title in new_title:
        return True

    # 中文/英文 token 重叠度
    def tokenize(s):
        result = []
        for ch in s:
            if '\u4e00' <= ch <= '\u9fff':
                result.append(ch)
            else:
                result.extend(re.findall(r'\w+', ch))
        return set(result)
    words = tokenize(new_title)
    ex_words = tokenize(existing_title)
    if not words or not ex_words:
        return False

    # 核心实体重叠度（降低阈值到 30%，因为 LLM 标题表述变化大）
    overlap = words & ex_words
    # 排除过于通用的单字（"的"/"与"/"和"/"在"等 无法出现在中文标题中）
    common = set("的与和在及于或是被把从以")
    overlap = overlap - common
    words = words - common
    ex_words = ex_words - common
    if not words or not ex_words:
        return False
    ratio = len(overlap) / min(len(words), len(ex_words))
    return ratio >= 0.3 or words.issubset(ex_words) or ex_words.issubset(words)


def update_events_db(events_db, result):
    """根据分析结果更新事件记忆库。"""
    today = datetime.now().strftime("%Y-%m-%d")
    events = events_db.get("events", [])

    # 构建索引：标题 → 事件
    title_to_event = {}
    for e in events:
        title_to_event[e["title"]] = e

    # 处理追踪事件更新（支持模糊标题匹配）
    seen_titles_for_today = set()
    for update in result.get("追踪事件更新", []):
        title = update.get("标题", "")
        if title in title_to_event:
            e = title_to_event[title]
        else:
            # 模糊匹配已有事件
            e = None
            for existing_title, existing_event in title_to_event.items():
                if is_duplicate(title, existing_title):
                    e = existing_event
                    break
            if e is None:
                continue  # 找不到对应事件，跳过

        e["last_updated"] = today
        e["daily_history"].append({
            "date": today,
            "summary": update.get("新动态", ""),
            "impact": update.get("更新评估", ""),
        })

        # 更新状态
        status_map = {"相同": "active", "升级": "escalating",
                      "缓解": "resolving", "解决": "resolved"}
        new_status = status_map.get(update.get("状态变化", ""))
        if new_status:
            e["status"] = new_status

    # 处理新检测事件（先去重：同一批次内标题相似的只保留第一个）
    new_event_titles_seen = set()
    for new_event in result.get("新检测事件", []):
        title = new_event.get("标题", "") or new_event.get("信号", "")[:60] or f"未命名事件: {new_event.get('为何重要','')[:40]}..."

        # 批次内去重
        is_dup_in_batch = False
        for seen in new_event_titles_seen:
            if is_duplicate(title, seen):
                is_dup_in_batch = True
                break
        if is_dup_in_batch:
            continue
        new_event_titles_seen.add(title)

        # 模糊去重：检查标题是否指向同一事件（is_duplicate 已提为函数级定义）
        existing_event = None
        for e in events:
            if is_duplicate(title, e.get("title", "")):
                existing_event = e
                break

        if existing_event:
            # 合并到已有事件：追加摘要和历史
            existing_event["last_updated"] = today
            if existing_event.get("tail_risk") != new_event.get("预估风险", "medium"):
                existing_event["tail_risk"] = new_event.get("预估风险", existing_event["tail_risk"])
            # 合并因果链
            new_chain = new_event.get("因果链", [])
            if new_chain:
                existing_chains = set(existing_event.get("causal_chain", []))
                for c in new_chain:
                    if c not in existing_chains:
                        existing_event.setdefault("causal_chain", []).append(c)
            existing_event.setdefault("daily_history", []).append({
                "date": today,
                "summary": new_event.get("为何重要", "合并更新"),
                "impact": f"潜在影响: {', '.join(new_event.get('潜在影响资产', []))}",
            })
        else:
            entry = {
                "id": generate_event_id(title),
                "title": title,
                "category": new_event.get("分类", "unknown"),
                "first_detected": today,
                "last_updated": today,
                "status": "active",
                "tail_risk": new_event.get("预估风险", "medium"),
                "daily_history": [{
                    "date": today,
                    "summary": new_event.get("为何重要", ""),
                    "impact": f"潜在影响: {', '.join(new_event.get('潜在影响资产', []))}",
                }],
                "causal_chain": new_event.get("因果链", []),
                "estimated_resolution": "N/A",
            }
            events.append(entry)

    # 旧事件清理：resolved/archived 超过 30 天移除
    cutoff = datetime.now() - timedelta(days=30)
    events_db["events"] = [
        e for e in events
        if not (e.get("status") in ("resolved", "archived")
                and datetime.strptime(e["last_updated"], "%Y-%m-%d") < cutoff)
    ]

    save_events_db(events_db)
    print(f"  > 事件记忆库已更新: {len(events_db['events'])} 条追踪事件")


def save_report(briefing_text):
    """保存简报到本地文件。"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(REPORTS_DIR, f"briefing_{today}.md")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(briefing_text)
    print(f"  > 简报已保存: {filepath}")
    return filepath


# ============================================================
# 模块 5：主流程
# ============================================================

def _run_pipeline():
    """核心流程：抓取 → 分析 → 输出 → 更新记忆。异常向上抛出由 main 记录。"""
    start_time = time.time()

    print("=" * 55)
    print("  [RADAR] 每日新闻情报系统")
    print("=" * 55)

    # Step 1: 抓取新闻
    all_news = fetch_all_news()
    if not all_news:
        print("\n[!] 未抓取到任何新闻，可能网络有问题")
        return None

    # Step 2: 读取事件记忆库
    events_db = get_events_db()
    events_text = format_events_for_prompt(events_db)

    # Step 3: API 分析
    result = call_deepseek_analysis(all_news, events_text)
    if result is None:
        print("\n[!] API 分析失败，请检查网络和 API Key")
        return None

    # Step 4: 生成简报
    print("\n[3/4] 生成简报...")
    briefing = format_briefing(result, len(all_news))

    # Step 4: 先保存简报（务必在更新事件库之前落盘，
    # 避免后续步骤异常导致简报文件缺失——这正是 7-13/7-14 漏推送的根因）
    saved_path = save_report(briefing)

    # Step 5: 更新事件记忆库（用 try/except 隔离，失败只记录不中断简报）
    print("\n[4/4] 更新事件记忆库...")
    try:
        update_events_db(events_db, result)
    except Exception:
        print("\n[!] 事件记忆库更新失败（简报已保存，不受影响）：")
        print(traceback.format_exc())

    # Step 6: 输出结果
    print("\n" + "=" * 55)
    print(briefing)
    print("=" * 55)

    # 统计
    elapsed = time.time() - start_time
    print(f"\n[DONE] 完成！耗时: {elapsed:.1f}s")
    print(f"   简报: {saved_path}")
    print(f"   事件库: {len(events_db['events'])} 条追踪事件")

    # 返回简报供内部使用
    return briefing


def main():
    """主入口：先启用日志，再运行流程，捕获并记录任何异常。"""
    log_path = setup_logging()
    print(f"  > 日志写入: {log_path}")
    try:
        return _run_pipeline()
    except Exception:
        # 记录完整堆栈到日志（同时打印到控制台）
        print("\n[FATAL] 运行中断，未捕获的异常：")
        print(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
