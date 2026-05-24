# src/fetcher.py — RSS 信源抓取模块
import feedparser
import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

def fetch_rss(url: str, max_items: int = 3) -> list[dict]:
    """抓取 RSS feed，返回最新的条目列表"""
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.warning(f"解析 RSS 失败: {url} - {feed.bozo_exception}")
            return []
    except Exception as e:
        logger.error(f"请求 RSS 异常: {url} - {e}")
        return []

    items = []
    for entry in feed.entries[:max_items]:
        item = {
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", ""),
            "summary": _clean_html(entry.get("summary", "") or ""),
            "published": entry.get("published", ""),
            "published_parsed": entry.get("published_parsed"),
        }
        items.append(item)
    return items


def resolve_podcast_rss(apple_id: int) -> Optional[str]:
    """通过 Apple Podcasts Lookup API 获取 RSS feed URL"""
    url = f"https://itunes.apple.com/lookup?id={apple_id}"
    try:
        import requests
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if results := data.get("results", []):
            return results[0].get("feedUrl")
    except Exception as e:
        logger.warning(f"Apple Podcasts Lookup 失败 (id={apple_id}): {e}")
    return None


def _clean_html(text: str) -> str:
    """移除 HTML 标签（保留纯文本）"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]  # 摘要控制在 500 字内


def is_recent(published_parsed, lookback_hours: int = 168) -> bool:
    """判断发布时间是否在指定时间窗口内"""
    if not published_parsed:
        return False
    try:
        pub_time = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (now - pub_time).total_seconds()
        return 0 <= delta <= lookback_hours * 3600
    except Exception:
        return True  # 无法判断时默认通过
