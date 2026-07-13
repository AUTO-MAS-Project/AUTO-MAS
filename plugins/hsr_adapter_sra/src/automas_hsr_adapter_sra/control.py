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

from app.models.task import UserItem

from automas_script_hsr.runtime.models import HSRPhase, HSRRunItem
from automas_script_hsr.runtime.tasks import HSRTaskModule
from automas_script_hsr.runtime.game import HSRAccountSwitcher, resolve_sra_start_mode
from automas_script_hsr.runtime.log_detect import detect_weekly_completion
from .runner import (
    build_sra_module_config,
    build_sra_tasklist_description,
    write_sra_temp_config,
)


def _on_sra_weekly_success(
    result: object,
    uid: str,
    user_name: str,
    module_name: str,
    module_key: str,
    queue_weekly_completion: Callable[[str, str, str], None],
    record_module_result: Callable[..., None],
) -> None:
    """SRA 差分宇宙 / 货币战争成功回调：先按日志判定再写完成态。"""

    completed, reason = detect_weekly_completion(result, "SRA", module_key)
    if not completed:
        record_module_result(
            user_id=uid,
            user_name=user_name,
            module_key=module_key,
            module_name=module_name,
            script="SRA",
            status="incomplete",
            reason=reason,
        )
        return
    queue_weekly_completion(uid, user_name, module_name)


class HSRSRAControl:
    """SRA 执行项创建与单任务控制。"""

    def __init__(
        self,
        *,
        script_config: Any,
        account_switcher: HSRAccountSwitcher,
        append_log: Callable[[str], None],
        phase_timeout_seconds: Callable[[HSRPhase], int],
        module_timeout_seconds: Callable[[str], int],
        queue_eow_completion: Callable[[str, str, bool, object, str], None],
        queue_weekly_completion: Callable[[str, str, str], None],
        record_module_result: Callable[..., None],
    ) -> None:
        self.script_config = script_config
        self._account_switcher = account_switcher
        self._append_log = append_log
        self._phase_timeout_seconds = phase_timeout_seconds
        self._module_timeout_seconds = module_timeout_seconds
        self._queue_eow_completion = queue_eow_completion
        self._queue_weekly_completion = queue_weekly_completion
        self._record_module_result = record_module_result

    async def run_sra_task(
        self,
        sra_exe_path: Path,
        task_class: str,
        temp_path: Path,
        user_name: str,
        module_name: str,
        timeout_seconds: int | None = None,
        module_key: str = "",
    ):
        """执行一条 SRA 单任务并同步调度台日志。"""

        return await self._account_switcher.run_sra_task(
            sra_exe_path,
            task_class,
            temp_path,
            user_name,
            module_name,
            timeout_seconds=timeout_seconds or 600,
            module_key=module_key,
        )

    def create_start_item(
        self,
        *,
        user_item: UserItem,
        user_cfg: Any,
        user_name: str,
        uid: str,
        phase: HSRPhase,
        sra_exe_path: Path,
        script_id: str,
        temp_files: list[Path],
    ) -> HSRRunItem:
        """创建 SRA 登录/切号队列项。"""

        start_mode = resolve_sra_start_mode(user_cfg, user_name)
        timeout_seconds = self._phase_timeout_seconds(phase)

        if start_mode == "switch":
            description = "SRA StartGameTask：通过 MAS 密文登录/切号"
        else:
            description = "SRA StartGameTask：使用当前已记住账号启动/进入游戏（不切号）"

        async def run_sra_start():
            return await self._account_switcher.run_start_game(
                user_config=user_cfg,
                user_name=user_name,
                user_id=uid,
                script_id=script_id,
                sra_exe_path=sra_exe_path,
                module_key=f"{phase}_StartGame",
                temp_files=temp_files,
                timeout_seconds=timeout_seconds,
            )

        return HSRRunItem(
            user_item=user_item,
            user_cfg=user_cfg,
            user_name=user_name,
            user_id=uid,
            phase=phase,
            module_key="StartGame",
            module_name="SRA 登录/切号",
            script="SRA",
            description=description,
            timeout_seconds=timeout_seconds,
            run=run_sra_start,
        )

    def create_module_item(
        self,
        *,
        user_item: UserItem,
        user_cfg: Any,
        user_name: str,
        uid: str,
        module: HSRTaskModule,
        phase: HSRPhase,
        sra_exe_path: Path,
        script_id: str,
        temp_files: list[Path],
        daily_eow_enabled: bool,
    ) -> HSRRunItem | None:
        """创建一个 SRA 模块队列项。"""

        timeout_seconds = self._module_timeout_seconds(module.key)
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
            description = f"SRA TrailblazePowerTask：{build_sra_tasklist_description(tasklist)}"
        else:
            cfg = build_sra_module_config(module, self.script_config, user_cfg)
            description = f"SRA {module.sra_task}：{module.description}"

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

        on_success = None
        if module.key == "Daily":
            on_success = (
                lambda result, uid=uid, user_name=user_name,
                daily_eow_enabled=daily_eow_enabled:
                self._queue_eow_completion(
                    uid,
                    user_name,
                    daily_eow_enabled,
                    result,
                    "SRA",
                )
            )
        elif module.key in ("DivergentUniverse", "CurrencyWars"):
            on_success = (
                lambda result, uid=uid, user_name=user_name,
                module_name=module.name, module_key=module.key:
                _on_sra_weekly_success(
                    result,
                    uid,
                    user_name,
                    module_name,
                    module_key,
                    self._queue_weekly_completion,
                    self._record_module_result,
                )
            )

        return HSRRunItem(
            user_item=user_item,
            user_cfg=user_cfg,
            user_name=user_name,
            user_id=uid,
            phase=phase,
            module_key=module.key,
            module_name=module.name,
            script="SRA",
            description=description,
            timeout_seconds=timeout_seconds,
            run=run_sra_module,
            on_success=on_success,
            extra={"daily_eow_enabled": daily_eow_enabled},
        )
