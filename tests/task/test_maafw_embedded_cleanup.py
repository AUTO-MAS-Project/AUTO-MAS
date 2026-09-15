"""启动清理对内嵌副本的口径：按有效根判 venv 归属；清 staging 半成品与无主副本。"""

import os
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import AppConfig
from app.task.MaaFW.tools.core.automas_maafw_agent_env.planner import (
    compute_isolated_venv_path,
)
from app.task.MaaFW.tools.embedded.embedded_project import embedded_project_dir


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _age(path: Path, days: float = 2) -> None:
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


@pytest.mark.asyncio
async def test_venv_cleanup_keeps_the_copy_venv_of_an_embedded_script(
    tmp_path: Path,
) -> None:
    # 内嵌脚本的 agent venv 是按副本路径哈希的；拿来源目录去算存活集合会把它当孤儿删掉。
    # 来源目录不能在工作目录之下（FileValidator 拒绝项目根内的路径），放在旁边。
    source = tmp_path / "src"
    _write(source / "interface.json", "{}")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    with patch("app.core.config.Path.cwd", return_value=cwd):
        manager = AppConfig()
        uid, script = await manager.add_script("MaaFW")
        await script.update(
            {"Info": {"Path": str(source)}, "Embedded": {"Enabled": True}}
        )
        copy = embedded_project_dir(str(uid), cwd)
        _write(copy / "interface.json", "{}")

        venv_root = cwd / "config" / "maafw_agent_venvs"
        copy_venv = compute_isolated_venv_path(copy, managed_env_root=venv_root)
        source_venv = compute_isolated_venv_path(source, managed_env_root=venv_root)
        for venv in (copy_venv, source_venv):
            _write(venv / "pyvenv.cfg", "home = x")
            _age(venv)

        await manager.clean_maafw_agent_venvs()

    assert copy_venv.is_dir()
    # 来源目录不再是有效根，它的 venv 才是孤儿。
    assert not source_venv.exists()


@pytest.mark.asyncio
async def test_embedded_copy_cleanup_removes_only_our_own_garbage(
    tmp_path: Path,
) -> None:
    with patch("app.core.config.Path.cwd", return_value=tmp_path):
        manager = AppConfig()
        uid, _script = await manager.add_script("MaaFW")
        root = tmp_path / "data" / "maafw_projects"
        live = root / str(uid)
        orphan = root / str(uuid.uuid4())
        leftover = root / ".staging" / f"{uuid.uuid4()}-abcd1234"
        stranger = root / "not-a-uuid"
        for directory in (live, orphan, leftover, stranger):
            _write(directory / "interface.json", "{}")

        await manager.clean_maafw_embedded_copies()

    assert (live / "interface.json").is_file()
    assert not orphan.exists()
    assert not leftover.exists()
    assert (root / ".staging").is_dir()
    # 名字不是 uuid 形状的目录不是我们铺的，不碰。
    assert (stranger / "interface.json").is_file()
