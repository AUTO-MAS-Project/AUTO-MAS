"""MaaFW 运行池复用 Runtime 基础设施（uv 缓存/Python 安装目录/镜像轮换）的纯逻辑回归。

覆盖契约 `doc/契约补充-v1-增补1.md` C11 与「新增注入环境变量」一节：受监督时
Runtime 经四个 ``AUTO_MAS_*`` 变量注入共享目录与有序镜像列表，池自行按序重试。
本文件只覆盖路径解析、候选列表构建与重试调度这三块纯逻辑，`subprocess.run`
全部打桩，不建 venv、不装依赖、不联网、不起子进程。
"""

import logging

import pytest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import installer as installer_module
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
    AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
    AUTO_MAS_MIRROR_PYTHON_ENV,
    AUTO_MAS_UV_CACHE_DIR_ENV,
    AUTO_MAS_UV_INDEX_URL_ENV,
    AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV,
    AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV,
    UV_CACHE_RELATIVE_PATH,
    UV_PYTHON_RELATIVE_PATH,
    _install_pool_managed_python,
    _install_requirements_with_uv,
    _resolve_python_mirror_candidates,
    resolve_package_index_candidates,
    resolve_python_install_dir,
    resolve_uv_cache_dir,
)

_LOGGER_NAME = "automas.maafw.runtime_pool.installer"

_ALL_RELEVANT_ENV_NAMES = (
    AUTO_MAS_UV_CACHE_DIR_ENV,
    AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV,
    AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
    AUTO_MAS_MIRROR_PYTHON_ENV,
    AUTO_MAS_UV_INDEX_URL_ENV,
    AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV,
    "UV_INDEX_URL",
    "UV_DEFAULT_INDEX",
    "UV_PYTHON_INSTALL_MIRROR",
)


class _FakeCompleted:
    def __init__(self, returncode: int, *, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # 每个用例独立起跑，不受运行本文件的真实 shell 环境或用例之间残留的影响。
    for name in _ALL_RELEVANT_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# resolve_uv_cache_dir / resolve_python_install_dir
# ---------------------------------------------------------------------------


def test_uv_cache_dir_defaults_to_pool_relative_path_when_unset(tmp_path) -> None:
    assert resolve_uv_cache_dir(tmp_path) == (tmp_path / UV_CACHE_RELATIVE_PATH).resolve()


def test_uv_cache_dir_uses_injected_absolute_path(tmp_path, monkeypatch) -> None:
    injected = tmp_path / "shared-cache" / "uv"
    injected.parent.mkdir(parents=True)
    monkeypatch.setenv(AUTO_MAS_UV_CACHE_DIR_ENV, str(injected))

    resolved = resolve_uv_cache_dir(tmp_path / "pool")

    assert resolved == injected.resolve()


def test_uv_cache_dir_ignores_relative_injected_value(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_CACHE_DIR_ENV, "relative/cache/uv")

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resolved = resolve_uv_cache_dir(tmp_path)

    assert resolved == (tmp_path / UV_CACHE_RELATIVE_PATH).resolve()
    assert "不是绝对路径" in caplog.text


def test_uv_cache_dir_ignores_injected_value_with_missing_parent(
    tmp_path, monkeypatch, caplog
) -> None:
    missing = tmp_path / "does-not-exist" / "uv"
    monkeypatch.setenv(AUTO_MAS_UV_CACHE_DIR_ENV, str(missing))

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resolved = resolve_uv_cache_dir(tmp_path)

    assert resolved == (tmp_path / UV_CACHE_RELATIVE_PATH).resolve()
    assert "父目录不存在" in caplog.text


def test_python_install_dir_defaults_to_pool_relative_path_when_unset(tmp_path) -> None:
    assert (
        resolve_python_install_dir(tmp_path) == (tmp_path / UV_PYTHON_RELATIVE_PATH).resolve()
    )


def test_python_install_dir_uses_injected_absolute_path(tmp_path, monkeypatch) -> None:
    injected = tmp_path / "shared-runtime" / "python"
    injected.parent.mkdir(parents=True)
    monkeypatch.setenv(AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV, str(injected))

    resolved = resolve_python_install_dir(tmp_path / "pool")

    assert resolved == injected.resolve()


def test_python_install_dir_ignores_relative_injected_value(
    tmp_path, monkeypatch, caplog
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV, "relative/python")

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resolved = resolve_python_install_dir(tmp_path)

    assert resolved == (tmp_path / UV_PYTHON_RELATIVE_PATH).resolve()
    assert "不是绝对路径" in caplog.text


def test_python_install_dir_ignores_injected_value_with_missing_parent(
    tmp_path, monkeypatch, caplog
) -> None:
    missing = tmp_path / "does-not-exist" / "python"
    monkeypatch.setenv(AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV, str(missing))

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resolved = resolve_python_install_dir(tmp_path)

    assert resolved == (tmp_path / UV_PYTHON_RELATIVE_PATH).resolve()
    assert "父目录不存在" in caplog.text


# ---------------------------------------------------------------------------
# resolve_package_index_candidates
# ---------------------------------------------------------------------------


def test_package_index_candidates_none_when_nothing_configured() -> None:
    assert resolve_package_index_candidates() is None


def test_package_index_candidates_blank_mirror_list_is_still_none(monkeypatch) -> None:
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, "  ; ; ")
    assert resolve_package_index_candidates() is None


def test_package_index_candidates_explicit_single_value_only(monkeypatch) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_INDEX_URL_ENV, "https://mirror-a.invalid/simple")
    assert resolve_package_index_candidates() == ["https://mirror-a.invalid/simple"]


def test_package_index_candidates_splits_trims_and_drops_empty_items(monkeypatch) -> None:
    monkeypatch.setenv(
        AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
        " https://mirror-a.invalid/simple ; ;https://mirror-b.invalid/simple;",
    )
    assert resolve_package_index_candidates() == [
        "https://mirror-a.invalid/simple",
        "https://mirror-b.invalid/simple",
    ]


def test_package_index_candidates_explicit_value_precedes_mirror_list(monkeypatch) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_INDEX_URL_ENV, "https://mirror-explicit.invalid/simple")
    monkeypatch.setenv(
        AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
        "https://mirror-a.invalid/simple;https://mirror-b.invalid/simple",
    )
    assert resolve_package_index_candidates() == [
        "https://mirror-explicit.invalid/simple",
        "https://mirror-a.invalid/simple",
        "https://mirror-b.invalid/simple",
    ]


def test_package_index_candidates_dedupes_across_explicit_and_mirror_list_in_order(
    monkeypatch,
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_INDEX_URL_ENV, "https://mirror-a.invalid/simple")
    monkeypatch.setenv(
        AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
        "https://mirror-a.invalid/simple;https://mirror-b.invalid/simple"
        ";https://mirror-b.invalid/simple",
    )
    assert resolve_package_index_candidates() == [
        "https://mirror-a.invalid/simple",
        "https://mirror-b.invalid/simple",
    ]


# ---------------------------------------------------------------------------
# _resolve_python_mirror_candidates
# ---------------------------------------------------------------------------


def test_python_mirror_candidates_none_when_nothing_configured() -> None:
    assert _resolve_python_mirror_candidates(explicit_mirror=None) is None


def test_python_mirror_candidates_orders_explicit_before_fallback_before_list(
    monkeypatch,
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV, "https://py-fallback.invalid")
    monkeypatch.setenv(AUTO_MAS_MIRROR_PYTHON_ENV, "https://py-a.invalid;https://py-b.invalid")

    assert _resolve_python_mirror_candidates(explicit_mirror="https://py-explicit.invalid") == [
        "https://py-explicit.invalid",
        "https://py-fallback.invalid",
        "https://py-a.invalid",
        "https://py-b.invalid",
    ]


# ---------------------------------------------------------------------------
# 包索引轮换：_install_requirements_with_uv
# ---------------------------------------------------------------------------


def test_index_rotation_retries_next_candidate_and_records_the_winner(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_INDEX_URL_ENV, "https://mirror-a.invalid/simple")
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, "https://mirror-b.invalid/simple")

    calls: list[dict] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, "env": kwargs.get("env")})
        if len(calls) == 1:
            return _FakeCompleted(1, stderr="connection reset")
        return _FakeCompleted(0)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    result = _install_requirements_with_uv(
        "uv.exe",
        tmp_path / "envs" / "shared" / "Scripts" / "python.exe",
        ["maafw==1.0"],
        cache_dir=tmp_path / "cache",
        link_mode="hardlink",
        cwd=tmp_path,
    )

    assert len(calls) == 2

    def _index_arg(command: list[str]) -> str:
        return command[command.index("--index-url") + 1]

    assert _index_arg(calls[0]["command"]) == "https://mirror-a.invalid/simple"
    assert _index_arg(calls[1]["command"]) == "https://mirror-b.invalid/simple"
    assert result == {"source": "https://mirror-b.invalid/simple", "attempt": 2}


def test_index_rotation_raises_the_last_error_after_every_candidate_fails(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_INDEX_URL_ENV, "https://mirror-a.invalid/simple")
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, "https://mirror-b.invalid/simple")

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        stderr = "first mirror down" if len(calls) == 1 else "second mirror down"
        return _FakeCompleted(1, stderr=stderr)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="second mirror down"):
        _install_requirements_with_uv(
            "uv.exe",
            tmp_path / "envs" / "shared" / "Scripts" / "python.exe",
            ["maafw==1.0"],
            cache_dir=tmp_path / "cache",
            link_mode="hardlink",
            cwd=tmp_path,
        )

    assert len(calls) == 2


def test_index_rotation_is_bypassed_when_uv_index_url_is_already_set(
    tmp_path, monkeypatch
) -> None:
    # 用户已经显式设置了 uv 原生的 UV_INDEX_URL：沿用 uv 自身的解析，不参与
    # 本机制的候选与重试，即使同时配置了 AUTO_MAS_MIRROR_PACKAGE_INDEX。
    monkeypatch.setenv("UV_INDEX_URL", "https://user-set.invalid/simple")
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, "https://mirror-b.invalid/simple")

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _FakeCompleted(0)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    result = _install_requirements_with_uv(
        "uv.exe",
        tmp_path / "envs" / "shared" / "Scripts" / "python.exe",
        ["maafw==1.0"],
        cache_dir=tmp_path / "cache",
        link_mode="hardlink",
        cwd=tmp_path,
    )

    assert len(calls) == 1
    assert "--index-url" not in calls[0]
    assert result is None


# ---------------------------------------------------------------------------
# Python 分发源轮换：_install_pool_managed_python
# ---------------------------------------------------------------------------


def test_python_distribution_mirror_rotation_switches_env_between_attempts(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV, "https://py-mirror-a.invalid")
    monkeypatch.setenv(AUTO_MAS_MIRROR_PYTHON_ENV, "https://py-mirror-b.invalid")

    calls: list[dict] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, "env": kwargs.get("env")})
        if len(calls) == 1:
            return _FakeCompleted(1, stderr="network unreachable")
        return _FakeCompleted(0)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    _install_pool_managed_python(
        "uv.exe",
        "3.13",
        pool_root=tmp_path,
        python_root=tmp_path / "python",
        cache_dir=tmp_path / "cache" / "uv",
    )

    assert len(calls) == 2
    assert calls[0]["env"]["UV_PYTHON_INSTALL_MIRROR"] == "https://py-mirror-a.invalid"
    assert calls[1]["env"]["UV_PYTHON_INSTALL_MIRROR"] == "https://py-mirror-b.invalid"
    # uv 的镜像只认环境变量，重试之间命令行本身不变。
    assert calls[0]["command"] == calls[1]["command"]


def test_python_distribution_mirror_rotation_raises_after_every_candidate_fails(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV, "https://py-mirror-a.invalid")

    def fake_run(command, **kwargs):
        return _FakeCompleted(1, stderr="still unreachable")

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="still unreachable"):
        _install_pool_managed_python(
            "uv.exe",
            "3.13",
            pool_root=tmp_path,
            python_root=tmp_path / "python",
            cache_dir=tmp_path / "cache" / "uv",
        )
