#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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
#   Contact: DLmaster_361@163.com

"""MAA 账号配置来源与更新策略。"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from auto_mas_core.host.config import ConfigEntry
from auto_mas_core.host.task_proxy_helpers import (
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)

from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.cultivate import (
    append_owned_cultivate_targets,
    depot_cultivate_service,
    takeover_notice_patch_value,
)
from maa_adapter.cultivate.activity_inventory import migrate_activity_inventory_plans


def resolve_user_config_dir(
    script: ConfigEntry, user: ConfigEntry, *, data_path: Path
) -> Path:
    """按当前来源定位 base；打开目录不导入或改写配置。"""
    script_config = cast(MaaConfig, script)
    base = read_config_base(user, CONFIG_BASE_SHARED)
    if base == CONFIG_BASE_NATIVE:
        if script_config.Info.Path is None:
            raise ValueError("MAA 路径未配置，请先设置脚本路径")
        return script_config.Info.Path / "config"
    owner = "Default" if base == CONFIG_BASE_SHARED else str(user.uid)
    return data_path / str(script.uid) / owner / "ConfigFile"


async def prepare_user_update(
    script: ConfigEntry, user: ConfigEntry, *, data: dict[str, Any]
) -> Callable[[], None] | None:
    """由 MAA 用户配置自身准备保存补丁，不作为宿主或插件系统的回调接口。"""
    user_config = cast(MaaUserConfig, user)
    guard: Callable[[], None] | None = None
    # 关闭养成接管后，清理上一轮运行留下的提示；判定与运行注入同源。
    if isinstance(data.get("Task"), dict):
        task_patch = data["Task"]
        if task_patch == {"CultivateAllOwned": False}:
            return
        # 仅开启托管时立即补入目标；关闭只改开关，不改目标或其他执行设置。
        if (
            task_patch.get("CultivateAllOwned") is True
            and not user_config.Task.CultivateAllOwned
        ):
            from auto_mas_core.host.core import Config

            from maa_adapter.cultivate.editor import get_cultivate_skland_progression

            binding = (
                user_config.Task.CultivateSklandAccount,
                user_config.Task.CultivateSklandUid,
            )
            # 不在同一个补丁内换绑：当前已保存角色才是本次注入的账号。
            if any(
                task_patch.get(key, getattr(user_config.Task, key))
                != getattr(user_config.Task, key)
                for key in ("CultivateSklandAccount", "CultivateSklandUid")
            ):
                raise ValueError("请先保存森空岛绑定，再开启全部干员培养托管")
            skland = await get_cultivate_skland_progression(
                str(script.uid), str(user.uid), force=True
            )
            if not skland or not skland[0]:
                raise ValueError("无法同步已有干员，请绑定森空岛并确认网络可用后重试")
            catalog = await depot_cultivate_service.operator_catalog(
                config_path=Config.config_path, proxy=Config.proxy
            )

            def finish_owned_update() -> None:
                """提交前复核森空岛绑定未变化，再按最新账号目标合并已拥有干员的养成目标，避免覆盖等待期间的修改。"""
                if binding != (
                    user_config.Task.CultivateSklandAccount,
                    user_config.Task.CultivateSklandUid,
                ):
                    raise ValueError("森空岛绑定已变更，请重新开启全部干员培养托管")
                # 写入方持有短保护范围后再读目标，保留同步和等待期间的手工保存。
                raw_targets = json.loads(
                    task_patch.get(
                        "CultivateTargets", user_config.Task.CultivateTargets
                    )
                )
                task_patch["CultivateTargets"] = json.dumps(
                    append_owned_cultivate_targets(
                        raw_targets, catalog=catalog, progressions=skland[0]
                    ),
                    ensure_ascii=False,
                )

            guard = finish_owned_update
        notice = takeover_notice_patch_value(
            task_patch.get("IfCultivate", user_config.Task.IfCultivate),
            task_patch.get("CultivateTargets", user_config.Task.CultivateTargets),
        )
        if notice is not None:
            data.setdefault("Data", {})["CultivateNotice"] = notice
        if "EventDepotMaintainPlans" in task_patch:
            rows = json.loads(task_patch["EventDepotMaintainPlans"])
            if any(
                isinstance(row, dict)
                and (row.get("LegacyActivityFirst") or row.get("LegacyIndex"))
                for row in rows
            ):
                from maa_adapter import stages as stage_service

                server = data.get("Info", {}).get("Server", user_config.Info.Server)
                stage_info = await stage_service.get_stage_info("Info", server=server)
                stages = (
                    stage_info.get("Activity", [])
                    if stage_info.get("ActivityStatus") == "ready"
                    else []
                )
                previous_guard = guard

                def finish_activity_migration() -> None:
                    """先执行已有提交保护，再按提交时实际服务器迁移活动计划，避免用旧服务器关卡覆盖新选择。"""
                    if previous_guard is not None:
                        previous_guard()
                    # 区服在等待期间变化时，不用旧区服数据永久改写序号。
                    current_server = data.get("Info", {}).get(
                        "Server", user_config.Info.Server
                    )
                    task_patch["EventDepotMaintainPlans"] = (
                        migrate_activity_inventory_plans(
                            task_patch["EventDepotMaintainPlans"],
                            stages if current_server == server else [],
                        )
                    )

                guard = finish_activity_migration
    return guard
