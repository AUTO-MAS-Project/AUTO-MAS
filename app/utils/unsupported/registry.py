"""尚无实现的注册表能力。"""

from collections.abc import Iterable, Iterator

from ..common.errors import UnsupportedPlatformError


def user_subkey_values(path: str, value_name: str) -> Iterator[tuple[str, str]]:
    raise UnsupportedPlatformError("registry")


def uninstall_entries(paths: Iterable[str]) -> Iterator[tuple[str, str]]:
    raise UnsupportedPlatformError("registry")


def com_server(clsid: str) -> str:
    raise UnsupportedPlatformError("registry")
