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

"""读项目内容的端点背后的业务：interface 预览、游戏包名推断、项目内图片资源。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.models.schema import MaaFWGamePackageData, MaaFWInterfacePreviewData
from app.task.MaaFW.api_service.common import (
    MaaFWApiReply,
    logger,
    maafw_effective_root,
)
from app.task.MaaFW.tools.core.interface.loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
)
from app.task.MaaFW.tools.core.interface.preview import (
    build_interface_preview_data,
)
from app.task.MaaFW.tools.embedded.game_package import (
    resolve_game_package,
    resource_paths_for,
)


async def resolve_project_game_package(
    script_id: str | None, path: str, resource: str
) -> MaaFWApiReply:
    """``/maafw/game-package``：按所选 resource 的 pipeline 推断安卓游戏包名。"""

    # 与 preview / prepare 同一口径：带 scriptId 就按脚本解析有效根（内嵌脚本读的是
    # 副本，来源目录可能已经不在了），path 只在没有脚本时兜底。
    root_path, error = await maafw_effective_root(script_id, path)
    if root_path is None:
        return MaaFWApiReply.error(400, error)
    try:
        root_path = root_path.resolve()
        interface = await asyncio.to_thread(load_interface_model_cached, root_path)
        paths = await asyncio.to_thread(
            resource_paths_for, root_path, interface, resource
        )
        resolution = await asyncio.to_thread(resolve_game_package, paths)
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, str(exc))
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"resolve_maafw_game_package失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"推断游戏包名失败: {exc}")
    return MaaFWApiReply(
        data=MaaFWGamePackageData(
            reason=resolution.reason,
            package=resolution.package,
            candidates=list(resolution.candidates),
        )
    )


async def preview_project_interface(script_id: str | None, path: str) -> MaaFWApiReply:
    """``/maafw/preview``：读取项目 interface，返回 controller/resource/task 摘要。"""

    root_path, error = await maafw_effective_root(script_id, path)
    if root_path is None:
        return MaaFWApiReply.error(400, error)
    try:
        interface = await asyncio.to_thread(load_interface_model_cached, root_path)
        preview = await asyncio.to_thread(
            build_interface_preview_data,
            root_path,
            interface,
        )
        data = MaaFWInterfacePreviewData.model_validate(preview.model_dump(mode="json"))
    except MaaFWInterfaceLoadError as exc:
        return MaaFWApiReply.error(400, str(exc))
    except Exception as exc:
        logger.opt(exception=True).warning(
            f"preview_maafw_interface失败: {type(exc).__name__}: {exc}"
        )
        return MaaFWApiReply.error(500, f"MFW interface 预览失败: {exc}")

    return MaaFWApiReply(
        message=f"已读取 MFW 项目 {data.project.name}，共 {len(data.tasks)} 个任务",
        data=data,
    )


_MAAFW_IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
"""允许外发的图片后缀。

白名单而非黑名单：``/maafw/asset`` 的 root 由请求方给定，等于把「读任意目录下的
文件」的能力暴露出去了，只能靠「必须在 root 内」+「必须是图片」两道闸门把它收窄
成「读项目内的图片」。放开成任意后缀就变成了任意文件读取。
"""


def maafw_asset_file_path(root: str, asset_path: str) -> Path:
    """把 (项目根, 项目内相对路径) 解析成一个可安全外发的图片绝对路径。

    ``/maafw/asset`` 的安全边界就在这里：``FileNotFoundError`` 由端点映射成 404，
    ``ValueError`` 映射成 400。
    """

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError("MFW 项目目录不存在")

    normalized_asset_path = asset_path.replace("\\", "/").strip()
    relative_path = Path(normalized_asset_path)
    if (
        not normalized_asset_path
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise ValueError("MFW 资源路径非法")

    file_path = (root_path / relative_path).resolve()
    # 逐段比对而不是比字符串前缀：符号链接与 ..（上面已挡）之外，
    # 大小写与短路径名的差异也会让前缀比较判错。
    if root_path not in file_path.parents:
        raise ValueError("MFW 资源路径越界")
    if file_path.suffix.casefold() not in _MAAFW_IMAGE_SUFFIXES:
        raise ValueError("仅支持 MFW 图片资源")
    if not file_path.is_file():
        raise FileNotFoundError("MFW 图片资源不存在")
    return file_path
