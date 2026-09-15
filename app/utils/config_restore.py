#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""通用配置恢复服务：双目标（MAS 用户配置 / 脚本原生配置）的列表、预览、恢复。

供各专项直接传参套用，避免重复实现「时间戳列表 → 预览摘要 → 恢复」这套
前端弹窗所需的统一后端能力。文件级快照/回写原语在 ``app.utils.config_archive``，
本层在其之上补齐「目标池」抽象：

- 专项在 ``tools/restore_service.py`` 声明 :class:`ConfigRestorePool` 池表
  （普通函数，显式收 :class:`RestoreContext`，可直接单测），核心门面按脚本
  类型分发并用 :func:`build_restore_service` 一次性绑定上下文；
- HTTP 层只有一组通用端点（``/backup/list|ensure|restore|preview``），
  target 取值由专项池定义，校验失败统一 400；
- 服务层不感知任何脚本结构，也不做文件读写之外的业务（守卫/信息字段回填等
  归专项池函数）。

参考实现：``app/task/ZzzOd/tools/restore_service.py`` 与
``app/task/OkNte/tools/restore_service.py``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.utils import get_logger
from app.utils.config_archive import (
    archive_files,
    dir_files,
    get_backup_dir,
    list_times,
    read_backup_text,
)

logger = get_logger("配置恢复服务")


@dataclass
class RestoreContext:
    """池函数的显式上下文（替代闭包捕获，专项池函数可直接单测）。"""

    config: Any
    """核心门面单例（专项内部业务方法挂在门面上时，经此薄委托调用）。"""

    script_config: Any
    """专项脚本配置对象（UserData / 专项字段从这里取）。"""

    script_id: str
    """脚本 ID。"""

    user_id: str
    """目标用户 ID。"""


@dataclass
class ConfigRestorePool:
    """一个可恢复目标池的专项声明（如「MAS 用户配置」「脚本原生配置」）。

    全部函数第一个参数收 :class:`RestoreContext`，其余参数见各字段；
    ``kind`` 供前端分段器渲染（``user``=MAS 用户配置、``script``=脚本原生），
    池表顺序即前端展示顺序（MAS 在前、脚本在后）。

    两种声明形态（可混用）：

    - **声明式（推荐）**：提供 :attr:`files`（归档什么）+ :attr:`backup_root`
      （放哪里）两个真知识回调，``list`` / ``snapshot`` / ``read_file`` /
      无 ``preview`` 时的 files 兜底载荷全部由基座自动派生；
    - **显式回调**：直接给 ``list_backups`` / ``snapshot`` / ``read_file`` /
      ``preview``，优先级高于声明式派生（已有专项的定制预览不受影响）。

    ``restore`` 恒为显式回调（恢复语义含守卫/回填/写回规则，是专项知识，
    不做缺省）；缺省表示该池不支持恢复。
    """

    key: str
    """目标标识（如 ``mas`` / ``onedragon`` / ``native``），前端与后端路由共用。"""

    kind: str
    """池类别：``user`` 或 ``script``。"""

    list_backups: Callable[[RestoreContext], Awaitable[list[str]]] | None = None
    """返回该目标全部备份时间戳（倒序，最新在前）；声明式下自动派生。"""

    preview: Callable[[RestoreContext, str], Awaitable[dict]] | None = None
    """给定时间戳返回预览载荷 dict（纯读不恢复；专项自定义结构）。"""

    restore: Callable[[RestoreContext, str], Awaitable[object]] | None = None
    """给定时间戳执行恢复（恢复前归档当前由池函数自理）。"""

    snapshot: Callable[[RestoreContext], Awaitable[dict]] | None = None
    """归档当前配置（指纹去重，无变化跳过）；供三时机 ``service.ensure`` 调用。

    返回 ``{"created": bool, "time": str}``。
    """

    read_file: Callable[[RestoreContext, str, str], Awaitable[dict]] | None = None
    """只读读取指定备份内一个文本文件（``(ctx, ts, rel_path)``）。

    供前端预览弹窗「查看原始文件」；返回 ``{"path", "size", "content"}``。
    路径越界/超限等校验建议直接调用
    :func:`app.utils.config_archive.read_backup_text`。``None`` 时若声明了
    :attr:`files` + :attr:`backup_root`，由基座按同函数自动实现。
    """

    files: (
        Callable[
            [RestoreContext],
            Awaitable["dict[str, Path | str | bytes] | None"],
        ]
        | None
    ) = None
    """声明式：本次要归档的文件集（``ctx`` → 相对键 → ``Path`` 或内存内容）。

    ``str`` 按 UTF-8 编码、``bytes`` 原样写入归档（页面字段侧车直接给
    JSON 字符串，免临时文件）；值为 ``None`` 或空 dict 表示当前无可归档
    内容（``snapshot`` 报「无变化」）。与 :attr:`backup_root` 一起构成
    声明式接入的最小面。
    """

    backup_root: Callable[[RestoreContext], Awaitable[Path | None]] | None = None
    """声明式：该池的归档根目录（含分桶规则，不含时间戳目录）。

    返回 ``None`` 表示当前无可归档根（如脚本路径未配置）——``list`` 为空、
    ``snapshot`` 报无变化，而不是抛错（用户未配置路径时编辑页不该报错）。
    声明式派生（``list`` / ``snapshot`` / ``read_file`` / files 兜底
    ``preview``）全部基于它；单独提供亦可让 ``read_file`` / files 兜底
    生效。
    """


@dataclass
class ConfigRestoreTarget:
    """一个可恢复目标池（如「MAS 用户配置」「脚本原生配置」）。"""

    key: str
    """目标标识（如 ``mas`` / ``onedragon``），前端 segmented 与后端路由共用。"""

    list_backups: Callable[[], Awaitable[list[str]]]
    """返回该目标全部备份时间戳（倒序，最新在前）。"""

    preview: Callable[[str], Awaitable[dict]] | None = None
    """给定时间戳返回预览摘要 dict（纯读不恢复）；None 表示该目标不支持预览。"""

    restore: Callable[[str], Awaitable[object]] | None = None
    """给定时间戳执行恢复（恢复前归档当前由回调自理）；返回供前端展示的结果。"""

    snapshot: Callable[[], Awaitable[dict]] | None = None
    """归档当前配置（指纹去重，无变化跳过）；None 表示该目标不支持按需归档。

    供编辑界面的三时机归档使用：进入编辑界面（MAS 会触碰的原生配置捕捉
    「操作前原始态」）、退出编辑界面（MAS 侧配置终态）、运行前。返回
    ``{"created": bool, "time": str}``。
    """

    read_file: Callable[[str, str], Awaitable[dict]] | None = None
    """只读读取指定备份内一个文本文件（``(ts, rel_path)``）；None 不支持。"""

    backup_dir_for: Callable[[str], Awaitable[Path | None]] | None = None
    """``ts`` → 归档目录（缺省派生用）；service.preview 借此为未带 ``files``
    字段的定制预览载荷注入标准文件清单（§基座兜底）。"""


class ConfigRestoreService:
    """双目标配置恢复服务：按 key 分发列表/预览/恢复。

    ``script_name`` 只用于文案参数化（错误提示等），前端展示文案走 i18n
    ``{script}`` 插值。
    """

    def __init__(
        self,
        script_name: str,
        targets: list[ConfigRestoreTarget],
    ) -> None:
        if not targets:
            raise ValueError("配置恢复服务至少需要一个目标池")
        self.script_name = script_name
        self._targets = {t.key: t for t in targets}

    @property
    def target_keys(self) -> list[str]:
        """目标池顺序（即前端 segmented 展示顺序，MAS 在前脚本在后）。"""

        return list(self._targets)

    def get_target(self, key: str) -> ConfigRestoreTarget:
        target = self._targets.get(key)
        if target is None:
            raise ValueError(f"不支持的恢复目标: {key}")
        return target

    async def list(self, key: str) -> list[str]:
        target = self.get_target(key)
        if target.list_backups is None:
            raise ValueError(f"目标「{key}」不支持列出备份")
        return await target.list_backups()

    async def preview(self, key: str, ts: str) -> dict:
        """预览载荷（专项定制结构）+ 标准 ``files`` 字段统一注入。

        专项定制预览**不需要**自己拼文件清单：载荷未带 ``files`` 键且池
        声明（或派生）了归档目录时，基座自动把归档内文件清单注入
        ``payload["files"]``，供前端「备份文件」兜底节渲染。
        """

        target = self.get_target(key)
        if target.preview is None:
            raise ValueError(f"目标「{key}」不支持预览")
        payload = await target.preview(ts)
        if "files" not in payload and target.backup_dir_for is not None:
            backup_dir = await target.backup_dir_for(ts)
            if backup_dir is not None:
                payload["files"] = [
                    {"path": rel, "size": path.stat().st_size}
                    for rel, path in sorted(dir_files(backup_dir).items())
                ]
        return payload

    async def restore(self, key: str, ts: str) -> object:
        target = self.get_target(key)
        if target.restore is None:
            raise ValueError(f"目标「{key}」不支持恢复")
        return await target.restore(ts)

    async def ensure(self, key: str) -> dict:
        """归档目标池当前配置（指纹去重，无变化自动跳过）。

        编辑界面三时机的通用入口：进入时（原生配置「操作前原始态」）、
        退出时（MAS 侧配置终态）、运行前。返回 ``{"created", "time"}``。
        """

        target = self.get_target(key)
        if target.snapshot is None:
            raise ValueError(f"目标「{key}」不支持按需归档")
        return await target.snapshot()

    async def read_backup_file(self, key: str, ts: str, rel_path: str) -> dict:
        """只读读取指定备份内一个文本文件（预览「查看原始文件」用）。"""

        target = self.get_target(key)
        if target.read_file is None:
            raise ValueError(f"目标「{key}」不支持查看文件内容")
        return await target.read_file(ts, rel_path)


def _bind_context(
    func: Callable[..., Awaitable] | None, ctx: RestoreContext
) -> Callable[..., Awaitable] | None:
    """把 ``(ctx, *args)`` 签名的池函数绑定为 Target 的闭包签名；None 透传。"""

    if func is None:
        return None

    async def call(*args: Any) -> Any:
        return await func(ctx, *args)

    return call


def _build_target(pool: ConfigRestorePool, ctx: RestoreContext) -> ConfigRestoreTarget:
    """把一个池声明绑定到上下文，并按声明式字段派生缺省回调。

    显式回调（``list_backups`` / ``snapshot`` / ``read_file`` / ``preview``）
    优先；缺省时若声明了 :attr:`ConfigRestorePool.files` +
    :attr:`ConfigRestorePool.backup_root`，由基座派生：

    - ``list_backups`` = ``list_times(backup_root)``
    - ``snapshot`` = ``archive_files(files(ctx), backup_root(ctx))``（指纹
      去重、保留清理全在 :func:`archive_files`，无可归档内容报无变化）
    - ``read_file`` = ``read_backup_text(归档目录, rel_path)``
    - ``preview``（未定制时）= 空载荷，由 :meth:`ConfigRestoreService.preview`
      统一注入归档文件清单 ``{"files": [...]}``
    """

    bound_list = _bind_context(pool.list_backups, ctx)
    bound_preview = _bind_context(pool.preview, ctx)
    bound_snapshot = _bind_context(pool.snapshot, ctx)
    bound_read_file = _bind_context(pool.read_file, ctx)
    bound_files = _bind_context(pool.files, ctx)
    bound_root = _bind_context(pool.backup_root, ctx)

    declarative = bound_files is not None and bound_root is not None
    root_only = bound_root is not None

    backup_dir_for: Callable[[str], Awaitable[Path | None]] | None = None
    if root_only:

        async def backup_dir_for(ts: str) -> Path | None:
            root = await bound_root()  # type: ignore[misc]
            if root is None:
                return None
            return get_backup_dir(root, ts)

    if bound_list is None and declarative:

        async def bound_list() -> list[str]:
            root = await bound_root()  # type: ignore[misc]
            return list_times(root) if root is not None else []

    if bound_snapshot is None and declarative:

        async def bound_snapshot() -> dict:
            payload = await bound_files()  # type: ignore[misc]
            root = await bound_root()  # type: ignore[misc]
            times = list_times(root) if root is not None else []
            latest = times[0] if times else ""
            if not payload or root is None:
                return {"created": False, "time": latest}
            dest = archive_files(payload, root)
            if dest is None:
                return {"created": False, "time": latest}
            logger.info(f"池「{pool.key}」配置已归档: {dest.name}")
            return {"created": True, "time": dest.name}

    if bound_read_file is None and root_only:

        async def bound_read_file(ts: str, rel_path: str) -> dict:
            root = await bound_root()  # type: ignore[misc]
            if root is None:
                raise ValueError(f"目标「{pool.key}」无可读备份")
            backup_dir = get_backup_dir(root, ts)
            if backup_dir is None:
                raise ValueError(f"备份不存在: {ts}")
            return read_backup_text(backup_dir, rel_path)

    if bound_preview is None and root_only:

        async def bound_preview(ts: str) -> dict:
            # 文件清单由 service.preview 统一注入（本闭包只占位表示可预览）
            return {}

    return ConfigRestoreTarget(
        key=pool.key,
        list_backups=bound_list,
        preview=bound_preview,
        restore=_bind_context(pool.restore, ctx),
        snapshot=bound_snapshot,
        read_file=bound_read_file,
        backup_dir_for=backup_dir_for,
    )


def build_restore_service(
    ctx: RestoreContext,
    script_name: str,
    pools: list[ConfigRestorePool],
) -> ConfigRestoreService:
    """把专项声明的池表绑定到具体脚本/用户上下文，构建运行时服务。

    绑定是唯一一处闭包捕获：池函数本身收显式 :class:`RestoreContext`，
    保持可直接单测。池表顺序即前端 segmented 展示顺序。
    """

    if not pools:
        raise ValueError("配置恢复服务至少需要一个目标池")
    for pool in pools:
        if pool.kind not in ("user", "script"):
            raise ValueError(f"池「{pool.key}」的 kind 非法: {pool.kind}")

    targets = [_build_target(pool, ctx) for pool in pools]
    return ConfigRestoreService(script_name=script_name, targets=targets)
