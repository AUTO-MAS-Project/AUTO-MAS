"""未提供密文存储的平台保留旧密文，不以明文回退。"""

from ..common.errors import UnsupportedPlatformError
from ..common.secret_format import looks_like_dpapi_blob as looks_like_dpapi_blob


def supports_secret_storage() -> bool:
    return False


def is_secret_storage_error(error: BaseException) -> bool:
    return isinstance(error, UnsupportedPlatformError) and error.capability == "secret"


def dpapi_encrypt(
    note: str, description: str | None = None, entropy: bytes | None = None
) -> str:
    if note == "":
        return ""
    raise UnsupportedPlatformError("secret")


def dpapi_decrypt(note: str, entropy: bytes | None = None) -> str:
    if note == "":
        return ""
    raise UnsupportedPlatformError("secret")
