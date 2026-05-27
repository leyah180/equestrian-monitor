# src/notifier.py — 飞书消息推送（扫描完成后通知用户）
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def send_notification(summary: str) -> bool:
    """通过飞书应用给用户发送扫描完成通知"""
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    user_open_id = os.getenv("FEISHU_USER_OPEN_ID")

    if not all([app_id, app_secret, user_open_id]):
        logger.info("飞书通知未配置（缺少 FEISHU_APP_ID/FEISHU_APP_SECRET/FEISHU_USER_OPEN_ID），跳过")
        return False

    try:
        import requests
        # 1. 获取 tenant_access_token
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = resp.json()
        token = data.get("tenant_access_token")
        if not token:
            logger.warning(f"获取 token 失败: {data}")
            return False

        # 2. 发送私信
        content = {"text": summary}
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": user_open_id,
                "msg_type": "text",
                "content": __import__("json").dumps(content, ensure_ascii=False),
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.warning(f"发送消息失败 (code={data.get('code')}): {data.get('msg', '')}")
            return False
        logger.info("飞书通知已发送")
        return True
    except Exception as e:
        logger.error(f"飞书通知异常: {e}")
        return False
