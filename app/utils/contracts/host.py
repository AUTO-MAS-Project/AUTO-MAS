"""HostAPI 的平台无关调用契约。"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

type HostPredicate = Callable[[], bool]


class HostAPI(Protocol):
    @property
    def IS_WINDOWS(self) -> bool: ...

    @property
    def IS_ELEVATED(self) -> bool: ...

    def is_admin(self) -> bool: ...

    def is_long_path_supported(self) -> bool: ...


class IntegrityAPI(Protocol):
    @property
    def INTEGRITY_LOW(self) -> int: ...

    def mandatory_label_rid(self, path: Path | str) -> int | None: ...
