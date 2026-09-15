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

"""OK-WW 配置备份恢复原语的最小回归测试。

用临时目录模拟 MAS 配置目录（owner：Default/用户）与 ok-ww 原生 working
配置目录，验证两池归档的指纹去重、恢复闭环（含恢复前强制存底）、运行前
归档的缺目录容错、三态 owner 解析与备份预览摘要的纯逻辑。
"""

import asyncio
import json
import uuid
from pathlib import Path

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.Okww.tools import restore_service as rs
from app.task.Okww.tools.backup_archive import (
    archive_mas_backup,
    archive_mas_runtime_backup,
    archive_native_backup,
    build_backup_file_summary,
    get_mas_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    read_overlay_sidecar,
    restore_mas_backup,
    restore_native_backup,
)
from app.utils.config_restore import RestoreContext, build_restore_service


class _FakeUserConfig:
    """最小用户配置桩：支撑 ``get("Info", "Mode"/"Id")`` 与 ``get("Task", key)``。"""

    def __init__(self, mode: str, task: dict | None = None, info: dict | None = None):
        self._mode = mode
        self._task = task or {}
        self._info = info or {}

    def get(self, section: str, key: str):
        if section == "Info":
            return {**{"Mode": self._mode}, **self._info}.get(key)
        if section == "Task":
            return self._task.get(key)
        return None


class _FakeUserData:
    def __init__(self, modes: dict[str, _FakeUserConfig]):
        self._modes = modes

    def __contains__(self, uid: object) -> bool:
        return str(uid) in self._modes

    def __getitem__(self, uid: object) -> _FakeUserConfig:
        return self._modes[str(uid)]


class _FakeScriptConfig:
    """最小脚本配置桩：UserData + ``get("Info", "RootPath")``。"""

    def __init__(self, modes: dict[str, _FakeUserConfig], root: str = ""):
        self.UserData = _FakeUserData(modes)
        self._root = root

    def get(self, section: str, key: str):
        return {"Info": {"RootPath": self._root}}.get(section, {}).get(key)


def _ctx(script_config: _FakeScriptConfig, user_id: str) -> RestoreContext:
    """构造显式恢复上下文（config 桩为 None：池逻辑不依赖核心门面）。"""

    return RestoreContext(
        config=None, script_config=script_config, script_id="s-1", user_id=user_id
    )


def test_mas_backup_dedup_and_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 池：无备份即建、内容一致跳过、内容/覆盖层变化再建、恢复闭环。"""

    monkeypatch.chdir(tmp_path)
    script_id, owner = "s-0001", "u-0001"
    mas_dir = tmp_path / "data" / script_id / owner / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyTask.json").write_text(
        json.dumps({"Which to Farm": "Tacet Suppression"}),
        encoding="utf-8",
    )
    overlay = {"WhichToFarm": "Tacet Suppression", "TaskIndex": 1}

    # 首次归档（含侧车）→ 内容一致跳过（指纹去重）
    first = archive_mas_backup(script_id, owner, mas_dir, overlay=overlay)
    assert first is not None and (first / "DailyTask.json").is_file()
    assert (first / "_mas_overlay.json").is_file()
    assert archive_mas_backup(script_id, owner, mas_dir, overlay=overlay) is None
    assert len(list_mas_backups(script_id, owner)) == 1

    # 只改覆盖层字段（文件未动）→ 指纹变化，新建归档
    overlay2 = {**overlay, "WhichToFarm": "Forgery Challenge"}
    second = archive_mas_backup(script_id, owner, mas_dir, overlay=overlay2)
    assert second is not None
    assert len(list_mas_backups(script_id, owner)) == 2

    # 只改文件（覆盖层同第二份）→ 同样新建归档
    (mas_dir / "a.json").write_text("{}", encoding="utf-8")
    assert archive_mas_backup(script_id, owner, mas_dir, overlay=overlay2) is not None
    assert len(list_mas_backups(script_id, owner)) == 3

    # 恢复到第一份：文件与覆盖层都回到该时点，侧车不留在 ConfigFile
    restored = restore_mas_backup(
        script_id, owner, first.name, mas_dir, overlay=overlay2
    )
    assert restored == overlay
    assert not (mas_dir / "a.json").exists()
    assert not (mas_dir / "_mas_overlay.json").exists()
    # 恢复前存底与最新份内容一致 → 跳过（不产生冗余条目）
    assert len(list_mas_backups(script_id, owner)) == 3

    # owner 分池：用户目录与脚本共享 Default 互不干扰
    assert list_mas_backups(script_id, "Default") == []

    # mas 目录为空/缺失时无可归档内容，跳过不报错
    assert archive_mas_backup(script_id, owner, tmp_path / "elsewhere") is None


def test_mas_backup_overlay_only_when_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用户级目录未物化（从未运行）时侧车仍入档：切来源/改页面字段可备份。

    回归：collect 曾在目录缺失/为空时连侧车一起丢，导致从未运行的用户
    切配置来源、改页面配置后退出，mas 池永远为空。
    """

    monkeypatch.chdir(tmp_path)
    script_id, owner = "s-0003", "u-0003"
    missing = tmp_path / "data" / script_id / owner / "ConfigFile"  # 从未创建
    overlay = {"Mode": "用户", "TaskIndex": 1}

    first = archive_mas_backup(script_id, owner, missing, overlay=overlay)
    assert first is not None
    assert (first / "_mas_overlay.json").is_file()
    # 仅侧车入档：归档里没有其他文件
    assert [p.name for p in first.iterdir() if p.is_file()] == ["_mas_overlay.json"]

    # 目录与侧车皆空 → 无可归档内容
    assert archive_mas_backup(script_id, owner, missing) is None

    # 恢复仅侧车备份：覆盖层回填，侧车不留在 ConfigFile；恢复前存底与
    # 该份一致 → 跳过，不产生冗余条目
    restored = restore_mas_backup(script_id, owner, first.name, missing, overlay=overlay)
    assert restored == overlay
    assert not (missing / "_mas_overlay.json").exists()
    assert len(list_mas_backups(script_id, owner)) == 1


def test_mas_restore_legacy_backup_without_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧版备份（无侧车）：文件正常回滚，覆盖层返回 None（不回填表单）。"""

    monkeypatch.chdir(tmp_path)
    script_id, owner = "s-0002", "u-0002"
    mas_dir = tmp_path / "data" / script_id / owner / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyTask.json").write_text("{}", encoding="utf-8")

    # 手工构造无侧车的旧版归档（直接用文件级原语）
    from app.utils.config_archive import archive_files, dir_files

    legacy = archive_files(
        dir_files(mas_dir),
        tmp_path / "data" / script_id / "OkwwBackups" / "mas" / owner,
    )
    assert legacy is not None and not (legacy / "_mas_overlay.json").exists()

    (mas_dir / "DailyTask.json").write_text('{"bad": true}', encoding="utf-8")
    restored = restore_mas_backup(script_id, owner, legacy.name, mas_dir)
    assert restored is None
    assert json.loads((mas_dir / "DailyTask.json").read_text("utf-8")) == {}


def test_native_backup_folder_restore_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """native 池：整目录备份 → 修改 → 恢复闭环；缺失/空目录跳过。"""

    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "native" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "Basic Options.json").write_text("{}", encoding="utf-8")
    first = archive_native_backup(config_dir)
    assert first is not None
    (config_dir / "Basic Options.json").write_text('{"bad": true}', encoding="utf-8")
    restore_native_backup(config_dir, first.name)
    assert json.loads((config_dir / "Basic Options.json").read_text("utf-8")) == {}
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


def test_mas_pool_isolates_script_mode_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """脚本模式多用户共享 Default 目录，但池按用户隔离，侧车互不混淆。"""

    monkeypatch.chdir(tmp_path)
    script_id, user_a, user_b = "s-0004", "u-aaa", "u-bbb"
    # 脚本模式：下发源是共享 Default 目录（两个用户指向同一份）
    default_dir = tmp_path / "data" / script_id / "Default" / "ConfigFile"
    default_dir.mkdir(parents=True)
    (default_dir / "DailyTask.json").write_text("{}", encoding="utf-8")

    overlay_a = {"WhichToFarm": "Tacet Suppression", "TaskIndex": 1}
    overlay_b = {"WhichToFarm": "Forgery Challenge", "TaskIndex": 7}

    first = archive_mas_backup(script_id, user_a, default_dir, overlay=overlay_a)
    assert first is not None and (first / "_mas_overlay.json").is_file()
    second = archive_mas_backup(script_id, user_b, default_dir, overlay=overlay_b)
    assert second is not None

    # 两用户池完全隔离：各只看到自己的备份
    assert list_mas_backups(script_id, user_a) == [first.name]
    assert list_mas_backups(script_id, user_b) == [second.name]

    # A 恢复自己的备份：文件回滚到 Default，侧车是 A 的（不是 B 的）
    restored = restore_mas_backup(
        script_id, user_a, first.name, default_dir, overlay=overlay_a
    )
    assert restored == overlay_a
    assert not (default_dir / "_mas_overlay.json").exists()

    # B 恢复自己的备份同理；双方池仍互不含对方的备份
    restored_b = restore_mas_backup(
        script_id, user_b, second.name, default_dir, overlay=overlay_b
    )
    assert restored_b == overlay_b
    times_a = list_mas_backups(script_id, user_a)
    # A 恢复前存底与最新份（first）内容一致 → 跳过（不产生冗余条目）
    assert len(times_a) == 1
    # 隔离的实质是侧车内容各归其主（同秒时间戳可能跨池同名，不能拿名字判断）
    from app.task.Okww.tools.backup_archive import read_overlay_sidecar

    sidecar_a = read_overlay_sidecar(get_mas_backup_dir(script_id, user_a, first.name))
    assert sidecar_a == overlay_a
    sidecar_b = read_overlay_sidecar(get_mas_backup_dir(script_id, user_b, second.name))
    assert sidecar_b == overlay_b


def test_mas_owner_respects_mode() -> None:
    """三态 owner 解析：用户=独立目录、脚本=Default、直控/未知=None。"""

    uid = str(uuid.uuid4())

    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("用户")}), uid)
    assert rs._mas_owner(ctx) == uid

    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("脚本")}), uid)
    assert rs._mas_owner(ctx) == "Default"

    # 旧值 简洁/详细 迁移后等价于 脚本/用户
    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("简洁")}), uid)
    assert rs._mas_owner(ctx) == "Default"
    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("详细")}), uid)
    assert rs._mas_owner(ctx) == uid

    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("直控")}), uid)
    assert rs._mas_owner(ctx) is None

    # 用户不存在 / user_id 非法（脚本级入口传 Default）：无法判态返回 None
    assert rs._mas_owner(_ctx(_FakeScriptConfig({}), str(uuid.uuid4()))) is None
    assert rs._mas_owner(_ctx(_FakeScriptConfig({}), "Default")) is None


def test_direct_control_user_mas_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直控用户无 MAS 配置：列表为空，恢复拒绝而非静默落错目录（service 级）。"""

    monkeypatch.chdir(tmp_path)
    uid = str(uuid.uuid4())
    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("直控")}), uid)
    service = build_restore_service(ctx, rs.RESTORE_POOLS)

    assert asyncio.run(service.list("mas")) == []
    with pytest.raises(ValueError):
        asyncio.run(service.restore("mas", "20260913-000000"))
    snapshot = asyncio.run(service.ensure("mas"))
    assert snapshot == {"created": False, "time": ""}


def test_mas_preview_shows_overlay_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览展示覆盖层侧车（备份时点的表单值），与页面认知同源。"""

    monkeypatch.chdir(tmp_path)
    uid = str(uuid.uuid4())
    task = {
        "TaskIndex": 1,
        "WhichToFarm": "Forgery Challenge",
        "MaterialSelection": "Shell Credit",
        "AdditionalTasks": ["Check Weekly Garden"],
    }
    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("用户", task)}), uid)
    service = build_restore_service(ctx, rs.RESTORE_POOLS)

    # ConfigFile 存在（归档前置）→ service.ensure 归档（侧车读取自 ctx 用户配置）
    mas_dir = tmp_path / "data" / "s-1" / uid / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyTask.json").write_text("{}", encoding="utf-8")
    snap = asyncio.run(service.ensure("mas"))
    assert snap["created"] is True
    payload = asyncio.run(service.preview("mas", snap["time"]))
    assert "fileCards" in payload  # 定制预览自带侧车摘要载荷
    cards = payload["fileCards"]
    assert len(cards) == 1 and cards[0]["label"] == "任务配置"
    rows = {row["key"]: row["value"] for row in cards[0]["summary"]}
    assert rows == {
        "配置文件来源": "用户",
        "启动任务（-t N）": "1",
        "消耗体力刷取": "凝素领域",
        "模拟领域材料": "贝币",
        "每日任务后运行的附加任务": "检查每周乐园",
    }

    # 声明式 read_file（基座从 backup_root 派生）
    content = asyncio.run(
        service.read_backup_file("mas", snap["time"], "DailyTask.json")
    )
    assert content["path"] == "DailyTask.json"

    # 无侧车（旧版备份）：预览为空，不误导
    from app.task.Okww.tools.restore_service import _overlay_preview_payload

    empty_backup = tmp_path / "legacy"
    empty_backup.mkdir()
    assert _overlay_preview_payload(empty_backup, snap["time"]) == {"fileCards": []}


def test_mas_preview_file_cards_and_masked_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mas 预览 = 侧车卡 + ConfigFile 文件卡；侧车含账号 Id 且预览脱敏。"""

    monkeypatch.chdir(tmp_path)
    uid = str(uuid.uuid4())
    config = _FakeUserConfig(
        "用户",
        {"WhichToFarm": "Tacet Suppression", "TaskIndex": 1},
        {"Id": "13800138000"},
    )
    ctx = _ctx(_FakeScriptConfig({uid: config}), uid)
    service = build_restore_service(ctx, rs.RESTORE_POOLS)

    # ConfigFile 含 MAS 管理的 DailyTask.json 字段 → 文件卡应进预览
    # （预览范围 = 恢复范围，两池同等存在的文件共用渲染）
    mas_dir = tmp_path / "data" / "s-1" / uid / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyTask.json").write_text(
        json.dumps({"Which to Farm": "Tacet Suppression"}), encoding="utf-8"
    )
    snap = asyncio.run(service.ensure("mas"))
    assert snap["created"] is True

    # 侧车收录账号 Id（完整原值，恢复回填需要）
    from app.task.Okww.tools.backup_archive import (
        get_mas_backup_dir,
        read_overlay_sidecar,
    )

    sidecar = read_overlay_sidecar(get_mas_backup_dir("s-1", uid, snap["time"]))
    assert sidecar["Id"] == "13800138000"

    payload = asyncio.run(service.preview("mas", snap["time"]))
    cards = payload["fileCards"]
    by_name = {card["name"]: card for card in cards}
    assert "overlay" in by_name and "DailyTask.json" in by_name

    # 预览账号行脱敏（11 位手机号保留前 3 后 4），明文不出现在载荷里
    rows = {row["key"]: row["value"] for row in by_name["overlay"]["summary"]}
    assert rows["账号"] == "138****8000"
    assert "13800138000" not in json.dumps(payload, ensure_ascii=False)


def test_mas_overlay_keeps_mode_preview_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """侧车收录 Info.Mode（配置文件来源），预览展示但恢复回填排除（对齐同类）。"""

    monkeypatch.chdir(tmp_path)
    uid = str(uuid.uuid4())
    config = _FakeUserConfig("用户", {"TaskIndex": 1})
    ctx = _ctx(_FakeScriptConfig({uid: config}), uid)
    service = build_restore_service(ctx, rs.RESTORE_POOLS)

    mas_dir = tmp_path / "data" / "s-1" / uid / "ConfigFile"
    mas_dir.mkdir(parents=True)
    (mas_dir / "DailyTask.json").write_text("{}", encoding="utf-8")
    snap = asyncio.run(service.ensure("mas"))
    assert snap["created"] is True

    # 侧车含 Mode 完整原值
    sidecar = read_overlay_sidecar(get_mas_backup_dir("s-1", uid, snap["time"]))
    assert sidecar["Mode"] == "用户"

    # 预览含「配置文件来源」行（mask 前的原文不出现，Mode 无敏感值故原样）
    payload = asyncio.run(service.preview("mas", snap["time"]))
    cards = payload["fileCards"]
    overlay_card = next(c for c in cards if c["name"] == "overlay")
    rows = {row["key"]: row["value"] for row in overlay_card["summary"]}
    assert rows["配置文件来源"] == "用户"

    # 恢复回填分组排除 Mode（回填旧来源会静默翻转脚本态/用户态/直控）；
    # Mode 是 Info 组唯一键，被剔除后 Info 组不生成
    grouped = group_overlay(dict(sidecar))
    assert "Info" not in grouped
    assert "Mode" not in grouped


def test_preview_payload_keeps_whitelist(tmp_path: Path) -> None:
    """预览只保留 MAS 任务配置文件，载荷挂 files 键；字段/取值翻译正确。"""

    uid = str(uuid.uuid4())
    ctx = _ctx(_FakeScriptConfig({uid: _FakeUserConfig("用户")}), uid)
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "DailyTask.json").write_text(
        json.dumps(
            {
                "Which to Farm": "Tacet Suppression",
                "Which Tacet Suppression to Farm": 3,
                "Additional Tasks to Run After Daily Task": [
                    "Check Weekly Garden",
                    "Auto Farm all Nightmare Nest",
                ],
                "Unknown GUI Field": "raw-value",
                "_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    # ok-ww GUI 自有文件（MAS 不管理）不进预览
    (backup / "Basic Options.json").write_text(
        json.dumps({"Exit App when Game Exits": True}), encoding="utf-8"
    )
    (backup / "Other.json").write_text(json.dumps({"k": "v"}), encoding="utf-8")

    payload = rs._preview_payload(ctx, "20260913-000000", backup)
    assert set(payload) == {"fileCards"}
    by_name = {f["name"]: f for f in payload["fileCards"]}
    assert set(by_name) == {"DailyTask.json"}

    daily = by_name["DailyTask.json"]
    assert daily["label"] == "日常任务"
    assert {row["key"]: row["value"] for row in daily["summary"]} == {
        "消耗体力刷取": "无音区",
        "F2 列表中的无音区序号": "3",
        "每日任务后运行的附加任务": "检查每周乐园、自动刷所有梦魇巢穴",
    }

    # 备份不存在抛 ValueError
    with pytest.raises(ValueError):
        rs._preview_payload(ctx, "missing", None)


def test_build_backup_file_summary_edges(tmp_path: Path) -> None:
    """摘要纯逻辑：未知取值显示原文、空附加任务显示「无」、坏 JSON 跳过。"""

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "DailyTask.json").write_text(
        json.dumps(
            {
                "Which to Farm": "SomeNewMode",
                "Additional Tasks to Run After Daily Task": [],
            }
        ),
        encoding="utf-8",
    )
    (backup / "broken.json").write_text("{oops", encoding="utf-8")
    (backup / "readme.txt").write_text("skip me", encoding="utf-8")

    files = build_backup_file_summary(backup)
    assert len(files) == 1
    rows = {row["key"]: row["value"] for row in files[0]["summary"]}
    assert rows == {
        "消耗体力刷取": "SomeNewMode",
        "每日任务后运行的附加任务": "无",
    }
