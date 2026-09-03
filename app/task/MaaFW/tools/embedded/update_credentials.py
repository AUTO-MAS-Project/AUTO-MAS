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

"""MaaFW 项目更新的凭据与时机合并。

核心更新包（``tools/core/automas_maafw_project_update``）不读 Config；脚本级
配置留空时用全局配置兜底这件事只在这里做一次。API 侧复制的是同一表达式，
所以逻辑必须保持极简：

- ``cdk``：脚本级 ``Update.MirrorChyanCDK`` 明文，空则全局 ``Update.MirrorChyanCDK``
- ``channel``：脚本级 ``Update.Channel``，空则全局 ``Update.Channel``，再空则 ``stable``

任何日志都不得出现 CDK 明文，打码用 :func:`describe_cdk`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AutoUpdateMode = Literal["Off", "BeforeRun", "AfterRun"]

AUTO_UPDATE_MODES: tuple[AutoUpdateMode, ...] = ("Off", "BeforeRun", "AfterRun")
DEFAULT_AUTO_UPDATE_MODE: AutoUpdateMode = "BeforeRun"
DEFAULT_UPDATE_CHANNEL = "stable"


@dataclass(frozen=True)
class MaaFWUpdateCredentials:
    """合并全局兜底后的更新凭据。"""

    cdk: str
    channel: str
    # 供日志说明 CDK 来自哪一层；不携带明文
    cdk_origin: Literal["script", "global", "none"]


def _read_text(config: Any, group: str, name: str) -> str:
    """读一个字符串配置项；配置项不存在或读取失败一律当空串。"""

    try:
        return str(config.get(group, name) or "").strip()
    except Exception:  # noqa: BLE001 - 旧配置对象缺项不该挡住运行
        return ""


def resolve_update_credentials(
    script_config: Any, global_config: Any
) -> MaaFWUpdateCredentials:
    """脚本级优先、全局兜底，得到传给核心更新包的明文 CDK 与渠道。"""

    script_cdk = _read_text(script_config, "Update", "MirrorChyanCDK")
    if script_cdk:
        cdk, origin = script_cdk, "script"
    else:
        global_cdk = _read_text(global_config, "Update", "MirrorChyanCDK")
        cdk, origin = (global_cdk, "global") if global_cdk else ("", "none")

    channel = (
        _read_text(script_config, "Update", "Channel")
        or _read_text(global_config, "Update", "Channel")
        or DEFAULT_UPDATE_CHANNEL
    )
    return MaaFWUpdateCredentials(cdk=cdk, channel=channel, cdk_origin=origin)


def resolve_auto_update_mode(script_config: Any) -> AutoUpdateMode:
    """读脚本的更新时机；非法值按默认值处理。"""

    mode = _read_text(script_config, "Update", "AutoUpdateMode")
    if mode in AUTO_UPDATE_MODES:
        return mode  # type: ignore[return-value]
    return DEFAULT_AUTO_UPDATE_MODE


def describe_cdk(credentials: MaaFWUpdateCredentials) -> str:
    """给日志用的 CDK 描述：只说有没有、来自哪一级，一个字符都不露。

    不打印前几位：Mirror 酱的 CDK 前缀高度重复（实测样例全是 ``0001bf52`` 开头），
    露出来既帮不上排查，又和核心包「只记有无」的口径不一致。真要区分是哪个 CDK
    在生效，看「脚本级/全局」就够了。
    """

    if not credentials.cdk:
        return "未配置"
    origin = "脚本级" if credentials.cdk_origin == "script" else "全局"
    return f"已配置（{origin}）"


__all__ = [
    "AUTO_UPDATE_MODES",
    "AutoUpdateMode",
    "DEFAULT_AUTO_UPDATE_MODE",
    "DEFAULT_UPDATE_CHANNEL",
    "MaaFWUpdateCredentials",
    "describe_cdk",
    "resolve_auto_update_mode",
    "resolve_update_credentials",
]
