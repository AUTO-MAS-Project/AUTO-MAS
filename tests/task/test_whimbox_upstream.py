"""奇想盒上游配置面回归测试（CI 全 mock：临时目录 + 内存数据，不依赖真机）。

覆盖：安装哨兵分场景报错、目录机械转换（真实三件套结构）、覆盖集过滤→物化→
存活链路、快照/还原（含会话期新建删除语义）与恢复池函数。
"""

import json
from pathlib import Path

import pytest

from app.task.Whimbox.tools.upstream import (
    APP_EXE_NAME,
    REL_PYTHON_EXE,
    REL_SITE_PACKAGES,
    WheelAssetsConfigSurface,
)

TEMPLATE = {
    "General": {"debug": {"value": "false", "description": "调试模式"}},
    "Agent": {"model_provider": {"value": "openai", "description": "模型提供商"}},
    "OneDragon": {
        "auto_start": {"value": "false", "description": "自动运行一条龙"},
        "change_account": {"value": "false", "description": "为所有账号运行一条龙"},
        "auto_close_game": {"value": "false", "description": "结束后关闭游戏"},
        "start_magnet": {"value": "false", "description": "收集结晶时开扇子"},
        "energy_cost": {"value": "素材激化幻境", "description": "消耗体力的幻境"},
        "jihua_cost": {"value": "星荧草", "description": "默认消耗材料"},
        "jihua_cost_2": {"value": "纽扣松果", "description": "备选消耗材料"},
        "realm_target": {"value": ["奇格格达", "卷卷"], "description": "周本目标"},
        "ability_plan": {"value": 3, "description": "能力配置方案号"},
    },
    "OneDragonDefaultSteps": {
        "step_dig": {"value": "true", "description": "美鸭梨挖掘"},
        "step_home_task": {"value": "true", "description": "家园日常"},
        "step_weekly_realm": {"value": "true", "description": "周本"},
    },
}
SETTING_OPTIONS = {
    "energy_cost": ["素材激化幻境", "祝福闪光幻境", "不消耗剩余体力"],
    "realm_target": ["奇格格达", "卷卷"],
    "model_provider": ["openai", "ollama"],
}
MATERIAL = {
    "星荧草": {"jihua": True},
    "纽扣松果": {"jihua": True},
    "装饰花盆": {"jihua": False},
}


@pytest.fixture
def surface(tmp_path: Path, monkeypatch) -> WheelAssetsConfigSurface:
    assets = tmp_path / REL_SITE_PACKAGES / "whimbox" / "assets"
    assets.mkdir(parents=True)
    (assets / "default_config.json").write_text(
        json.dumps(TEMPLATE, ensure_ascii=False), encoding="utf-8"
    )
    (assets / "setting_options.json").write_text(
        json.dumps(SETTING_OPTIONS, ensure_ascii=False), encoding="utf-8"
    )
    (assets / "material.json").write_text(
        json.dumps(MATERIAL, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / APP_EXE_NAME).write_bytes(b"exe")
    (tmp_path / REL_PYTHON_EXE).write_bytes(b"py")
    monkeypatch.chdir(tmp_path)
    return WheelAssetsConfigSurface(tmp_path)


class TestCatalog:
    def test_steps_and_options_from_template(self, surface: WheelAssetsConfigSurface):
        catalog = surface.read_catalog()
        assert [s.key for s in catalog.steps] == [
            "step_dig",
            "step_home_task",
            "step_weekly_realm",
        ]
        assert catalog.steps[0].display == "美鸭梨挖掘"
        option_keys = {o.key for o in catalog.options}
        assert {"auto_start", "change_account", "auto_close_game"}.isdisjoint(
            option_keys
        )
        assert {
            "start_magnet",
            "energy_cost",
            "realm_target",
            "ability_plan",
        } <= option_keys
        by_key = {o.key: o for o in catalog.options}
        assert by_key["start_magnet"].field_type == "bool"
        assert by_key["start_magnet"].default is False
        assert by_key["energy_cost"].field_type == "select"
        assert by_key["energy_cost"].options == tuple(SETTING_OPTIONS["energy_cost"])
        assert by_key["jihua_cost"].options == ("星荧草", "纽扣松果")
        assert by_key["realm_target"].field_type == "multi_select"
        assert by_key["realm_target"].default == ["奇格格达", "卷卷"]
        assert by_key["ability_plan"].field_type == "int"
        assert by_key["ability_plan"].default == 3


class TestMaterializeOverrides:
    def test_filter_write_and_survive(self, surface: WheelAssetsConfigSurface):
        (surface.root_path / "configs").mkdir(exist_ok=True)
        (surface.root_path / "configs" / "config.json").write_text(
            json.dumps({"General": TEMPLATE["General"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        surface.materialize_overrides(
            {"step_dig": False, "not_in_template": True},
            {
                "jihua_cost": "纽扣松果",
                "realm_target": ["卷卷"],
                "ability_plan": 5,
                "evil_key": 1,
            },
            run_all_accounts=True,
        )
        data = json.loads(surface.config_path.read_text(encoding="utf-8"))
        steps = data["OneDragonDefaultSteps"]
        one_dragon = data["OneDragon"]
        assert steps["step_dig"]["value"] == "false"
        assert "not_in_template" not in steps
        assert "step_home_task" not in steps
        assert one_dragon["jihua_cost"]["value"] == "纽扣松果"
        assert one_dragon["jihua_cost"]["description"] == "默认消耗材料"
        assert one_dragon["realm_target"]["value"] == ["卷卷"]
        assert "evil_key" not in one_dragon
        assert one_dragon["change_account"]["value"] == "true"
        assert one_dragon["auto_close_game"]["value"] == "true"
        assert one_dragon["ability_plan"]["value"] == 5
        assert "auto_start" not in one_dragon


class TestUnwritableInstall:
    """上游装在受保护目录（Program Files）时的报错必须可操作。"""

    @staticmethod
    def _deny(monkeypatch: pytest.MonkeyPatch) -> None:
        import app.task.Whimbox.tools.upstream as upstream_mod

        def boom(path: Path, data: bytes) -> None:
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(upstream_mod, "atomic_write", boom)

    def test_preserves_existing_sections_and_descriptions(
        self, surface: WheelAssetsConfigSurface
    ):
        (surface.root_path / "configs").mkdir(exist_ok=True)
        (surface.root_path / "configs" / "config.json").write_text(
            json.dumps(
                {
                    "General": {"debug": {"value": "true", "description": "用户改过"}},
                    "OneDragon": {
                        "jihua_cost": {
                            "value": "星荧草",
                            "description": "用户自定义描述",
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        surface.materialize_overrides(
            {"step_dig": True}, {"jihua_cost": "纽扣松果"}, run_all_accounts=False
        )
        data = json.loads(surface.config_path.read_text(encoding="utf-8"))
        assert data["General"]["debug"]["value"] == "true"
        assert data["OneDragon"]["jihua_cost"]["description"] == "用户自定义描述"


class TestSnapshotRestore:
    def test_roundtrip(self, surface: WheelAssetsConfigSurface):
        (surface.root_path / "configs").mkdir()
        original = {
            "OneDragon": {"start_magnet": {"value": "false", "description": "x"}}
        }
        (surface.root_path / "configs" / "config.json").write_text(
            json.dumps(original, ensure_ascii=False), encoding="utf-8"
        )
        ts = surface.snapshot_pre_run()
        assert ts is not None
        surface.materialize_overrides({"step_dig": False}, {}, run_all_accounts=True)
        assert surface.config_path.is_file()
        surface.restore_pre_run(ts)
        assert json.loads(surface.config_path.read_text(encoding="utf-8")) == original

    def test_no_config_pre_run_deletes_session_created(self, surface):
        assert surface.snapshot_pre_run() is None
        surface.materialize_overrides({}, {}, run_all_accounts=False)
        assert surface.config_path.is_file()
        surface.restore_pre_run(None)
        assert not surface.config_path.exists()


class TestRestorePools:
    def test_mas_display_translates_with_catalog(
        self, surface: WheelAssetsConfigSurface
    ):
        """展示快照用目录显示名翻译覆盖集键；未知键降级保留原始键。"""
        from app.task.Whimbox.tools import restore_service as rs

        overlay = {
            "Task": {
                "Tasks": '{"step_dig": false, "unknown_step": true}',
                "Options": '{"jihua_cost": "纽扣松果"}',
            }
        }
        display = rs._build_display(overlay, surface)
        steps = {item["key"]: item for item in display["steps"]}
        assert steps["step_dig"]["display"] == "美鸭梨挖掘"
        assert steps["unknown_step"]["display"] == "unknown_step"
        assert steps["step_dig"]["value"] is False
        assert display["options"][0]["display"] == "默认消耗材料"
