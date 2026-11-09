"""回退旧版后重迁的来源选择、失败恢复和拒绝覆盖回归。"""

from pathlib import Path

import pytest
from pydantic import Field

from app.config import ConfigEntry, ConfigGroup
from app.core.config.upgrade import CONFIG_FILES, MIGRATION_RECORD, upgrade_json_configs
from app.utils import io as config_io


class _Values(ConfigGroup):
    Revision: int = 1


class _Profile(ConfigEntry):
    Values: _Values = Field(default_factory=_Values)


@pytest.fixture
def migrated_profile(tmp_path):
    nodes = {key: _Profile.build() for _, _, key in CONFIG_FILES}
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / old, {"Values": {"Revision": 1}})
    upgrade_json_configs(tmp_path, nodes)
    for old, new, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / new, {"Values": {"Revision": 2}})
        config_io.write_file(tmp_path / old, {"Values": {"Revision": 3}})
    return tmp_path, nodes


@pytest.mark.parametrize("interrupted", [False, True])
def test_remigration_uses_current_json_and_resumes(
    migrated_profile, monkeypatch, interrupted
):
    folder, nodes = migrated_profile
    if interrupted:
        unlink = Path.unlink

        def fail_removal(path, *args, **kwargs):
            if path == folder / "legacy-json" / "EmulatorConfig.json":
                raise PermissionError("file is occupied")
            return unlink(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "unlink", fail_removal)
            with pytest.raises(PermissionError):
                upgrade_json_configs(folder, nodes)

    upgrade_json_configs(folder, nodes)

    for old, new, _ in CONFIG_FILES:
        expected = {"Values": {"Revision": 3}}
        assert config_io.read_dict_file(folder / new) == expected
        assert config_io.read_dict_file(folder / "legacy-json" / old) == expected
    # 根目录只留下本轮 YAML 和迁移记录，不额外保存旧 YAML 或遗留 JSON。
    assert set(folder.iterdir()) == {
        folder / MIGRATION_RECORD,
        folder / "legacy-json",
        *(folder / new for _, new, _ in CONFIG_FILES),
    }
    setting = folder / "setting.yaml"
    config_io.write_file(setting, {"Values": {"Revision": 4}})
    upgrade_json_configs(folder, nodes)
    assert config_io.read_dict_file(setting) == {"Values": {"Revision": 4}}


@pytest.mark.parametrize("invalid", ["record", "missing", "corrupted"])
def test_invalid_remigration_keeps_existing_yaml(migrated_profile, invalid):
    folder, nodes = migrated_profile
    if invalid == "record":
        record = config_io.read_dict_file(folder / MIGRATION_RECORD)
        record["complete"] = False
        config_io.write_file(folder / MIGRATION_RECORD, record)
    elif invalid == "missing":
        (folder / "GameSignAccounts.json").unlink()
    else:
        (folder / "QueueConfig.json").write_text("{", encoding="utf-8")
    paths = [folder / MIGRATION_RECORD, *(folder / new for _, new, _ in CONFIG_FILES)]
    saved = {path: path.read_bytes() for path in paths}

    with pytest.raises(ValueError):
        upgrade_json_configs(folder, nodes)

    assert saved == {path: path.read_bytes() for path in paths}
