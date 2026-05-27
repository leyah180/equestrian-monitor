#!/usr/bin/env python3
# src/monitor.py — 扫描信源，写入原文内容到飞书多维表
# AI 分析和通知已迁移到飞书 Workflow 自动处理

import sys
import yaml
import logging
import hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetcher import fetch_rss, resolve_podcast_rss
from src.feishu_writer import write_to_bitable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("monitor")

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


def process_source(cfg: dict, config: dict, source_type: str) -> int:
    """处理单个信源，返回新增选题数"""
    name = cfg["name"]
    max_items = config["scan"]["max_per_source"]

    rss_url = cfg.get("rss_url")
    if not rss_url and cfg.get("apple_id"):
        rss_url = resolve_podcast_rss(cfg["apple_id"])
        if rss_url:
            logger.info(f"{name}: 通过 Apple ID 获取 RSS → {rss_url}")
    if not rss_url:
        logger.info(f"{name}: 无可用 RSS URL，跳过")
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

        logger.info(f"发现新内容: [{name}] {item['title']}")

        record = {
            "原文标题": item["title"][:500],
            "原文链接": item["link"],
            "原文内容": item["summary"],
            "来源名称": name,
            "来源类型": source_type,
            "状态": "待评估",
            "信息差评分": 3,
            "话题热度": 3,
            "制作难度": "中等",
            "优先级": "P2",
        }

        ok = write_to_bitable(
            config["feishu"]["base_token"],
            config["feishu"]["table_id"],
            record,
        )
        if ok:
            _save_seen(fp)
            added += 1

    return added


def main():
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    total = 0

    logger.info(f"=== 开始扫描播客（共 {len(config['podcasts'])} 个）===")
    for podcast in config["podcasts"]:
        try:
            total += process_source(podcast, config, "播客")
        except Exception as e:
            logger.error(f"处理播客 {podcast['name']} 失败: {e}")

    logger.info(f"=== 开始扫描博客（共 {len(config['blogs'])} 个）===")
    for blog in config["blogs"]:
        try:
            total += process_source(blog, config, "博客/网站")
        except Exception as e:
            logger.error(f"处理博客 {blog['name']} 失败: {e}")

    logger.info(f"=== 完成！本次新增 {total} 个选题到多维表 ===")
    logger.info(f"（AI 分析与飞书通知由 Workflow 自动处理）")


if __name__ == "__main__":
    main()
