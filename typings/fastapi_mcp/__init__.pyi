from typing import Any


class FastApiMCP:
    def __init__(self, app: Any, *args: Any, **kwargs: Any) -> None: ...

    def mount_http(self) -> None: ...
