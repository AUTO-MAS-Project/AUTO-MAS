from pathlib import Path
from typing import Any


class AdbDevice:
    adb_path: Path
    address: str
    name: str


class Toolkit:
    @staticmethod
    def init_option(
        user_path: str | Path,
        default_config: dict[str, Any] = ...,
    ) -> bool: ...

    @staticmethod
    def find_adb_devices() -> list[AdbDevice]: ...
