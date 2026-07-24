"""密文落盘与解密契约验证。

验证 EncryptedValue 的内存常态为密文、落盘必为密文前缀、
ExportContext 控制解密导出、历史格式迁移以及非字符串拒绝。
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from app.configuration import (
    EncryptedValue,
    EncryptedValueError,
    ExportContext,
    encrypted,
    read_wire_toml,
    write_wire_toml,
)
from app.utils.security import (
    DPAPI_APPLICATION_ENTROPY,
    DPAPI_CONFIG_PREFIX,
    dpapi_encrypt,
    is_probable_dpapi_ciphertext,
)

_DPAPI_BLOB_HEADER = bytes.fromhex(
    "01000000d08c9ddf0115d1118c7a00c04fc297eb"
)


class _FakeWin32Crypt:
    """带 entropy 区分的小型 DPAPI 替身，用于确定性测试。"""

    def __init__(self) -> None:
        self.protect_entropies: list[bytes | None] = []
        self.unprotect_entropies: list[bytes | None] = []

    @staticmethod
    def _prefix(entropy: bytes | None) -> bytes:
        if entropy == DPAPI_APPLICATION_ENTROPY:
            return b"app-bound:"
        if entropy is None:
            return b"legacy:"
        return b"custom:" + entropy + b":"

    def CryptProtectData(
        self,
        data: bytes,
        _description: str | None,
        entropy: bytes | None,
        *_args: object,
    ) -> bytes:
        self.protect_entropies.append(entropy)
        return _DPAPI_BLOB_HEADER + self._prefix(entropy) + data

    def CryptUnprotectData(
        self,
        data: bytes,
        entropy: bytes | None,
        *_args: object,
    ) -> tuple[str, bytes]:
        self.unprotect_entropies.append(entropy)
        if not data.startswith(_DPAPI_BLOB_HEADER):
            raise OSError("invalid DPAPI blob")
        data = data[len(_DPAPI_BLOB_HEADER) :]
        prefix = self._prefix(entropy)
        if not data.startswith(prefix):
            raise OSError("entropy mismatch")
        return ("", data[len(prefix) :])


def test_encrypted_value_ciphertext_on_disk(tmp_path):
    """密文落盘时以 DPAPI:v1: 开头且不含明文。"""
    with patch("app.utils.security.win32crypt", _FakeWin32Crypt()):
        ev = EncryptedValue.from_string("secret-token")
        cipher = ev.ciphertext()
        assert cipher.startswith(DPAPI_CONFIG_PREFIX)
        assert "secret-token" not in cipher

        path = tmp_path / "secrets.toml"
        write_wire_toml(path, {"secrets": {"token": cipher}})

        content = path.read_text(encoding="utf-8")
        assert DPAPI_CONFIG_PREFIX in content
        assert "secret-token" not in content

        restored = read_wire_toml(path)
        assert restored["secrets"]["token"] == cipher


def test_export_context_if_decrypt_true_returns_plaintext():
    """ExportContext(if_decrypt=True) 导出明文，if_decrypt=False 导出密文。"""
    with patch("app.utils.security.win32crypt", _FakeWin32Crypt()):

        class SecretModel(BaseModel):
            token: Annotated[str, encrypted()] = ""

        model = SecretModel(token="secret-token")

        plaintext_dump = model.model_dump(
            context=ExportContext(if_decrypt=True)
        )
        assert plaintext_dump["token"] == "secret-token"

        ciphertext_dump = model.model_dump(
            context=ExportContext(if_decrypt=False)
        )
        cipher = ciphertext_dump["token"]
        assert cipher.startswith(DPAPI_CONFIG_PREFIX)
        assert "secret-token" not in cipher


def test_empty_encrypted_value_roundtrip(tmp_path):
    """空字符串加密值落盘与读回均无密文前缀。"""
    ev = EncryptedValue.from_string("")
    assert ev.ciphertext() == ""

    path = tmp_path / "empty.toml"
    write_wire_toml(path, {"secrets": {"token": ""}})

    content = path.read_text(encoding="utf-8")
    assert DPAPI_CONFIG_PREFIX not in content

    restored = read_wire_toml(path)
    assert restored["secrets"]["token"] == ""


def test_legacy_dpapi_ciphertext_migration():
    """历史格式密文被识别为密文，解密后重包为 v1 格式并报告迁移。"""
    fake = _FakeWin32Crypt()
    with patch("app.utils.security.win32crypt", fake):
        secret = "legacy-v2-secret"
        # legacy v2 格式：DPAPI: + 裸 DPAPI blob（entropy=None）
        legacy_blob = dpapi_encrypt(secret, entropy=None)
        legacy_cipher = "DPAPI:" + legacy_blob

        assert is_probable_dpapi_ciphertext(legacy_cipher)

        ev = EncryptedValue.from_string(legacy_cipher)

        # 解密成功，明文与原始一致
        assert ev.plaintext() == secret

        # 迁移结果为 legacy_dpapi_rewrapped_to_v1
        assert ev.migration_outcome() == "legacy_dpapi_rewrapped_to_v1"

        # 密文已重包为当前 v1 格式
        new_cipher = ev.ciphertext()
        assert new_cipher.startswith(DPAPI_CONFIG_PREFIX)
        assert secret not in new_cipher


def test_encrypt_validator_rejects_non_string():
    """_validate_encrypted 对非字符串输入通过 pydantic ValidationError 拒绝。

    EncryptedValueError 继承 ValueError，pydantic v2 wrap validator 会将其
    包装为 ValidationError。验证错误消息中包含 "must be a string"。
    """
    from pydantic import ValidationError

    with patch("app.utils.security.win32crypt", _FakeWin32Crypt()):

        class SecretModel(BaseModel):
            token: Annotated[str, encrypted()] = ""

        with pytest.raises(ValidationError) as exc_int:
            SecretModel(token=12345)
        assert "must be a string" in str(exc_int.value)

        with pytest.raises(ValidationError) as exc_list:
            SecretModel(token=["not", "a", "string"])
        assert "must be a string" in str(exc_list.value)

        with pytest.raises(ValidationError) as exc_dict:
            SecretModel(token={"key": "value"})
        assert "must be a string" in str(exc_dict.value)
