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

核心更新包（``tools/core/automas_maafw_project_update``）不读 Config，配置到
参数的翻译只在这里做一次；API 侧直接复用本函数，保证手动更新与运行时自动更新
的行为一致。

三项全部只看脚本级，**不做全局兜底**：

- ``source``：``Update.Source``，``MirrorChyan`` / ``GitHub``（默认 GitHub）
- ``cdk``：``Update.MirrorChyanCDK`` 明文，用户自己填，空就是空
- ``channel``：``Update.Channel``（默认 ``stable``）

全局那两项（``Update.MirrorChyanCDK`` / ``Update.Channel``）服务的是 MAS 自身的
更新，和脚本本体的版本档位不是一回事，串在一起只会让人猜自己在用哪个。

任何日志都不得出现 CDK 明文，打码用 :func:`describe_cdk`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AutoUpdateMode = Literal["Off", "BeforeRun", "AfterRun"]

AUTO_UPDATE_MODES: tuple[AutoUpdateMode, ...] = ("Off", "BeforeRun", "AfterRun")
DEFAULT_AUTO_UPDATE_MODE: AutoUpdateMode = "BeforeRun"
DEFAULT_UPDATE_CHANNEL = "stable"

UpdateSource = Literal["MirrorChyan", "GitHub"]

# 与 MaaFWConfig.Update_Source 的 OptionsValidator、schema 的 Literal、前端的
# updateSourceOptions 必须一致；任一处多给一项，用户选了就会 422 或被静默纠回。
UPDATE_SOURCES: tuple[UpdateSource, ...] = ("MirrorChyan", "GitHub")
DEFAULT_UPDATE_SOURCE: UpdateSource = "GitHub"

# 核心更新包内部用的源名；配置里的展示名映射到它。
PACKAGE_SOURCE_BY_UPDATE_SOURCE: dict[str, str] = {
    "MirrorChyan": "mirrorchyan",
    "GitHub": "github_release",
}


@dataclass(frozen=True)
class MaaFWUpdateCredentials:
    """脚本级更新凭据。不做全局兜底，所见即所得。"""

    source: UpdateSource
    cdk: str
    channel: str

    @property
    def package_source(self) -> str:
        """核心更新包用的内部源名。"""

        return PACKAGE_SOURCE_BY_UPDATE_SOURCE[self.source]


def _read_text(config: Any, group: str, name: str) -> str:
    """读一个字符串配置项；配置项不存在或读取失败一律当空串。"""

    try:
        return str(config.get(group, name) or "").strip()
    except Exception:  # noqa: BLE001 - 旧配置对象缺项不该挡住运行
        return ""


def resolve_update_credentials(script_config: Any) -> MaaFWUpdateCredentials:
    """只读脚本级配置，得到传给核心更新包的下载源、明文 CDK 与渠道。"""

    source = _read_text(script_config, "Update", "Source")
    if source not in UPDATE_SOURCES:
        source = DEFAULT_UPDATE_SOURCE
    cdk = _read_text(script_config, "Update", "MirrorChyanCDK")
    channel = (
        _read_text(script_config, "Update", "Channel") or DEFAULT_UPDATE_CHANNEL
    )
    return MaaFWUpdateCredentials(source=source, cdk=cdk, channel=channel)


def resolve_auto_update_mode(script_config: Any) -> AutoUpdateMode:
    """读脚本的更新时机；非法值按默认值处理。"""

    mode = _read_text(script_config, "Update", "AutoUpdateMode")
    if mode in AUTO_UPDATE_MODES:
        return mode  # type: ignore[return-value]
    return DEFAULT_AUTO_UPDATE_MODE


def describe_cdk(credentials: MaaFWUpdateCredentials) -> str:
    """给日志用的 CDK 描述：只说有没有，一个字符都不露。

    不打印前几位：Mirror 酱的 CDK 前缀高度重复（实测样例全是 ``0001bf52`` 开头），
    露出来既帮不上排查，又和核心包「只记有无」的口径不一致。
    """

    return "已配置" if credentials.cdk else "未配置"


__all__ = [
    "AUTO_UPDATE_MODES",
    "AutoUpdateMode",
    "DEFAULT_AUTO_UPDATE_MODE",
    "DEFAULT_UPDATE_CHANNEL",
    "DEFAULT_UPDATE_SOURCE",
    "PACKAGE_SOURCE_BY_UPDATE_SOURCE",
    "UPDATE_SOURCES",
    "UpdateSource",
    "MaaFWUpdateCredentials",
    "describe_cdk",
    "resolve_auto_update_mode",
    "resolve_update_credentials",
]
