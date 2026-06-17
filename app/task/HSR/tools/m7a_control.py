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
from typing import Callable

import yaml

from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import UserItem
from app.utils import get_logger

from .run_model import (
    HSRPhase,
    HSRRetryableTaskError,
    HSRRunItem,
    external_result_failure_summary,
)
from ..task_mapping import HSRTaskModule
from . import m7a_config as m7a
from .account_switch import HSRAccountSwitcher
from .log_detect import detect_weekly_completion
from .m7a_runtime import M7ARunner
from .stage_runtime import (
    resolve_m7a_eow_stage,
    resolve_m7a_main_stage,
    resolve_m7a_ornament_stage,
)

logger = get_logger("HSR M7A 控制")


def _on_m7a_weekly_success(
    result: object,
    uid: str,
    user_name: str,
    module_name: str,
    module_key: str,
    queue_weekly_completion: Callable[[str, str, str], None],
    record_module_result: Callable[..., None],
) -> None:
    """M7A 差分宇宙 / 货币战争成功回调：先按日志判定再写完成态。"""

    completed, reason = detect_weekly_completion(result, "M7A", module_key)
    if not completed:
        record_module_result(
            user_id=uid,
            user_name=user_name,
            module_key=module_key,
            module_name=module_name,
            script="M7A",
            status="incomplete",
            reason=reason,
        )
        return
    queue_weekly_completion(uid, user_name, module_name)


class HSRM7AControl:
    """M7A 执行项创建与 config.yaml patch 控制。"""

    def __init__(
        self,
        *,
        script_config: HSRConfig,
        account_switcher: HSRAccountSwitcher,
        append_log: Callable[[str], None],
        module_timeout_seconds: Callable[[str], int],
        queue_eow_completion: Callable[[str, str, bool, object, str], None],
        queue_weekly_completion: Callable[[str, str, str], None],
        queue_abyss_completion: Callable[[str, str], None],
        record_module_result: Callable[..., None],
    ) -> None:
        self.script_config = script_config
        self._account_switcher = account_switcher
        self._append_log = append_log
        self._module_timeout_seconds = module_timeout_seconds
        self._queue_eow_completion = queue_eow_completion
        self._queue_weekly_completion = queue_weekly_completion
        self._queue_abyss_completion = queue_abyss_completion
        self._record_module_result = record_module_result

    async def run_m7a_command(
        self,
        m7a_runner: M7ARunner,
        user_name: str,
        module_name: str,
        command: str,
        timeout_seconds: int | None = None,
    ):
        """执行一条 M7A 命令并同步调度台日志。"""

        await self._account_switcher.wait_before_external_script("M7A", user_name)
        self._append_log(
            f"用户「{user_name}」开始执行 M7A {module_name}（{command}）"
        )
        result = await m7a_runner.run_task(command, timeout=timeout_seconds or 600)
        if getattr(result, "success", False):
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
        user_cfg: HSRUserConfig,
        user_name: str,
        module: HSRTaskModule,
        m7a_path: str,
        m7a_runner: M7ARunner,
        daily_eow_enabled: bool,
        timeout_seconds: int | None = None,
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
        last_result: object | None = None
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

        return last_result

    def create_patched_item(
        self,
        *,
        user_item: UserItem,
        user_cfg: HSRUserConfig,
        user_name: str,
        uid: str,
        module: HSRTaskModule,
        phase: HSRPhase,
        m7a_path: str,
        m7a_runner: M7ARunner,
        patch: dict,
        whitelist: frozenset[str],
        commands: list[str],
        description: str,
        on_success: Callable[[object], None] | None = None,
    ) -> HSRRunItem:
        """创建一个写入 M7A config.yaml patch 的队列项。"""

        timeout_seconds = self._module_timeout_seconds(module.key)
        m7a_config_path = Path(m7a_path) / "config.yaml"

        async def run_m7a_patched():
            if not m7a_config_path.exists():
                raise RuntimeError(f"M7A config.yaml 不存在: {m7a_config_path}")

            self.write_m7a_patch(
                m7a_config_path,
                patch,
                whitelist=whitelist,
            )
            last_result: object | None = None
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
            return last_result

        return HSRRunItem(
            user_item=user_item,
            user_cfg=user_cfg,
            user_name=user_name,
            user_id=uid,
            phase=phase,
            module_key=module.key,
            module_name=module.name,
            script="M7A",
            description=description,
            timeout_seconds=timeout_seconds,
            run=run_m7a_patched,
            on_success=on_success,
        )

    def create_monthly_item(
        self,
        *,
        user_item: UserItem,
        user_cfg: HSRUserConfig,
        user_name: str,
        uid: str,
        module: HSRTaskModule,
        m7a_path: str,
        m7a_runner: M7ARunner,
    ) -> HSRRunItem:
        """创建三深渊月常队列项。"""

        timeout_seconds = self._module_timeout_seconds(module.key)
        m7a_config_path = Path(m7a_path) / "config.yaml"
        abyss_runs: list[tuple[str, str, str]] = []
        abyss_patch: dict = {"cloud_game_enable": False}
        for abyss_type, command, label in m7a.ABYSS_RUN_SEQUENCE:
            try:
                single_patch = m7a.build_single_abyss_patch(user_cfg, abyss_type)
            except Exception as e:
                raise RuntimeError(
                    f"用户「{user_name}」三深渊「{label}」快照无效，"
                    f"三深渊未执行：{e}"
                ) from e
            abyss_patch.update(single_patch)
            abyss_runs.append((abyss_type, command, label))

        abyss_patch["forgottenhall_enable"] = True
        abyss_patch["purefiction_enable"] = True
        abyss_patch["apocalyptic_enable"] = True

        order_text = " → ".join(label for _, _, label in abyss_runs)
        description = f"M7A 三深渊：{order_text}（使用已导入快照）"

        async def run_m7a_monthly():
            if not m7a_config_path.exists():
                raise RuntimeError(f"M7A config.yaml 不存在: {m7a_config_path}")

            self.write_m7a_patch(
                m7a_config_path,
                abyss_patch,
                whitelist=m7a.M7A_FORGOTTEN_HALL_PATCH_WHITELIST,
            )
            last_result: object | None = None
            for _, command, label in abyss_runs:
                result = await self.run_m7a_command(
                    m7a_runner,
                    user_name,
                    label,
                    command,
                    timeout_seconds=timeout_seconds,
                )
                last_result = result
                if not result.success:
                    return result

            return last_result

        return HSRRunItem(
            user_item=user_item,
            user_cfg=user_cfg,
            user_name=user_name,
            user_id=uid,
            phase="monthly",
            module_key=module.key,
            module_name=module.name,
            script="M7A",
            description=description,
            timeout_seconds=timeout_seconds,
            run=run_m7a_monthly,
            on_success=lambda _result, uid=uid, user_name=user_name: self._queue_abyss_completion(
                uid,
                user_name,
            ),
        )

    def create_module_item(
        self,
        *,
        user_item: UserItem,
        user_cfg: HSRUserConfig,
        user_name: str,
        uid: str,
        module: HSRTaskModule,
        phase: HSRPhase,
        m7a_path: str,
        m7a_runner: M7ARunner,
        daily_eow_enabled: bool,
    ) -> HSRRunItem | None:
        """创建一个 M7A 模块队列项。"""

        timeout_seconds = self._module_timeout_seconds(module.key)

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

            return HSRRunItem(
                user_item=user_item,
                user_cfg=user_cfg,
                user_name=user_name,
                user_id=uid,
                phase=phase,
                module_key=module.key,
                module_name=module.name,
                script="M7A",
                description=(
                    f"M7A routine：主关卡={'已配置' if daily_main_stage else '未配置'}，"
                    f"历战余响本周尝试={'是' if daily_eow_enabled else '否'}"
                ),
                timeout_seconds=timeout_seconds,
                run=run_m7a_daily,
                on_success=(
                    lambda result, uid=uid, user_name=user_name,
                    daily_eow_enabled=daily_eow_enabled:
                    self._queue_eow_completion(
                        uid,
                        user_name,
                        daily_eow_enabled,
                        result,
                        "M7A",
                    )
                ),
            )

        if module.key == "ReceiveRewards":
            return self.create_patched_item(
                user_item=user_item,
                user_cfg=user_cfg,
                user_name=user_name,
                uid=uid,
                module=module,
                phase=phase,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
                patch=m7a.build_receive_rewards_patch(user_cfg),
                whitelist=m7a.M7A_RECEIVE_REWARDS_PATCH_WHITELIST,
                commands=list(module.m7a_tasks),
                description=f"M7A routine：{module.description}",
            )

        if module.key == "DivergentUniverse":
            return self.create_patched_item(
                user_item=user_item,
                user_cfg=user_cfg,
                user_name=user_name,
                uid=uid,
                module=module,
                phase=phase,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
                patch=m7a.build_divergent_universe_patch(
                    self.script_config,
                    user_cfg,
                    ornament_stage_name=resolve_m7a_ornament_stage(user_cfg),
                ),
                whitelist=m7a.M7A_COSMIC_STRIFE_PATCH_WHITELIST,
                commands=list(module.m7a_tasks),
                description=f"M7A divergent：{module.description}",
                on_success=(
                    lambda result, uid=uid, user_name=user_name,
                    module_name=module.name, module_key=module.key:
                    _on_m7a_weekly_success(
                        result,
                        uid,
                        user_name,
                        module_name,
                        module_key,
                        self._queue_weekly_completion,
                        self._record_module_result,
                    )
                ),
            )

        if module.key == "CurrencyWars":
            return self.create_patched_item(
                user_item=user_item,
                user_cfg=user_cfg,
                user_name=user_name,
                uid=uid,
                module=module,
                phase=phase,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
                patch=m7a.build_currency_wars_patch(
                    user_cfg,
                    ornament_stage_name=resolve_m7a_ornament_stage(user_cfg),
                ),
                whitelist=m7a.M7A_COSMIC_STRIFE_PATCH_WHITELIST,
                commands=list(module.m7a_tasks),
                description=f"M7A currencywars：{module.description}",
                on_success=(
                    lambda result, uid=uid, user_name=user_name,
                    module_name=module.name, module_key=module.key:
                    _on_m7a_weekly_success(
                        result,
                        uid,
                        user_name,
                        module_name,
                        module_key,
                        self._queue_weekly_completion,
                        self._record_module_result,
                    )
                ),
            )

        if module.key == "ForgottenHall":
            return self.create_monthly_item(
                user_item=user_item,
                user_cfg=user_cfg,
                user_name=user_name,
                uid=uid,
                module=module,
                m7a_path=m7a_path,
                m7a_runner=m7a_runner,
            )

        return None
