#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

import importlib.util
from pathlib import Path

from app.utils.io import read_file, write_file

# 直接按文件路径加载 one_dragon 模块：``app.task`` 的 ``__init__`` 会急切 import 全部
# 管理器触发 app.core 循环依赖，pytest 收集时无法经包导入，故绕开走独立加载。
_OD_SPEC = importlib.util.spec_from_file_location(
    "one_dragon",
    Path(__file__).resolve().parents[2] / "app" / "task" / "BetterGI" / "tools" / "one_dragon.py",
)
one_dragon = importlib.util.module_from_spec(_OD_SPEC)
assert _OD_SPEC.loader is not None
_OD_SPEC.loader.exec_module(one_dragon)


def _od(root, name="默认配置"):
    return read_file(one_dragon.one_dragon_path(root, name))


def _write(root, party="", tmp_path=None, monkeypatch=None):
    """调用 write_user_one_dragon，per-user 缓存写入 root 内避免污染仓库 data/。"""
    if monkeypatch is not None:
        monkeypatch.setattr(
            one_dragon,
            "per_user_one_dragon_path",
            lambda sid, uid, name: tmp_path
            / "cache"
            / sid
            / uid
            / f"{name}.json",
        )
    one_dragon.write_user_one_dragon(
        root, "script", "user", "默认配置", [], party_name=party
    )


def _seed_cache(root, tmp_path, **fields):
    """直接往 per-user 缓存写入种子配置（write_user_one_dragon 实际读取的来源）。"""
    one_dragon.write_one_dragon(root, "默认配置", fields)  # Name 同步
    cfg = _od(root)
    p = tmp_path / "cache" / "script" / "user" / "默认配置.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    write_file(p, cfg)


def test_global_team_writes_ley_line_and_stygian(tmp_path) -> None:
    """通用战斗队伍落到 config.json 地脉花/幽境危战 camelCase 段，保留同段其余字段。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(
        root / "User" / "config.json",
        {
            "autoLeyLineOutcropConfig": {"count": 3},
            "notRelated": {"x": 1},
        },
    )
    one_dragon.apply_global_battle_team(root, "锄地队")

    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoLeyLineOutcropConfig"]["Team"] == "锄地队"
    assert cfg["autoLeyLineOutcropConfig"]["count"] == 3  # 忽略其它字段
    assert cfg["autoStygianOnslaughtConfig"]["fightTeamName"] == "锄地队"
    assert cfg["notRelated"] == {"x": 1}


def test_global_team_creates_missing_sections(tmp_path) -> None:
    """config.json 无这两段时按需创建（对应初次使用/未配置独立任务）。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(root / "User" / "config.json", {"scriptConfig": {}})

    one_dragon.apply_global_battle_team(root, "跑图队")

    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoLeyLineOutcropConfig"]["Team"] == "跑图队"
    assert cfg["autoStygianOnslaughtConfig"]["fightTeamName"] == "跑图队"
    assert "scriptConfig" in cfg


def test_global_team_empty_is_noop(tmp_path) -> None:
    """通用战斗队伍留空时不写入 config.json（不覆盖用户手工配置）。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(
        root / "User" / "config.json",
        {"autoLeyLineOutcropConfig": {"Team": "手动队伍"}},
    )
    one_dragon.apply_global_battle_team(root, "  ")

    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoLeyLineOutcropConfig"]["Team"] == "手动队伍"


def test_write_user_one_dragon_sets_auto_boss_team(tmp_path, monkeypatch) -> None:
    """通用战斗队伍同时写进一条龙的 AutoBossTeamName（首领讨伐取队字段）。"""
    root = tmp_path
    _seed_cache(root, tmp_path)
    _write(root, party="锄地队", tmp_path=tmp_path, monkeypatch=monkeypatch)

    cfg = _od(root)
    assert cfg["PartyName"] == "锄地队"
    assert cfg["AutoBossTeamName"] == "锄地队"


def test_write_user_one_dragon_empty_keeps_auto_boss_team(tmp_path, monkeypatch) -> None:
    """通用战斗队伍留空时不动 AutoBossTeamName（不覆盖已有值）。"""
    root = tmp_path
    _seed_cache(root, tmp_path, AutoBossTeamName="团队X")
    _write(root, party="", tmp_path=tmp_path, monkeypatch=monkeypatch)

    cfg = _od(root)
    assert cfg["AutoBossTeamName"] == "团队X"


def test_write_user_one_dragon_keeps_other_fields(tmp_path, monkeypatch) -> None:
    """写入通用队伍不破坏其它设置字段。"""
    root = tmp_path
    _seed_cache(root, tmp_path, AutoBossStrategyName="自定义策略")
    _write(root, party="锄地队", tmp_path=tmp_path, monkeypatch=monkeypatch)

    cfg = _od(root)
    assert cfg["AutoBossStrategyName"] == "自定义策略"
    assert cfg["AutoBossTeamName"] == "锄地队"
    assert cfg["PartyName"] == "锄地队"


def test_restore_removes_injected_team(tmp_path) -> None:
    """运行结束后把 inject 的地脉花/幽境危战队伍字段还原（缺失则删除、空段一并删）。

    AutoProxy 在写入前先快照、结束再还原，故此处先 snapshot 后 apply。
    """
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(root / "User" / "config.json", {})

    snap = one_dragon.snapshot_global_battle_config(root)
    one_dragon.apply_global_battle_team(root, "锄地队")
    one_dragon.restore_global_battle_config(root, snap)

    cfg = read_file(root / "User" / "config.json")
    assert "autoLeyLineOutcropConfig" not in cfg
    assert "autoStygianOnslaughtConfig" not in cfg


def test_restore_preserves_original_team(tmp_path) -> None:
    """原本存在的手动队伍值在还原后回写原值。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(
        root / "User" / "config.json",
        {
            "autoLeyLineOutcropConfig": {"Team": "手动队伍", "count": 2},
        },
    )
    snap = one_dragon.snapshot_global_battle_config(root)

    one_dragon.apply_global_battle_team(root, "锄地队")
    one_dragon.restore_global_battle_config(root, snap)

    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoLeyLineOutcropConfig"]["Team"] == "手动队伍"
    assert cfg["autoLeyLineOutcropConfig"]["count"] == 2


def test_restore_idempotent(tmp_path) -> None:
    """快照后无变化时重复还原不报错。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(root / "User" / "config.json", {})
    snap = one_dragon.snapshot_global_battle_config(root)

    one_dragon.restore_global_battle_config(root, snap)
    assert read_file(root / "User" / "config.json") == {}


def test_global_strategy_writes_all_tasks(tmp_path) -> None:
    """通用战斗策略写进 config.json：秘境/地脉花(嵌套)/幽境危战，保留同段其余字段。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(
        root / "User" / "config.json",
        {
            "autoFightConfig": {"teamNames": "刻晴"},
            "autoLeyLineOutcropConfig": {"count": 3},
            "notRelated": {"x": 1},
        },
    )
    one_dragon.apply_global_battle_strategy(root, "夜兰蒸发")

    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoFightConfig"]["strategyName"] == "夜兰蒸发"
    assert cfg["autoFightConfig"]["teamNames"] == "刻晴"  # 保留同段其余字段
    assert cfg["autoLeyLineOutcropConfig"]["fightConfig"]["strategyName"] == "夜兰蒸发"
    assert cfg["autoLeyLineOutcropConfig"]["count"] == 3
    assert cfg["autoStygianOnslaughtConfig"]["strategyName"] == "夜兰蒸发"
    assert cfg["notRelated"] == {"x": 1}


def test_global_strategy_empty_is_noop(tmp_path) -> None:
    """通用战斗策略留空时不写 config.json（不覆盖用户手工配置）。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(
        root / "User" / "config.json",
        {"autoFightConfig": {"strategyName": "手动策略"}},
    )
    one_dragon.apply_global_battle_strategy(root, "  ")
    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoFightConfig"]["strategyName"] == "手动策略"


def test_restore_removes_injected_team_and_strategy(tmp_path) -> None:
    """运行结束后把队伍与策略叶子一并还原，含嵌套 fightConfig 空段清理。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(root / "User" / "config.json", {})

    snap = one_dragon.snapshot_global_battle_config(root)
    one_dragon.apply_global_battle_team(root, "锄地队")
    one_dragon.apply_global_battle_strategy(root, "夜兰蒸发")
    one_dragon.restore_global_battle_config(root, snap)

    cfg = read_file(root / "User" / "config.json")
    assert cfg == {}


def test_restore_preserves_original_strategy(tmp_path) -> None:
    """原本存在的手动策略值还原后回写原值（含地脉花嵌套段）。"""
    root = tmp_path
    (root / "User").mkdir(parents=True)
    write_file(
        root / "User" / "config.json",
        {
            "autoFightConfig": {"strategyName": "手动通用"},
            "autoLeyLineOutcropConfig": {"fightConfig": {"strategyName": "手动地脉"}},
            "autoLeyLineOutcropConfig2": {},
        },
    )
    snap = one_dragon.snapshot_global_battle_config(root)

    one_dragon.apply_global_battle_strategy(root, "夜兰蒸发")
    one_dragon.restore_global_battle_config(root, snap)

    cfg = read_file(root / "User" / "config.json")
    assert cfg["autoFightConfig"]["strategyName"] == "手动通用"
    assert cfg["autoLeyLineOutcropConfig"]["fightConfig"]["strategyName"] == "手动地脉"