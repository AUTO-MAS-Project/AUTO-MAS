"""加密字段：``encrypted()`` marker + ``EncryptedValue`` 存储类型。

声明格式与一般字段一致，仅在 ``Annotated`` 末位追加 ``encrypted()``::

    token: Annotated[str, encrypted()] = ""
    api_key: Annotated[str, AfterValidator(strip), encrypted()] = ""

内存常态为 ``EncryptedValue``（密文）；读路径 unwrap 为明文 ``str``；
落盘默认导出密文，``if_decrypt=True`` 导出明文。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import GetCoreSchemaHandler
from pydantic.fields import FieldInfo
from pydantic_core import core_schema

from app.utils.security import dpapi_decrypt, dpapi_encrypt

from ..wire import ExportContext

ENCRYPTED_PREFIX = "DPAPI:"
"""加密密文落盘前缀。"""


class EncryptedValue:
    """内存常态为密文的加密值；读路径 unwrap 为 ``str``。"""

    __slots__ = ("_cipher",)

    def __init__(self, cipher: str = "") -> None:
        # _cipher: "" 或 "DPAPI:<base64>"（仅内部 / 已归一化形态）
        self._cipher = cipher

    @classmethod
    def from_string(cls, value: str) -> "EncryptedValue":
        """统一构造：``""``、``DPAPI:`` 前缀密文、其余视为明文并加密。"""
        if value == "":
            return cls("")
        if value.startswith(ENCRYPTED_PREFIX):
            return cls(value)
        return cls(ENCRYPTED_PREFIX + dpapi_encrypt(value))

    # ── 访问 ──
    def plaintext(self) -> str:
        if self._cipher == "":
            return ""
        try:
            return dpapi_decrypt(self._cipher[len(ENCRYPTED_PREFIX) :])
        except Exception:
            return self._cipher

    def ciphertext(self) -> str:
        return self._cipher

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


def _parse_encrypted(value: object) -> EncryptedValue:
    if isinstance(value, EncryptedValue):
        return value
    if isinstance(value, str):
        return EncryptedValue.from_string(value)
    raise TypeError(f"加密字段仅接受 str / EncryptedValue, 收到 {type(value).__name__}")


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

    仅注册 ``encrypt → EncryptedValue`` 的末 step 与序列化器，
    不吞并同字段上的 ``AfterValidator``。
    """

    def __get_pydantic_core_schema__(
        self, source: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        inner = handler(source)  # str + 先前的 AfterValidator 链
        return core_schema.no_info_after_validator_function(
            _parse_encrypted,
            core_schema.union_schema(
                [core_schema.is_instance_schema(EncryptedValue), inner]
            ),
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
