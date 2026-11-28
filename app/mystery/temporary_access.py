"""为 v5.10.0-beta.1 的神秘入口提供限时开放。"""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from threading import Lock

from app.mystery.gate import CONFIG_FILE_NAME
from app.utils import UTC8

if sys.platform == "win32":
    from app.mystery.windows_config import replace_if_unchanged

TEMPORARY_ACCESS_END = date(2026, 12, 10)
_AUTO_OPEN_DATE = "mysteryAutoOpenedDate"
_write_lock = Lock()


def open_for_today(config_dir: Path, fingerprint: str) -> None:
    """按北京时间每天自动解锁至多一次，保留同日的手动重新锁定。"""
    if sys.platform != "win32":
        return

    with _write_lock:
        today = datetime.now(UTC8).date()
        if today >= TEMPORARY_ACCESS_END:
            return

        path = config_dir / CONFIG_FILE_NAME
        try:
            original = path.read_bytes()
        except FileNotFoundError:
            original = None
        config = json.loads(original.decode("utf-8")) if original is not None else {}
        if not isinstance(config, dict):
            raise ValueError("前端配置必须是 JSON 对象")

        day = today.isoformat()
        if config.get(_AUTO_OPEN_DATE) == day:
            return

        config.update(
            {
                _AUTO_OPEN_DATE: day,
                "mysteryUnlockedDate": day,
                "mysteryUnlockedFingerprint": fingerprint,
            }
        )
        updated = json.dumps(config, ensure_ascii=True, allow_nan=False, indent=2)
        replace_if_unchanged(
            path=path, original=original, updated=updated.encode("utf-8")
        )
