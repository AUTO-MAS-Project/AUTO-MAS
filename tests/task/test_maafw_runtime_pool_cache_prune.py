"""运行池 uv 缓存 prune 对 Runtime 注入缓存的处理。

受监督时 ``AUTO_MAS_UV_CACHE_DIR`` 指向 Runtime 主项目也在用的共享缓存，池不能
替它 prune；未注入时仍 prune 池自己的缓存，但超时要短，失败只记录、不阻塞任务收尾。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import cache as cache_module
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.cache import prune_uv_cache
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
    AUTO_MAS_UV_CACHE_DIR_ENV,
    UV_CACHE_RELATIVE_PATH,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AUTO_MAS_UV_CACHE_DIR_ENV, raising=False)


def _stub_uv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    calls: list[list[str]] = []
    fake_uv = tmp_path / "uv.exe"
    fake_uv.write_text("", encoding="utf-8")

    def fake_run(command, **kwargs):  # noqa: ANN001 - 打桩
        calls.append(list(command))
        calls.append([f"timeout={kwargs.get('timeout')}"])
        return subprocess.CompletedProcess(command, 0, "Removed 0 entries", "")

    monkeypatch.setattr(cache_module.subprocess, "run", fake_run)
    monkeypatch.setattr(cache_module, "_find_uv_executable", lambda _b: str(fake_uv))
    monkeypatch.setattr(cache_module, "_uv_version", lambda _u: "0.12.3")
    return calls


def test_injected_cache_dir_is_never_pruned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_root = tmp_path / "pool"
    shared_cache = tmp_path / "runtime" / "cache" / "uv"
    shared_cache.mkdir(parents=True)
    monkeypatch.setenv(AUTO_MAS_UV_CACHE_DIR_ENV, str(shared_cache))
    calls = _stub_uv(monkeypatch, tmp_path)

    result = prune_uv_cache(pool_root, dry_run=False)

    assert result["status"] == "skipped"
    assert result["injected"] is True
    assert result["attempted"] is False
    assert Path(result["cachePath"]) == shared_cache.resolve()
    assert result["relativeToPool"] is None
    assert AUTO_MAS_UV_CACHE_DIR_ENV in result["reason"]
    assert calls == [], "注入的共享缓存不能起 uv cache prune"


def test_pool_local_cache_is_pruned_with_short_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_root = tmp_path / "pool"
    (pool_root / UV_CACHE_RELATIVE_PATH).mkdir(parents=True)
    calls = _stub_uv(monkeypatch, tmp_path)

    result = prune_uv_cache(pool_root, dry_run=False)

    assert result["status"] == "pruned"
    assert result.get("injected") is None
    assert calls[0][1:3] == ["cache", "prune"]
    assert calls[1] == [f"timeout={cache_module.UV_CACHE_PRUNE_TIMEOUT_SECONDS}"]
    assert cache_module.UV_CACHE_PRUNE_TIMEOUT_SECONDS <= 60


def test_prune_timeout_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_root = tmp_path / "pool"
    (pool_root / UV_CACHE_RELATIVE_PATH).mkdir(parents=True)
    _stub_uv(monkeypatch, tmp_path)

    def slow_run(command, **kwargs):  # noqa: ANN001 - 打桩
        raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))

    monkeypatch.setattr(cache_module.subprocess, "run", slow_run)

    result = prune_uv_cache(pool_root, dry_run=False)

    assert result["status"] == "error"
    assert "timed out" in result["error"]
