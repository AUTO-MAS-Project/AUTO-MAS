#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 端点共用的小件：结果载体、脚本解析、有效项目根、同组候选。"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.config import MaaFWConfig as RuntimeMaaFWConfig
from app.task.MaaFW.tools.embedded.embedded_project import (
    EmbeddedProjectError,
    GroupMember,
    embedded_project_dir,
    ensure_embedded_copy,
    resolve_maafw_project_root,
)
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.update_credentials import (
    resolve_update_proxy_url,
)
from app.utils import get_logger

# 这些日志原先由 API 层记录，模块名沿用「脚本管理 API」：搬家不改日志上的模块名。
logger = get_logger("脚本管理 API")


@dataclass(frozen=True, slots=True)
class MaaFWApiReply:
    """专项函数交回端点的结果，端点只做 ``XxxOut(**reply.out_fields())``。

    ``code != 200`` 即失败，一律 ``status="error"``；``message`` / ``data`` 为 None 时
    不传，让响应模型用自己的缺省值——与业务还写在端点里时直接构造响应的写法逐字段一致。
    """

    code: int = 200
    message: str | None = None
    data: Any = None

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> MaaFWApiReply:
        return cls(code=code, message=message, data=data)

    def out_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.code != 200:
            fields["code"] = self.code
            fields["status"] = "error"
        if self.message is not None:
            fields["message"] = self.message
        if self.data is not None:
            fields["data"] = self.data
        return fields


def maafw_script_config(script_id: str) -> RuntimeMaaFWConfig:
    """Resolve a MaaFW script and reject cross-type IDs before domain access."""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeMaaFWConfig):
        raise TypeError("脚本配置类型错误, 不是 MFW 类型")
    return script_config


def maafw_sibling_configs() -> list[tuple[str, Any]]:
    """来源目录已删、副本又没了时可以克隆的候选：所有 MFW 家族脚本（含自己，服务层会跳过）。"""

    return [
        (str(uid), config)
        for uid, config in Config.ScriptConfig.items()
        if isinstance(config, RuntimeMaaFWConfig)
    ]


def maafw_group_members(script_id: str) -> list[GroupMember]:
    """同组候选：除自己外的 MFW 家族脚本（事件循环线程上抄出来）。运行中的标 ``busy``。"""

    members: list[GroupMember] = []
    for uid, config in Config.ScriptConfig.items():
        if not isinstance(config, RuntimeMaaFWConfig) or str(uid) == script_id:
            continue
        members.append(
            GroupMember(
                script_id=str(uid),
                channel=str(config.get("Update", "Channel") or "stable"),
                busy=bool(getattr(config, "is_locked", False)),
                name=str(config.get("Info", "Name") or ""),
                proxy_url=resolve_update_proxy_url(config) or None,
            )
        )
    return members


async def maafw_effective_root(
    script_id: str | None, fallback_path: str
) -> tuple[Path | None, str]:
    """按脚本解析有效根；内嵌脚本副本缺失时先从来源重建。

    返回 ``(root, error)``：root 为 None 时 error 是给用户的一句话。
    """

    if script_id:
        try:
            script_config = maafw_script_config(script_id)
        except (KeyError, ValueError, TypeError) as exc:
            return None, f"MFW 脚本无效: {exc}"
        # 副本还没建（老脚本）或来源换了目录：先导入，报告写回配置。
        # 导入期间持有项目预约：正在更新 / 准备 / 运行的脚本不能被整棵换树。
        root_key = await try_reserve_project_path(embedded_project_dir(script_id))
        if root_key is None:
            copy_dir = resolve_maafw_project_root(script_id, script_config)
            if copy_dir.is_dir():
                return copy_dir.resolve(), ""
            return None, "该 MFW 脚本正在运行或更新，稍后再试"
        try:
            rebuilt = await asyncio.to_thread(
                ensure_embedded_copy,
                script_id,
                script_config,
                siblings=maafw_sibling_configs(),
            )
        except EmbeddedProjectError as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001 - 磁盘满、文件被占用之类的 OSError 也要给出文案
            logger.opt(exception=True).warning(
                f"MFW 项目导入失败（{script_id}）：{exc}"
            )
            return None, f"MFW 项目导入失败：{exc}"
        finally:
            await release_project_path(root_key)
        if rebuilt is not None:
            await Config.update_script(
                script_id,
                {
                    "Embedded": {
                        "Report": json.dumps(rebuilt["report"], ensure_ascii=False),
                        "SourceVersion": rebuilt["sourceVersion"],
                        "ImportedAt": rebuilt["importedAt"],
                    }
                },
            )
        return resolve_maafw_project_root(script_id, script_config).resolve(), ""
    value = str(fallback_path or "").strip()
    if not value:
        return None, "请先设置 MFW 项目路径"
    return Path(value).resolve(), ""
