from types import SimpleNamespace

import pytest

from app.task.HSR.tools.backup_archive import (
    archive_native_backup,
    restore_native_backup,
)
from app.task.HSR.tools.log_detect import detect_echo_of_war_completion
from app.task.HSR.tools.m7a_config import load_m7a_native_config


def write_m7a_version(root, version):
    marker = root / "assets" / "config" / "version.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text(version, encoding="utf-8")


def test_restore_legacy_archive_to_migrated_config(
    tmp_path, monkeypatch, isolated_app_paths
):
    monkeypatch.delenv("M7A_DATA_DIR", raising=False)
    root = tmp_path / "m7a"
    sra = tmp_path / "sra"
    write_m7a_version(root, "v2026.11.17")
    legacy = root / "config.yaml"
    legacy.write_text("daily_enable: true\n", encoding="utf-8")
    archived = archive_native_backup(root, sra)
    assert archived is not None

    (root / "assets" / "config" / "version.txt").write_text(
        "v2026.11.25-beta", encoding="utf-8"
    )
    current = root / "userdata" / "config.yaml"
    current.parent.mkdir()
    legacy.rename(current)
    current.write_text("daily_enable: false\n", encoding="utf-8")
    account_file = current.parent / "account-data"
    account_file.write_bytes(b"account")

    script_config = SimpleNamespace(Info=SimpleNamespace(M7APath=root))
    assert load_m7a_native_config(script_config) == {"daily_enable": False}
    restore_native_backup(root, sra, archived.name)

    assert load_m7a_native_config(script_config) == {"daily_enable": True}
    assert not legacy.exists()
    assert account_file.read_bytes() == b"account"


@pytest.mark.asyncio
@pytest.mark.parametrize("migration_completes", [True, False])
async def test_prepare_m7a_config_waits_for_upstream_migration(
    tmp_path, monkeypatch, migration_completes
):
    from app.task.HSR.tools import m7a_paths

    monkeypatch.setattr(m7a_paths, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.delenv("M7A_DATA_DIR", raising=False)
    write_m7a_version(tmp_path, "v2026.11.25-beta")
    legacy = tmp_path / "config.yaml"
    legacy.write_bytes(b"daily_enable: true\n")
    current = tmp_path / "userdata" / "config.yaml"

    async def upstream_status(program, command, **kwargs):
        assert program == tmp_path / "m7a.exe"
        assert command == "--status"
        assert kwargs["cwd"] == tmp_path
        if migration_completes:
            current.parent.mkdir()
            legacy.rename(current)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(m7a_paths.ProcessRunner, "run_process", upstream_status)
    if migration_completes:
        assert await m7a_paths.prepare_m7a_config(tmp_path) == current
        assert current.read_bytes() == b"daily_enable: true\n"
    else:
        with pytest.raises(RuntimeError, match="迁移未完成"):
            await m7a_paths.prepare_m7a_config(tmp_path)
        assert legacy.read_bytes() == b"daily_enable: true\n"
        assert not current.exists()


@pytest.mark.parametrize(
    ("log", "completed"),
    [
        ("历战余响本周剩余奖励次数：0/3", True),
        ("历战余响本周剩余奖励次数：1/3", False),
        ("历战余响本周可领取奖励次数：0/3", True),
    ],
)
def test_m7a_echo_of_war_reward_limit(log, completed):
    assert (
        detect_echo_of_war_completion(SimpleNamespace(output=log), "M7A")[0]
        is completed
    )
