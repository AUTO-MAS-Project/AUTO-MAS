"""运行池 uv 安装路径上的 binding 兜底触发判据与 attempts 收集的纯逻辑回归。

``subprocess.run`` 全部打桩：不建 venv、不装依赖、不联网。兜底本身（下载 → 打 wheel）
用池缓存里预置的最小源码包走真实的 ``ensure_binding_wheel``，只有 HTTP 那一步被
断言不会发生。stderr 夹具是 uv 0.11.26 的原文（含折行）。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.task.MaaFW.tools.core.automas_maafw_runner import (
    environment as runner_environment,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
    installer as installer_module,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding_fallback import (
    BINDING_SRC_CACHE_RELATIVE_PATH,
    MaaFWBindingFallbackError,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.host_environment import (
    subprocess_proxy_scope,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
    AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
    AUTO_MAS_UV_INDEX_URL_ENV,
    MaaFWRuntimeSourceRotationError,
    _install_requirements_with_uv,
)

UV_MISSING_VERSION_STDERR = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because there is no version of maafw==5.14.0b1 and you require\n"
    "      maafw==5.14.0b1, we can conclude that your requirements are\n"
    "      unsatisfiable.\n"
)
UV_NETWORK_STDERR = (
    "error: Failed to fetch: `https://mirror.invalid/simple/maafw/`\n"
    "  Caused by: Request failed after 3 retries\n"
)
UV_OFFLINE_STDERR = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because maafw was not found in the cache and you require\n"
    "      maafw==5.14.0b1, we can conclude that your requirements are\n"
    "      unsatisfiable.\n"
)

FIVE_CANDIDATES = (
    "http://127.0.0.1:41234/simple/",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://mirrors.ustc.edu.cn/pypi/simple/",
    "https://pypi.org/simple/",
)
REQUIREMENTS = (
    "json-with-comments",
    "json5==0.14.0",
    "maafw==5.14.0b1",
    "packaging",
    "psutil",
    "pydantic==2.11.7",
)


class _FakeCompleted:
    def __init__(self, returncode: int, *, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV,
        AUTO_MAS_UV_INDEX_URL_ENV,
        "UV_INDEX_URL",
        "UV_DEFAULT_INDEX",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def pool_root(tmp_path: Path) -> Path:
    """池根，源码包缓存里预置 v5.14.0-beta.1 的最小 tag 包，兜底不需要联网。"""

    root = tmp_path / "pool"
    src_dir = root / BINDING_SRC_CACHE_RELATIVE_PATH
    src_dir.mkdir(parents=True)
    top = "MaaFramework-5.14.0-beta.1"
    base = f"{top}/source/binding/Python/"
    with zipfile.ZipFile(src_dir / "v5.14.0-beta.1.zip", "w") as zf:
        zf.writestr(f"{top}/LICENSE.md", "LGPL\n")
        zf.writestr(
            f"{base}pyproject.toml",
            '[project]\nname = "MaaFw"\nversion = "0"\nrequires-python = ">=3.9"\n'
            'dependencies = ["numpy", "strenum", "MaaAgentBinary"]\n',
        )
        zf.writestr(f"{base}maa/__init__.py", "")
        zf.writestr(f"{base}maa/library.py", "")
    return root


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args, **_kwargs):
        raise AssertionError("测试里不得联网")

    monkeypatch.setattr(
        "app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding_fallback._download_to_file",
        _fail,
    )


def _install(
    tmp_path: Path,
    *,
    pool_root: Path | None,
    log=None,
    requirements=REQUIREMENTS,
    proxy_url: str | None = None,
):
    return _install_requirements_with_uv(
        "uv.exe",
        tmp_path / "envs" / "shared" / "Scripts" / "python.exe",
        list(requirements),
        cache_dir=tmp_path / "cache",
        link_mode="hardlink",
        cwd=tmp_path,
        pool_root=pool_root,
        proxy_url=proxy_url,
        log=log,
    )


def _requirement_args(command: list[str]) -> list[str]:
    """命令末尾的 requirement 位置参数（``--quiet`` 之后，去掉 --index-url 对）。"""

    tail = command[command.index("--quiet") + 1 :]
    if tail and tail[0] == "--index-url":
        tail = tail[2:]
    return tail


# ---------------------------------------------------------------------------
# 触发：五个候选全失败，其中任一说「索引上没有 maafw==X」
# ---------------------------------------------------------------------------


def test_fallback_rebuilds_binding_and_reruns_with_local_wheel(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, ";".join(FIVE_CANDIDATES))
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        if len(calls) <= 5:
            # 中继连不上，四个镜像都说没有这个版本
            stderr = UV_NETWORK_STDERR if len(calls) == 1 else UV_MISSING_VERSION_STDERR
            return _FakeCompleted(1, stderr=stderr)
        return _FakeCompleted(0)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)
    logs: list[str] = []

    result = _install(tmp_path, pool_root=pool_root, log=logs.append)

    # 5 轮失败 + 兜底后第一轮就成功
    assert len(calls) == 6
    for command in calls[:5]:
        assert _requirement_args(command) == list(REQUIREMENTS)
    rerun = _requirement_args(calls[5])
    assert "maafw==5.14.0b1" not in rerun
    wheel_args = [item for item in rerun if item.startswith("maafw @ file:///")]
    assert len(wheel_args) == 1
    assert wheel_args[0].endswith("/maafw-5.14.0b1-py3-none-any.whl")
    assert "\\" not in wheel_args[0]
    # 其余 requirement 原位不动
    assert [item for item in rerun if not item.startswith("maafw")] == [
        item for item in REQUIREMENTS if not item.startswith("maafw")
    ]
    # 重跑仍按候选轮换：第一个候选就是中继
    assert calls[5][calls[5].index("--index-url") + 1] == FIVE_CANDIDATES[0]
    wheel_path = Path(wheel_args[0].removeprefix("maafw @ file:///"))
    assert wheel_path.is_file()
    assert wheel_path.parent == pool_root / "cache" / "binding-wheels"

    assert result == {
        "source": FIVE_CANDIDATES[0],
        "attempt": 1,
        "bindingSource": "github-source:v5.14.0-beta.1",
    }
    assert (
        "PyPI 无 maafw 5.14.0b1，改用 MaaFramework v5.14.0-beta.1 源码打包的 binding"
        in logs
    )


def test_fallback_without_candidates_reports_binding_source_only(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    # 未受监督：候选为 None，只跑「不指定索引」一次
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        if len(calls) == 1:
            return _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR)
        return _FakeCompleted(0)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    result = _install(tmp_path, pool_root=pool_root)

    assert len(calls) == 2
    assert "--index-url" not in calls[1]
    assert result == {"bindingSource": "github-source:v5.14.0-beta.1"}


# ---------------------------------------------------------------------------
# 不触发
# ---------------------------------------------------------------------------


def test_network_failures_do_not_trigger_fallback_but_keep_every_attempt(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, ";".join(FIVE_CANDIDATES))
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _FakeCompleted(
            1, stderr=UV_NETWORK_STDERR.replace("mirror.invalid", str(len(calls)))
        )

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)
    logs: list[str] = []

    with pytest.raises(MaaFWRuntimeSourceRotationError) as excinfo:
        _install(tmp_path, pool_root=pool_root, log=logs.append)

    assert len(calls) == 5
    assert [source for source, _, _ in excinfo.value.attempts] == list(FIVE_CANDIDATES)
    assert [code for _, code, _ in excinfo.value.attempts] == [1] * 5
    assert "https://1/simple" in excinfo.value.attempts[0][2]
    assert "https://5/simple" in str(excinfo.value)
    assert "GitHub 兜底" not in str(excinfo.value)
    assert not logs
    assert not (pool_root / "cache" / "binding-wheels").exists()


def test_offline_bypass_does_not_trigger_fallback(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    monkeypatch.setenv(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, "")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _FakeCompleted(1, stderr=UV_OFFLINE_STDERR)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="was not found in the cache"):
        _install(tmp_path, pool_root=pool_root)

    assert len(calls) == 1
    assert "--offline" in calls[0]
    assert not (pool_root / "cache" / "binding-wheels").exists()


def test_explicit_uv_index_url_bypass_does_not_trigger_fallback(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    monkeypatch.setenv("UV_INDEX_URL", "https://user-set.invalid/simple")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="there is no version of maafw"):
        _install(tmp_path, pool_root=pool_root)

    assert len(calls) == 1
    assert not (pool_root / "cache" / "binding-wheels").exists()


def test_non_exact_maafw_requirement_does_not_trigger_fallback(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(MaaFWRuntimeSourceRotationError):
        _install(
            tmp_path, pool_root=pool_root, requirements=("maafw>=5.14.0b1", "psutil")
        )
    assert len(calls) == 1


def test_missing_pool_root_disables_fallback(
    tmp_path: Path, monkeypatch, no_network
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(MaaFWRuntimeSourceRotationError):
        _install(tmp_path, pool_root=None)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# 兜底本身失败：原错误 + 「GitHub 兜底也失败」
# ---------------------------------------------------------------------------


def test_fallback_download_failure_is_appended_to_original_error(
    tmp_path: Path, monkeypatch
) -> None:
    empty_pool = tmp_path / "pool"  # 没有预置源码包，会尝试下载

    def _refuse(*_args, **_kwargs):
        raise MaaFWBindingFallbackError("HTTP 404")

    monkeypatch.setattr(
        "app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding_fallback._download_to_file",
        _refuse,
    )
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)
    logs: list[str] = []

    with pytest.raises(RuntimeError) as excinfo:
        _install(tmp_path, pool_root=empty_pool, log=logs.append)

    message = str(excinfo.value)
    assert message.startswith("MaaFW runtime 依赖安装失败 (exit=1)")
    assert "there is no version of maafw==5.14.0b1" in message
    assert "；GitHub 兜底也失败：" in message
    assert "v5.14.0-beta.1" in message
    assert "HTTP 404" in message
    assert len(calls) == 1  # 没有重跑
    assert not any("改用 MaaFramework" in line for line in logs)


def test_fallback_reinstall_failure_is_appended_to_original_error(
    tmp_path: Path, monkeypatch, pool_root: Path, no_network
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        if len(calls) == 1:
            return _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR)
        return _FakeCompleted(2, stderr="error: Failed to install numpy: disk full")

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as excinfo:
        _install(tmp_path, pool_root=pool_root)

    message = str(excinfo.value)
    assert "there is no version of maafw==5.14.0b1" in message
    assert "；GitHub 兜底也失败：安装源码打包的 binding 失败：" in message
    assert "disk full" in message
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# 代理串从作用域取（install_python_runtime 的取法），兜底下载用同一个
# ---------------------------------------------------------------------------


def test_fallback_passes_proxy_url_to_downloader(tmp_path: Path, monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_ensure(
        version, pool_root, *, proxy_url=None, check_cancelled=None, log=None
    ):
        seen["version"] = version
        seen["proxy_url"] = proxy_url
        raise MaaFWBindingFallbackError("stop here")

    monkeypatch.setattr(installer_module, "ensure_binding_wheel", fake_ensure)
    monkeypatch.setattr(
        installer_module.subprocess,
        "run",
        lambda command, **_kwargs: _FakeCompleted(1, stderr=UV_MISSING_VERSION_STDERR),
    )

    with subprocess_proxy_scope("http://user:pw@proxy:3128"):
        with pytest.raises(RuntimeError, match="stop here"):
            _install(
                tmp_path,
                pool_root=tmp_path / "pool",
                proxy_url=installer_module.current_subprocess_proxy(),
            )
    assert seen == {"version": "5.14.0b1", "proxy_url": "http://user:pw@proxy:3128"}


# ---------------------------------------------------------------------------
# 无 DLL 项目守卫（runner/environment.py）
# ---------------------------------------------------------------------------


def test_guard_rejects_project_without_dll_on_source_built_binding(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    runtime = {"installerMetadata": {"bindingSource": "github-source:v5.14.0-beta.1"}}
    with pytest.raises(RuntimeError, match="项目未自带 MaaFramework 原生库"):
        runner_environment._guard_source_built_binding(project, runtime)


def test_guard_allows_project_with_bundled_dll(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "maafw").mkdir(parents=True)
    (project / "maafw" / "MaaFramework.dll").write_bytes(b"MZ")
    runtime = {"installerMetadata": {"bindingSource": "github-source:v5.14.0-beta.1"}}
    runner_environment._guard_source_built_binding(project, runtime)


def test_guard_ignores_runtimes_installed_from_index(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for runtime in (
        {},
        {"installerMetadata": {}},
        {"installerMetadata": {"index": {"source": "https://pypi.org/simple/"}}},
        {"installerMetadata": None},
    ):
        runner_environment._guard_source_built_binding(project, runtime)
