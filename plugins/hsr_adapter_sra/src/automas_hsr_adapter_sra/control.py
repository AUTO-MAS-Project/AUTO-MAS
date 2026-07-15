#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


from pathlib import Path
from typing import Any, Callable

from automas_script_hsr.contracts import HSRNativeRunPlan
from automas_script_hsr.runtime.models import HSRPhase
from automas_script_hsr.runtime.tasks import HSRTaskModule
from automas_script_hsr.runtime.game import HSRAccountSwitcher, resolve_sra_start_mode
from .runner import (
    build_sra_module_config,
    build_sra_start_game_config,
    run_sra_single_task,
    SRAProcessRegistry,
    write_sra_temp_config,
)


class HSRSRAControl:
    """SRA 执行项创建与单任务控制。"""

    def __init__(
        self,
        *,
        script_config: Any,
        account_switcher: HSRAccountSwitcher,
        process_registry: SRAProcessRegistry,
        append_log: Callable[[str], None],
    ) -> None:
        self.script_config = script_config
        self._account_switcher = account_switcher
        self._process_registry = process_registry
        self._append_log = append_log

    async def run_sra_task(
        self,
        sra_exe_path: Path,
        task_class: str,
        temp_path: Path,
        user_name: str,
        module_name: str,
        timeout_seconds: int | None = None,
        module_key: str = "",
        track_script_switch: bool = True,
    ):
        """执行一条 SRA 单任务并同步调度台日志。"""

        await self._account_switcher.wait_before_external_script(
            "SRA",
            user_name,
            track_last_script=track_script_switch,
        )
        self._append_log(
            f"用户「{user_name}」开始执行 SRA {module_name}（{task_class}）"
        )
        result = await run_sra_single_task(
            sra_exe_path,
            task_class,
            temp_path,
            timeout=timeout_seconds or 600,
            process_registry=self._process_registry,
            log_callback=self._append_log,
            output_line_callback=(
                self._account_switcher.recover_game_window_if_screenshot_blocked
            ),
            module_key=module_key,
        )
        state = "完成" if result.success else "失败"
        self._append_log(f"用户「{user_name}」SRA {module_name} 执行{state}")
        return result

    async def run_start_game(
        self,
        *,
        user_config: Any,
        user_name: str,
        user_id: str,
        script_id: str,
        sra_exe_path: Path,
        module_key: str,
        temp_files: list[Path],
        timeout_seconds: int,
    ):
        """Build and execute the SRA StartGame task inside the SRA adapter."""

        await self._account_switcher.ensure_game_started_by_mas()
        start_cfg = build_sra_start_game_config(
            self.script_config,
            user_config,
            mode=resolve_sra_start_mode(user_config, user_name),
        )
        temp_path = write_sra_temp_config(
            start_cfg,
            script_id,
            user_id,
            module_key,
        )
        temp_files.append(temp_path)
        result = await self.run_sra_task(
            sra_exe_path,
            "StartGameTask",
            temp_path,
            user_name,
            "登录/切号",
            timeout_seconds=timeout_seconds,
            module_key=module_key,
            track_script_switch=False,
        )
        self._account_switcher.mark_game_session_clean(result.success)
        return result

    def create_start_item(
        self,
        *,
        user_cfg: Any,
        user_name: str,
        uid: str,
        phase: HSRPhase,
        timeout_seconds: int,
        sra_exe_path: Path,
        script_id: str,
        temp_files: list[Path],
    ) -> HSRNativeRunPlan:
        """创建 SRA 登录/切号队列项。"""

        async def run_sra_start():
            return await self.run_start_game(
                user_config=user_cfg,
                user_name=user_name,
                user_id=uid,
                script_id=script_id,
                sra_exe_path=sra_exe_path,
                module_key=f"{phase}_StartGame",
                temp_files=temp_files,
                timeout_seconds=timeout_seconds,
            )

        return HSRNativeRunPlan(run=run_sra_start)

    def create_module_item(
        self,
        *,
        user_cfg: Any,
        user_name: str,
        uid: str,
        module: HSRTaskModule,
        timeout_seconds: int,
        sra_exe_path: Path,
        script_id: str,
        temp_files: list[Path],
        daily_eow_enabled: bool,
    ) -> HSRNativeRunPlan | None:
        """创建一个 SRA 模块队列项。"""

        if module.key == "Daily":
            cfg = build_sra_module_config(
                module,
                self.script_config,
                user_cfg,
                daily_eow_enabled=daily_eow_enabled,
            )
            tasklist = cfg.get("trailblazePower", {}).get("tasklist") or []
            if not tasklist:
                self._append_log(f"用户「{user_name}」体力模块无可执行副本，跳过")
                return None
        else:
            cfg = build_sra_module_config(module, self.script_config, user_cfg)

        temp_path = write_sra_temp_config(cfg, script_id, uid, module.key)
        temp_files.append(temp_path)

        async def run_sra_module():
            return await self.run_sra_task(
                sra_exe_path,
                module.sra_task or "",
                temp_path,
                user_name,
                module.name,
                timeout_seconds=timeout_seconds,
                module_key=module.key,
            )

        return HSRNativeRunPlan(run=run_sra_module)
