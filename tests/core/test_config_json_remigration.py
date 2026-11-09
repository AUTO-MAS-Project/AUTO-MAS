"""回退旧版后重迁的来源选择、失败恢复和拒绝覆盖回归。"""

from pathlib import Path

import pytest
from pydantic import Field

from app.config import ConfigCollection, ConfigEntry, ConfigGroup
from app.core.config.upgrade import CONFIG_FILES, MIGRATION_RECORD, upgrade_json_configs
from app.models.config import EmulatorConfig
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


@pytest.mark.parametrize("failure", [None, "replace", "checkpoint"])
def test_remigration_uses_current_json_and_resumes(
    migrated_profile, monkeypatch, failure
):
    folder, nodes = migrated_profile
    if failure:
        replace = Path.replace
        write_file = config_io.write_file
        target = folder / "emulators.yaml"
        original = target.read_bytes()

        def fail_replace(path, destination):
            if destination == target:
                raise PermissionError("file is occupied")
            return replace(path, destination)

        def fail_checkpoint(path, *args, **kwargs):
            if (
                path == folder / MIGRATION_RECORD
                and not (folder / "EmulatorConfig.json").exists()
            ):
                raise PermissionError("progress cannot be saved")
            return write_file(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            if failure == "replace":
                patch.setattr(Path, "replace", fail_replace)
            else:
                patch.setattr(config_io, "write_file", fail_checkpoint)
            with pytest.raises(PermissionError):
                upgrade_json_configs(folder, nodes)
        if failure == "replace":
            assert target.read_bytes() == original

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


def test_unconvertible_collection_keeps_yaml_and_archive(tmp_path):
    nodes = {key: _Profile.build() for _, _, key in CONFIG_FILES}
    nodes["EmulatorConfig"] = ConfigCollection.build([EmulatorConfig])
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / old, {})
    upgrade_json_configs(tmp_path, nodes)
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / old, {})
    config_io.write_file(tmp_path / "EmulatorConfig.json", {"instances": "bad"})
    paths = [tmp_path / "emulators.yaml", tmp_path / "legacy-json/EmulatorConfig.json"]
    saved = {path: path.read_bytes() for path in paths}

    with pytest.raises(ValueError):
        upgrade_json_configs(tmp_path, nodes)

    assert saved == {path: path.read_bytes() for path in paths}
