"""框架异常类型。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID


class ConfigError(Exception):
    """配置框架基类异常。"""


class DeletedNodeError(ConfigError):
    """对已软删除节点进行读写时抛出。"""

    def __init__(self, uid: UUID | str) -> None:
        super().__init__(f"节点已删除: {uid}")
        self.uid = uid


class ConfigRemoveRejected(ConfigError):
    """Collection 成员删除被 ``remove_guard`` 拒绝。"""


class ConfigPersistenceError(ConfigError):
    """单个持久化根保存失败；摘要不包含可能携带配置值的原始错误文本。"""

    def __init__(
        self, path: Path, phase: Literal["export", "write"], cause: Exception
    ) -> None:
        self.path = path
        self.phase: Literal["export", "write"] = phase
        self.cause = cause
        self.__cause__ = cause
        super().__init__(f"配置保存失败：{path}（{phase}，{type(cause).__name__}）")


class ConfigAggregateError(ConfigError):
    """聚合多条错误（activate / commit / update）；``errors`` 可含嵌套的 ``ConfigAggregateError``。"""

    def __init__(self, errors: list[Exception]) -> None:
        self.errors = list(errors)
        detail = "; ".join(f"{type(e).__name__}: {e}" for e in self.errors)
        super().__init__(detail or "操作失败")


# activate / commit / update 收集的错误列表元素类型（可嵌套聚合）
type ConfigErrorList = list[Exception]
