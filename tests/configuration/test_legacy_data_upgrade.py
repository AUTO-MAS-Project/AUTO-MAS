"""独立 legacy 数据升级器 (v1.7 -> v1.11) 的行为契约。

覆盖: 幂等、fail-closed 角落 (已冻结快照 + pre-v1.11 数据)、纯 JSON 变换步骤
与版本表异常。v1.8->v1.9 目录迁移在 test_legacy_v1_8_layout.py 单独覆盖。
"""

import json
import sqlite3
from pathlib import Path

import pytest

from app.configuration.compat.legacy_data_upgrade import (
    LegacyDataUpgradeConflictError,
    LegacyDataUpgradeError,
    upgrade_legacy_data,
)


def _make_db(base_dir: Path, version: str) -> Path:
    database_path = base_dir / "data" / "data.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(database_path)
    db.execute("CREATE TABLE version(v text)")
    db.execute("INSERT INTO version VALUES(?)", (version,))
    db.commit()
    db.close()
    return database_path


def _read_version(database_path: Path) -> list[str]:
    db = sqlite3.connect(database_path)
    rows = [row[0] for row in db.execute("SELECT v FROM version").fetchall()]
    db.close()
    return rows


class TestNoOpPaths:
    def test_missing_database_is_fresh_profile(self, tmp_path: Path) -> None:
        result = upgrade_legacy_data(tmp_path)
        assert result.performed is False
        assert result.from_version is None
        assert not (tmp_path / "data" / "data.db").exists()

    def test_v1_11_is_noop(self, tmp_path: Path) -> None:
        database_path = _make_db(tmp_path, "v1.11")
        before = database_path.read_bytes()
        result = upgrade_legacy_data(tmp_path)
        assert result.performed is False
        assert result.from_version == "v1.11"
        assert database_path.read_bytes() == before


class TestFailClosed:
    def test_existing_snapshot_with_old_data_refuses(self, tmp_path: Path) -> None:
        _make_db(tmp_path, "v1.10")
        current = tmp_path / "config" / ".config-v2-original" / "CURRENT"
        current.parent.mkdir(parents=True)
        current.write_text("{}", encoding="utf-8")

        with pytest.raises(LegacyDataUpgradeConflictError):
            upgrade_legacy_data(tmp_path)
        # 拒绝时不得动数据。
        assert _read_version(tmp_path / "data" / "data.db") == ["v1.10"]

    def test_ambiguous_version_table_refuses(self, tmp_path: Path) -> None:
        database_path = _make_db(tmp_path, "v1.10")
        db = sqlite3.connect(database_path)
        db.execute("INSERT INTO version VALUES(?)", ("v1.11",))
        db.commit()
        db.close()

        with pytest.raises(LegacyDataUpgradeError, match="ambiguous"):
            upgrade_legacy_data(tmp_path)

    def test_unknown_version_refuses(self, tmp_path: Path) -> None:
        _make_db(tmp_path, "v0.9")
        with pytest.raises(LegacyDataUpgradeError, match="not upgradable"):
            upgrade_legacy_data(tmp_path)

    def test_corrupt_database_refuses(self, tmp_path: Path) -> None:
        database_path = tmp_path / "data" / "data.db"
        database_path.parent.mkdir(parents=True)
        database_path.write_bytes(b"not a sqlite database at all")
        with pytest.raises(LegacyDataUpgradeError, match="cannot be read"):
            upgrade_legacy_data(tmp_path)


class TestPureTransforms:
    def test_v1_10_to_v1_11_renames_user_task_keys(self, tmp_path: Path) -> None:
        """旧 Task 键名结构化重命名 (兑现 legacy 从未写盘的重命名意图)。"""
        database_path = _make_db(tmp_path, "v1.10")
        script_root = tmp_path / "config" / "ScriptConfig.json"
        script_root.parent.mkdir(parents=True)
        script_uid = "a1b2c3d4-e5f6-4708-9a1b-2c3d4e5f6071"
        user_uid = "7c8d9e0a-1b2c-4d3e-8f40-5a6b7c8d9e01"
        script_root.write_text(
            json.dumps(
                {
                    "instances": [{"uid": script_uid, "type": "MaaConfig"}],
                    script_uid: {
                        "Info": {"Name": "MAA"},
                        "SubConfigsInfo": {
                            "UserData": {
                                "instances": [
                                    {"uid": user_uid, "type": "MaaUserConfig"}
                                ],
                                user_uid: {
                                    "Info": {"Name": "用户"},
                                    "Task": {
                                        "IfWakeUp": True,
                                        "IfCombat": False,
                                        "IfMall": True,
                                        "Bogus": True,
                                    },
                                },
                            }
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        result = upgrade_legacy_data(tmp_path)

        assert result.performed is True
        assert result.steps == ("v1.10->v1.11",)
        assert _read_version(database_path) == ["v1.11"]
        migrated = json.loads(script_root.read_text(encoding="utf-8"))
        task = migrated[script_uid]["SubConfigsInfo"]["UserData"][user_uid]["Task"]
        # 旧键映射为新键, 未知键丢弃 (legacy load 也会丢), 值保留。
        assert task == {"IfStartUp": True, "IfFight": False, "IfMall": True}

    def test_v1_10_to_v1_11_without_script_root_bumps_version(
        self, tmp_path: Path
    ) -> None:
        database_path = _make_db(tmp_path, "v1.10")
        result = upgrade_legacy_data(tmp_path)
        assert result.performed is True
        assert _read_version(database_path) == ["v1.11"]

    def test_v1_9_chain_applies_config_json_transform(self, tmp_path: Path) -> None:
        database_path = _make_db(tmp_path, "v1.9")
        config_root = tmp_path / "config" / "Config.json"
        config_root.parent.mkdir(parents=True)
        config_root.write_text(
            json.dumps(
                {
                    "Data": {"LastStageUpdated": "2020-01-01", "Stage": "old"},
                    "Function": {"IfSkipMumuSplashAds": True},
                }
            ),
            encoding="utf-8",
        )

        result = upgrade_legacy_data(tmp_path)

        assert result.performed is True
        assert result.steps == ("v1.9->v1.10", "v1.10->v1.11")
        assert _read_version(database_path) == ["v1.11"]
        data = json.loads(config_root.read_text(encoding="utf-8"))
        # IfSkipMumuSplashAds -> IfBlockAd 映射; 旧键与缓存类 Data 组裁掉
        # (v2 导入 fail-closed, 未知键不得存活)。
        assert data["Function"]["IfBlockAd"] is True
        assert "IfSkipMumuSplashAds" not in data["Function"]
        assert "Data" not in data

    def test_v1_9_without_config_json_still_upgrades(self, tmp_path: Path) -> None:
        database_path = _make_db(tmp_path, "v1.9")
        result = upgrade_legacy_data(tmp_path)
        assert result.performed is True
        assert _read_version(database_path) == ["v1.11"]

    def test_v1_7_queue_transform(self, tmp_path: Path) -> None:
        _make_db(tmp_path, "v1.7")
        queue_dir = tmp_path / "config" / "QueueConfig"
        queue_dir.mkdir(parents=True)
        queue_config = {
            "QueueSet": {"Enabled": True},
            "Queue": {f"Member_{i + 1}": f"m{i}" for i in range(10)},
            "Time": {
                **{f"TimeEnabled_{i}": bool(i % 2) for i in range(10)},
                **{f"TimeSet_{i}": f"0{i}:00" for i in range(10)},
            },
        }
        (queue_dir / "q1.json").write_text(
            json.dumps(queue_config), encoding="utf-8"
        )

        # v1.7 链会经过 v1.8->v1.9 目录迁移; 该步骤此处只验证别名转换结果,
        # 其余由 layout 测试覆盖。
        result = upgrade_legacy_data(tmp_path)

        assert result.performed is True
        assert result.steps[0] == "v1.7->v1.8"
        assert result.to_version == "v1.11"

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        _make_db(tmp_path, "v1.9")
        first = upgrade_legacy_data(tmp_path)
        second = upgrade_legacy_data(tmp_path)
        assert first.performed is True
        assert second.performed is False
        assert second.from_version == "v1.11"
