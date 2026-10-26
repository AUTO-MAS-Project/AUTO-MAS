#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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
"""BetterGI 编辑业务入口：来源选择、Plan 同步与原生副本读写。"""

import uuid
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.config import BetterGIConfig as RuntimeBetterGIConfig
from app.models.config import BetterGIUserConfig


def _bettergi_script_config(script_id: str) -> RuntimeBetterGIConfig:
    """Resolve a BetterGI script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeBetterGIConfig):
        raise TypeError("脚本配置类型错误, 不是 BetterGI 类型")
    return script_config


def _bettergi_user_id(script_config: RuntimeBetterGIConfig, user_id: str) -> None:
    """Validate that a BetterGI user exists before domain access."""

    try:
        script_config.UserData[uuid.UUID(user_id)]
    except KeyError:
        raise ValueError("用户不存在或无权访问该配置")


def _bettergi_root(script_config: RuntimeBetterGIConfig) -> Path:
    """目录选项查询需要已配置的安装目录。"""
    root = script_config.Info.RootPath
    if root is None:
        raise ValueError("请先设置 BetterGI 脚本安装目录")
    return root


def _bettergi_user_config(
    script_config: RuntimeBetterGIConfig, user_id: str
) -> BetterGIUserConfig:
    """Resolve a BetterGI user config and reject unknown IDs before domain access."""

    user_config = script_config.UserData[uuid.UUID(user_id)]
    return user_config


def _read_combat_from_plan(
    script_config: RuntimeBetterGIConfig,
    user_id: str,
    group: str,
    source: str,
    data: dict,
) -> dict:
    """把战斗组 Plan 里的设置反查回右栏键，合并进读取结果（回显）。"""
    from app.task.BetterGI.tools import one_dragon_plan

    target_group = _combat_target_group(source, group)
    mapping = one_dragon_plan.RIGHTBAR_TO_PLAN.get(
        one_dragon_plan.resolve_base_name(target_group)
    )
    if not mapping:
        return data
    user_config = _bettergi_user_config(script_config, user_id)
    plan_json = user_config.OneDragon.Plan or ""
    data.update(
        one_dragon_plan.extract_rightbar_from_plan(plan_json, target_group) or {}
    )
    # 还原 weekly 嵌套结构为平铺右栏键（供前端周表回显）
    steps = one_dragon_plan.parse_one_dragon_plan(plan_json) if plan_json else []
    target = next((s for s in steps if s.get("name") == target_group), None)
    if target:
        data.update(
            one_dragon_plan.flatten_weekly_struct(
                target_group, target.get("settings") or {}
            )
        )
    # 「开启每日地脉花」未配置（Plan 无该键，如新用户）时默认开启：与种子模板的
    # 「每日耗尽模式」标准状态一致；用户选过每周模式则 Plan 已有显式 false，不受影响。
    if target_group == "自动地脉花":
        data.setdefault("leyLineDailyEnabled", True)
    return data


def _route_combat_to_plan(
    script_config: RuntimeBetterGIConfig,
    user_id: str,
    group: str,
    settings: dict,
    source: str,
) -> tuple[dict, str | None]:
    """战斗4项右栏设置：可映射字段翻译后写入 OneDragon.Plan（执行层参数源）。

    原生侧**保留全量字段**（双写）：执行层只接管「Plan 中有该组步骤且队列中启用」
    的战斗组，其余战斗组仍走原生一条龙 / 全局 config.json，必须能读到最新值；
    已被接管的组会从一条龙副本剔除，多写的原生值不会被消费。

    返回 ``(原生字段, 新 Plan JSON 或 None)``。非战斗组 / 无可映射键时返回
    ``(settings, None)``，调用方按原逻辑写原生存储即可。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    target_group = _combat_target_group(source, group)
    mapping = one_dragon_plan.RIGHTBAR_TO_PLAN.get(
        one_dragon_plan.resolve_base_name(target_group)
    )
    if not mapping or not settings:
        return settings, None
    plan_settings = {k: v for k, v in settings.items() if k in mapping}
    extra = one_dragon_plan.extract_weekly_struct(target_group, settings)
    if not plan_settings and not extra:
        return settings, None
    user_config = _bettergi_user_config(script_config, user_id)
    plan_json = user_config.OneDragon.Plan or ""
    new_plan = one_dragon_plan.merge_rightbar_into_plan(
        plan_json, target_group, plan_settings, extra=extra or None
    )
    return settings, new_plan


def _combat_target_group(source: str, group: str) -> str:
    """确定右栏设置归属的战斗组（支持同一战斗组的多个独立实例）。

    优先采用前端传入的**实例组名**（形如 ``自动幽境危战-3``、``自动秘境-3``）：
    同一战斗组可配多个实例，各自独立保存/回显设置。未传组名（或组名不是内置
    战斗组）时按 source 固定映射（globalStygian→自动幽境危战、globalDomain→
    自动秘境），兼容不带 groupName 的调用方与旧数据。
    """
    from app.task.BetterGI.tools import one_dragon_plan

    if group and one_dragon_plan.resolve_base_name(group):
        return group
    return {"globalStygian": "自动幽境危战", "globalDomain": "自动秘境"}.get(
        source, group
    )


def list_strategies(script_id: str) -> list[str]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    names = one_dragon.list_auto_boss_strategies(root)
    return names


def list_custom_groups(
    script_id: str, *, user_id: str, config_name: str, use_mas_config: bool
) -> list[dict]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    if use_mas_config:
        if not user_id:
            raise ValueError("用户独立配置下必须提供 user_id")
        _bettergi_user_id(script_config, user_id)
        items = one_dragon.list_user_custom_groups(
            root, script_id, user_id, one_dragon.launch_slot_name()
        )
    else:
        items = one_dragon.list_custom_groups(
            root, one_dragon.resolve_config_name(config_name)
        )
    return items


def list_one_dragon_configs(script_id: str) -> list[str]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    names = one_dragon.list_one_dragon_configs(root)
    return names


def list_js_scripts(script_id: str) -> list[tuple[str, str]]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    items = one_dragon.list_js_scripts(root)
    return items


def list_key_mouse_scripts(script_id: str) -> list[str]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    names = one_dragon.list_key_mouse_scripts(root)
    return names


def list_script_groups(script_id: str, user_id: str = "") -> list[str]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    names = one_dragon.list_script_groups(root)
    if user_id:
        _bettergi_user_id(script_config, user_id)
        copy_names = one_dragon.list_user_script_group_names(script_id, user_id)
        merged: list[str] = []
        for name in (*copy_names, *names):
            if name and name not in merged:
                merged.append(name)
        names = merged
    return names


def read_script_group(script_id: str, user_id: str, *, name: str) -> dict | None:
    script_config = _bettergi_script_config(script_id)
    _bettergi_user_id(script_config, user_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    data = one_dragon.read_user_script_group(root, script_id, user_id, name)
    return data


def read_script_settings_ui(script_id: str, folder: str) -> list[dict[str, Any]]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    ui = one_dragon.list_script_settings_ui(root, folder)
    return ui


def read_script_readme(script_id: str, folder: str) -> str:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    text = one_dragon.read_script_readme(root, folder)
    return text


def resolve_script_dirs(script_id: str) -> dict[str, str]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    dirs = one_dragon.resolve_script_dirs(root)
    return dirs


def read_auto_pathing_tree(script_id: str) -> tuple[str, list[dict]]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    root_dir, tree = one_dragon.build_auto_pathing_tree(root)
    return (root_dir, tree)


def read_one_dragon_settings(
    script_id: str, user_id: str, *, config_name: str, group_name: str
) -> dict:
    script_config = _bettergi_script_config(script_id)
    _bettergi_user_id(script_config, user_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    data = one_dragon.read_user_one_dragon_settings(
        root, script_id, user_id, config_name
    )
    # 战斗4项：用 Plan 中的执行层参数回显右栏（Plan 优先于原生副本）。
    # 第三参必须传 group_name（内置组名），传 config_name 会导致 Plan 回显失效。
    data = _read_combat_from_plan(script_config, user_id, group_name, "dragon", data)
    return data


async def save_one_dragon_settings(
    script_id: str, user_id: str, *, config_name: str, group_name: str, settings: dict
) -> None:
    """先提交 Plan，再写一条龙副本；外部文件不参与配置事务。"""

    script_config = _bettergi_script_config(script_id)
    _bettergi_user_id(script_config, user_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    # 战斗4项：可映射字段同步到 Plan，全量设置仍写入原生副本。
    # 注意第三参是「右栏当前编辑的内置组名」（前端 group_name），绝不能传 config_name——
    # RIGHTBAR_TO_PLAN 按组名（自动秘境/自动地脉花…）查映射，传配置名会导致
    # Plan 路由静默失效，周表/每日行等白名单外键（StrategyName/leyLineDailyEnabled/
    # team/country/LeyLineDefault* 等）全部丢弃。
    native_leftover, new_plan = _route_combat_to_plan(
        script_config, user_id, group_name, settings, "dragon"
    )
    if new_plan is not None:
        user_config = _bettergi_user_config(script_config, user_id)
        await user_config.update(
            type(user_config).model_validate({"OneDragon": {"Plan": new_plan}}),
            check_visibility=False,
        )
    if native_leftover:
        one_dragon.write_user_one_dragon_settings(
            root, script_id, user_id, config_name, native_leftover
        )


async def set_plan_step_enabled(
    script_id: str, user_id: str, *, name: str, enabled: bool
) -> None:
    """按实例名创建或修改步骤，再提交用户 Plan。"""

    from app.task.BetterGI.tools import one_dragon_plan

    script_config = _bettergi_script_config(script_id)
    _bettergi_user_id(script_config, user_id)
    user_config = _bettergi_user_config(script_config, user_id)
    plan = one_dragon_plan.parse_one_dragon_plan(user_config.OneDragon.Plan or "")
    target = next((s for s in plan if s.get("name") == name), None)
    if target is None:
        plan.append(
            {
                "uid": uuid.uuid4().hex[:12],
                "kind": "builtin",
                "name": name,
                "enabled": enabled,
                "settings": {},
            }
        )
    else:
        target["enabled"] = enabled
    await user_config.update(
        type(user_config).model_validate(
            {"OneDragon": {"Plan": one_dragon_plan.plan_to_json(plan)}}
        ),
        check_visibility=False,
    )


def read_global_domain_settings(
    script_id: str, user_id: str, *, group_name: str
) -> dict:
    script_config = _bettergi_script_config(script_id)
    if user_id:
        _bettergi_user_id(script_config, user_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    data = (
        one_dragon.read_user_global_domain_settings(root, script_id, user_id)
        if user_id
        else one_dragon.read_global_domain_settings(root)
    )
    # 战斗4项（自动秘境）的可映射字段（领奖树脂/分解圣遗物/奖励识别等）在 Plan 中回显
    if user_id:
        data = _read_combat_from_plan(
            script_config, user_id, group_name, "globalDomain", data
        )
    return data


async def save_global_domain_settings(
    script_id: str, user_id: str | None, *, group_name: str, settings: dict
) -> None:
    """保存秘境设置，保留用户副本与原生来源的分流顺序。"""

    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    if user_id:
        _bettergi_user_id(script_config, user_id)
        # 战斗4项（自动秘境）可映射字段同步到 Plan，全量设置仍写入副本
        native_leftover, new_plan = _route_combat_to_plan(
            script_config, user_id, group_name, settings, "globalDomain"
        )
        if new_plan is not None:
            user_config = _bettergi_user_config(script_config, user_id)
            await user_config.update(
                type(user_config).model_validate({"OneDragon": {"Plan": new_plan}}),
                check_visibility=False,
            )
        if native_leftover:
            one_dragon.write_user_global_domain_settings(
                script_id, user_id, native_leftover
            )
    else:
        one_dragon.write_global_domain_settings(root, settings)


def read_global_stygian_settings(
    script_id: str, user_id: str, *, group_name: str
) -> dict:
    script_config = _bettergi_script_config(script_id)
    if user_id:
        _bettergi_user_id(script_config, user_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    data = (
        one_dragon.read_user_global_stygian_settings(root, script_id, user_id)
        if user_id
        else one_dragon.read_global_stygian_settings(root)
    )
    # 战斗4项（自动幽境危战）全部字段在 Plan 中回显
    if user_id:
        data = _read_combat_from_plan(
            script_config, user_id, group_name, "globalStygian", data
        )
    return data


async def save_global_stygian_settings(
    script_id: str, user_id: str | None, *, group_name: str, settings: dict
) -> None:
    """保存幽境设置，保留用户副本与原生来源的分流顺序。"""

    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    if user_id:
        _bettergi_user_id(script_config, user_id)
        # 战斗4项（自动幽境危战）设置同步到 Plan，全量设置仍写入副本
        native_leftover, new_plan = _route_combat_to_plan(
            script_config, user_id, group_name, settings, "globalStygian"
        )
        if new_plan is not None:
            user_config = _bettergi_user_config(script_config, user_id)
            await user_config.update(
                type(user_config).model_validate({"OneDragon": {"Plan": new_plan}}),
                check_visibility=False,
            )
        if native_leftover:
            one_dragon.write_user_global_stygian_settings(
                script_id, user_id, native_leftover
            )
    else:
        one_dragon.write_global_stygian_settings(root, settings)


def read_domain_catalog(script_id: str) -> tuple[str, list[dict[str, Any]]]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    source, items = one_dragon.scan_domain_catalog(root)
    return (source, items)


def save_script_group(
    script_id: str, user_id: str, *, name: str, data: dict
) -> tuple[Path | None, int]:
    script_config = _bettergi_script_config(script_id)
    _bettergi_user_id(script_config, user_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import one_dragon

    projects = (data or {}).get("projects")
    if not isinstance(projects, list):
        raise ValueError("projects 必须为数组（按执行顺序的项目列表）")
    out = one_dragon.write_user_script_group(root, script_id, user_id, name, data)
    return (out, len(projects))


def read_game_info(script_id: str, detect_path: str) -> dict[str, str | None]:
    script_config = _bettergi_script_config(script_id)
    root = _bettergi_root(script_config)
    from app.task.BetterGI.tools import game_info

    data = game_info.read_game_info(root, detect_path)
    return data


def prepare_user_update(script_id: str, user_id: str, data: dict[str, Any]) -> None:
    # 队列是唯一真相源：落盘 OneDragon.Queue 时，清理 Plan 中不再被引用的战斗实例
    # （前端删除队列行只改 Queue，Plan 对应实例会残留成孤儿）。仅当 patch 含 Queue 时触发，
    # 避免其它字段保存误伤；被关闭（enabled=false）但仍在队列的行其实例保留。
    od = data.get("OneDragon") if isinstance(data, dict) else None
    if isinstance(od, dict) and "Queue" in od:
        try:
            from app.task.BetterGI.tools import one_dragon_plan

            script_cfg = Config.ScriptConfig[uuid.UUID(script_id)]
            uc = script_cfg.UserData[uuid.UUID(user_id)]
            plan = uc.OneDragon.Plan or ""
            groups = uc.OneDragon.Groups or []
            new_plan = one_dragon_plan.prune_plan_to_queue(plan, od["Queue"], groups)
            if new_plan != plan:
                od["Plan"] = new_plan
            # 录制（KeyMouse）加入队列：提前生成 per-user 配置组副本（含单 KeyMouse 项目），
            # 使右栏项目编辑能读到录制内容、运行时可被物化，避免「一条龙里没有内容」。
            try:
                from app.task.BetterGI.tools import one_dragon as _od

                _root = Path(str(script_cfg.Info.RootPath or "")).expanduser()
                _queue = _od.parse_one_dragon_queue(od["Queue"])
                _od.ensure_keymouse_groups(
                    _root,
                    script_id,
                    user_id,
                    [e.get("name") for e in _queue if isinstance(e, dict)],
                )
            except Exception:  # pragma: no cover - 兜底：生成失败不应阻断保存
                import logging

                logging.getLogger(__name__).warning(
                    "为队列中的录制生成配置组副本失败（已忽略）", exc_info=True
                )
        except Exception as e:  # pragma: no cover - 兜底：同步失败不应阻断保存
            import logging

            logging.getLogger(__name__).warning(
                "队列变更同步清理 Plan 孤儿实例失败（已忽略）: %s", e
            )
