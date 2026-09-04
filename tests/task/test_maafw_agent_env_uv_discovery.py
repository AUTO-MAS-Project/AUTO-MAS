"""`automas_maafw_agent_env._find_uv_executable` 在受管模式下的发现优先级。

背景：受管模式下（AUTO-MAS-Runtime 用 Job Object 监督后端）没有便携 Python
（根目录不再有 ``environment/``），监督器改为用环境变量 ``AUTO_MAS_UV_EXE``
注入它已校验过的 uv 路径，也不会把这个 uv 加进 PATH——所以发现顺序必须优先
信这个环境变量，找不到（未设置或指向的文件不存在）再退回原有的便携路径与
PATH 查找。
"""

from pathlib import Path

import pytest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_agent_env import env as agent_env


def test_find_uv_executable_prefers_the_injected_supervisor_uv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_uv = tmp_path / "uv.exe"
    fake_uv.write_text("", encoding="utf-8")
    monkeypatch.setenv("AUTO_MAS_UV_EXE", str(fake_uv))

    found = agent_env._find_uv_executable()

    assert found == str(fake_uv.resolve())


def test_find_uv_executable_ignores_env_var_pointing_at_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 指向的文件不存在时不能直接采信，要继续走后面的候选链
    missing = tmp_path / "does-not-exist.exe"
    monkeypatch.setenv("AUTO_MAS_UV_EXE", str(missing))
    monkeypatch.chdir(tmp_path)  # cwd 下没有 environment/python/Scripts/uv.exe
    monkeypatch.setattr(agent_env.shutil, "which", lambda name: None)

    found = agent_env._find_uv_executable()

    assert found != str(missing)
    assert found is None


def test_find_uv_executable_falls_back_to_which_when_env_var_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 不设置 AUTO_MAS_UV_EXE 时，行为应与改动前一致：便携路径缺失就退回 PATH 查找
    monkeypatch.delenv("AUTO_MAS_UV_EXE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        agent_env.shutil,
        "which",
        lambda name: "C:/PATH/uv.exe" if name == "uv" else None,
    )

    found = agent_env._find_uv_executable()

    assert found == "C:/PATH/uv.exe"
