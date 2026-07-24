"""加密字段：``encrypted()`` marker + ``EncryptedValue`` 存储类型。

声明格式与一般字段一致，仅在 ``Annotated`` 末位追加 ``encrypted()``::

    token: Annotated[str, encrypted()] = ""
    api_key: Annotated[str, AfterValidator(strip), encrypted()] = ""

内存常态为 ``EncryptedValue``（密文）；读路径 unwrap 为明文 ``str``；
持久化默认导出密文，Pydantic/FastAPI transport 默认导出逻辑明文。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal

from pydantic import GetCoreSchemaHandler
from pydantic.fields import FieldInfo
from pydantic_core import core_schema

from .errors import EncryptedValueError
from .support.constants import ENCRYPTED_PREFIX
from .support.security import (
    DPAPIDecryptionResult,
    dpapi_decrypt,
    dpapi_decrypt_with_status,
    dpapi_encrypt,
    is_probable_dpapi_ciphertext,
)
from .wire import ExportContext

type EncryptedMigrationOutcome = Literal["legacy_dpapi_rewrapped_to_v1"] | None
_LEGACY_REWRAP_OUTCOME = "legacy_dpapi_rewrapped_to_v1"


def _encrypt_value(value: str) -> str:
    """加密明文，并兼容测试/插件注入的裸 DPAPI 实现。"""
    ciphertext = dpapi_encrypt(value)
    if ciphertext == "" or ciphertext.startswith(ENCRYPTED_PREFIX):
        return ciphertext
    return ENCRYPTED_PREFIX + ciphertext


def _decrypt_value(ciphertext: str) -> DPAPIDecryptionResult:
    """解密共享格式，并保留 Config v2 既有模块注入兼容点。"""
    try:
        return dpapi_decrypt_with_status(ciphertext)
    except Exception:
        legacy_payload = (
            ciphertext[len(ENCRYPTED_PREFIX) :]
            if ciphertext.startswith(ENCRYPTED_PREFIX)
            else ciphertext
        )
        try:
            plaintext = dpapi_decrypt(legacy_payload)
        except Exception:
            raise EncryptedValueError(
                "DPAPI encrypted configuration value cannot be decrypted"
            ) from None
        return DPAPIDecryptionResult(plaintext, needs_migration=False)


class EncryptedValue:
    """内存常态为密文的加密值；读路径 unwrap 为 ``str``。"""

    __slots__ = ("_cipher", "_migration_outcome")

    def __init__(self, cipher: str = "") -> None:
        # _cipher: ""、当前 "DPAPI:v1:<base64>" 或待迁移历史密文。
        self._cipher = cipher
        self._migration_outcome: EncryptedMigrationOutcome = None

    @classmethod
    def from_string(cls, value: str) -> "EncryptedValue":
        """统一构造：``""``、``DPAPI:`` 前缀密文、其余视为明文并加密。"""
        if value == "":
            return cls("")
        if is_probable_dpapi_ciphertext(value):
            return cls(value)
        return cls(_encrypt_value(value))

    def _ensure_current_ciphertext(self) -> str:
        """解密并在内存中原子重包历史格式，返回逻辑明文。"""
        if self._cipher == "":
            return ""
        result = _decrypt_value(self._cipher)
        if result.needs_migration:
            try:
                migrated = _encrypt_value(result.plaintext)
            except Exception:
                raise EncryptedValueError(
                    "DPAPI encrypted configuration value migration failed"
                ) from None
            self._cipher = migrated
            self._migration_outcome = _LEGACY_REWRAP_OUTCOME
        return result.plaintext

    # ── 访问 ──
    def plaintext(self) -> str:
        return self._ensure_current_ciphertext()

    def ciphertext(self) -> str:
        self._ensure_current_ciphertext()
        return self._cipher

    def migration_outcome(self) -> EncryptedMigrationOutcome:
        """返回本实例发生的存储迁移结果，不包含明文或密文。"""
        return self._migration_outcome

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EncryptedValue):
            return self.plaintext() == other.plaintext()
        if isinstance(other, str):
            return self.plaintext() == other
        return NotImplemented

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self.plaintext())

    def __repr__(self) -> str:
        return "EncryptedValue(***)"

    def __iter__(self) -> Iterator[object]:
        """Allow API error encoders to render a safe empty object."""
        return iter(())


class _ProtectedEncryptedInput:
    """One validation-call input whose repr/JSON conversion cannot reveal it."""

    __slots__ = ("_value",)

    def __init__(self, value: object) -> None:
        self._value = value

    def unwrap(self) -> object:
        return self._value

    def __repr__(self) -> str:
        return "ProtectedEncryptedInput(***)"

    def __iter__(self) -> Iterator[object]:
        """FastAPI's generic encoder falls back to ``dict(value)``."""
        return iter(())


def protect_encrypted_input(value: object) -> object:
    """Replace transport input with a redaction-safe validation carrier."""
    if isinstance(value, (EncryptedValue, _ProtectedEncryptedInput)):
        return value
    return _ProtectedEncryptedInput(value)


def _validate_encrypted(
    value: object,
    inner_handler: Callable[[object], object],
) -> EncryptedValue:
    """Validate both plaintext assignments and persisted DPAPI ciphertext."""
    if isinstance(value, _ProtectedEncryptedInput):
        value = value.unwrap()
    existing: EncryptedValue | None = None
    if isinstance(value, EncryptedValue):
        existing = value
        plaintext = value.plaintext()
    elif isinstance(value, str):
        if is_probable_dpapi_ciphertext(value):
            existing = EncryptedValue.from_string(value)
            plaintext = existing.plaintext()
        else:
            plaintext = value
    else:
        raise EncryptedValueError(
            "encrypted configuration value must be a string"
        ) from None

    try:
        validated = inner_handler(plaintext)
    except EncryptedValueError:
        raise
    except Exception:
        # Do not retain an inner validator exception whose message/context may
        # include the plaintext.  The active assignment path adds the field
        # name while preserving this redacted boundary.
        raise EncryptedValueError(
            "encrypted configuration value failed validation"
        ) from None
    if not isinstance(validated, str):
        raise EncryptedValueError(
            "encrypted configuration validator did not return a string"
        )
    if existing is not None and validated == plaintext:
        return existing
    return EncryptedValue.from_string(validated)


def _dump_encrypted(value: EncryptedValue, info: object) -> str:
    ctx = getattr(info, "context", None)
    if isinstance(ctx, ExportContext) and ctx.if_decrypt:
        return value.plaintext()
    if isinstance(ctx, dict) and ctx.get("if_decrypt"):
        return value.plaintext()
    return value.ciphertext()


@dataclass(frozen=True)
class EncryptedMarker:
    """``Annotated[str, …, encrypted()]`` 的末位 marker。

    明文赋值和已持久化的 DPAPI 密文都会先以逻辑明文通过同一条 inner
    validator 链；当前版本密文原样复用，历史密文只在成功解密后重包为
    ``DPAPI:v1``，并通过 ``EncryptedValue.migration_outcome()`` 报告。
    """

    def __get_pydantic_core_schema__(
        self, source: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        inner = handler(source)  # str + 先前的 AfterValidator 链
        return core_schema.no_info_wrap_validator_function(
            _validate_encrypted,
            inner,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _dump_encrypted, info_arg=True, return_schema=core_schema.str_schema()
            ),
        )


def encrypted() -> EncryptedMarker:
    """生成加密字段 marker，须置于 ``Annotated`` 元组末位。"""
    return EncryptedMarker()


def is_encrypted_model_field(field: FieldInfo) -> bool:
    """判断 pydantic ``FieldInfo`` 是否为加密字段。"""
    return any(isinstance(m, EncryptedMarker) for m in getattr(field, "metadata", ()))
