#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""M9A 配置备份恢复原语的最小回归测试。

M9A 无 per-user ConfigFile 目录：mas 池是纯字段侧车（Info 核心 + Queue
原始值 + Display 展示快照），native 池是安装目录 config/ 整目录。用临时
目录与鸭子类型配置对象验证两池归档的指纹去重、恢复闭环、选项翻译与
降级、预览分区摘要，以及 service 级真实调用链（声明式快照、基座
files 注入）。
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.M9A.tools.backup_archive import (
    archive_mas_backup,
    archive_native_backup,
    build_display_overlay,
    build_native_preview,
    build_overlay_preview,
    build_queue_display,
    get_mas_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)

_QUEUE = json.dumps(
    [
        {"name": "常规作战", "options": [{"name": "难度", "index": 1}]},
        {"name": "自动深眠", "options": []},
    ],
    ensure_ascii=False,
)

_OPTION_DEFINITIONS = {
    "难度": {
        "type": "select",
        "cases": [{"name": "简单"}, {"name": "困难"}],
        "default_case": "简单",
    },
}


class _FakeTaskLoader:
    """鸭子类型任务加载器（仅需 get_full_definition）。"""

    def __init__(self, definitions: dict | None = None):
        self._definitions = definitions or {}

    def get_full_definition(self, task_name: str):
        if task_name in self._definitions:
            return {
                "name": task_name,
                "_option_definitions": self._definitions[task_name],
            }
        return None


class _FakeUser:
    """鸭子类型用户配置（read_overlay_values / update 回填验证）。"""

    def __init__(self, values: dict):
        self._values = values
        self.updated: list[dict] = []

    def get(self, group: str, key: str):
        return self._values.get(f"{group}.{key}")

    async def update(self, grouped: dict):
        self.updated.append(grouped)


def test_mas_overlay_grouping_and_dedup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车归档：指纹去重、字段变化再建、group_overlay 排除 Mode/Display。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0001", "u-0001"
    user = _FakeUser(
        {
            "Info.Mode": "用户",
            "Info.IfQuickConfig": True,
            "Info.Resource": "官服",
            "Info.Account": "13012345678",
            "Task.Queue": _QUEUE,
        }
    )
    overlay = build_display_overlay(read_overlay_values(user), _FakeTaskLoader())
    assert "Display" in overlay

    first = archive_mas_backup(script_id, user_id, overlay)
    assert first is not None
    assert archive_mas_backup(script_id, user_id, overlay) is None  # 指纹去重
    assert len(list_mas_backups(script_id, user_id)) == 1

    # 字段变化（表单保存）→ 侧车指纹变化 → 新建归档
    overlay2 = build_display_overlay(
        {**read_overlay_values(user), "Resource": "B服"}, _FakeTaskLoader()
    )
    assert archive_mas_backup(script_id, user_id, overlay2) is not None
    assert len(list_mas_backups(script_id, user_id)) == 2

    grouped = group_overlay(overlay2)
    assert set(grouped) == {"Info", "Task"}
    assert "Mode" not in grouped["Info"]  # 配置来源只预览不回填
    assert grouped["Task"]["Queue"] == _QUEUE


def test_queue_display_translation_and_fallback() -> None:
    """展示快照：index 翻译成 case 名、checkbox/输入值直出、定义缺失降级。"""

    queue = [
        {
            "name": "常规作战",
            "options": [
                {"name": "难度", "index": 1},
                {
                    "name": "关卡选择",
                    "index": 0,
                    "selected_cases": ["主线", "活动"],
                },
                {"name": "次数", "index": 0, "input_values": {"体力": 60}},
            ],
        },
        {"name": "未定义任务", "options": [{"name": "难度", "index": 1}]},
    ]
    loader = _FakeTaskLoader({"常规作战": _OPTION_DEFINITIONS})
    display = build_queue_display(queue, loader)
    assert display[0]["name"] == "常规作战"
    values = {row["name"]: row["value"] for row in display[0]["options"]}
    assert values["难度"] == "困难"  # index → case 名
    assert values["关卡选择"] == "主线、活动"  # checkbox case 名直出
    assert values["次数"] == "体力=60"  # 输入值直出
    # 任务定义缺失：降级为原始 index
    fallback = {row["name"]: row["value"] for row in display[1]["options"]}
    assert fallback["难度"] == "1"

    # 无任务定义加载器：全部降级为原始值
    no_loader = build_queue_display(queue, None)
    assert {row["name"]: row["value"] for row in no_loader[0]["options"]}["难度"] == "1"


def test_native_backup_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池：整目录备份 → 修改 → 恢复闭环；缺失/空目录跳过。"""

    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "native" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text("{}", encoding="utf-8")
    first = archive_native_backup(config_dir)
    assert first is not None
    (config_dir / "config.json").write_text(
        json.dumps({"Language": "zh-Hans"}), encoding="utf-8"
    )
    restore_native_backup(config_dir, first.name)
    assert json.loads((config_dir / "config.json").read_text("utf-8")) == {}
    assert len(list_native_backups(config_dir)) == 2  # 恢复前强制存底 +1

    assert archive_native_backup(tmp_path / "nope") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert archive_native_backup(empty) is None
    assert list_native_backups(tmp_path / "nope") == []


def test_overlay_preview_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池预览：三分区（MAS 独有 / M9A 配置 / 任务配置详情）与账号脱敏。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0002", "u-0002"
    overlay = build_display_overlay(
        {
            "Mode": "用户",
            "IfQuickConfig": True,
            "Resource": "官服",
            "Account": "13012345678",
            "Queue": _QUEUE,
        },
        _FakeTaskLoader({"常规作战": _OPTION_DEFINITIONS}),
    )
    archive_mas_backup(script_id, user_id, overlay)
    ts = list_mas_backups(script_id, user_id)[0]
    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    assert backup_dir is not None
    payload = build_overlay_preview(
        json.loads((backup_dir / "_mas_overlay.json").read_text("utf-8"))
    )

    sections = {s["name"]: s for s in payload["sections"]}
    assert set(sections) == {"mas-only", "m9a", "task-details"}
    mas_rows = {row["key"]: row["value"] for row in sections["mas-only"]["rows"]}
    assert mas_rows == {"配置文件来源": "用户", "启用快速配置": "开启"}
    m9a_rows = {row["key"]: row["value"] for row in sections["m9a"]["rows"]}
    assert m9a_rows["账号"] == "130****5678"
    assert m9a_rows["已启用任务"] == "常规作战、自动深眠"
    detail = {g["name"]: g for g in sections["task-details"]["groups"]}
    detail_rows = {row["key"]: row["value"] for row in detail["常规作战"]["rows"]}
    assert detail_rows["难度"] == "困难"


def test_native_preview_reads_all_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池预览：逐个反读 instances/*.json（折叠实例，名称取 InstanceName）。"""

    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "native" / "config"
    (config_dir / "instances").mkdir(parents=True)
    (config_dir / "config.json").write_text("{}", encoding="utf-8")
    (config_dir / "instances" / "default.json").write_text(
        json.dumps(
            {
                "InstanceName": "日常号",
                "Resource": "官服",
                "Connect.Address": "127.0.0.1:5555",
                "CurrentControllerName": "ADB",
                "TaskItems": [
                    {
                        "name": "常规作战",
                        "option": [
                            {"name": "难度", "index": 1},
                            {
                                "name": "目标账号(可选)",
                                "index": 0,
                                "data": {"账号": "13012345678"},
                            },
                        ],
                    },
                    {"name": "自动深眠", "option": []},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "instances" / "小号.json").write_text(
        json.dumps({"Resource": "B服", "TaskItems": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    first = archive_native_backup(config_dir)
    assert first is not None

    payload = build_native_preview(
        config_dir, first.name, _FakeTaskLoader({"常规作战": _OPTION_DEFINITIONS})
    )
    instances = {inst["name"]: inst for inst in payload["instances"]}
    assert set(instances) == {"日常号", "小号"}  # 名称取 InstanceName，缺失回退文件名
    default_rows = {row["key"]: row["value"] for row in instances["日常号"]["rows"]}
    assert default_rows["服务器资源"] == "官服"
    assert default_rows["已启用任务"] == "常规作战、自动深眠"
    assert default_rows["账号"] == "130****5678"  # 切换账号任务里的账号脱敏
    assert default_rows["连接地址"] == "127.0.0.1:5555"
    assert {row["key"]: row["value"] for row in instances["小号"]["rows"]}[
        "服务器资源"
    ] == "B服"
    assert instances["小号"]["details"] == []  # 空队列无任务详情
    detail = {g["name"]: g for g in instances["日常号"]["details"]}
    detail_rows = {row["key"]: row["value"] for row in detail["常规作战"]["rows"]}
    assert detail_rows["难度"] == "困难"  # 任务定义可用时翻译
    assert "目标账号(可选)" not in detail_rows  # 账号已单独成行，不重复


def test_restore_service_callbacks_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """service 级真实调用链：声明式 snapshot → preview（files 注入）→ restore 回填。"""

    from app.task.M9A.tools.restore_service import (
        RESTORE_POOLS,
        RESTORE_SCRIPT_NAME,
    )
    from app.utils.config_restore import RestoreContext, build_restore_service

    monkeypatch.chdir(tmp_path)
    script_id = "s-0003"
    uid = uuid.uuid4()
    user = _FakeUser(
        {
            "Info.Mode": "用户",
            "Info.IfQuickConfig": True,
            "Info.Resource": "官服",
            "Task.Queue": _QUEUE,
        }
    )
    script_config = SimpleNamespace(
        get=lambda g, k: str(tmp_path / "M9A") if (g, k) == ("Info", "Path") else "",
        UserData={uid: user},
    )
    ctx = RestoreContext(
        config=None,
        script_config=script_config,
        script_id=script_id,
        user_id=str(uid),
    )
    service = build_restore_service(ctx, RESTORE_SCRIPT_NAME, RESTORE_POOLS)

    # snapshot：归档当前字段（含展示快照）
    created = asyncio.run(service.ensure("mas"))
    assert created["created"] is True and created["time"]
    ts = created["time"]

    # preview：定制摘要 + 基座注入归档内文件清单（侧车唯一文件）
    payload = asyncio.run(service.preview("mas", ts))
    sections = {s["name"] for s in payload["sections"]}
    assert "m9a" in sections
    assert payload["files"] == [
        {
            "path": "_mas_overlay.json",
            "size": (get_mas_backup_dir(script_id, str(uid), ts) / "_mas_overlay.json")
            .stat()
            .st_size,
        }
    ]

    # 声明式 read_file（基座从 backup_root 派生）
    content = asyncio.run(service.read_backup_file("mas", ts, "_mas_overlay.json"))
    assert "Resource" in content["content"]

    # restore：回填 UserData，Mode/Display 排除；恢复前当前字段强制存底
    user._values["Info.Resource"] = "B服"
    asyncio.run(service.restore("mas", ts))
    assert len(user.updated) == 1
    grouped = user.updated[0]
    assert grouped["Info"]["Resource"] == "官服"
    assert grouped["Task"]["Queue"] == _QUEUE
    assert "Mode" not in grouped["Info"]
    assert len(list_mas_backups(script_id, str(uid))) == 2  # snapshot + 恢复前存底


def test_get_mas_backup_dir_guards_timestamp(tmp_path: Path) -> None:
    """get_mas_backup_dir 拒绝非法时间戳（路径穿越防护由公共原语保证）。"""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    script_id, user_id = "s-0004", "u-0004"
    archive_mas_backup(script_id, user_id, build_display_overlay({"Queue": _QUEUE}))
    monkeypatch.undo()

    assert get_mas_backup_dir(script_id, user_id, "..") is None
    assert get_mas_backup_dir(script_id, user_id, "20260101-000000") is None
    with pytest.raises(ValueError):
        restore_mas_backup(script_id, user_id, "..")
    with pytest.raises(ValueError):
        restore_native_backup(tmp_path / "cfg", "..")
