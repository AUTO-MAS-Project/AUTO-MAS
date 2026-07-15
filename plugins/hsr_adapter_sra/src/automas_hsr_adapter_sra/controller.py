from __future__ import annotations

from pathlib import Path
from typing import Any

from automas_script_hsr import HSRControllerSession

from .catalog import SRA_DESCRIPTOR


class SRAController:
    descriptor = SRA_DESCRIPTOR

    def probe(self, script_config: Any) -> tuple[bool, str]:
        root = str(script_config.get("SRA", "Path") or "").strip()
        if not root:
            return False, "请设置 SRA 路径"
        executable = Path(root) / "SRA-cli.exe"
        if not executable.is_file():
            return False, f"SRA 路径中未找到 SRA-cli.exe：{executable}"
        return True, ""

    async def open_session(
        self,
        *,
        script_id: str,
        script_config: Any,
        log,
        coordinator: Any,
    ) -> HSRControllerSession:
        from .runtime import SRAControllerSessionImpl

        return await SRAControllerSessionImpl.create(
            script_id=script_id,
            script_config=script_config,
            log=log,
            coordinator=coordinator,
        )
