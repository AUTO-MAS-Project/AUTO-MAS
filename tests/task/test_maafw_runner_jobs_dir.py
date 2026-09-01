"""MaaFW job 文件落盘目录改用 `data/` 后的路径与旧目录迁移回归

AUTO-MAS-Runtime 监督器接管后把 `<app-root>/runtime/` 当自己的地盘（uv 工具、
受管 Python、venv、缓存），后端不能再用同名目录落盘 job 文件，需要改存受保护
的 `data/` 目录；用户机器上可能已有旧 `runtime/maafw_runner_jobs`，首次访问
新路径时要整体搬迁过去，不能丢历史 job 文件。
"""

from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.embedded.runner_task import _maafw_runner_jobs_dir


def test_new_path_is_used_under_data_dir(tmp_path: Path, monkeypatch) -> None:
    """无历史目录时，job 落盘目录必须落在 `data/` 下，不再是 `runtime/`。"""

    monkeypatch.chdir(tmp_path)

    work_dir = _maafw_runner_jobs_dir()

    assert work_dir == tmp_path / "data" / "maafw_runner_jobs"
    assert not (tmp_path / "runtime").exists()


def test_legacy_runtime_dir_is_migrated_on_first_access(
    tmp_path: Path, monkeypatch
) -> None:
    """旧 `runtime/maafw_runner_jobs` 有历史 job 文件时，首次访问须整体搬到 `data/` 下。"""

    monkeypatch.chdir(tmp_path)
    legacy_dir = tmp_path / "runtime" / "maafw_runner_jobs"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "maafw-runner-job-legacy.json").write_text("{}", encoding="utf-8")

    work_dir = _maafw_runner_jobs_dir()

    assert work_dir == tmp_path / "data" / "maafw_runner_jobs"
    assert (
        work_dir / "maafw-runner-job-legacy.json"
    ).read_text(encoding="utf-8") == "{}"
    assert not legacy_dir.exists()
