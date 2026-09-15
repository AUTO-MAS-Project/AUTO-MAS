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

"""MaaEnd 配置备份恢复原语的最小回归测试。

用临时目录模拟 MAS 配置目录（owner：Default/用户）与 MaaEnd 安装目录
config/，验证两池归档的指纹去重、恢复闭环（含恢复前强制存底）、播种、
脚本模式多用户隔离与备份预览摘要（双分区）的纯逻辑。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.MaaEnd.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_backup_file_summary,
    build_overlay_summary,
    get_mas_backup_dir,
    group_overlay,
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
    (mas_dir / "mxu-MaaEnd.json").write_text(
        json.dumps({"instances": [], "lastActiveInstanceId": ""}), encoding="utf-8"
    )
    overlay = {"IfQuickConfig": True, "IfSanity": False, "SanityMode": "Fixed"}

    # 首次归档（含侧车）→ 内容一致跳过（指纹去重）
    first = archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)
    assert first is not None and (first / "mxu-MaaEnd.json").is_file()
    assert (first / "_mas_overlay.json").is_file()
    assert archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay) is None
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 只改侧车字段（文件未动）→ 指纹变化，新建归档
    overlay2 = {**overlay, "IfSanity": True, "Mode": "脚本"}
    second = archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay2)
    assert second is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    # 恢复到第一份：文件与侧车都回到该时点，侧车不留在 ConfigFile
    restored = restore_mas_backup(
        script_id, user_id, first.name, mas_dir, overlay=overlay2
    )
    assert restored == overlay
    assert not (mas_dir / "_mas_overlay.json").exists()
    # 恢复前存底与最新份内容一致 → 跳过（不产生冗余条目）
    assert len(list_mas_backups(script_id, user_id)) == 2

    # 用户池隔离：另一个用户看不到这个池
    assert list_mas_backups(script_id, "u-other") == []

    # mas 目录为空/缺失时无可归档内容，跳过不报错
    assert archive_mas_backup(script_id, user_id, tmp_path / "elsewhere") is None


def test_native_backup_folder_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池：整目录备份 → 修改 → 恢复闭环；缺失/空目录跳过。"""

    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "native" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "mxu-MaaEnd.json").write_text("{}", encoding="utf-8")
    first = archive_native_backup(config_dir)
    assert first is not None
    (config_dir / "mxu-MaaEnd.json").write_text(
        json.dumps({"instances": [{"id": "b"}]}), encoding="utf-8"
    )
    restore_native_backup(config_dir, first.name)
    assert json.loads((config_dir / "mxu-MaaEnd.json").read_text("utf-8")) == {}
    assert len(list_native_backups(config_dir)) == 2  # 恢复前强制存底 +1

    # 缺失配置/空目录跳过（无可归档内容），不产生归档条目
    assert archive_native_backup(tmp_path / "nope") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert archive_native_backup(empty) is None
    assert list_native_backups(tmp_path / "nope") == []


def test_seed_mas_dir_from_install(tmp_path: Path) -> None:
    """MAS 配置目录缺失时从 MaaEnd 本体播种；已有内容或源缺失时保持原状。"""

    from types import SimpleNamespace

    from app.task.MaaEnd.tools.restore_service import _seed_mas_dir

    install = tmp_path / "MaaEnd" / "config"
    install.mkdir(parents=True)
    (install / "mxu-MaaEnd.json").write_text("{}", encoding="utf-8")
    ctx = SimpleNamespace(
        script_config=SimpleNamespace(get=lambda g, k: str(tmp_path / "MaaEnd"))
    )

    mas_dir = tmp_path / "data" / "s" / "Default" / "ConfigFile"
    _seed_mas_dir(ctx, mas_dir)
    assert (mas_dir / "mxu-MaaEnd.json").is_file()

    # 已有内容不重复播种（不覆盖现场）
    (mas_dir / "mxu-MaaEnd.json").write_text(
        json.dumps({"seeded": True}), encoding="utf-8"
    )
    _seed_mas_dir(ctx, mas_dir)
    assert json.loads((mas_dir / "mxu-MaaEnd.json").read_text("utf-8")) == {
        "seeded": True
    }

    # MaaEnd 路径未配置时静默跳过
    empty_ctx = SimpleNamespace(script_config=SimpleNamespace(get=lambda g, k: ""))
    other = tmp_path / "data" / "s2" / "ConfigFile"
    _seed_mas_dir(empty_ctx, other)
    assert not other.exists()


def test_native_preview_shows_instance_and_tasks(tmp_path: Path) -> None:
    """native 预览：任务启用罗列 + optionValues 配置内容，标签与 mas 同口径。"""

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "mxu-MaaEnd.json").write_text(
        json.dumps(
            {
                "lastActiveInstanceId": "inst-2",
                "instances": [
                    {
                        "id": "inst-1",
                        "name": "别的实例",
                        "tasks": [{"taskName": "DailyRewards", "enabled": True}],
                    },
                    {
                        "id": "inst-2",
                        "name": "AUTO-MAS",
                        "tasks": [
                            {
                                "taskName": "AutoEssence",
                                "customName": "基质刷取",
                                "enabled": True,
                                "optionValues": {
                                    "AutoEssenceMenu": {
                                        "type": "select",
                                        "caseName": "Location",
                                    },
                                    "AutoEssenceSelectLocation": {
                                        "type": "select",
                                        "caseName": "VFTheHub",
                                    },
                                },
                            },
                            {"taskName": "DailyRewards", "enabled": True},
                            {
                                "taskName": "ProtocolSpace",
                                "enabled": False,
                                "optionValues": {
                                    "ProtocolSpaceTab": {
                                        "type": "select",
                                        "caseName": "OperatorProgression",
                                    },
                                    "OperatorProgression": {
                                        "type": "select",
                                        "caseName": "Promotions",
                                    },
                                },
                            },
                            {"taskName": "__MXU_KILLPROC__", "enabled": True},
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (backup / "readme.txt").write_text("skip me", encoding="utf-8")
    (backup / "broken.json").write_text("{oops", encoding="utf-8")

    files = build_backup_file_summary(backup)
    assert [f["name"] for f in files] == ["mxu-MaaEnd.json"]
    # AUTO-MAS 实例优先于最近活跃实例；__MXU_ 内部任务不计入；任务启用
    # 罗列与配置内容表单和 mas 池同词表同口径（基质标签为源码固化词表）
    rows = {row["key"]: row["value"] for row in files[0]["summary"]}
    assert rows["实例"] == "AUTO-MAS"
    assert rows["已启用任务"] == "基质刷取、日常奖励领取"
    assert rows["理智任务"] == "干员养成"
    assert rows["干员养成任务"] == "干员进阶"
    assert rows["基质刷取模式"] == "地区模式"
    assert rows["基质地点"] == "枢纽区"


def test_overlay_preview_sections(tmp_path: Path) -> None:
    """侧车预览：独有/任务启用罗列/配置内容表单三分区，Mode 仅预览不回填。"""

    overlay = {
        "Mode": "脚本",
        "Id": "13084046220",
        "IfQuickConfig": True,
        "SanityMode": "Fixed",
        "SanityTaskType": "Essence",
        "AutoEssenceMenu": "Target",
        "AutoEssenceTargetWeapons": ["Weapon1", "Weapon2"],
        "OperatorProgression": "OperatorEXP",
        "WeaponProgression": "WeaponEXP",
        "CrisisDrills": "AdvancedProgression1",
        "RewardsSetOption": "RewardsSetA",
        "IfSanity": True,
        "IfAutoUseSpMedication": False,
        "IfSeizeDeliveryJobs": True,
        "SeizeDeliveryJobsReward": 15.9,
        "SeizeDeliveryJobsCommissionSource": "WulingCity",
        "IfAutoCollect": True,
        "AutoCollectMode": "Distributed",
        "AutoCollectRoutes": ["Route1", "Route2", "Route3"],
        "AutoCollectCommonRoutes": ["CommonRoute1"],
        "DailyOnceTasks": ["Sanity", "VisitFriends"],
    }
    sections = {section["name"]: section for section in build_overlay_summary(overlay)}
    assert set(sections) == {"mas-only", "tasks", "config"}

    # MAS 独有区：MaaEnd GUI 无对应概念的调度类字段
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["summary"]}
    assert mas_rows == {
        "配置文件来源": "脚本",
        "快速配置": "是",
        "每日仅执行一次": "理智任务、拜访好友",
    }

    # 任务启用：罗列行（启用了哪些；夹具未提供的开关视为关）
    tasks_rows = {row["key"]: row["value"] for row in sections["tasks"]["summary"]}
    assert tasks_rows == {"已启用任务": "理智作战、抢委托送货、自动采集"}

    # 配置内容：表单行（理智全类型已存配置 + 送货/采集细节 + 账号）
    # 基质刷取类型无奖励组（奖励组仅干员/武器养成且选项带奖励组时显示）
    # 武器名随版本漂移，展示数量而不是臆造译文
    config_rows = {row["key"]: row["value"] for row in sections["config"]["summary"]}
    assert config_rows == {
        "账号": "130****6220",
        "理智任务配置模式": "固定",
        "理智任务": "基质刷取",
        "基质刷取模式": "目标选择",
        "目标武器": "已选 2 把",
        "干员养成任务": "干员经验",
        "武器养成任务": "武器经验",
        "危境预演任务": "高阶培养 I",
        "送货最低接取价格（万）": "15.9",
        "委托接收点": "武陵城",
        "采集安排": "分散采集",
        "区域采集路线": "已选 3 / 15 条",
        "通用采集路线": "已选 1 / 8 条",
    }

    # 分组回填：Info/Task 各归其段；仅预览字段（Mode）不回填
    grouped = group_overlay(overlay)
    assert set(grouped) == {"Info", "Task"}
    assert grouped["Info"]["IfQuickConfig"] is True
    assert grouped["Task"]["IfSanity"] is True
    assert "Mode" not in grouped["Info"]


def test_overlay_preview_gates_quick_config_fields(tmp_path: Path) -> None:
    """快速配置关闭时覆盖层字段不生效，任务启用/配置内容（除账号）隐藏。"""

    overlay = {
        "IfQuickConfig": False,
        "Id": "13084046220",
        "SanityMode": "Fixed",
        "IfSanity": True,
        "IfSeizeDeliveryJobs": True,
        "DailyOnceTasks": ["VisitFriends"],
    }
    sections = {section["name"]: section for section in build_overlay_summary(overlay)}
    assert set(sections) == {"mas-only", "config"}

    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["summary"]}
    assert mas_rows == {
        "快速配置": "否",
        "每日仅执行一次": "拜访好友",
    }

    # 账号不受门控（登录与账号切换始终生效），其余覆盖层字段隐藏
    config_rows = {row["key"]: row["value"] for row in sections["config"]["summary"]}
    assert config_rows == {"账号": "130****6220"}


def test_overlay_preview_sanitizes_protocol_sanity(tmp_path: Path) -> None:
    """理智任务全类型配置都记录，不止当前选中类型。"""

    overlay = {
        "IfQuickConfig": True,
        "SanityTaskType": "OperatorProgression",
        "OperatorProgression": "Promotions",
        "WeaponProgression": "WeaponEXP",
        "CrisisDrills": "AdvancedProgression2",
        "RewardsSetOption": "RewardsSetA",
    }
    sections = {section["name"]: section for section in build_overlay_summary(overlay)}
    config_rows = {row["key"]: row["value"] for row in sections["config"]["summary"]}
    assert config_rows["理智任务"] == "干员养成"
    assert config_rows["干员养成任务"] == "干员进阶"
    assert config_rows["武器养成任务"] == "武器经验"
    assert config_rows["危境预演任务"] == "高阶培养 II"
    assert config_rows["奖励组"] == "奖励组 A"

    # 当前任务取值不带奖励组（T-Creds）时奖励组行不显示，其余类型仍记录
    sections2 = {
        section["name"]: section
        for section in build_overlay_summary(
            {**overlay, "OperatorProgression": "T-Creds"}
        )
    }
    config_rows2 = {row["key"]: row["value"] for row in sections2["config"]["summary"]}
    assert config_rows2["干员养成任务"] == "钱币收集"
    assert "奖励组" not in config_rows2


def test_overlay_preview_resolves_essence_labels(tmp_path: Path) -> None:
    """基质刷取模式/地点标签用源码固化 zh_cn 词表（与 MXU GUI 一致）。"""

    overlay = {
        "IfQuickConfig": True,
        "SanityTaskType": "Essence",
        "AutoEssenceMenu": "Location",
        "AutoEssenceSpecifiedLocation": "VFTheHub",
        "AutoEssenceTargetWeapons": ["wpn_funnel_0008", "wpn_sword_0005"],
    }
    sections = {section["name"]: section for section in build_overlay_summary(overlay)}
    config_rows = {row["key"]: row["value"] for row in sections["config"]["summary"]}
    assert config_rows["理智任务"] == "基质刷取"
    assert config_rows["基质刷取模式"] == "地区模式"
    assert config_rows["基质地点"] == "枢纽区"
    # 武器名随版本漂移，展示数量而不是臆造译文
    assert config_rows["目标武器"] == "已选 2 把"


def test_preview_mas_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mas 池预览回调：签名/三分区载荷端到端（池函数真实调用链）。"""

    from app.task.MaaEnd.tools.restore_service import _preview_mas

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0005", "u-0005"
    mas_dir = tmp_path / "data" / script_id / user_id / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "mxu-MaaEnd.json").write_text("{}", encoding="utf-8")
    archive_mas_backup(
        script_id, user_id, mas_dir, overlay={"IfQuickConfig": True, "IfSanity": True}
    )
    ts = list_mas_backups(script_id, user_id)[0]

    # MaaEnd 路径指向空目录：资源加载失败走原值回退
    (tmp_path / "MaaEnd" / "config").mkdir(parents=True)
    ctx = SimpleNamespace(
        script_id=script_id,
        user_id=user_id,
        script_config=SimpleNamespace(get=lambda g, k: str(tmp_path / "MaaEnd")),
    )
    payload = asyncio.run(_preview_mas(ctx, ts))
    cards = {f["name"]: f for f in payload["fileCards"]}
    # 夹具只有开关没有账号/理智选项，配置内容区无行时整体省略
    assert set(cards) == {"mas-only", "tasks"}
    tasks_rows = {row["key"]: row["value"] for row in cards["tasks"]["summary"]}
    assert tasks_rows["已启用任务"] == "理智作战"


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


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级真实调用链：声明式 snapshot（含播种）→ preview → restore。"""

    from types import SimpleNamespace

    from app.task.MaaEnd.tools import restore_service as rs
    from app.utils.config_restore import RestoreContext, build_restore_service

    monkeypatch.chdir(tmp_path)
    script_id, uid = "s-0006", uuid.uuid4()
    install = tmp_path / "MaaEnd" / "config"
    install.mkdir(parents=True)
    (install / "mxu-MaaEnd.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "automas",
                        "name": "AUTO-MAS",
                        "tasks": [{"taskName": "MAA_END_SANITY", "enabled": True}],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _FakeUser:
        def __init__(self):
            self.updated: list[dict] = []

        def get(self, section: str, key: str):
            data = {
                "Info": {"Mode": "用户", "Id": "13084046220"},
                "Task": {"IfQuickConfig": False},
            }
            return data.get(section, {}).get(key)

        async def update(self, values: dict) -> None:
            self.updated.append(values)

    user = _FakeUser()
    script_config = SimpleNamespace(
        get=lambda g, k: {("Info", "Path"): str(tmp_path / "MaaEnd")}.get((g, k), ""),
        UserData={uid: user},
    )
    ctx = RestoreContext(
        config=None, script_config=script_config, script_id=script_id, user_id=str(uid)
    )
    service = build_restore_service(ctx, rs.RESTORE_SCRIPT_NAME, rs.RESTORE_POOLS)

    # mas：目录缺失 → 播种后声明式归档（侧车读取自 ctx 用户配置）
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    mas_dir = tmp_path / "data" / script_id / str(uid) / "ConfigFile"
    assert (mas_dir / "mxu-MaaEnd.json").is_file()  # 播种生效

    payload = asyncio.run(service.preview("mas", created["time"]))
    assert "fileCards" in payload  # 定制预览自带侧车分区载荷
    # 快速配置关闭时任务启用/配置细节隐藏，但账号行不受门控（config 区仍在）
    assert {section["name"] for section in payload["fileCards"]} == {
        "mas-only",
        "config",
        "mxu-MaaEnd.json",  # 副本里的 mxu 摘要与 native 池同口径共用渲染
    }

    # 声明式 read_file（基座从 backup_root 派生）
    content = asyncio.run(
        service.read_backup_file("mas", created["time"], "_mas_overlay.json")
    )
    assert "13084046220" in content["content"]

    # 恢复：文件回滚 + 侧车按段回填（Mode 仅预览不回填）
    asyncio.run(service.restore("mas", created["time"]))
    assert user.updated == [{"Info": {"Id": "13084046220"}}]

    # native：快照 + 恢复闭环（预览载荷带 fileCards 键）
    created_native = asyncio.run(service.ensure("native"))
    assert created_native["created"] is True
    payload_native = asyncio.run(service.preview("native", created_native["time"]))
    assert "fileCards" in payload_native
    # 同一份 mxu 文件两池同口径：mas 摘要行与 native 完全一致
    mas_mxu = next(c for c in payload["fileCards"] if c["name"] == "mxu-MaaEnd.json")
    native_mxu = next(
        c for c in payload_native["fileCards"] if c["name"] == "mxu-MaaEnd.json"
    )
    assert mas_mxu["summary"] == native_mxu["summary"]
    asyncio.run(service.restore("native", created_native["time"]))
