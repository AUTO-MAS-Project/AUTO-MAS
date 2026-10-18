#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""BetterGI 配置来源（Info.Base）到「一条龙编排归属」的解析。

来源三态 ``shared`` / ``independent`` / ``native`` 由 ``app.utils.constants`` 定义、
模型层加载时归一（旧字面量「脚本」「用户」「直控」）。「脚本」来源（shared）的用户
共读共写脚本级那份编排与 per-user 副本，其余来源各归各，native 不读 MAS 副本。

归属判定属专项知识，放在本模块而不是 API 层：接口只负责解析请求、组织返回。
"""

from __future__ import annotations

from app.task.proxy_helpers import CONFIG_BASE_SHARED, read_config_base
from app.utils.constants import normalize_base_source

__all__ = [
    "apply_script_level_source",
    "config_base",
    "dict_base",
    "owner_config",
    "owner_id",
    "user_config",
    "uses_script_source",
]


def user_config(script_config: object, user_id: str):
    """按用户 ID 取该用户的配置对象（用户是否存在由调用方先行校验）。"""

    import uuid

    return script_config.UserData[uuid.UUID(user_id)]  # type: ignore[attr-defined]


def config_base(config: object) -> str:
    """配置对象（ConfigBase）的来源三态。"""

    return read_config_base(config)


def dict_base(data: dict) -> str:
    """序列化后配置字典（``Config.get_user`` 的返回）的来源三态。

    ``read_config_base`` 走的是 ConfigBase 的 ``get(group, key)``；对 dict 而言第二个
    参数只是默认值，返回的是整个 Info 段，判定必然落空，所以这里直接取 ``Info.Base``
    再走同一套归一。
    """

    info = data.get("Info")
    if not isinstance(info, dict):
        return ""
    return normalize_base_source(info.get("Base"))


def uses_script_source(script_config: object, user_id: str) -> bool:
    """该用户的编排是否落在脚本级共享段。"""

    return config_base(user_config(script_config, user_id)) == CONFIG_BASE_SHARED


def owner_id(script_config: object, user_id: str) -> str:
    """per-user 副本的 owner 维度（shared → 脚本级保留 id）。"""

    from . import one_dragon

    return one_dragon.owner_user_id(
        user_id, config_base(user_config(script_config, user_id))
    )


def owner_config(script_config: object, user_id: str):
    """一条龙编排的读写对象：shared → 脚本配置，其余 → 该用户自己的配置。

    Info / Task / Switch 段（来源、名称、账号等）始终属于用户自己，不走本入口。
    """

    return (
        script_config
        if uses_script_source(script_config, user_id)
        else user_config(script_config, user_id)
    )


async def apply_script_level_source(script_config: object, data: dict) -> dict:
    """把 shared 用户的 OneDragon 段整段换成脚本级共享段的内容（只改该段）。

    ``data`` 是序列化后的字典（``Config.get_user`` 返回）；读取失败时保持用户级值，
    不阻断读取。
    """

    if not hasattr(script_config, "toDict") or not isinstance(data, dict):
        return data
    try:
        shared = (await script_config.toDict()).get("OneDragon")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 读取失败退回用户级值
        return data
    if not isinstance(shared, dict):
        return data
    for cfg in data.values():
        if not isinstance(cfg, dict):
            continue
        if dict_base(cfg) != CONFIG_BASE_SHARED:
            continue
        one_dragon_cfg = cfg.get("OneDragon")
        if isinstance(one_dragon_cfg, dict):
            one_dragon_cfg.update(shared)
        else:
            cfg["OneDragon"] = dict(shared)
    return data
