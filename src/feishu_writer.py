# src/feishu_writer.py — 飞书多维表格写入模块（支持 API + lark-cli 双模式）
import json
import os
import subprocess
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TOKEN_CACHE = {"token": None, "expires_at": 0}


def _get_tenant_token() -> Optional[str]:
    """获取飞书 tenant_access_token（API 模式）"""
    now = time.time()
    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["token"]

    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
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
        _TOKEN_CACHE["expires_at"] = now + expire - 60
        return token
    except Exception as e:
        logger.error(f"获取飞书 token 失败: {e}")
        return None


def _write_via_api(base_token: str, table_id: str, record: dict) -> bool:
    """通过 OpenAI API 写入"""
    token = _get_tenant_token()
    if not token:
        return False

    url = f"https://open.feishu.cn/open-apis/base/v3/bases/{base_token}/tables/{table_id}/records"
    try:
        import requests
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"fields": record},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.warning(f"API 写入失败 (code={data.get('code')}): {data.get('msg', '')}")
            return False
        logger.info(f"API 写入成功: {record.get('选题标题', '无标题')}")
        return True
    except Exception as e:
        logger.error(f"API 写入异常: {e}")
        return False


def _write_via_larkcli(base_token: str, table_id: str, record: dict) -> bool:
    """
    通过 lark-cli 写入。
    @file 语法只支持当前目录的相对路径，所以临时文件建在 CWD 而非系统 temp 目录。
    """
    lark_cli = os.getenv("LARK_CLI_PATH", "lark-cli")
    tmp_name = f"__lark_{os.getpid()}.json"
    try:
        payload = json.dumps(record, ensure_ascii=False)
        with open(tmp_name, "w", encoding="utf-8") as f:
            f.write(payload)

        result = subprocess.run(
            [lark_cli, "base", "+record-upsert",
             "--base-token", base_token,
             "--table-id", table_id,
             "--json", f"@{tmp_name}"],
            capture_output=True, text=False, timeout=15,
        )
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

        if result.returncode != 0:
            logger.warning(f"lark-cli 写入失败: {stderr[:300]}")
            return False
        logger.info(f"lark-cli 写入成功: {record.get('选题标题', '无标题')}")
        return True
    except FileNotFoundError:
        logger.warning("lark-cli 不存在，无法写入")
        return False
    except Exception as e:
        logger.error(f"lark-cli 写入异常: {e}")
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        return False


def _sanitize_record(record: dict) -> dict:
    """将 None/list/dict 等非标量值转为字符串，避免 Feishu API 拒绝"""
    result = {}
    for k, v in record.items():
        if v is None:
            result[k] = ""
        elif isinstance(v, list):
            # AI 有时返回数组而非字符串，转成换行分隔文本
            result[k] = "\n".join(str(x) for x in v)
        elif isinstance(v, dict):
            result[k] = json.dumps(v, ensure_ascii=False)
        else:
            result[k] = v
    return result


def write_to_bitable(base_token: str, table_id: str, record: dict) -> bool:
    """
    往飞书多维表格写入一条记录。
    优先用 API（GitHub Actions 环境），失败时回退到 lark-cli（本地环境）。
    """
    record = _sanitize_record(record)
    # 先尝试 API 模式
    if os.getenv("FEISHU_APP_ID") and os.getenv("FEISHU_APP_SECRET"):
        if _write_via_api(base_token, table_id, record):
            return True
        logger.info("API 写入失败，尝试 lark-cli 回退...")
    # 回退到 lark-cli
    return _write_via_larkcli(base_token, table_id, record)
