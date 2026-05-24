#!/usr/bin/env python3
# src/monitor.py — 主入口：扫描所有信源，AI 分析，写入飞书

import os
import sys
import yaml
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetcher import fetch_rss, resolve_podcast_rss, is_recent
from src.analyzer import analyze_content
from src.feishu_writer import write_to_bitable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("monitor")

# 已处理记录的指纹缓存（避免重复写入）
_SEEN_FILE = Path(__file__).resolve().parent.parent / ".seen_fingerprints.txt"


def _load_seen() -> set:
    if _SEEN_FILE.exists():
        return set(_SEEN_FILE.read_text().strip().splitlines())
    return set()


def _save_seen(fingerprint: str):
    with open(_SEEN_FILE, "a") as f:
        f.write(fingerprint + "\n")


def _fingerprint(source_name: str, title: str) -> str:
    raw = f"{source_name}:{title}"
    return hashlib.md5(raw.encode()).hexdigest()


def process_podcast_source(cfg: dict, config: dict) -> int:
    """处理单个播客信源，返回新增选题数"""
    name = cfg["name"]
    max_items = config["scan"]["max_per_source"]
    lookback = config["scan"]["lookback_hours"]

    # 获取 RSS URL
    rss_url = cfg.get("rss_url")
    if not rss_url and cfg.get("apple_id"):
        rss_url = resolve_podcast_rss(cfg["apple_id"])
        if rss_url:
            logger.info(f"{name}: 通过 Apple ID 获取 RSS → {rss_url}")
    if not rss_url:
        logger.warning(f"{name}: 无可用 RSS URL，跳过")
        return 0

    items = fetch_rss(rss_url, max_items)
    if not items:
        logger.info(f"{name}: 无新条目")
        return 0

    seen = _load_seen()
    added = 0

    for item in items:
        fp = _fingerprint(name, item["title"])
        if fp in seen:
            continue

        # 分析内容
        logger.info(f"分析中: [{name}] {item['title']}")
        analysis = analyze_content(item["title"], item["summary"], name)

        # 构建飞书记录
        record = {
            "选题标题": analysis["suggestion"][:30] if analysis and analysis.get("suggestion") else f"{name}: {item['title'][:30]}",
            "原文标题": item["title"][:200],
            "来源类型": "播客",
            "来源名称": name,
            "原文链接": item["link"],
            "AI摘要": analysis["ai_summary"] if analysis else item["summary"][:200],
            "核心观点": analysis["key_points"] if analysis else "",
            "AI选题建议": analysis["suggestion"] if analysis else "",
            "信息差评分": analysis["info_gap_score"] if analysis else 3,
            "话题热度": analysis["topic_heat_score"] if analysis else 3,
            "制作难度": analysis["difficulty"] if analysis else "中等",
            "状态": "待评估",
        }
        if analysis and analysis.get("info_gap_score", 0) >= 4:
            record["优先级"] = "P1"
        elif analysis and analysis.get("info_gap_score", 0) >= 3:
            record["优先级"] = "P2"
        else:
            record["优先级"] = "P3"

        ok = write_to_bitable(config["feishu"]["base_token"], config["feishu"]["table_id"], record)
        if ok:
            _save_seen(fp)
            added += 1

    return added


def process_blog_source(cfg: dict, config: dict) -> int:
    """处理单个博客信源"""
    name = cfg["name"]
    rss_url = cfg.get("rss_url", "")
    max_items = config["scan"]["max_per_source"]

    if not rss_url:
        logger.info(f"{name}: 无 RSS（后续可做网页抓取），跳过")
        return 0

    items = fetch_rss(rss_url, max_items)
    if not items:
        return 0

    seen = _load_seen()
    added = 0

    for item in items:
        fp = _fingerprint(name, item["title"])
        if fp in seen:
            continue

        logger.info(f"分析中: [{name}] {item['title']}")
        analysis = analyze_content(item["title"], item["summary"], name)

        record = {
            "选题标题": analysis["suggestion"][:30] if analysis and analysis.get("suggestion") else f"{name}: {item['title'][:30]}",
            "原文标题": item["title"][:200],
            "来源类型": "博客/网站",
            "来源名称": name,
            "原文链接": item["link"],
            "AI摘要": analysis["ai_summary"] if analysis else item["summary"][:200],
            "核心观点": analysis["key_points"] if analysis else "",
            "AI选题建议": analysis["suggestion"] if analysis else "",
            "信息差评分": analysis["info_gap_score"] if analysis else 3,
            "话题热度": analysis["topic_heat_score"] if analysis else 3,
            "制作难度": analysis["difficulty"] if analysis else "中等",
            "状态": "待评估",
        }
        if analysis and analysis.get("info_gap_score", 0) >= 4:
            record["优先级"] = "P1"
        elif analysis and analysis.get("info_gap_score", 0) >= 3:
            record["优先级"] = "P2"
        else:
            record["优先级"] = "P3"

        ok = write_to_bitable(config["feishu"]["base_token"], config["feishu"]["table_id"], record)
        if ok:
            _save_seen(fp)
            added += 1

    return added


def main():
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    total = 0

    # 扫描播客
    logger.info(f"=== 开始扫描播客（共 {len(config['podcasts'])} 个）===")
    for podcast in config["podcasts"]:
        try:
            total += process_podcast_source(podcast, config)
        except Exception as e:
            logger.error(f"处理播客 {podcast['name']} 失败: {e}")

    # 扫描博客
    logger.info(f"=== 开始扫描博客（共 {len(config['blogs'])} 个）===")
    for blog in config["blogs"]:
        try:
            total += process_blog_source(blog, config)
        except Exception as e:
            logger.error(f"处理博客 {blog['name']} 失败: {e}")

    logger.info(f"=== 完成！本次新增 {total} 个选题 ===")

    # 设置 GitHub Actions 输出
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"new_topics={total}\n")


if __name__ == "__main__":
    main()
