"""共享 fixture：独立 scratch config 目录与 AuthoritativeConfigurationRuntime 初始化助手。

所有 fixture 仅在 ``tempfile.TemporaryDirectory`` 中工作，绝不读取真实
用户 ``config/``。``NativeConfigFacade`` 与 ``AuthoritativeConfigurationRuntime``
共享同一个 owner 锁，因此测试必须显式 ``close()`` 释放，否则跨用例污染。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.configuration import authoritative as authoritative_module
from app.configuration import config_manager
from app.configuration.authoritative import (
    AuthoritativeConfigurationRuntime,
)
from app.configuration.roots.script import (
    EMULATOR_COLLECTION_NAME,
    PLAN_COLLECTION_NAME,
    SCRIPT_COLLECTION_NAME,
)

from .corpus_variants import build_all_variants, write_corpus_to_dir


_DPAPI_BLOB_HEADER = bytes.fromhex(
    "01000000d08c9ddf0115d1118c7a00c04fc297eb"
)


class _FakeWin32Crypt:
    """Portable, entropy-aware DPAPI substitute for synthetic recovery data.

    This fixture is deliberately limited to this test package.  It lets the
    recovery matrix use syntactically valid, decryptable test ciphertext on
    every Windows CI account without pretending that a redacted audit marker
    is a real DPAPI blob.
    """

    @staticmethod
    def _prefix(entropy: bytes | None) -> bytes:
        from app.utils.security import DPAPI_APPLICATION_ENTROPY

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
        return _DPAPI_BLOB_HEADER + self._prefix(entropy) + data

    def CryptUnprotectData(
        self,
        data: bytes,
        entropy: bytes | None,
        *_args: object,
    ) -> tuple[str, bytes]:
        if not data.startswith(_DPAPI_BLOB_HEADER):
            raise OSError("invalid DPAPI blob")
        body = data[len(_DPAPI_BLOB_HEADER) :]
        prefix = self._prefix(entropy)
        if not body.startswith(prefix):
            raise OSError("entropy mismatch")
        return ("", body[len(prefix) :])


@pytest.fixture(autouse=True)
def deterministic_dpapi():
    """Keep synthetic recovery corpus decryptable and platform-independent."""

    with patch("app.utils.security.win32crypt", _FakeWin32Crypt()) as fake:
        yield fake


@pytest.fixture(autouse=True)
def assert_authoritative_runtime_isolation():
    """让本包每个用例结束时暴露 runtime/registry 泄漏。"""

    yield

    assert not config_manager.in_transaction
    assert config_manager._prepare_commit_hook is None
    assert authoritative_module._OWNER is None
    for name in (
        EMULATOR_COLLECTION_NAME,
        PLAN_COLLECTION_NAME,
        SCRIPT_COLLECTION_NAME,
    ):
        with pytest.raises(LookupError):
            config_manager.get_collection(name)


@pytest.fixture
def scratch_config() -> Path:
    """每个测试独立 scratch config_dir；绝不读真实用户 config。

    使用 ``tempfile.TemporaryDirectory`` 而非 pytest ``tmp_path``：当前
    Windows 机器 ``LongPathsEnabled=0``，store 路径
    ``.config-v2-authoritative/<gen>/generations/g-<20d>-<32hex>/roots/<name>.bin``
    叠加在 ``.pytest_tmp`` 长基路径上会超过 MAX_PATH=260，导致
    ``store.commit()`` 的 ``_durable_move`` / ``_write_new_bytes`` 抛
    ``OSError``，被 coordinator ``except Exception`` 吞掉变成
    ``TransactionGenerationCommitError``。chaos 测试使用
    ``tempfile.TemporaryDirectory()``（短路径）且全部通过。
    """
    import tempfile

    tmpdir = tempfile.TemporaryDirectory(prefix="cv2rc_")
    config_dir = Path(tmpdir.name) / "config"
    config_dir.mkdir()
    try:
        yield config_dir
    finally:
        tmpdir.cleanup()


@pytest.fixture
def normal_corpus_config(scratch_config, deterministic_dpapi) -> Path:
    """写入 normal 脱敏语料的 scratch 目录。"""
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(variants["normal"]["corpus"], scratch_config)
    return scratch_config


def try_initialize(runtime: AuthoritativeConfigurationRuntime):
    """同步初始化 runtime，返回 (state, error)；失败时清理 owner。"""

    async def _do():
        return await runtime.initialize()

    try:
        state = asyncio.run(_do())
        return state, None
    except BaseException as exc:
        runtime.close()
        return None, exc


def safe_close(runtime: AuthoritativeConfigurationRuntime | None) -> None:
    if runtime is None:
        return
    runtime.close()
