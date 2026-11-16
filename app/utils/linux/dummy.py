"""缺失能力的显式错误。"""

from ..common.errors import UnsupportedPlatformError


def unsupported(capability: str) -> None:
    raise UnsupportedPlatformError(capability)
