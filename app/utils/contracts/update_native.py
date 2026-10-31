"""UpdateNativeAPI 的平台无关调用契约。"""

from typing import Protocol


class UpdateNativeAPI(Protocol):
    @property
    def supports_fluxdown_install(self) -> bool: ...

    @property
    def FLUXDOWN_EXE_NAMES(self) -> tuple[str, ...]: ...

    @property
    def FLUXDOWN_AGENT_NAME(self) -> str | None: ...

    @property
    def FLUXDOWN_DAEMON_NAME(self) -> str | None: ...

    @property
    def HPATCHZ_MEMBER(self) -> str | None: ...

    @property
    def HPATCHZ_FILENAME(self) -> str | None: ...

    def candidate_drives(self) -> list[str]: ...
