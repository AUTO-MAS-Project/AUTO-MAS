"""共享脚本解释器约定；未知后缀交由系统默认程序打开。"""

import sys
from pathlib import Path

from app.utils import UnsupportedPlatformError


def build(script_path: Path) -> list[str] | None:
    suffix = script_path.suffix.lower()
    if suffix in {".bat", ".cmd"}:
        raise UnsupportedPlatformError("windows_batch_script")
    if suffix == ".py":
        return [sys.executable, str(script_path)]
    if suffix == ".exe":
        return [str(script_path)]
    if suffix == ".ps1":
        return [
            "pwsh",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
    if suffix == ".js":
        return ["node", str(script_path)]
    if suffix == ".sh":
        return ["bash", str(script_path)]
    return None
