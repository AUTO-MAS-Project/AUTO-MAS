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

import yaml

from app.utils import get_logger

from automas_script_hsr.contracts import HSRNativeRunPlan
from automas_script_hsr.runtime.models import (
    HSRRetryableTaskError,
    external_result_failure_summary,
)
from automas_script_hsr.runtime.tasks import HSRTaskModule
from . import config as m7a
from automas_script_hsr.runtime.game import HSRAccountSwitcher
from .runner import M7ACommandResult, M7ARunner
from automas_script_hsr.runtime.stage_runtime import (
    resolve_m7a_eow_stage,
    resolve_m7a_main_stage,
    resolve_m7a_ornament_stage,
)

logger = get_logger("HSR M7A 控制")


class HSRM7AControl:
    """M7A 执行项创建与 config.yaml patch 控制。"""

    def __init__(
        self,
        *,
        script_config: Any,
        account_switcher: HSRAccountSwitcher,
        append_log: Callable[[str], None],
    ) -> None:
        self.script_config = script_config
        self._account_switcher = account_switcher
        self._append_log = append_log

    async def run_m7a_command(
        self,
        m7a_runner: M7ARunner,
        user_name: str,
        module_name: str,
        command: str,
        timeout_seconds: int | None = None,
    ) -> M7ACommandResult:
        """执行一条 M7A 命令并同步调度台日志。"""

        await self._account_switcher.wait_before_external_script("M7A", user_name)
        self._append_log(
            f"用户「{user_name}」开始执行 M7A {module_name}（{command}）"
        )
        timeout = 600 if timeout_seconds is None else timeout_seconds
        result = await m7a_runner.run_task(command, timeout=timeout)
        if result.success:
            self._append_log(
                f"用户「{user_name}」M7A {module_name}（{command}）执行完成"
            )
        else:
            self._append_log(
                f"用户「{user_name}」M7A {module_name}（{command}）执行失败"
            )
        return result

    @staticmethod
    def write_m7a_patch(
        config_path: Path,
        patch: dict,
        *,
        whitelist: frozenset[str] | None = None,
        deep_merge_keys: frozenset[str] | None = None,
    ) -> None:
        """把 MAS 模板 patch 直接写入 M7A config.yaml。"""

        effective_patch = m7a.with_disabled_notifications(patch)
        effective_whitelist = (
            whitelist if whitelist is not None else m7a.M7A_DAILY_PATCH_WHITELIST
        ) | m7a.M7A_NOTIFICATION_PATCH_WHITELIST
        current_config = yaml.safe_load(
            config_path.read_text(encoding="utf-8-sig")
        ) or {}
        if not isinstance(current_config, dict):
            raise ValueError(f"M7A config.yaml 顶层必须是对象: {config_path}")
        patched_config = m7a.merge_whitelist(
            current_config,
            effective_patch,
            whitelist=effective_whitelist,
            deep_merge_keys=deep_merge_keys,
        )
        temp_path = config_path.with_name(f"{config_path.name}.tmp")
        temp_path.write_text(
            yaml.safe_dump(
                patched_config,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=4096,
            ),
            encoding="utf-8",
            newline="\n",
        )
        temp_path.replace(config_path)
        logger.info(
            f"M7A config.yaml 已写入 MAS 模板字段：{sorted(effective_patch.keys())}"
        )

    async def execute_m7a_daily(
        self,
        *,
        user_cfg: Any,
        user_name: str,
        module: HSRTaskModule,
        timeout_seconds: int,
        m7a_path: str,
        m7a_runner: M7ARunner,
        daily_eow_enabled: bool,
    ):
        """执行 M7A Daily 模块。"""

        m7a_config_path = Path(m7a_path) / "config.yaml"
        main_stage = resolve_m7a_main_stage(user_cfg)

        daily_patch = m7a.build_m7a_daily_patch(
            user_cfg,
            daily_eow_enabled=daily_eow_enabled,
            main_stage=main_stage,
            eow_name=resolve_m7a_eow_stage(user_cfg),
        )
        self.write_m7a_patch(m7a_config_path, daily_patch)
        if not module.m7a_tasks:
            raise RuntimeError(f"M7A {module.key} 未声明上游命令")
        last_result: M7ACommandResult | None = None
        for command in module.m7a_tasks:
            result = await self.run_m7a_command(
                m7a_runner,
                user_name,
                module.name,
                command,
                timeout_seconds=timeout_seconds,
            )
            last_result = result
            if not result.success:
                raise HSRRetryableTaskError(
                    f"用户「{user_name}」模块「{module.name}」"
                    f" M7A 命令「{command}」执行失败："
                    f"{external_result_failure_summary(result)}",
                    result=result,
                )

        if last_result is None:
            raise RuntimeError(f"M7A {module.key} 未执行任何上游命令")
        return last_result

    def create_patched_item(
        self,
        *,
        user_name: str,
        module: HSRTaskModule,
        m7a_path: str,
        m7a_runner: M7ARunner,
        patch: dict,
        whitelist: frozenset[str],
        commands: list[str],
    ) -> HSRNativeRunPlan:
        """创建一个写入 M7A config.yaml patch 的队列项。"""

        m7a_config_path = Path(m7a_path) / "config.yaml"

        async def run_m7a_patched():
            if not m7a_config_path.exists():
                raise RuntimeError(f"M7A config.yaml 不存在: {m7a_config_path}")
            if not commands:
                raise RuntimeError(f"M7A {module.key} 未声明上游命令")

            self.write_m7a_patch(
                m7a_config_path,
                patch,
                whitelist=whitelist,
            )
            last_result: M7ACommandResult | None = None
            for command in commands:
                result = await self.run_m7a_command(
                    m7a_runner,
                    user_name,
                    module.name,
                    command,
                    timeout_seconds=timeout_seconds,
                )
                last_result = result
                if not result.success:
                    return result
            if last_result is None:
                raise RuntimeError(f"M7A {module.key} 未执行任何上游命令")
            return last_result

        return HSRNativeRunPlan(run=run_m7a_patched)

    def create_module_item(
        self,
        *,
        user_cfg: Any,
        user_name: str,
        module: HSRTaskModule,
        timeout_seconds: int,
        m7a_path: str,
        m7a_runner: M7ARunner,
        daily_eow_enabled: bool,
    ) -> HSRNativeRunPlan | None:
        """创建一个 M7A 模块队列项。"""

        if module.key == "Daily":
            daily_main_stage = resolve_m7a_main_stage(user_cfg)
            if daily_main_stage is None and not daily_eow_enabled:
                self._append_log(f"用户「{user_name}」体力模块无可执行副本，跳过")
                return None

            async def run_m7a_daily():
                return await self.execute_m7a_daily(
                    user_cfg=user_cfg,
                    user_name=user_name,
                    module=module,
                    m7a_path=m7a_path,
                    m7a_runner=m7a_runner,
                    daily_eow_enabled=daily_eow_enabled,
                    timeout_seconds=timeout_seconds,
                )

            return HSRNativeRunPlan(run=run_m7a_daily)

        if module.key == "ReceiveRewards":
            return self.create_patched_item(
                user_name=user_name,
                module=module,
                timeout_seconds=timeout_seconds,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
                patch=m7a.build_receive_rewards_patch(user_cfg),
                whitelist=m7a.M7A_RECEIVE_REWARDS_PATCH_WHITELIST,
                commands=list(module.m7a_tasks),
            )

        if module.key == "DivergentUniverse":
            return self.create_patched_item(
                user_name=user_name,
                module=module,
                timeout_seconds=timeout_seconds,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
                patch=m7a.build_divergent_universe_patch(
                    self.script_config,
                    user_cfg,
                    ornament_stage_name=resolve_m7a_ornament_stage(user_cfg),
                ),
                whitelist=m7a.M7A_COSMIC_STRIFE_PATCH_WHITELIST,
                commands=list(module.m7a_tasks),
            )

        if module.key == "CurrencyWars":
            return self.create_patched_item(
                user_name=user_name,
                module=module,
                timeout_seconds=timeout_seconds,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
                patch=m7a.build_currency_wars_patch(
                    user_cfg,
                    ornament_stage_name=resolve_m7a_ornament_stage(user_cfg),
                ),
                whitelist=m7a.M7A_COSMIC_STRIFE_PATCH_WHITELIST,
                commands=list(module.m7a_tasks),
            )

        return None
