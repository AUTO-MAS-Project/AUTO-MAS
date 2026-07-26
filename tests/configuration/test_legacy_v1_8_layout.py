"""v1.8 目录布局迁移 (_legacy_v1_8_layout) 的行为契约。

关键验收: 产物必须被真实的 Config v2 legacy 导入链
(``legacy_production_roots_to_wire``) 无异常接受——v2 端 fail-closed,
这是比字段级断言更强的兼容性证明。
"""

import json
from pathlib import Path

from app.configuration.compat._legacy_v1_8_layout import migrate_v1_8_directories
from app.configuration.compat.legacy_data_upgrade import upgrade_legacy_data
from app.configuration.compat.legacy_original_snapshot import LEGACY_ROOT_FILE_NAMES
from app.configuration.production import legacy_production_roots_to_wire

from .test_legacy_data_upgrade import _make_db


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _build_v1_8_profile(base: Path) -> Path:
    """构造一个覆盖四类目录的 v1.8 档案。返回 MAA 脚本引用的真实目录。"""

    config = base / "config"
    maa_path = base / "MAA-install"
    maa_path.mkdir(parents=True)

    _write_json(
        config / "config.json",
        {"Data": {"Stage": "old"}, "Function": {"IfSkipMumuSplashAds": True}},
    )

    _write_json(
        config / "MaaPlanConfig" / "周常" / "config.json",
        {
            "Info": {"Name": "周常", "Mode": "Weekly"},
            "ALL": {"MedicineNumb": 2, "Stage": "1-7"},
            "Monday": {"Stage": "CE-6", "SeriesNumb": "6"},
        },
    )

    maa_dir = config / "MaaConfig" / "主号"
    _write_json(
        maa_dir / "config.json",
        {
            "MaaSet": {"Name": "MAA主", "Path": str(maa_path)},
            "RunSet": {
                "ProxyTimesLimit": 2,
                "RunTimesLimit": 3,
                "AnnihilationTimeLimit": 40,
                "RoutineTimeLimit": 10,
            },
        },
    )
    _write_json(maa_dir / "Default" / "gui.json", {"gui": "default"})
    user_dir = maa_dir / "UserData" / "博士甲"
    _write_json(
        user_dir / "config.json",
        {
            "Info": {
                "Name": "博士甲",
                "Id": "doctor@example.com",
                "Password": "should-be-cleared",
                "Mode": "简洁",
                "StageMode": "周常",
                "Server": "Official",
                "Status": True,
                "RemainedDay": 30,
                "MedicineNumb": 1,
                "Stage": "1-7",
                "Notes": "备注",
            },
            "Data": {
                "LastProxyDate": "2024-01-01",
                "ProxyTimes": 5,
                "IfPassCheck": True,
            },
            # 旧键名 (v1.10 重命名从未写盘) 混合新键名
            "Task": {"IfWakeUp": True, "IfCombat": True, "IfMall": False},
        },
    )
    _write_json(user_dir / "Routine" / "gui.json", {"gui": "user"})
    _write_json(
        user_dir / "Infrastructure" / "infrastructure.json", {"infrast": 1}
    )

    general_dir = config / "GeneralConfig" / "通用脚本"
    _write_json(
        general_dir / "config.json",
        {
            "Script": {
                "Name": "通用脚本",
                "RootPath": str(maa_path),
                "ConfigPathMode": "所有文件 (*)",
                "Arguments": "--auto",
            }
        },
    )
    sub_user = general_dir / "SubData" / "用户乙"
    _write_json(
        sub_user / "config.json",
        {
            "Info": {"Name": "用户乙", "Status": True},
            "Data": {"LastProxyDate": "2024-02-02", "ProxyTimes": 3},
        },
    )
    (sub_user / "ConfigFiles").mkdir(parents=True)
    (sub_user / "ConfigFiles" / "cfg.ini").write_text("k=v", encoding="utf-8")

    # v1.7→v1.8 别名后的队列文件形状
    _write_json(
        config / "QueueConfig" / "早晨队列.json",
        {
            "QueueSet": {
                "Name": "早晨队列",
                "Enabled": True,
                "TimeEnabled": True,
                "AfterAccomplish": "无动作",
            },
            "Queue": {
                **{"Script_0": "主号"},
                **{f"Script_{i}": "禁用" for i in range(1, 10)},
            },
            "Time": {
                **{"Enabled_0": True, "Set_0": "07:30"},
                **{f"Enabled_{i}": False for i in range(1, 10)},
                **{f"Set_{i}": "00:00" for i in range(1, 10)},
            },
        },
    )

    (base / "data").mkdir(exist_ok=True)
    (base / "data" / "gameid.txt").write_text("123", encoding="utf-8")
    return maa_path


def _load_root(base: Path, name: str) -> dict:
    return json.loads((base / "config" / name).read_text(encoding="utf-8"))


class TestLayoutMigration:
    def test_full_profile_migrates_and_cleans_up(self, tmp_path: Path) -> None:
        maa_path = _build_v1_8_profile(tmp_path)
        migrate_v1_8_directories(tmp_path)

        config = tmp_path / "config"
        # 旧目录清理 + config.json 改名
        assert not (config / "MaaConfig").exists()
        assert not (config / "GeneralConfig").exists()
        assert not (config / "MaaPlanConfig").exists()
        assert not (config / "QueueConfig").exists()
        # Windows 大小写不敏感, Path.exists() 区分不了两个名字; 查真实目录项
        real_names = {entry.name for entry in config.iterdir()}
        assert "config.json" not in real_names
        assert "Config.json" in real_names
        assert not (tmp_path / "data" / "gameid.txt").exists()

        plan_root = _load_root(tmp_path, "PlanConfig.json")
        script_root = _load_root(tmp_path, "ScriptConfig.json")
        queue_root = _load_root(tmp_path, "QueueConfig.json")

        assert len(plan_root["instances"]) == 1
        plan_uid = plan_root["instances"][0]["uid"]
        assert plan_root[plan_uid]["Info"]["Name"] == "周常"
        assert plan_root[plan_uid]["Monday"]["Stage"] == "CE-6"

        types = {i["type"] for i in script_root["instances"]}
        assert types == {"MaaConfig", "GeneralConfig"}
        maa_uid = next(
            i["uid"]
            for i in script_root["instances"]
            if i["type"] == "MaaConfig"
        )
        maa_entry = script_root[maa_uid]
        assert maa_entry["Info"]["Name"] == "MAA主"
        assert maa_entry["Info"]["Path"] == str(maa_path)
        assert maa_entry["Run"]["AnnihilationTimeLimit"] == 40

        users = maa_entry["SubConfigsInfo"]["UserData"]
        assert len(users["instances"]) == 1
        user_uid = users["instances"][0]["uid"]
        user = users[user_uid]
        # 密码清空、StageMode 映射为计划 uid、Task 旧键名重命名
        assert user["Info"]["Password"] == ""
        assert user["Info"]["StageMode"] == plan_uid
        assert user["Task"] == {
            "IfStartUp": True,
            "IfFight": True,
            "IfMall": False,
        }

        # 文件复制/移动
        assert (
            tmp_path / "data" / maa_uid / "Default/ConfigFile/gui.json"
        ).exists()
        assert (
            tmp_path / "data" / maa_uid / user_uid / "ConfigFile/gui.json"
        ).exists()
        assert (
            tmp_path
            / "data"
            / maa_uid
            / user_uid
            / "Infrastructure/infrastructure.json"
        ).exists()
        general_uid = next(
            i["uid"]
            for i in script_root["instances"]
            if i["type"] == "GeneralConfig"
        )
        general_user_uid = script_root[general_uid]["SubConfigsInfo"][
            "UserData"
        ]["instances"][0]["uid"]
        assert (
            tmp_path
            / "data"
            / general_uid
            / general_user_uid
            / "ConfigFile/cfg.ini"
        ).exists()
        # General ConfigPathMode 中文语义映射
        assert script_root[general_uid]["Script"]["ConfigPathMode"] == "File"

        # 队列: 中文动作映射、10 组 TimeSet/QueueItem、脚本引用解析
        queue_uid = queue_root["instances"][0]["uid"]
        queue_entry = queue_root[queue_uid]
        assert queue_entry["Info"]["AfterAccomplish"] == "NoAction"
        assert queue_entry["Info"]["TimeEnabled"] is True
        time_sets = queue_entry["SubConfigsInfo"]["TimeSet"]
        queue_items = queue_entry["SubConfigsInfo"]["QueueItem"]
        assert len(time_sets["instances"]) == 10
        assert len(queue_items["instances"]) == 10
        first_time = time_sets[time_sets["instances"][0]["uid"]]
        assert first_time["Info"] == {"Enabled": True, "Time": "07:30"}
        first_item = queue_items[queue_items["instances"][0]["uid"]]
        assert first_item["Info"]["ScriptId"] == maa_uid
        second_item = queue_items[queue_items["instances"][1]["uid"]]
        assert second_item["Info"]["ScriptId"] == "-"

    def test_output_is_accepted_by_v2_import(self, tmp_path: Path) -> None:
        """v2 legacy 导入链 fail-closed; 完整升级链产物必须被无异常接受。"""
        _build_v1_8_profile(tmp_path)
        _make_db(tmp_path, "v1.8")
        result = upgrade_legacy_data(tmp_path)
        assert result.to_version == "v1.11"

        legacy_roots: dict[str, dict | None] = {
            name: None for name in LEGACY_ROOT_FILE_NAMES
        }
        for name in (
            "Config.json",
            "PlanConfig.json",
            "ScriptConfig.json",
            "QueueConfig.json",
        ):
            legacy_roots[name] = _load_root(tmp_path, name)

        wires = legacy_production_roots_to_wire(legacy_roots)
        assert wires

    def test_full_chain_from_v1_7_via_upgrader(self, tmp_path: Path) -> None:
        """v1.7 起步: 别名步 + 布局步 + Config.json 变换 + 版本单行 v1.11。"""
        _build_v1_8_profile(tmp_path)
        database_path = _make_db(tmp_path, "v1.8")

        result = upgrade_legacy_data(tmp_path)

        assert result.performed is True
        assert result.steps == (
            "v1.8->v1.9",
            "v1.9->v1.10",
            "v1.10->v1.11",
        )
        config_json = _load_root(tmp_path, "Config.json")
        assert config_json["Function"]["IfBlockAd"] is True
        assert "IfSkipMumuSplashAds" not in config_json.get("Function", {})
        assert "Data" not in config_json
        import sqlite3

        db = sqlite3.connect(database_path)
        assert [r[0] for r in db.execute("SELECT v FROM version")] == ["v1.11"]
        db.close()

    def test_empty_profile_produces_empty_roots(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        migrate_v1_8_directories(tmp_path)
        assert _load_root(tmp_path, "ScriptConfig.json") == {"instances": []}
        assert _load_root(tmp_path, "PlanConfig.json") == {"instances": []}
        assert _load_root(tmp_path, "QueueConfig.json") == {"instances": []}
