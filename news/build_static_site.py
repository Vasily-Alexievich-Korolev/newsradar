#!/usr/bin/env python3
"""
build_static_site.py — 生成新闻情报静态网站

从本地 news_data/ + reports/ + events.json 生成完整的静态 HTML 网站，
可通过 CloudStudio 部署到公网。

用法：
  python build_static_site.py
  # 输出到 news/static_site/ 目录
"""

import os
import json
import re
import glob
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
NEWS_DATA_DIR = os.path.join(PROJECT_DIR, "news_data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
EVENTS_PATH = os.path.join(BASE_DIR, "events.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "static_site")

CAT_LABELS = {
    "world": "World",
    "politics": "Politics",
    "finance": "Finance",
    "tech": "Tech",
    "crypto": "Crypto",
}

CAT_COLORS = {
    "world": "bg-blue-100 text-blue-800",
    "politics": "bg-red-100 text-red-800",
    "finance": "bg-green-100 text-green-800",
    "tech": "bg-purple-100 text-purple-800",
    "crypto": "bg-amber-100 text-amber-800",
}

# 部署后的根路径（GitHub Pages project site 用 /newsradar/，根域名用空字符串）
# 可通过环境变量 SITE_BASE_URL 覆盖，例如：export SITE_BASE_URL=/my-site
BASE_URL = os.environ.get("SITE_BASE_URL", "/newsradar")


def nav_links():
    """生成导航栏链接（使用绝对路径，从任何子目录都能正确跳转）。"""
    return f"""
<a href="{BASE_URL}/index.html" class="text-lg font-bold text-gray-900">NewsRadar</a>
<div class="hidden sm:flex space-x-4 text-sm">
<a href="{BASE_URL}/index.html" class="text-gray-600 hover:text-gray-900">Dashboard</a>
<a href="{BASE_URL}/briefings.html" class="text-gray-600 hover:text-gray-900">Briefings</a>
<a href="{BASE_URL}/eco.html" class="text-gray-600 hover:text-gray-900">Economy</a>
<a href="{BASE_URL}/news.html" class="text-gray-600 hover:text-gray-900">News</a>
<a href="{BASE_URL}/events.html" class="text-gray-600 hover:text-gray-900">Events</a>
</div>"""

# ============================================================
# HTML Layout
# ============================================================

def base_html(title, body, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — NewsRadar</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
body {{ font-family: 'Inter', -apple-system, sans-serif; }}
.markdown h2 {{ font-size: 1.25rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
.markdown h3 {{ font-size: 1.1rem; font-weight: 600; margin-top: 1.2rem; margin-bottom: 0.3rem; }}
.markdown p {{ margin-bottom: 0.5rem; line-height: 1.7; }}
.markdown ul {{ list-style: disc; padding-left: 1.5rem; margin-bottom: 0.5rem; }}
.markdown li {{ margin-bottom: 0.25rem; }}
.markdown hr {{ margin: 1.5rem 0; border-color: #e5e7eb; }}
.markdown blockquote {{ border-left: 3px solid #d1d5db; padding-left: 1rem; color: #6b7280; margin: 0.5rem 0; }}
{extra_head}
</style>
</head>
<body class="bg-gray-50 min-h-screen">
<nav class="bg-white border-b border-gray-200 sticky top-0 z-50">
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
<div class="flex justify-between h-14 items-center">
<div class="flex items-center space-x-6">
{nav_links()}
</div>
</div>
<div class="text-xs text-gray-400">{datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
</div>
</div>
</nav>
<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
{body}
</main>
</body>
</html>"""


def md_to_html(md_text):
    """简易 Markdown → HTML。"""
    if not md_text:
        return ""
    html = md_text
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>(?:\n<li>.*?</li>)*)', r'<ul>\1</ul>', html)
    html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
    html = re.sub(r'^---$', r'<hr>', html, flags=re.MULTILINE)
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" target="_blank" class="text-blue-600 underline">\1</a>', html)
    lines = html.split('\n')
    result = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('<h') or s.startswith('<ul') or s.startswith('</ul') or s.startswith('<li') or s.startswith('<blockquote') or s.startswith('</blockquote') or s.startswith('<hr'):
            result.append(line)
            continue
        result.append(f'<p>{s}</p>')
    return '\n'.join(result)


# ============================================================
# 页面生成函数
# ============================================================

def get_category_counts():
    counts = {}
    total = 0
    for cat in CAT_LABELS:
        cat_dir = os.path.join(NEWS_DATA_DIR, cat)
        c = 0
        if os.path.isdir(cat_dir):
            for root, dirs, files in os.walk(cat_dir):
                c += len([f for f in files if f.endswith('.json')])
        counts[cat] = c
        total += c
    return counts, total


def get_category_sources():
    result = []
    for cat in ["world", "politics", "finance", "tech", "crypto"]:
        cat_dir = os.path.join(NEWS_DATA_DIR, cat)
        sources = []
        if os.path.isdir(cat_dir):
            for item in sorted(os.listdir(cat_dir)):
                item_path = os.path.join(cat_dir, item)
                if os.path.isdir(item_path):
                    count = len([f for f in os.listdir(item_path) if f.endswith('.json')])
                    if count > 0:
                        sources.append((item, count))
        result.append((cat, sources))
    return result


def load_events():
    if not os.path.exists(EVENTS_PATH):
        return []
    with open(EVENTS_PATH, 'r', encoding='utf-8') as f:
        db = json.load(f)
    return db.get("events", [])


def sorted_events(events):
    risk = {"high": 0, "medium": 1, "low": 2}
    status = {"escalating": 0, "active": 1, "resolving": 2, "resolved": 3}
    return sorted(events, key=lambda e: (
        risk.get(e.get("tail_risk", "low"), 3),
        status.get(e.get("status", "active"), 1),
    ))


def sanitize_filename(s):
    return re.sub(r'[^\w\-]', '_', s)[:80]


def load_article(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def make_article_path(category, source, filename):
    return f"article/{category}/{source}/{filename.replace('.json','.html')}"


# ============================================================
# 生成页面
# ============================================================

def generate_index():
    """首页仪表盘。"""
    counts, total = get_category_counts()
    events = sorted_events(load_events())
    active = [e for e in events if e.get("status") in ("active", "escalating")]

    # 找到最新简报快照
    briefings = sorted(glob.glob(os.path.join(REPORTS_DIR, "briefing_*.md")), reverse=True)
    latest_html = "<p class='text-gray-400'>No briefing yet. Run news_intelligence.py first.</p>"
    latest_date = ""
    if briefings:
        latest = briefings[0]
        latest_date = os.path.basename(latest).replace("briefing_", "").replace(".md", "")
        with open(latest, 'r', encoding='utf-8') as f:
            raw = f.read()
        lines = raw.split('\n')
        preview_lines = []
        sec = 0
        for line in lines:
            preview_lines.append(line)
            if line.startswith('## '):
                sec += 1
            if sec >= 8:
                break
        latest_html = md_to_html('\n'.join(preview_lines))

    # Stats cards
    cards = f"""
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <div class="text-2xl font-bold text-gray-900">{total}</div>
        <div class="text-xs text-gray-500 mt-1">News today</div>
      </div>
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <div class="text-2xl font-bold text-blue-600">{len(events)}</div>
        <div class="text-xs text-gray-500 mt-1">Tracked events</div>
      </div>
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <div class="text-2xl font-bold text-amber-600">{len(active)}</div>
        <div class="text-xs text-gray-500 mt-1">Active/escalating</div>
      </div>
      <div class="bg-white rounded-xl border border-gray-200 p-4">
        <div class="text-2xl font-bold text-green-600">{sum(len(s) for _, s in get_category_sources())}</div>
        <div class="text-xs text-gray-500 mt-1">Sources</div>
      </div>
    </div>"""

    # Category breakdown
    cat_items = ""
    for cat in ["world", "politics", "finance", "tech", "crypto"]:
        c = counts.get(cat, 0)
        cat_items += f"""
        <a href="news/{cat}.html" class="flex items-center justify-between py-2 border-b border-gray-100 last:border-0 hover:bg-gray-50 -mx-2 px-2 rounded">
          <span class="text-sm text-gray-700">{CAT_LABELS.get(cat, cat)}</span>
          <span class="text-sm font-medium text-gray-900">{c}</span>
        </a>"""

    # Top events
    ev_items = ""
    for e in active[:8]:
        color = {"high": "bg-red-500", "medium": "bg-amber-400", "low": "bg-green-400"}
        ev_items += f"""
        <a href="events.html#event-{e.get('id', '')}" class="block text-sm py-1.5 border-b border-gray-100 last:border-0 hover:bg-gray-50 -mx-2 px-2 rounded">
          <span class="inline-block w-2 h-2 rounded-full mr-2 {color.get(e.get('tail_risk','low'), 'bg-gray-400')}"></span>
          <span class="text-gray-700">{e.get('title', '')[:50]}{'...' if len(e.get('title','')) > 50 else ''}</span>
        </a>"""

    body = f"""
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Dashboard</h1>
      <span class="text-sm text-gray-500">Last run: {latest_date}</span>
    </div>
    {cards}
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
      <div class="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-5">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold">Latest Briefing</h2>
          <a href="briefing/{latest_date}.html" class="text-xs text-blue-600 hover:underline">View full</a>
        </div>
        <div class="markdown text-sm text-gray-700 leading-relaxed max-h-[600px] overflow-y-auto">{latest_html}</div>
      </div>
      <div class="space-y-4">
        <div class="bg-white rounded-xl border border-gray-200 p-5">
          <h2 class="text-base font-semibold mb-3">By Category</h2>
          {cat_items}
        </div>
        <div class="bg-white rounded-xl border border-gray-200 p-5">
          <h2 class="text-base font-semibold mb-3">Active Events</h2>
          {ev_items if ev_items else '<p class="text-xs text-gray-400">No active events</p>'}
        </div>
      </div>
    </div>"""
    return base_html("Dashboard", body)


def generate_report_list(prefix, title):
    """通用报告列表页（简报/经济报告等）。"""
    reports = sorted(glob.glob(os.path.join(REPORTS_DIR, f"{prefix}_*.md")), reverse=True)
    items = ""
    for b in reports:
        date = os.path.basename(b).replace(f"{prefix}_", "").replace(".md", "")
        size = os.path.getsize(b) // 1024
        preview = ""
        with open(b, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('## '):
                    preview = line.strip()
                    break
        items += f"""
        <a href="{prefix}/{date}.html" class="block bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-300 transition">
          <div class="flex items-center justify-between">
            <span class="font-medium text-gray-900">{date}</span>
            <span class="text-xs text-gray-400">{size}KB</span>
          </div>
          <p class="text-sm text-gray-500 mt-1">{preview}</p>
        </a>"""
    body = f"""
    <h1 class="text-2xl font-bold text-gray-900 mb-6">{title}</h1>
    <div class="grid gap-3">{items}</div>"""
    return base_html(title, body)


def generate_briefing_detail(date, content_md):
    """单个简报详情页。"""
    html = md_to_html(content_md)
    body = f"""
    <div class="mb-4">
      <a href="../briefings.html" class="text-sm text-blue-600 hover:underline">&larr; Back to briefings</a>
    </div>
    <div class="bg-white rounded-xl border border-gray-200 p-6 markdown text-sm">{html}</div>"""
    return base_html(f"Briefing {date}", body)


def generate_news_overview():
    """新闻总览页。"""
    categories = get_category_sources()
    cards = ""
    for cat, sources in categories:
        counts, _ = get_category_counts()
        total = counts.get(cat, 0)
        src_items = ""
        for src, c in sources:
            src_items += f"""
            <a href="news/{cat}/{src}.html" class="flex items-center justify-between py-1.5 text-sm hover:bg-gray-50 -mx-2 px-2 rounded">
              <span class="text-gray-700">{src}</span>
              <span class="text-xs text-gray-400">{c}</span>
            </a>"""
        cards += f"""
        <div class="bg-white rounded-xl border border-gray-200 p-5">
          <h2 class="text-base font-semibold mb-3 flex items-center justify-between">
            <span>{CAT_LABELS.get(cat, cat)}</span>
            <span class="text-xs text-gray-400">{total} articles</span>
          </h2>
          {src_items}
        </div>"""
    body = f"""
    <h1 class="text-2xl font-bold text-gray-900 mb-6">News Sources</h1>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">{cards}</div>"""
    return base_html("News", body)


def generate_category_page(cat):
    """单个分类的新闻页（列出该分类下所有来源的最新文章）。"""
    cat_dir = os.path.join(NEWS_DATA_DIR, cat)
    all_articles = []
    for item in sorted(os.listdir(cat_dir)):
        item_path = os.path.join(cat_dir, item)
        if os.path.isdir(item_path):
            for fname in sorted(os.listdir(item_path), reverse=True)[:10]:
                if fname.endswith('.json'):
                    fp = os.path.join(item_path, fname)
                    try:
                        data = load_article(fp)
                        data['_source'] = item
                        all_articles.append(data)
                    except:
                        pass
    all_articles.sort(key=lambda x: x.get('published', ''), reverse=True)

    items = ""
    for a in all_articles[:50]:
        items += article_card(a, cat)

    body = f"""
    <div class="mb-4"><a href="../news.html" class="text-sm text-blue-600 hover:underline">&larr; Back to sources</a></div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900">{CAT_LABELS.get(cat, cat)} (all)</h1>
      <span class="text-sm text-gray-400">{len(all_articles)} articles</span>
    </div>
    <div class="grid gap-3">{items}</div>"""
    return base_html(f"{CAT_LABELS.get(cat, cat)} News", body)


def generate_source_page(cat, src):
    """单个新闻源的页面。"""
    src_dir = os.path.join(NEWS_DATA_DIR, cat, src)
    articles = []
    for fname in sorted(os.listdir(src_dir), reverse=True):
        if fname.endswith('.json'):
            fp = os.path.join(src_dir, fname)
            try:
                data = load_article(fp)
                articles.append(data)
            except:
                pass

    items = ""
    for a in articles:
        items += article_card(a, cat)

    body = f"""
    <div class="mb-4"><a href="../../news/{cat}.html" class="text-sm text-blue-600 hover:underline">&larr; Back to {CAT_LABELS.get(cat, cat)}</a></div>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold text-gray-900">{CAT_LABELS.get(cat, cat)} / {src}</h1>
      <span class="text-sm text-gray-400">{len(articles)} articles</span>
    </div>
    <div class="grid gap-3">{items}</div>"""
    return base_html(f"{src} — News", body)


def article_card(a, cat):
    title = a.get('title', 'No title')
    summary = a.get('summary', '')[:200]
    published = (a.get('published', '') or '')[:10]
    link = a.get('link', '#')
    source = a.get('source', a.get('_source', 'Unknown'))
    badge = CAT_COLORS.get(cat, 'bg-gray-100 text-gray-800')
    return f"""
    <div class="bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-200 transition">
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="text-xs px-2 py-0.5 rounded {badge}">{cat}</span>
            <span class="text-xs text-gray-400">{source}</span>
          </div>
          <h3 class="font-medium text-gray-900 text-sm">{title}</h3>
          <p class="text-xs text-gray-500 mt-1">{summary}{'...' if len(a.get('summary','')) > 200 else ''}</p>
        </div>
        <div class="flex-shrink-0 text-right">
          <div class="text-xs text-gray-400">{published}</div>
          <a href="{link}" target="_blank" class="text-xs text-blue-500 hover:underline block mt-1">Original</a>
        </div>
      </div>
    </div>"""


def generate_events_page():
    """事件追踪页。"""
    events = sorted_events(load_events())
    items = ""
    for e in events:
        eid = e.get('id', '')
        status_class = {"high": "border-l-red-500", "medium": "border-l-amber-400", "low": "border-l-green-400"}
        border = status_class.get(e.get('tail_risk', 'low'), 'border-l-gray-400')
        chain = ""
        for i, c in enumerate(e.get('causal_chain', [])):
            chain += f'<span class="px-2 py-0.5 bg-gray-100 rounded text-xs">{c}</span>'
            if i < len(e.get('causal_chain', [])) - 1:
                chain += '<span class="text-gray-300 text-xs mx-1">&rarr;</span>'

        history = ""
        for h in e.get('daily_history', [])[-5:]:
            history += f"""
            <div class="flex gap-2 text-xs">
              <span class="text-gray-400 flex-shrink-0 w-20">{h.get('date','')}</span>
              <span class="text-gray-600">{h.get('summary','')[:150]}{'...' if len(h.get('summary','')) > 150 else ''}</span>
            </div>"""

        items += f"""
        <div id="event-{eid}" class="bg-white rounded-xl border border-gray-200 p-5 border-l-4 {border}">
          <div class="flex items-start justify-between mb-2">
            <div>
              <h2 class="font-semibold text-gray-900">{e.get('title','')}</h2>
              <div class="flex items-center gap-3 text-xs text-gray-500 mt-1">
                <span>Status: <strong class="{'text-amber-600' if e.get('status') in ('active','escalating') else 'text-gray-600'}">{e.get('status','')}</strong></span>
                <span>Risk: <strong>{e.get('tail_risk','')}</strong></span>
                <span>Since: {e.get('first_detected','')}</span>
              </div>
            </div>
          </div>
          {f'<div class="mt-2 flex items-center gap-1 text-xs text-gray-500 flex-wrap">{chain}</div>' if chain else ''}
          {f'<div class="mt-3 space-y-1 max-h-48 overflow-y-auto">{history}</div>' if history else ''}
        </div>"""

    body = f"""
    <h1 class="text-2xl font-bold text-gray-900 mb-6">Event Intelligence</h1>
    <div class="grid gap-4">{items}</div>"""
    return base_html("Events", body)


def generate_404_page():
    """404 页面。"""
    body = """
    <div class="flex flex-col items-center justify-center py-20">
      <div class="text-6xl font-bold text-gray-200 mb-4">404</div>
      <h1 class="text-xl font-semibold text-gray-700 mb-2">Page Not Found</h1>
      <p class="text-gray-500 mb-6 text-center">The page you're looking for doesn't exist or has been moved.</p>
      <a href="%s/index.html" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition text-sm">
        Back to Dashboard
      </a>
    </div>""" % BASE_URL
    return base_html("404 Not Found", body)


# ============================================================
# 构建
# ============================================================

def build():
    # 清理输出目录（跳过 .git 因为权限问题）
    if os.path.exists(OUTPUT_DIR):
        for item in os.listdir(OUTPUT_DIR):
            if item == '.git':
                continue
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                os.unlink(item_path)
    else:
        os.makedirs(OUTPUT_DIR)

    # 生成各页面
    pages = {}

    pages['index.html'] = generate_index()
    pages['briefings.html'] = generate_report_list("briefing", "Daily Briefings")
    pages['eco.html'] = generate_report_list("eco", "Economic Reports")
    pages['news.html'] = generate_news_overview()
    pages['events.html'] = generate_events_page()
    pages['404.html'] = generate_404_page()

    print("  > Generating: index, briefings, eco, news overview, events, 404")

    # 各分类页面
    for cat in CAT_LABELS:
        cat_dir = os.path.join(OUTPUT_DIR, "news")
        os.makedirs(cat_dir, exist_ok=True)
        pages[f"news/{cat}.html"] = generate_category_page(cat)
        print(f"  > Generating: news/{cat}.html")

        # 各来源页面
        src_dir = os.path.join(NEWS_DATA_DIR, cat)
        if os.path.isdir(src_dir):
            for src in os.listdir(src_dir):
                src_path = os.path.join(src_dir, src)
                if os.path.isdir(src_path):
                    src_out = os.path.join(OUTPUT_DIR, "news", cat)
                    os.makedirs(src_out, exist_ok=True)
                    pages[f"news/{cat}/{src}.html"] = generate_source_page(cat, src)

    # 简报详情页
    briefings = sorted(glob.glob(os.path.join(REPORTS_DIR, "briefing_*.md")), reverse=True)
    for b in briefings:
        date = os.path.basename(b).replace("briefing_", "").replace(".md", "")
        briefing_dir = os.path.join(OUTPUT_DIR, "briefing")
        os.makedirs(briefing_dir, exist_ok=True)
        with open(b, 'r', encoding='utf-8') as f:
            content = f.read()
        pages[f"briefing/{date}.html"] = generate_briefing_detail(date, content)
        print(f"  > Generating: briefing/{date}.html")

    # 经济报告
    for ep in sorted(glob.glob(os.path.join(REPORTS_DIR, "eco_*.md")), reverse=True):
        date = os.path.basename(ep).replace("eco_", "").replace(".md", "")
        eco_dir = os.path.join(OUTPUT_DIR, "eco")
        os.makedirs(eco_dir, exist_ok=True)
        with open(ep, 'r', encoding='utf-8') as f:
            content = f.read()
        pages[f"eco/{date}.html"] = generate_briefing_detail(date, content)
        print(f"  > Generating: eco/{date}.html")

    # 写入文件
    for path, html in pages.items():
        full_path = os.path.join(OUTPUT_DIR, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(html)

    # 统计
    total_pages = len(pages)
    total_size = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            total_size += os.path.getsize(os.path.join(root, f))

    print(f"\n  Build complete: {total_pages} pages, {total_size // 1024} KB")
    print(f"  Output: {OUTPUT_DIR}")
    return total_pages


if __name__ == "__main__":
    print("NewsRadar Static Site Builder")
    print("=" * 40)
    build()
