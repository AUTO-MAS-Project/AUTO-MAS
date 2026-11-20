"""神秘入口的解锁状态判定。

解锁记录由入口页面写在同一个 config 目录的 frontend_config.json 里。
后端沿用它和前端相同的判据（当日 + 设备与源码指纹），
插件市场与安装门禁因此和入口页面看到的是同一个状态，不会一边放行一边拒绝。
"""

from __future__ import annotations

import json
from datetime import datetime

from app.mystery.access import MysteryContextError, get_access_context

CONFIG_FILE_NAME = "frontend_config.json"


def _unlock_record() -> tuple[str, str]:
    """读取入口页面记下的解锁日期与指纹；文件缺失或格式不符时按未解锁处理。"""
    from app.core import Config

    path = Config.config_path / CONFIG_FILE_NAME
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    if not isinstance(record, dict):
        return "", ""
    date = record.get("mysteryUnlockedDate")
    fingerprint = record.get("mysteryUnlockedFingerprint")
    if not isinstance(date, str) or not isinstance(fingerprint, str):
        return "", ""
    return date, fingerprint


def is_unlocked() -> bool:
    """当日已解锁且指纹仍属于当前设备与当前后端源码时才成立。"""
    from app.utils import UTC8

    date, fingerprint = _unlock_record()
    if not date or not fingerprint:
        return False
    if date != datetime.now(UTC8).strftime("%Y-%m-%d"):
        return False
    try:
        device_hash, backend_hash = get_access_context()
    except MysteryContextError:
        # 申请信息不可用时入口页面本身也进不去，这里同样按未解锁处理。
        return False
    return fingerprint == f"{device_hash}:{backend_hash}"
