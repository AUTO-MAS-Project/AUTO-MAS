"""SRC 的只读预取、快进安装和失败保护，使用本地 Git 仓库替代网络。"""

import asyncio
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import script_install
from app.task.SRC.tools import program_update as update


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def installation(tmp_path, monkeypatch):
    upstream = tmp_path / "remote"
    upstream.mkdir()
    git(upstream, "init", "-b", "main")
    git(upstream, "config", "user.name", "test")
    git(upstream, "config", "user.email", "test@example.test")
    (upstream / ".gitignore").write_text("config/\nsrc.exe\nnative-finished\n")
    (upstream / "code.py").write_text("old")
    (upstream / "installer.py").write_text(
        "from pathlib import Path\nPath('native-finished').write_text('done')\n"
    )
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "initial")
    root = tmp_path / "SRC"
    subprocess.run(
        ["git", "clone", str(upstream), str(root)], check=True, capture_output=True
    )
    (root / "src.exe").write_bytes(b"native")
    (root / "config").mkdir()
    python_executable = sys.executable.replace("\\", "/")
    deploy = f"Repository: https://src.example/repo\nBranch: main\nGitExecutable: git\nPythonExecutable: {python_executable}\nAutoUpdate: true\nEnableReload: true\n"
    (root / "config/deploy.yaml").write_text(deploy)
    (upstream / "code.py").write_text("new")
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "update")
    monkeypatch.setattr(update, "Config", SimpleNamespace(data_path=tmp_path / "cache"))
    monkeypatch.setattr(update, "assert_idle", lambda root: None)
    original = update.command

    async def transport(*args, **kwargs):
        return await original(
            *(
                str(upstream) if arg == "https://src.example/repo" else arg
                for arg in args
            ),
            **kwargs,
        )

    monkeypatch.setattr(update, "command", transport)
    return root, deploy


@pytest.mark.asyncio
async def test_prepare_is_read_only_then_apply_runs_native_installer(installation):
    root, deploy = installation
    before = git(root, "rev-parse", "HEAD")
    snapshot = {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    candidate = await update.prepare_update(root)
    assert candidate is not None
    assert snapshot == {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert git(root, "rev-parse", "HEAD") == before
    assert (root / "code.py").read_text() == "old"
    assert (root / "config/deploy.yaml").read_text() == deploy
    assert not (root / "native-finished").exists()
    with script_install.installation_access(root):
        await update.apply_update(root, candidate)
    assert (root / "code.py").read_text() == "new"
    assert (root / "native-finished").read_text() == "done"
    assert (root / "config/deploy.yaml").read_text() == deploy
    await update.confirm_current_install(root)


@pytest.mark.asyncio
async def test_changed_worktree_invalidates_prepared_update(installation):
    root, deploy = installation
    candidate = await update.prepare_update(root)
    (root / "code.py").write_text("user edit")
    with pytest.raises(ValueError):
        await update.apply_update(root, candidate)
    assert (root / "code.py").read_text() == "user edit"
    assert (root / "config/deploy.yaml").read_text() == deploy


@pytest.mark.asyncio
async def test_native_install_failure_blocks_run_and_restores_deploy(
    installation, monkeypatch
):
    root, deploy = installation
    candidate = await update.prepare_update(root)
    original = update.command

    async def fail_install(*args, **kwargs):
        if "installer.py" in args:
            raise script_install.InstallUnsafeError("native failed")
        return await original(*args, **kwargs)

    monkeypatch.setattr(update, "command", fail_install)
    with pytest.raises(script_install.InstallUnsafeError):
        await update.apply_update(root, candidate)
    assert (root / "config/deploy.yaml").read_text() == deploy
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)


@pytest.mark.asyncio
async def test_cancelled_write_waits_until_process_finishes(tmp_path, monkeypatch):
    finished = asyncio.Event()

    async def communicate():
        await finished.wait()
        return b"", b""

    process = SimpleNamespace(communicate=communicate, returncode=0)
    monkeypatch.setattr(
        update.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    operation = asyncio.create_task(
        update.command("installer", cwd=tmp_path, writing=True)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    operation.cancel()
    await asyncio.sleep(0)
    assert not operation.done()
    finished.set()
    with pytest.raises(asyncio.CancelledError):
        await operation


def test_cached_git_objects_windows_readonly_cleanup(tmp_path):
    import stat

    cache = tmp_path / "objects"
    nested = cache / "pack"
    nested.mkdir(parents=True)
    child = nested / "object"
    child.write_text("git object")
    child.chmod(stat.S_IREAD)
    update.remove_cached_git_objects(cache)
    assert not cache.exists()


def test_independent_user_deploy_restores_only_injected_update_fields(tmp_path):
    from app.task.SRC.tools.config import save_src_user_config

    root = tmp_path / "SRC"
    src_config = root / "config"
    src_config.mkdir(parents=True)
    user = tmp_path / "independent"
    user.mkdir()
    (src_config / "src.json").write_text('{"Alas":{}}')
    (user / "src.json").write_text('{"Alas":{}}')
    (src_config / "deploy.yaml").write_text(
        "AutoUpdate: false\\nEnableReload: false\\n"
        "AppAsarUpdate: false\\nBranch: dev\\n"
    )
    (user / "deploy.yaml").write_text(
        "AutoUpdate: true\\nEnableReload: true\\nAppAsarUpdate: true\\nBranch: main\\n"
    )
    save_src_user_config(
        src_config,
        user,
        runtime_deploy_baseline={
            "AutoUpdate": False,
            "EnableReload": False,
            "AppAsarUpdate": False,
        },
    )
    result = (user / "deploy.yaml").read_text()
    assert "AutoUpdate: true" in result
    assert "EnableReload: true" in result
    assert "AppAsarUpdate: true" in result
    assert "Branch: dev" in result


def test_src_launch_gate_refuses_unconfirmed_install(tmp_path, monkeypatch):
    root = tmp_path / "SRC"
    (root / "config").mkdir(parents=True)
    marker = script_install.workspace(root) / "src-install.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}")
    monkeypatch.setattr(update, "assert_idle", lambda root, **kwargs: None)
    with pytest.raises(script_install.InstallUnsafeError):
        update.assert_safe_to_launch(root)
