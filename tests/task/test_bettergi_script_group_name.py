"""BetterGI 配置组名：含路径分隔符的「路径」引用不得抛「配置组名非法」。

回归背景（2026-09-16 实机）：右栏为「路径」类型的自定义项取配置组详情时，会用 AutoPathing
路线名（形如 ``地方特产/挪德卡莱/便携轴承/01-便携轴承-…-9个``）去读配置组，底层
``resolve_script_group_name`` 因含 ``/`` 抛 ValueError，直接把错误弹给了用户。
读路径必须容错（读不到视为不存在），写路径仍走严格校验防路径穿越。

2026-09-19 补充：右栏「添加脚本」会把「路径」项升级成多项目配置组，而原名不能作文件名，
故这类引用的 per-user 副本落在 ``per_user_copy_name`` 的确定性别名上；别名只写 MAS 的
``data/{script}/{user}/ScriptGroup/``，BGI 的 ``User/ScriptGroup`` 零接触。
"""

import pytest

from app.task.BetterGI.tools import one_dragon

_PATH_NAME = "地方特产/挪德卡莱/便携轴承/01-便携轴承-叮铃哐啷蛋卷红坊-9个"
_SID = "354c7241-47c2-4604-8981-90a1e82bd5b6"
_UID = "79878431-68c7-4a1d-a196-c7fb3addb334"


def test_read_user_script_group_tolerates_path_like_name(tmp_path):
    assert one_dragon.read_user_script_group(tmp_path, "sid", "uid", _PATH_NAME) == {}


def test_read_script_group_tolerates_path_like_name(tmp_path):
    assert one_dragon.read_script_group(tmp_path, _PATH_NAME) == {}


def test_write_user_script_group_stores_path_like_name_under_deterministic_alias(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    out = one_dragon.write_user_script_group(
        tmp_path, _SID, _UID, _PATH_NAME, {"projects": [{"name": "附加脚本"}]}
    )

    assert out is not None
    assert out.name.startswith("MAS-路径-")
    assert out.parent.parts[-3:] == (_SID, _UID, "ScriptGroup")
    # 同一引用恒得同一别名：再次保存覆盖同一份副本，不产生第二份
    again = one_dragon.write_user_script_group(
        tmp_path, _SID, _UID, _PATH_NAME, {"projects": []}
    )
    assert again == out
    assert sorted(p.name for p in out.parent.glob("*.json")) == [out.name]
    # BGI 侧（User/ScriptGroup）从未被写入
    assert not (tmp_path / "User" / "ScriptGroup").exists()


def test_path_like_reference_reads_back_saved_copy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    one_dragon.write_user_script_group(
        tmp_path,
        _SID,
        _UID,
        _PATH_NAME,
        {"projects": [{"name": "附加脚本", "type": "Javascript"}]},
    )

    saved = one_dragon.read_user_script_group(tmp_path, _SID, _UID, _PATH_NAME)

    assert saved["projects"] == [{"name": "附加脚本", "type": "Javascript"}]


def test_path_like_reference_runtime_resolution_prefers_saved_copy(tmp_path, monkeypatch):
    # 运行时（逐项物化 / 执行层切段）经 resolve_custom_group 取用户编辑过的组；
    # 取不到才会退回「按路径文件合成单项目」，右栏加的脚本就白加了
    monkeypatch.chdir(tmp_path)
    one_dragon.write_user_script_group(
        tmp_path,
        _SID,
        _UID,
        _PATH_NAME,
        {"projects": [{"name": "附加脚本", "type": "Javascript"}]},
    )

    group = one_dragon.resolve_custom_group(tmp_path, _SID, _UID, _PATH_NAME, _PATH_NAME)

    assert group.get("projects") == [{"name": "附加脚本", "type": "Javascript"}]


def test_path_copy_alias_is_not_listed_as_config_group(tmp_path, monkeypatch):
    # 别名副本归属某条「路径」引用，不该作为新配置组出现在「配置组」候选里
    monkeypatch.chdir(tmp_path)
    one_dragon.write_user_script_group(tmp_path, _SID, _UID, _PATH_NAME, {"projects": []})

    assert one_dragon.list_user_script_group_names(_SID, _UID) == []


def test_write_user_script_group_returns_none_for_empty_name(tmp_path):
    assert (
        one_dragon.write_user_script_group(tmp_path, _SID, _UID, "  ", {"projects": []})
        is None
    )


def test_file_safe_predicate_matches_resolver(tmp_path):
    assert one_dragon.is_file_safe_script_group_name("普通配置组") is True
    assert one_dragon.is_file_safe_script_group_name(_PATH_NAME) is False
    assert one_dragon.is_file_safe_script_group_name("") is False


def test_resolve_script_group_name_still_rejects_separators():
    with pytest.raises(ValueError):
        one_dragon.resolve_script_group_name(_PATH_NAME)
