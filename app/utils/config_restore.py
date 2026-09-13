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
from typing import Any, Awaitable, Callable

from app.utils import get_logger

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
    """

    key: str
    """目标标识（如 ``mas`` / ``onedragon`` / ``native``），前端与后端路由共用。"""

    kind: str
    """池类别：``user`` 或 ``script``。"""

    list_backups: Callable[[RestoreContext], Awaitable[list[str]]]
    """返回该目标全部备份时间戳（倒序，最新在前）。"""

    preview: Callable[[RestoreContext, str], Awaitable[dict]] | None = None
    """给定时间戳返回预览载荷 dict（纯读不恢复；专项自定义结构）。"""

    restore: Callable[[RestoreContext, str], Awaitable[object]] | None = None
    """给定时间戳执行恢复（恢复前归档当前由池函数自理）。"""

    snapshot: Callable[[RestoreContext], Awaitable[dict]] | None = None
    """归档当前配置（指纹去重，无变化跳过）；供三时机 ``service.ensure`` 调用。

    返回 ``{"created": bool, "time": str}``。
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
        return await self.get_target(key).list_backups()

    async def preview(self, key: str, ts: str) -> dict:
        target = self.get_target(key)
        if target.preview is None:
            raise ValueError(f"目标「{key}」不支持预览")
        return await target.preview(ts)

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


def _bind_context(
    func: Callable[..., Awaitable] | None, ctx: RestoreContext
) -> Callable[..., Awaitable] | None:
    """把 ``(ctx, *args)`` 签名的池函数绑定为 Target 的闭包签名；None 透传。"""

    if func is None:
        return None

    async def call(*args: Any) -> Any:
        return await func(ctx, *args)

    return call


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

    targets = [
        ConfigRestoreTarget(
            key=pool.key,
            list_backups=_bind_context(pool.list_backups, ctx),
            preview=_bind_context(pool.preview, ctx),
            restore=_bind_context(pool.restore, ctx),
            snapshot=_bind_context(pool.snapshot, ctx),
        )
        for pool in pools
    ]
    return ConfigRestoreService(script_name=script_name, targets=targets)
