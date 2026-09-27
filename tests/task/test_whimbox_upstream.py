#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""奇想盒上游配置面回归测试（CI 全 mock：临时目录 + 内存数据，不依赖真机）。

覆盖：安装哨兵分场景报错、目录机械转换（真实三件套结构）、覆盖集过滤→物化→
存活链路、快照/还原（含会话期新建删除语义）与恢复池函数。
"""

import json
from pathlib import Path

import pytest

from app.task.Whimbox.tools.restore_service import RESTORE_POOLS
from app.task.Whimbox.tools.upstream import (
    APP_EXE_NAME,
    REL_PYTHON_EXE,
    REL_SITE_PACKAGES,
    WheelAssetsConfigSurface,
)

# ── 测试 fixture：与上游 v3.0.5 三件套同构的最小模板 ───────────────────────

TEMPLATE = {
    "General": {"debug": {"value": "false", "description": "调试模式"}},
    "Agent": {
        "model_provider": {
            "value": "openai",
            "description": "模型提供商",
        }
    },
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
def surface(tmp_path: Path) -> WheelAssetsConfigSurface:
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
    # 备份池根落 tmp 下，避免污染仓库 data/
    import app.task.Whimbox.tools.upstream as upstream_mod

    original = upstream_mod.Path.cwd
    upstream_mod.Path.cwd = lambda: tmp_path  # type: ignore[method-assign]
    yield WheelAssetsConfigSurface(tmp_path)
    upstream_mod.Path.cwd = original  # type: ignore[method-assign]


class TestInstallSentinel:
    def test_missing_app_exe(self, tmp_path: Path):
        s = WheelAssetsConfigSurface(tmp_path)
        assert "请先安装奇想盒" in (s.check_install() or "")

    def test_missing_python_runtime(self, tmp_path: Path):
        (tmp_path / APP_EXE_NAME).write_bytes(b"exe")
        s = WheelAssetsConfigSurface(tmp_path)
        assert "重新安装" in (s.check_install() or "")

    def test_missing_backend_package(self, tmp_path: Path):
        (tmp_path / APP_EXE_NAME).write_bytes(b"exe")
        python = tmp_path / REL_PYTHON_EXE
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_bytes(b"py")
        s = WheelAssetsConfigSurface(tmp_path)
        assert "完整运行一次奇想盒" in (s.check_install() or "")


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
        # 非托管键（MAS 静态字段物化 / app 专属）不出现在动态目录
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
        # 布尔语义字符串归一为 bool
        assert by_key["start_magnet"].field_type == "bool"
        assert by_key["start_magnet"].default is False
        # 值域枚举：setting_options 原文
        assert by_key["energy_cost"].field_type == "select"
        assert by_key["energy_cost"].options == tuple(SETTING_OPTIONS["energy_cost"])
        # material 值域：jihua=True 的材料名，jihua=False 的被排除
        assert by_key["jihua_cost"].options == ("星荧草", "纽扣松果")
        # 多选 + int
        assert by_key["realm_target"].field_type == "multi_select"
        assert by_key["realm_target"].default == ["奇格格达", "卷卷"]
        assert by_key["ability_plan"].field_type == "int"
        assert by_key["ability_plan"].default == 3

    def test_catalog_mtime_cache(self, surface: WheelAssetsConfigSurface):
        first = surface.read_catalog()
        second = surface.read_catalog()
        assert first is second  # 指纹未变时命中缓存

    def test_missing_assets_raises(self, tmp_path: Path):
        """三件套不可读时响亮失败（不静默返回空目录——空目录会伪装成「上游没这些字段」）。"""

        (tmp_path / APP_EXE_NAME).write_bytes(b"exe")
        surface = WheelAssetsConfigSurface(tmp_path)
        with pytest.raises(RuntimeError, match="三件套不可读"):
            surface.read_catalog()


class TestMaterializeOverrides:
    def test_filter_write_and_survive(self, surface: WheelAssetsConfigSurface):
        # 预置最小原生 config（上游首启会播种完整模板；此处模拟既有局部配置）
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

        # 步骤开关：布尔写入为上游字符串语义；未知键被过滤
        assert steps["step_dig"]["value"] == "false"
        assert "not_in_template" not in steps
        # 未触及的步骤保持模板缺省（不写入，由上游加载时补默认）
        assert "step_home_task" not in steps
        # 参数：值透传；未知键被过滤；description 取模板
        assert one_dragon["jihua_cost"]["value"] == "纽扣松果"
        assert one_dragon["jihua_cost"]["description"] == "默认消耗材料"
        assert one_dragon["realm_target"]["value"] == ["卷卷"]
        assert "evil_key" not in one_dragon
        # 静态语义字段落两个流程开关（布尔字符串）；关游戏恒强制为开、不随用户配置
        assert one_dragon["change_account"]["value"] == "true"
        assert one_dragon["auto_close_game"]["value"] == "true"
        # int 键保持 int
        assert one_dragon["ability_plan"]["value"] == 5
        # 非托管节不写入
        assert "auto_start" not in one_dragon


class TestUnwritableInstall:
    """上游装在受保护目录（Program Files）时的报错必须可操作。"""

    @staticmethod
    def _deny(monkeypatch: pytest.MonkeyPatch) -> None:
        import app.task.Whimbox.tools.upstream as upstream_mod

        def boom(path: Path, data: bytes) -> None:
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(upstream_mod, "atomic_write", boom)

    def test_materialize_hint(self, surface: WheelAssetsConfigSurface, monkeypatch):
        self._deny(monkeypatch)
        with pytest.raises(RuntimeError) as err:
            surface.materialize_overrides(
                {"step_dig": True}, {}, run_all_accounts=False
            )
        msg = str(err.value)
        assert "不可写" in msg
        assert str(surface.config_path.parent) in msg
        # 两条出路都要给：提权运行 MAS；或切直控（「以管理员运行」只提权脚本进程）
        assert "以管理员身份运行 AUTO-MAS" in msg
        assert "直控" in msg

    def test_restore_hint(self, surface: WheelAssetsConfigSurface, monkeypatch):
        (surface.root_path / "configs").mkdir(exist_ok=True)
        surface.config_path.write_text('{"General": {}}', encoding="utf-8")
        ts = surface.snapshot_pre_run()
        assert ts is not None

        self._deny(monkeypatch)
        with pytest.raises(RuntimeError, match="不可写"):
            surface.restore_pre_run(ts)

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
            {"step_dig": True},
            {"jihua_cost": "纽扣松果"},
            run_all_accounts=False,
        )
        data = json.loads(surface.config_path.read_text(encoding="utf-8"))
        # 其他节原样保留
        assert data["General"]["debug"]["value"] == "true"
        # 已有 description 沿用（上游 set() 同款行为）
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

    def test_dedup_returns_latest_ts(self, surface: WheelAssetsConfigSurface):
        (surface.root_path / "configs").mkdir()
        (surface.root_path / "configs" / "config.json").write_text(
            "{}", encoding="utf-8"
        )
        first = surface.snapshot_pre_run()
        second = surface.snapshot_pre_run()
        assert first == second  # 内容未变，指纹去重命中


class TestRestorePools:
    def test_pool_declaration(self):
        """mas = 纯字段侧车（用户级）在前；native = 脚本级、无三态标注。"""

        assert [p.key for p in RESTORE_POOLS] == ["mas", "native"]
        mas, native = RESTORE_POOLS
        assert (mas.kind, mas.mas_mode) == ("user", "sidecar_only")
        assert mas.files is not None and mas.backup_root is not None
        assert mas.preview is not None and mas.restore is not None
        assert (native.kind, native.mas_mode) == ("script", None)
        assert native.files is not None and native.backup_root is not None

    def test_native_pool_is_declarative(self, surface: WheelAssetsConfigSurface):
        """native 池声明 files + backup_root（list/snapshot/read_file 交基座派生）。"""

        import asyncio

        native = next(p for p in RESTORE_POOLS if p.key == "native")

        class Ctx:
            script_config = type(
                "C", (), {"get": lambda self, sec, key: str(surface.root_path)}
            )()

        ctx = Ctx()
        (surface.root_path / "configs").mkdir()
        (surface.root_path / "configs" / "config.json").write_text(
            "{}", encoding="utf-8"
        )

        assert asyncio.run(native.files(ctx)) == {"config.json": surface.config_path}
        assert asyncio.run(native.backup_root(ctx)) == surface.backup_root()

    def test_read_callbacks_degrade_without_root(self):
        """未配置安装目录：只读回调返回 None（编辑页 ensure 不报错）。"""

        import asyncio

        native = next(p for p in RESTORE_POOLS if p.key == "native")

        class Ctx:
            script_config = type("C", (), {"get": lambda self, sec, key: None})()

        assert asyncio.run(native.files(Ctx())) is None
        assert asyncio.run(native.backup_root(Ctx())) is None

    def test_mas_overlay_read_and_group(self):
        """mas 侧车读页面字段；回填分组排除来源段（回填旧来源会静默翻转是否写入）。"""

        import uuid

        from app.task.Whimbox.tools import restore_service as rs

        uid = uuid.uuid4()

        class User:
            def get(self, section, key):
                return {
                    ("Info", "Mode"): "脚本",
                    ("OneDragon", "IfRunAllAccounts"): False,
                    ("Task", "Tasks"): '{"step_dig": false}',
                    ("Task", "Options"): '{"jihua_cost": "纽扣松果"}',
                }.get((section, key))

        class Ctx:
            script_id = "sid"
            user_id = str(uid)
            script_config = type("C", (), {"UserData": {uid: User()}})()

        overlay = rs._read_overlay(Ctx())
        assert overlay["Info"] == {"Mode": "脚本"}
        # 关游戏已改为恒强制，不再是侧车字段（只剩循环全部游戏账号一个流程开关）
        assert overlay["OneDragon"] == {"IfRunAllAccounts": False}
        assert overlay["Task"]["Tasks"] == '{"step_dig": false}'

        grouped = rs._group_restore(overlay)
        assert set(grouped) == {"OneDragon", "Task"}
        assert "Info" not in grouped

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
