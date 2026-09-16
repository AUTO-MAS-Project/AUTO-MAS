#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MAA 配置备份恢复原语的最小回归测试。

用临时目录模拟 MAS 配置目录（owner：Default/用户）与 MAA 安装目录
config/，验证两池归档的指纹去重、恢复闭环（含恢复前强制存底）、运行前
归档的缺目录容错、脚本模式多用户隔离与备份预览摘要的纯逻辑。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.MAA.tools.backup_archive import (
    archive_mas_backup,
    archive_mas_runtime_backup,
    archive_native_backup,
    build_backup_file_summary,
    get_mas_backup_dir,
    list_mas_backups,
    list_native_backups,
    restore_mas_backup,
    restore_native_backup,
)


def test_mas_backup_dedup_and_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池：无备份即建、内容一致跳过、内容/侧车变化再建、恢复闭环。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "gui.json").write_text(
        json.dumps({"Current": "Default", "Global": {}}), encoding="utf-8"
    )
    overlay = {
        "IfFight": True,
        "IfInfrast": False,
        "ActivityStageIndex": 3,
        "Server": "Official",
    }

    # 首次归档（含侧车）→ 内容一致跳过（指纹去重）
    first = archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)
    assert first is not None and (first / "gui.json").is_file()
    assert (first / "_mas_overlay.json").is_file()
    assert archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay) is None
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 只改侧车字段（文件未动）→ 指纹变化，新建归档
    overlay2 = {**overlay, "IfFight": False, "Server": "Bilibili"}
    second = archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay2)
    assert second is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    # 只改文件（侧车同第二份）→ 同样新建归档
    (mas_dir / "gui.new.json").write_text("{}", encoding="utf-8")
    assert archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay2) is not None
    assert len(list_mas_backups(script_id, user_id)) == 3

    # 恢复到第一份：文件与侧车都回到该时点，侧车不留在 ConfigFile
    restored = restore_mas_backup(
        script_id, user_id, first.name, mas_dir, overlay=overlay2
    )
    assert restored == overlay
    assert not (mas_dir / "gui.new.json").exists()
    assert not (mas_dir / "_mas_overlay.json").exists()
    # 恢复前存底与最新份内容一致 → 跳过（不产生冗余条目）
    assert len(list_mas_backups(script_id, user_id)) == 3

    # 用户池隔离：另一个用户看不到这个池
    assert list_mas_backups(script_id, "u-other") == []

    # mas 目录为空/缺失时无可归档内容，跳过不报错
    assert archive_mas_backup(script_id, user_id, tmp_path / "elsewhere") is None


def test_mas_backup_mode_annotation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """tri_state 池：运行前/恢复前归档带 mode 标注，跨来源恢复不退化为旧版无标注。"""

    from app.utils.config_archive import read_backup_mode

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0009", "u-0001"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "gui.json").write_text("{}", encoding="utf-8")

    # 运行前归档带 mode → 备份有 _mas_mode 标注
    dest = archive_mas_backup(script_id, user_id, mas_dir, mode="用户")
    assert dest is not None
    assert read_backup_mode(dest) == "用户"

    # 恢复前 force 存底透传 mode（set_mode 已切回备份来源后存底）
    force_dir = restore_mas_backup(
        script_id, user_id, dest.name, mas_dir, overlay=None, mode="脚本"
    )
    assert force_dir is None  # 存底与最新份内容一致 → 指纹跳过，不产生新条目

    # 未传 mode → 无标注（与旧版无标注备份一致，恢复时不切来源）
    (mas_dir / "gui.new.json").write_text("{}", encoding="utf-8")
    plain = archive_mas_backup(script_id, user_id, mas_dir)
    assert plain is not None
    assert read_backup_mode(plain) is None


def test_mas_pool_isolates_script_mode_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """脚本模式多用户共享 Default 目录，但池按用户隔离。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_a, user_b = "s-0002", "u-aaa", "u-bbb"
    # 脚本模式：下发源是共享 Default 目录（两个用户指向同一份）
    default_dir = tmp_path / "data" / script_id / "Default" / "ConfigFile"
    default_dir.mkdir(parents=True)
    (default_dir / "gui.json").write_text(
        json.dumps({"Current": "Default"}), encoding="utf-8"
    )

    first = archive_mas_backup(script_id, user_a, default_dir)
    assert first is not None
    (default_dir / "gui.json").write_text(
        json.dumps({"Current": "方案B"}), encoding="utf-8"
    )
    second = archive_mas_backup(script_id, user_b, default_dir)
    assert second is not None

    # 两用户池完全隔离：各只看到自己的备份
    assert list_mas_backups(script_id, user_a) == [first.name]
    assert list_mas_backups(script_id, user_b) == [second.name]

    # A 恢复自己的备份：文件回滚到 Default
    restore_mas_backup(script_id, user_a, first.name, default_dir)
    assert json.loads((default_dir / "gui.json").read_text("utf-8")) == {
        "Current": "Default"
    }
    assert len(list_mas_backups(script_id, user_a)) == 2  # 恢复前强制存底 +1


def test_native_backup_folder_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池：整目录备份 → 修改 → 恢复闭环；缺失/空目录跳过。"""

    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "native" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "gui.json").write_text(
        json.dumps({"Current": "Default"}), encoding="utf-8"
    )
    first = archive_native_backup(config_dir)
    assert first is not None
    (config_dir / "gui.json").write_text(
        json.dumps({"Current": "方案X"}), encoding="utf-8"
    )
    restore_native_backup(config_dir, first.name)
    assert json.loads((config_dir / "gui.json").read_text("utf-8")) == {
        "Current": "Default"
    }
    assert len(list_native_backups(config_dir)) == 2  # 恢复前强制存底 +1

    # 缺失配置/空目录跳过（无可归档内容），不产生归档条目
    assert archive_native_backup(tmp_path / "nope") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert archive_native_backup(empty) is None
    assert list_native_backups(tmp_path / "nope") == []


def test_runtime_backup_skips_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """运行前归档：mas 目录缺失静默跳过，绝不抛错；存在则正常归档。"""

    monkeypatch.chdir(tmp_path)
    archive_mas_runtime_backup("s-0003", "u-0003", tmp_path / "nope")
    assert list_mas_backups("s-0003", "u-0003") == []

    mas_dir = tmp_path / "data" / "s-0003" / "u-0003" / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "a.json").write_text("{}", encoding="utf-8")
    archive_mas_runtime_backup("s-0003", "u-0003", mas_dir)
    assert len(list_mas_backups("s-0003", "u-0003")) == 1


def test_preview_summary_keeps_stable_fields(tmp_path: Path) -> None:
    """native 预览：标签/取值与 MAS 侧同口径，TaskQueue 反读任务开关与参数。"""

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "gui.json").write_text(
        json.dumps(
            {
                "Current": "Default",
                "Configurations": {
                    "Default": {
                        "Connect.Address": "127.0.0.1:16384",
                        "Start.ClientType": "Official",
                        "Start.StartGame": "True",
                    },
                    "B": {},
                },
            }
        ),
        encoding="utf-8",
    )
    (backup / "gui.new.json").write_text(
        json.dumps(
            {
                "Current": "Default",
                "Configurations": {
                    "Default": {
                        "Gui": {
                            "ConnectSettings": {"Address": "127.0.0.1:16384"},
                            "RuntimeSettings": {"ClientType": 1, "StartGame": True},
                        },
                        "TaskQueue": [
                            {
                                "$type": "StartUpTask",
                                "TaskType": "StartUp",
                                "Name": "开始唤醒",
                                "IsEnable": True,
                                "AccountName": "13084046220",
                            },
                            {
                                "$type": "FightTask",
                                "TaskType": "Fight",
                                "Name": "理智作战",
                                "IsEnable": True,
                                "UseMedicine": True,
                                "MedicineCount": 998,
                                "Series": 0,
                                "StagePlan": ["1-7", ""],
                            },
                            # 缺 TaskType/$type：按中文名兜底识别
                            {"Name": "自动公招", "IsEnable": False},
                            {
                                "$type": "InfrastTask",
                                "TaskType": "Infrast",
                                "Name": "基建换班",
                                "IsEnable": False,
                                "Mode": "Custom",
                            },
                            # 剩余理智是第二个 Fight 任务，单独成行
                            {
                                "$type": "FightTask",
                                "TaskType": "Fight",
                                "Name": "剩余理智",
                                "IsEnable": False,
                                "StagePlan": [],
                            },
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (backup / "broken.json").write_text("{oops", encoding="utf-8")
    (backup / "readme.txt").write_text("skip me", encoding="utf-8")
    (backup / "other_config.json").write_text(
        json.dumps({"Anything": 1}), encoding="utf-8"
    )

    files = build_backup_file_summary(backup)
    by_name = {f["name"]: f for f in files}
    # 白名单外/坏 JSON/非 JSON 文件不进预览
    assert set(by_name) == {"gui.json", "gui.new.json"}

    gui = by_name["gui.json"]
    assert gui["label"] == "MAA 设置"
    assert {row["key"]: row["value"] for row in gui["summary"]} == {
        "当前方案": "Default",
        "连接地址": "127.0.0.1:16384",
        "服务器": "官服",
        "启动游戏": "是",
    }

    gui_new = by_name["gui.new.json"]
    assert gui_new["label"] == "MAA 设置（新版）"
    assert {row["key"]: row["value"] for row in gui_new["summary"]} == {
        "当前方案": "Default",
        "连接地址": "127.0.0.1:16384",
        "服务器": "B服",
        "启动游戏": "是",
        "自动唤醒": "是",
        "账号": "130****6220",
        "理智作战": "是",
        "吃理智药": "998",
        "连战次数": "AUTO",
        "关卡": "1-7",
        "公开招募": "否",
        "基建换班": "否",
        "基建模式": "自定义",
        "剩余理智": "否",
        "剩余理智关卡": "不选择",
    }


def test_fight_stage_plan_default_shows_current(tmp_path: Path) -> None:
    """空 StagePlan = MAA GUI 的「关卡指定=当前/上次」，不是「不选择」。"""

    from app.task.MAA.tools.backup_archive import build_backup_file_summary

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "gui.new.json").write_text(
        json.dumps(
            {
                "Current": "Default",
                "Configurations": {
                    "Default": {
                        "TaskQueue": [
                            {
                                "$type": "FightTask",
                                "TaskType": "Fight",
                                "Name": "理智作战",
                                "IsEnable": True,
                                # 使用药剂未勾选但数量仍显示配置值（对齐 GUI）
                                "UseMedicine": False,
                                "MedicineCount": 998,
                                "StagePlan": [],
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    files = build_backup_file_summary(backup)
    rows = {row["key"]: row["value"] for row in files[0]["summary"]}
    assert rows["关卡"] == "当前/上次"
    assert rows["吃理智药"] == "998"


def test_overlay_preview_shows_core_fields(tmp_path: Path) -> None:
    """侧车预览：MAS 独有/MAA 对应双分区，枚举/哨兵值/账号脱敏正确。"""

    from app.task.MAA.tools.backup_archive import build_overlay_summary, group_overlay

    overlay = {
        "Server": "Official",
        "Id": "13084046220",
        "Mode": "脚本",
        "StageMode": "Fixed",
        "IfStartUp": True,
        "IfFight": False,
        "IfGreenTicketStore": True,
        "MedicineNumb": 998,
        "SeriesNumb": "0",
        "Stage": "-",
        "Stage_1": "1-7",
        "Stage_Remain": "",
        "IfActivityFirst": True,
        "ActivityStageIndex": 3,
        "ActivityMedicineNumb": 0,
        "Annihilation": "Annihilation",
        "AnnihilationStartWeekday": "Monday",
        "IfDepotMaintain": False,
        "DepotMaintainPlans": "[]",
        "InfrastMode": "Normal",
        "InfrastName": "未使用自定义基建模式",
    }
    sections = {section["name"]: section for section in build_overlay_summary(overlay)}
    assert set(sections) == {"mas-only", "maa"}

    # MAS 独有区：查看详细配置看不到的字段，全量展示
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["summary"]}
    assert mas_rows == {
        "配置文件来源": "脚本",
        "关卡配置模式": "固定",
        "剿灭开始星期": "周一",
        "活动关优先": "是",
        "活动关卡序号": "3",
        "活动理智药": "0",
        "绿票商店": "是",
        "库存保持计划": "无",
    }

    # MAA 对应区：与 MAA GUI 同口径；关卡为合成后的具体刷本内容
    maa_rows = {row["key"]: row["value"] for row in sections["maa"]["summary"]}
    assert maa_rows == {
        "服务器": "官服",
        "账号": "130****6220",
        "自动唤醒": "是",
        "理智作战": "否",
        "库存保持": "否",
        "吃理智药": "998",
        "连战次数": "AUTO",
        "关卡": "1-7",
        "剩余理智关卡": "不选择",
        "剿灭模式": "当期剿灭",
        "基建模式": "标准",
    }

    # 自定义模式：基建配置名进预览
    sections2 = {
        section["name"]: section
        for section in build_overlay_summary(
            {**overlay, "InfrastMode": "Custom", "InfrastName": " my plan - v2 "}
        )
    }
    maa_rows2 = {row["key"]: row["value"] for row in sections2["maa"]["summary"]}
    assert maa_rows2["基建模式"] == "自定义"
    assert maa_rows2["基建配置"] == " my plan - v2 "

    # 全部关卡槽位禁用 → 与配置界面折叠摘要同口径显示当前/上次
    overlay_all_disabled = {
        **overlay,
        "Stage": "-",
        "Stage_1": "-",
        "Stage_2": "-",
        "Stage_3": "-",
    }
    sections3 = {
        section["name"]: section
        for section in build_overlay_summary(overlay_all_disabled)
    }
    maa_rows3 = {row["key"]: row["value"] for row in sections3["maa"]["summary"]}
    assert maa_rows3["关卡"] == "当前/上次"

    # 分组回填：Info/Task 各归其段；仅预览字段（Mode）不回填
    grouped = group_overlay(overlay)
    assert set(grouped) == {"Info", "Task"}
    assert grouped["Info"]["Server"] == "Official"
    assert grouped["Task"]["IfFight"] is False
    assert "Mode" not in grouped["Info"]


def test_overlay_cultivate_fields_in_sidecar_and_preview() -> None:
    """干员养成 4 字段进侧车，预览 MAS 独有区含养成行（目标只给数量不臆造）。"""

    from app.task.MAA.tools.backup_archive import (
        build_overlay_summary,
        read_overlay_values,
    )

    class _FakeUserConfig:
        _data = {
            "Task": {
                "IfCultivate": True,
                "CultivateTargets": json.dumps(
                    [
                        {"operatorId": "char_001", "name": "能天使", "goals": []},
                        {"operatorId": "char_002", "name": "银灰", "goals": []},
                    ],
                    ensure_ascii=False,
                ),
                "CultivateSkipDuringActivity": True,
                "CultivateSkipDuringResourceCollection": False,
            }
        }

        def get(self, section: str, key: str):
            return self._data.get(section, {}).get(key)

    # 侧车含 4 个干员养成字段（read_overlay_values 走 _OVERLAY_TASK_KEYS）
    values = read_overlay_values(_FakeUserConfig())
    assert set(values) == {
        "IfCultivate",
        "CultivateTargets",
        "CultivateSkipDuringActivity",
        "CultivateSkipDuringResourceCollection",
    }

    # 预览：养成 4 行全部在 MAS 独有区；养成目标只显示数量
    sections = {s["name"]: s for s in build_overlay_summary(values)}
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["summary"]}
    assert mas_rows == {
        "干员养成": "是",
        "养成目标": "已配置 2 个目标",
        "活动期间跳过": "是",
        "资源收集期间跳过": "否",
    }
    assert "maa" not in sections

    # 空目标 / 坏 JSON 的展示兜底
    empty = build_overlay_summary(
        {
            "IfCultivate": False,
            "CultivateTargets": "[]",
            "CultivateSkipDuringActivity": False,
            "CultivateSkipDuringResourceCollection": False,
        }
    )
    empty_rows = {row["key"]: row["value"] for row in empty[0]["summary"]}
    assert empty_rows["干员养成"] == "否"
    assert empty_rows["养成目标"] == "无"


def test_read_overlay_values_covers_both_groups() -> None:
    """read_overlay_values 覆盖 Info/Task 两段，None 值键跳过。"""

    from app.task.MAA.tools.backup_archive import read_overlay_values

    class _FakeUserConfig:
        _data = {
            "Info": {"Server": "Bilibili", "Stage": "-", "InfrastName": None},
            "Task": {"IfFight": True, "DepotMaintainPlans": "[]"},
        }

        def get(self, section: str, key: str):
            return self._data.get(section, {}).get(key)

    values = read_overlay_values(_FakeUserConfig())
    assert values == {
        "Server": "Bilibili",
        "Stage": "-",
        "IfFight": True,
        "DepotMaintainPlans": "[]",
    }


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0004", "u-0004"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "a.json").write_text("{}", encoding="utf-8")
    archive_mas_backup(script_id, user_id, mas_dir)
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "20260913-000000") is None
    assert get_mas_backup_dir(script_id, user_id, "../../../evil") is None


def test_seed_mas_dir_from_install(tmp_path: Path) -> None:
    """MAS 配置目录缺失时从 MAA 本体播种；已有内容或源缺失时保持原状。"""

    from types import SimpleNamespace

    from app.task.MAA.tools.restore_service import _seed_mas_dir

    install = tmp_path / "MAA" / "config"
    install.mkdir(parents=True)
    (install / "gui.json").write_text("{}", encoding="utf-8")
    ctx = SimpleNamespace(
        script_config=SimpleNamespace(get=lambda g, k: str(tmp_path / "MAA"))
    )

    mas_dir = tmp_path / "data" / "s" / "Default" / "ConfigFile"
    _seed_mas_dir(ctx, mas_dir)
    assert (mas_dir / "gui.json").is_file()

    # 已有内容不重复播种（不覆盖现场）
    (mas_dir / "gui.json").write_text(json.dumps({"Current": "X"}), encoding="utf-8")
    _seed_mas_dir(ctx, mas_dir)
    assert json.loads((mas_dir / "gui.json").read_text("utf-8")) == {"Current": "X"}

    # MAA 路径未配置时静默跳过
    empty_ctx = SimpleNamespace(script_config=SimpleNamespace(get=lambda g, k: ""))
    other = tmp_path / "data" / "s2" / "ConfigFile"
    _seed_mas_dir(empty_ctx, other)
    assert not other.exists()


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级真实调用链：声明式 snapshot（含播种）→ preview → restore。"""

    from app.task.MAA.tools import restore_service as rs
    from app.utils.config_restore import RestoreContext, build_restore_service

    monkeypatch.chdir(tmp_path)
    script_id, uid = "s-0005", uuid.uuid4()
    install = tmp_path / "MAA" / "config"
    install.mkdir(parents=True)
    (install / "gui.json").write_text(
        json.dumps(
            {
                "Current": "Default",
                "Configurations": {"Default": {"Connect.Address": "127.0.0.1:16384"}},
            }
        ),
        encoding="utf-8",
    )

    class _FakeUser:
        def __init__(self):
            self.updated: list[dict] = []

        def get(self, section: str, key: str):
            data = {
                "Info": {"Mode": "用户", "Server": "Official"},
                "Task": {"IfFight": True},
            }
            return data.get(section, {}).get(key)

        async def update(self, values: dict) -> None:
            self.updated.append(values)

    user = _FakeUser()
    script_config = SimpleNamespace(
        get=lambda g, k: {("Info", "Path"): str(tmp_path / "MAA")}.get((g, k), ""),
        UserData={uid: user},
    )
    ctx = RestoreContext(
        config=None, script_config=script_config, script_id=script_id, user_id=str(uid)
    )
    service = build_restore_service(ctx, rs.RESTORE_POOLS)

    # mas：目录缺失 → 播种后声明式归档（侧车读取自 ctx 用户配置）
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    mas_dir = tmp_path / "data" / script_id / str(uid) / "ConfigFile"
    assert (mas_dir / "gui.json").is_file()  # 播种生效

    payload = asyncio.run(service.preview("mas", created["time"]))
    assert "fileCards" in payload  # 定制预览自带侧车分区载荷
    assert {section["name"] for section in payload["fileCards"]} == {
        "mas-only",
        "maa",
        "gui.json",  # 副本里的 gui.json 摘要与 native 池同口径共用渲染
    }

    # 声明式 read_file（基座从 backup_root 派生）
    content = asyncio.run(
        service.read_backup_file("mas", created["time"], "_mas_overlay.json")
    )
    assert "IfFight" in content["content"]

    # 恢复：文件回滚 + 侧车按段回填（Mode 仅预览不回填）
    asyncio.run(service.restore("mas", created["time"]))
    assert user.updated == [{"Info": {"Server": "Official"}, "Task": {"IfFight": True}}]

    # native：快照 + 恢复闭环（预览载荷带 fileCards 键）
    created_native = asyncio.run(service.ensure("native"))
    assert created_native["created"] is True
    payload_native = asyncio.run(service.preview("native", created_native["time"]))
    assert "fileCards" in payload_native
    # 同一份 gui.json 两池同口径：mas 摘要行与 native 完全一致
    mas_gui = next(c for c in payload["fileCards"] if c["name"] == "gui.json")
    native_gui = next(c for c in payload_native["fileCards"] if c["name"] == "gui.json")
    assert mas_gui["summary"] == native_gui["summary"]
    asyncio.run(service.restore("native", created_native["time"]))
