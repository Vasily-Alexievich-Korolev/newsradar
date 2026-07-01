#!/usr/bin/env python3
"""
run_news_pipeline.py — 本地新闻情报管线运行主控

完整流水线：
  1. 加载 .env 密钥
  2. 抓取 12 项宏观/市场数据
  3. 经济分析（DeepSeek）
  4. 新闻简报（DeepSeek）
  5. 构建静态站点
  6. Git 提交 + 推送到远程
  7. 部署到 GitHub Pages (gh-pages 分支)
  8. 自动关机（可选）

使用方式：
  python run_news_pipeline.py                # 完整运行
  python run_news_pipeline.py --no-shutdown  # 跑完不关机
  python run_news_pipeline.py --skip-fetch   # 跳过数据抓取
  python run_news_pipeline.py --skip-ai      # 跳过 AI 分析
"""

import os
import sys
import subprocess
import time
import argparse
import platform
import glob
import tempfile
import shutil
from datetime import datetime

# ── 项目根目录 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# ── 步骤耗时统计 ──
timings = []


def log(msg):
    print(f"\n{'='*56}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")
    print(f"{'='*56}")


def run_step(name, cmd, cwd=None, env=None, timeout=600):
    """运行单个步骤，捕获超时和异常"""
    print(f"  > {name}")
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or BASE_DIR,
            env=env or os.environ,
            timeout=timeout,
        )
        elapsed = time.time() - start
        ok = result.returncode == 0
        status = "OK" if ok else f"FAIL (code={result.returncode})"
        print(f"  > {status}  [{elapsed:.1f}s]")
        timings.append((name, elapsed, ok))
        return ok
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"  > TIMEOUT  [{elapsed:.1f}s]")
        timings.append((name, elapsed, False))
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"  > ERROR: {e}  [{elapsed:.1f}s]")
        timings.append((name, elapsed, False))
        return False


def load_env():
    """从 .env 文件加载环境变量"""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        print("  [WARN] .env 文件不存在，跳过")
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()
            print(f"  > 加载环境变量: {key.strip()}")


def check_api_key():
    """检查 DeepSeek API Key"""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key or key == "sk-xxxx":
        print("  [WARN] DEEPSEEK_API_KEY 未设置或为占位值")
        print("    请编辑 .env 文件填入真实 API Key")
        print("    跳过 AI 分析步骤")
        return False
    return True


def git_push():
    """Git 提交并推送到远程 main 分支"""
    log("步骤 5: Git 提交 + 推送")

    # git add
    run_step("git add 数据文件", ["git", "add",
        "eco_data/", "news/reports/", "news/events.json",
        "sse_etf_data/", "data_stock/",
    ])
    daily_files = glob.glob(os.path.join(BASE_DIR, "data", "*_history_1d.csv"))
    if daily_files:
        run_step("git add 日K线", ["git", "add"] + daily_files)
    else:
        print("  > 无日K线文件，跳过")

    # 检查是否有变更
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=BASE_DIR, capture_output=True,
    )
    if result.returncode == 0:
        print("  > 无数据变更，跳过提交")
        return True

    date_str = datetime.now().strftime("%Y-%m-%d")
    ok = run_step("git commit", ["git", "commit", "-m", f"auto: update {date_str}"])
    if not ok:
        return False
    ok = run_step("git push", ["git", "push", "newsradar", "main"])
    return ok


def deploy_pages():
    """部署静态站点到 gh-pages 分支（用于 GitHub Pages）"""
    log("步骤 6: 部署到 GitHub Pages")
    site_dir = os.path.join(BASE_DIR, "news", "static_site")
    if not os.path.isdir(site_dir):
        print("  > static_site 目录不存在，跳过")
        return False

    tmp = tempfile.mkdtemp(prefix="gh_pages_")
    try:
        dst = os.path.join(tmp, "site")
        shutil.copytree(site_dir, dst)

        # 在临时目录创建 orphan 分支
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "checkout", "--orphan", "gh-pages"],
                       cwd=tmp, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        r = subprocess.run(
            ["git", "commit", "-m", f"deploy: {date_str}"],
            cwd=tmp, capture_output=True,
        )
        if r.returncode != 0:
            print("  > 无变更，跳过部署")
            return True

        # 推送到远程 gh-pages 分支
        remote_url = subprocess.run(
            ["git", "remote", "get-url", "newsradar"],
            cwd=BASE_DIR, capture_output=True, text=True,
        ).stdout.strip()

        subprocess.run(
            ["git", "push", "--force", remote_url, "gh-pages:gh-pages"],
            cwd=tmp, capture_output=True, timeout=30,
        )
        print("  > 已推送到远程 gh-pages 分支")
        print("  > Pages 地址: https://vasily-alexievich-korolev.github.io/newsradar/")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def shutdown():
    """Windows 关机"""
    log("步骤 7: 自动关机")
    if platform.system() == "Windows":
        print("  > 60 秒后关机...")
        subprocess.run(["shutdown", "/s", "/t", "60"])
    else:
        print("  > 非 Windows 系统，跳过关机")


def print_summary():
    print(f"\n{'='*56}")
    print(f"  执行汇总")
    print(f"{'='*56}")
    success = sum(1 for _, _, ok in timings if ok)
    total = len(timings)
    for name, elapsed, ok in timings:
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name:<30s} {elapsed:>6.1f}s")
    print(f"\n  成功: {success}/{total}  |  总耗时: {sum(e for _, e, _ in timings):.0f}s")
    print(f"{'='*56}")


def main():
    parser = argparse.ArgumentParser(description="本地新闻情报管线")
    parser.add_argument("--no-shutdown", action="store_true", help="跑完后不关机")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过数据抓取")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 分析")
    args = parser.parse_args()

    log("NewsRadar 本地管线启动")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目录: {BASE_DIR}")

    # 步骤 0: 加载密钥
    log("步骤 0: 加载环境变量")
    load_env()
    has_api_key = check_api_key()

    # 步骤 1: 数据抓取
    if not args.skip_fetch:
        log("步骤 1: 宏观经济 + 市场数据抓取")
        run_step("update_all_eco.py", [PYTHON, "data_fetch/update_all_eco.py"])
    else:
        print("  > 跳过数据抓取 (--skip-fetch)")

    # 步骤 2: 经济分析
    if not args.skip_ai and has_api_key:
        log("步骤 2: 经济分析 (DeepSeek)")
        run_step("eco_analysis.py", [PYTHON, "news/eco_analysis.py"])
    else:
        print("  > 跳过经济分析")

    # 步骤 3: 新闻简报
    if not args.skip_ai and has_api_key:
        log("步骤 3: 新闻简报 (DeepSeek)")
        run_step("news_intelligence.py", [PYTHON, "news/news_intelligence.py"])
    else:
        print("  > 跳过新闻简报")

    # 步骤 4: 构建静态站
    log("步骤 4: 构建静态站点")
    run_step("build_static_site.py", [PYTHON, "news/build_static_site.py"])

    # 步骤 5: Git 提交 + 推送
    git_push()

    # 步骤 6: 部署到 GitHub Pages
    deploy_pages()

    # 汇总
    print_summary()

    # 步骤 7: 关机
    if not args.no_shutdown:
        shutdown()
    else:
        print("  > 跳过关机 (--no-shutdown)")


if __name__ == "__main__":
    main()
