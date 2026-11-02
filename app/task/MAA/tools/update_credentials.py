#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""MAA 本体与资源更新共用的接管凭据，避免两个更新器的启用条件分歧。"""

from collections.abc import Sequence
from pathlib import Path

from app.core import Config
from app.models.config import MaaConfig
from app.services.common.update import transport as _service_update_transport
from app.utils import get_logger
from app.utils import io as _utils_io

logger = get_logger("MAA 更新凭据")


def resolve_takeover_cdk(cdk: str) -> str:
    """专用 CDK 留空时使用全局 CDK，不写回脚本配置。"""
    return cdk.strip() or str(Config.setting.Update.MirrorChyanCDK or "").strip()


def resolve_takeover_credentials(config: MaaConfig) -> tuple[bool, str | None]:
    """返回 Mirror 酱路径是否启用及其 CDK；无 CDK 的接管改走 GitHub。"""
    if not config.Update.TakeoverEnabled:
        return False, None
    cdk = resolve_takeover_cdk(str(config.Update.MirrorChyanCDK or ""))
    return bool(cdk), cdk or None


def use_maa_github_update(config: MaaConfig, *, config_dirs: Sequence[Path]) -> bool:
    """无 CDK 时使用 GitHub；下载器由全局 FluxDown 接管开关独立决定。

    按用户要求，MAA 专项、MAS 全局或原生配置存在 CDK 均保留 Mirror 酱路径，
    由专项更新接管开关控制。配置损坏时也不绕过其下载来源选择。
    """
    if not config.Update.TakeoverEnabled:
        return False
    if resolve_takeover_cdk(str(config.Update.MirrorChyanCDK or "")):
        return False
    # 上游 Update.cs / ConfigurationKeys.cs 定义的原生字段。仅用于执行
    # 「配置 CDK 时不代理下载」策略，不消费凭据语义，也不传给 MAS 下载器。
    for directory in config_dirs:
        for name, section, key in (
            ("gui.new.json", "Update", "MirrorChyanCdk"),
            ("gui.json", "Global", "VersionUpdate.ResourceUpdateSource.MirrorChyanCdk"),
        ):
            path = directory / name
            if not path.is_file():
                continue
            try:
                data = _utils_io.read_dict_file(path)
                values = data.get(section, {})
                if not isinstance(values, dict):
                    raise ValueError("更新配置不是对象")
                value = values.get(key)
                if value is not None and (not isinstance(value, str) or value.strip()):
                    return False
            except (OSError, ValueError):
                logger.warning("无法确认 MAA 原生 CDK 设置，保留原生更新路径")
                return False
    return True


async def query_takeover_cdk(cdk: str) -> _service_update_transport.MirrorCdkStatus:
    """仅校验 MAA 的有效凭据，不依赖安装目录或读取 MAA 加密配置。"""
    # CDK 的有效期不随安装版本变化；使用稳定版元数据完成无下载查询。
    return await _service_update_transport.query_mirror_cdk_status(
        "MAA", cdk=resolve_takeover_cdk(cdk), channel="stable", proxy=Config.proxy
    )
