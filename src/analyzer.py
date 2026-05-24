# src/analyzer.py — AI 内容分析与选题建议模块
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def analyze_content(title: str, summary: str, source_name: str) -> Optional[dict]:
    """
    调用 Claude API 分析单条内容，返回结构化选题建议。
    返回: {
        "ai_summary": "...",
        "key_points": "...",
        "info_gap_score": 4,
        "topic_heat_score": 3,
        "suggestion": "..."
    }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 未设置，跳过 AI 分析")
        return None

    prompt = f"""你是一个马术内容编辑，专门为国内马术圈筛选国外优质内容。

原始来源：{source_name}
标题：{title}
摘要：{summary[:800]}

请分析这条内容对国内马术读者的价值，返回 JSON（不要多余文字）：
{{
  "ai_summary": "用 2-3 句中文概括核心信息",
  "key_points": "列出 1-3 个核心观点，用中文",
  "info_gap_score": 1-5 的整数（5=国内极稀缺，1=国内已有大量类似内容）,
  "topic_heat_score": 1-5 的整数（5=话题度很高，容易传播）,
  "difficulty": "简单/中等/困难"（制作一篇解读文章的工作量）,
  "suggestion": "给出一个切入角度和推荐标题方向"
}}
"""
    try:
        import requests
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        resp = requests.post(
            f"{base_url}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.getenv("CLAUDE_MODEL", "deepseek-chat"),
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]

        # 提取 JSON
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("\n", 1)[0]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text.strip())

    except Exception as e:
        logger.error(f"AI 分析失败: {e}")
        return None
