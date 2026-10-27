"""无公共注册表实现。"""

from .errors import UnsupportedPlatformError


def uninstall_entries(paths):
    raise UnsupportedPlatformError("registry")


def com_server(clsid: str) -> str:
    raise UnsupportedPlatformError("registry")
