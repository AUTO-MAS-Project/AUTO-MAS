"""通用旧目录迁移辅助函数 `migrate_legacy_dir` 的纯逻辑回归测试

AUTO-MAS-Runtime 监督器接管后把 `<app-root>/runtime/` 当自己的地盘，后端两处
落盘（MaaFW job 文件、HSR SRA 临时配置）改存 `data/` 下，用户机器上已有的旧
`runtime/` 数据需要在首次访问新路径时自动搬迁，不能静默丢失。
"""

from pathlib import Path

from app.utils.io import migrate_legacy_dir


def test_moves_old_dir_to_new_path_when_new_path_is_missing(tmp_path: Path) -> None:
    """旧目录存在、新目录不存在：整体搬迁，旧目录本身不再残留。"""

    old_dir = tmp_path / "runtime" / "maafw_runner_jobs"
    old_dir.mkdir(parents=True)
    (old_dir / "job.json").write_text("{}", encoding="utf-8")

    new_dir = tmp_path / "data" / "maafw_runner_jobs"

    assert migrate_legacy_dir(old_dir, new_dir) is True
    assert (new_dir / "job.json").read_text(encoding="utf-8") == "{}"
    assert not old_dir.exists()


def test_does_nothing_when_new_path_already_exists(tmp_path: Path) -> None:
    """新目录已存在：即便旧目录还在，也不覆盖新目录、不触碰旧目录（只做一次）。"""

    old_dir = tmp_path / "runtime" / "maafw_runner_jobs"
    old_dir.mkdir(parents=True)
    (old_dir / "old-job.json").write_text("old", encoding="utf-8")

    new_dir = tmp_path / "data" / "maafw_runner_jobs"
    new_dir.mkdir(parents=True)
    (new_dir / "new-job.json").write_text("new", encoding="utf-8")

    assert migrate_legacy_dir(old_dir, new_dir) is False
    assert (new_dir / "new-job.json").read_text(encoding="utf-8") == "new"
    assert not (new_dir / "old-job.json").exists()
    assert (old_dir / "old-job.json").exists()


def test_does_nothing_when_old_path_is_missing(tmp_path: Path) -> None:
    """旧目录不存在：不凭空创建新目录，留给调用方按正常首次使用流程创建。"""

    old_dir = tmp_path / "runtime" / "maafw_runner_jobs"
    new_dir = tmp_path / "data" / "maafw_runner_jobs"

    assert migrate_legacy_dir(old_dir, new_dir) is False
    assert not new_dir.exists()


def test_failure_is_swallowed_as_a_warning_and_does_not_raise(
    tmp_path: Path, monkeypatch
) -> None:
    """迁移失败（如跨设备移动出错）只记 warning，不向上抛出、不阻塞调用方。"""

    old_dir = tmp_path / "runtime" / "maafw_runner_jobs"
    old_dir.mkdir(parents=True)
    (old_dir / "job.json").write_text("{}", encoding="utf-8")

    new_dir = tmp_path / "data" / "maafw_runner_jobs"

    def boom(*_args, **_kwargs):
        raise OSError("simulated cross-device move failure")

    monkeypatch.setattr("app.utils.io.shutil.move", boom)

    assert migrate_legacy_dir(old_dir, new_dir) is False
    assert not new_dir.exists()
    # 旧目录原样保留，下次访问还有机会重试迁移。
    assert (old_dir / "job.json").exists()
