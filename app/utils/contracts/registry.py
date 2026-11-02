"""RegistryAPI 的平台无关调用契约。"""

from collections.abc import Iterable, Iterator
from typing import Protocol


class RegistryAPI(Protocol):
    def user_subkey_values(
        self, path: str, value_name: str
    ) -> Iterator[tuple[str, str]]: ...

    def uninstall_entries(self, paths: Iterable[str]) -> Iterator[tuple[str, str]]: ...

    def com_server(self, clsid: str) -> str: ...
