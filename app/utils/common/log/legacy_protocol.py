"""通用脚本 stdout 回传标记的共享解码。"""

import json
from typing import Any

MSG_PREFIX = "@@LOGBOX@@"


def parse_marker(line: str) -> dict[str, Any] | None:
    """返回有效的协议对象，普通行和损坏标记交给文本规则。"""
    if not line.startswith(MSG_PREFIX):
        return None
    try:
        payload = json.loads(line[len(MSG_PREFIX) :])
    except (ValueError, RecursionError):
        return None
    return payload if isinstance(payload, dict) else None
