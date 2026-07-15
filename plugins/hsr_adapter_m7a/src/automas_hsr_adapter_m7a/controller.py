from __future__ import annotations

from pathlib import Path
from typing import Any

from automas_script_hsr import HSRControllerSession

from .catalog import M7A_DESCRIPTOR


class M7AController:
    descriptor = M7A_DESCRIPTOR

    def probe(self, script_config: Any) -> tuple[bool, str]:
        root = str(script_config.get("M7A", "Path") or "").strip()
        if not root:
            return False, "请设置三月七助手路径"
        executable = Path(root) / "March7th Assistant.exe"
        if not executable.is_file():
            return False, f"三月七助手路径中未找到 March7th Assistant.exe：{executable}"
        return True, ""

    async def open_session(
        self,
        *,
        script_id: str,
        script_config: Any,
        log,
        coordinator: Any,
    ) -> HSRControllerSession:
        from .runtime import M7AControllerSessionImpl

        return await M7AControllerSessionImpl.create(
            script_id=script_id,
            script_config=script_config,
            log=log,
            coordinator=coordinator,
        )
