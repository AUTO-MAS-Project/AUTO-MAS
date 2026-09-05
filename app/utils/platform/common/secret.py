from app.utils.platform.common.errors import UnsupportedPlatformError


def dpapi_encrypt(*args, **kwargs) -> str:
    raise UnsupportedPlatformError("secret")


def dpapi_decrypt(*args, **kwargs) -> str:
    raise UnsupportedPlatformError("secret")
