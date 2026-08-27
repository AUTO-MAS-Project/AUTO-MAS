from .errors import UnsupportedPlatformError


class CommonProcessPlatform:
    creation_flags = 0
    detached_flags = 0

    async def open_protocol(self, protocol_url: str) -> None:
        raise UnsupportedPlatformError("open_protocol")
