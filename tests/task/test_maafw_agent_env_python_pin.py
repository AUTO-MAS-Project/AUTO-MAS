"""内嵌副本要求的 Python 大版本决定隔离 venv 的引导解释器。

投影把项目自带的 python/ 去掉了，agent 却常写死大版本（create-maa-project 模板要求
>=3.13,<3.14）：用宿主 3.12 建的隔离 venv 会被 agent 拒绝，宿主只看到「Agent 进程
已退出」。实测 M9A v4.9.0 的副本就是这么挂的。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from app.task.MaaFW.tools.core.automas_maafw_agent_env import env as agent_env

HOST_MINOR = f"{sys.version_info[0]}.{sys.version_info[1]}"
OTHER_MINOR = "3.13" if HOST_MINOR != "3.13" else "3.12"


def _marker(root: Path, python_version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".auto_mas_maafw_projection.json").write_text(
        json.dumps(
            {
                "version": 1,
                "bundledMaaFWVersion": "5.13.0",
                "bundledPythonVersion": python_version,
            }
        ),
        encoding="utf-8",
    )


def test_requirement_is_read_from_the_marker_and_validated(tmp_path: Path) -> None:
    assert agent_env.read_projected_python_requirement(tmp_path) is None
    _marker(tmp_path, "3.13")
    assert agent_env.read_projected_python_requirement(tmp_path) == "3.13"
    _marker(tmp_path, "garbage")
    assert agent_env.read_projected_python_requirement(tmp_path) is None
    _marker(tmp_path, "")
    assert agent_env.read_projected_python_requirement(tmp_path) is None


def test_matching_bootstrap_interpreter_is_kept(tmp_path: Path) -> None:
    logs: list[str] = []
    chosen = agent_env._bootstrap_python_for_requirement(
        HOST_MINOR, sys.executable, logs.append
    )
    assert chosen == sys.executable
    assert logs == []


def test_mismatched_requirement_asks_the_runtime_pool(tmp_path: Path) -> None:
    logs: list[str] = []
    requests: list[dict] = []

    class FakePool:
        def resolve_python(self, request, *, allow_install):
            requests.append({**request, "allow_install": allow_install})
            return {"executable": r"D:\pool\python\cpython-3.13\python.exe"}

    class FakeService:
        pool = FakePool()

    with patch(
        "app.task.MaaFW.tools.core.automas_maafw_runtime_pool.MaaFWRuntimePoolService",
        FakeService,
    ):
        chosen = agent_env._bootstrap_python_for_requirement(
            OTHER_MINOR, sys.executable, logs.append
        )

    assert chosen == r"D:\pool\python\cpython-3.13\python.exe"
    assert requests == [
        {
            "implementation": "cpython",
            "constraint": f"=={OTHER_MINOR}.*",
            "allow_install": True,
        }
    ]


def test_pool_failure_falls_back_to_the_given_interpreter(tmp_path: Path) -> None:
    logs: list[str] = []

    class FakePool:
        def resolve_python(self, request, *, allow_install):
            raise RuntimeError("no supported CPython target")

    class FakeService:
        pool = FakePool()

    with patch(
        "app.task.MaaFW.tools.core.automas_maafw_runtime_pool.MaaFWRuntimePoolService",
        FakeService,
    ):
        chosen = agent_env._bootstrap_python_for_requirement(
            OTHER_MINOR, sys.executable, logs.append
        )

    assert chosen == sys.executable
    assert any("no supported CPython target" in line for line in logs)


def test_venv_version_check_reads_pyvenv_cfg(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = x\nversion = 3.13.4\n", encoding="utf-8")
    assert agent_env._venv_python_version(venv) == "3.13.4"
    assert agent_env._venv_python_matches(venv, "3.13")
    assert not agent_env._venv_python_matches(venv, "3.12")


def test_manifest_change_in_python_requirement_forces_a_rebuild(tmp_path: Path) -> None:
    # 已有的 3.12 venv 在项目开始要求 3.13 后必须重建：清单里多了一项就够。
    project = tmp_path / "project"
    project.mkdir()
    (project / "interface.json").write_text("{}", encoding="utf-8")
    before = agent_env.build_agent_env_manifest(project)
    _marker(project, "3.13")
    after = agent_env.build_agent_env_manifest(project)
    assert before["pythonRequirement"] == ""
    assert after["pythonRequirement"] == "3.13"


def test_existing_venv_with_the_wrong_python_is_rebuilt(tmp_path: Path) -> None:
    # 实测：升级前建的 3.12 venv 在项目开始要求 3.13 后仍被判「已存在」，agent 起来即退。
    project = tmp_path / "project"
    project.mkdir()
    (project / "interface.json").write_text("{}", encoding="utf-8")
    venv = tmp_path / "maafw_agent_venvs" / "maafw_venv_deadbeef"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(
        f"home = {Path(sys.executable).parent}\nversion = 3.12.13\n", encoding="utf-8"
    )
    scripts = venv / ("Scripts" if sys.platform == "win32" else "bin")
    scripts.mkdir()
    agent_env.venv_python_exe(venv).write_text("", encoding="utf-8")
    manifest = agent_env.build_agent_env_manifest(project)
    (venv / agent_env.AGENT_ENV_MANIFEST_NAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    logs: list[str] = []

    with patch.object(agent_env, "venv_base_python_missing", lambda _path: False):
        assert (
            agent_env._should_rebuild_isolated_venv(venv, project, logs.append) is False
        )
        _marker(project, "3.13")
        assert (
            agent_env._should_rebuild_isolated_venv(venv, project, logs.append) is True
        )
        assert agent_env._is_isolated_venv_manifest_current(venv, project) is False

    assert any("不是项目要求的 3.13" in line for line in logs)
