from typing import TYPE_CHECKING

from .base import (
    MultipleConfig,
    MultipleConfigAddEvent,
    MultipleConfigDeleteEvent,
    MultipleConfigReorderEvent,
    dump_toml,
)
from .fields import RefField, VirtualField
from .pydantic import PydanticConfigBase
from .types import (
    EncryptedString,
    HHMMString,
    JsonDictString,
    JsonListString,
    KeyboardKeyString,
    UrlString,
    YmdHmString,
    YmdHmsString,
    YmdString,
    decrypt_encrypted_string,
)

if TYPE_CHECKING:
    from .manager import AppConfig, Config


def __getattr__(name: str):
    if name in {"AppConfig", "Config"}:
        from .manager import AppConfig, Config

        return {"AppConfig": AppConfig, "Config": Config}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "MultipleConfig",
    "MultipleConfigAddEvent",
    "MultipleConfigDeleteEvent",
    "MultipleConfigReorderEvent",
    "dump_toml",
    "RefField",
    "VirtualField",
    "PydanticConfigBase",
    "JsonDictString",
    "JsonListString",
    "HHMMString",
    "YmdHmString",
    "YmdString",
    "YmdHmsString",
    "UrlString",
    "KeyboardKeyString",
    "EncryptedString",
    "decrypt_encrypted_string",
    "AppConfig",
    "Config",
]
