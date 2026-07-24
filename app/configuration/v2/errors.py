"""框架异常类型。"""

from __future__ import annotations

from uuid import UUID


class ConfigError(Exception):
    """配置框架基类异常。"""


class DeletedNodeError(ConfigError):
    """对已软删除节点进行读写时抛出。"""

    def __init__(self, uid: UUID | str) -> None:
        super().__init__(f"节点已删除: {uid}")
        self.uid = uid


class EncryptedValueError(ConfigError, ValueError):
    """Raised when an encrypted value cannot be decrypted safely."""


class ConfigAggregateError(ConfigError):
    """聚合多条错误（activate / commit / update）；``errors`` 可含嵌套的 ``ConfigAggregateError``。"""

    def __init__(self, errors: list[Exception]) -> None:
        self.errors = list(errors)
        detail = "; ".join(f"{type(e).__name__}: {e}" for e in self.errors)
        super().__init__(detail or "操作失败")


# activate / commit / update 收集的错误列表元素类型（可嵌套聚合）
type ConfigErrorList = list[Exception]
