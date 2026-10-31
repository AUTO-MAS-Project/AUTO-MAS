"""Windows 的批处理和 PowerShell 解释器选择。"""

from pathlib import Path

from app.services.common.custom_script.native import build as build_common


def build(script_path: Path) -> list[str] | None:
    if script_path.suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/c", str(script_path), "admin"]
    if script_path.suffix.lower() == ".ps1":
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
    return build_common(script_path)
