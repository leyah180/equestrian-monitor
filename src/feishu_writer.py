# src/feishu_writer.py — 飞书多维表格写入模块
import json
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TOKEN_CACHE = {"token": None, "expires_at": 0}


def _get_tenant_token() -> Optional[str]:
    """获取飞书 tenant_access_token"""
    now = time.time()
    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["token"]

    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        logger.warning("FEISHU_APP_ID 或 FEISHU_APP_SECRET 未设置")
        return None

    try:
        import requests
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = resp.json()
        token = data.get("tenant_access_token")
        expire = data.get("expire", 7200)
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = now + expire - 60  # 提前 1 分钟过期
        return token
    except Exception as e:
        logger.error(f"获取飞书 token 失败: {e}")
        return None


def write_to_bitable(base_token: str, table_id: str, record: dict) -> bool:
    """
    往飞书多维表格写入一条记录。
    record 的 key 是字段名，value 是对应的 CellValue。
    """
    token = _get_tenant_token()
    if not token:
        return False

    url = f"https://open.feishu.cn/open-apis/base/v3/bases/{base_token}/tables/{table_id}/records"

    payload = {"fields": record}

    try:
        import requests
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.error(f"写入飞书失败: {data}")
            return False
        logger.info(f"写入成功: {record.get('选题标题', '无标题')}")
        return True
    except Exception as e:
        logger.error(f"写入飞书异常: {e}")
        return False
