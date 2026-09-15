"""BetterGI 配置组名：含路径分隔符的「路径」引用不得抛「配置组名非法」。

回归背景（2026-09-16 实机）：右栏为「路径」类型的自定义项取配置组详情时，会用 AutoPathing
路线名（形如 ``地方特产/挪德卡莱/便携轴承/01-便携轴承-…-9个``）去读配置组，底层
``resolve_script_group_name`` 因含 ``/`` 抛 ValueError，直接把错误弹给了用户。
读路径必须容错（读不到视为不存在），而写路径必须继续严格拒绝（防路径穿越）。
"""

import pytest

from app.task.BetterGI.tools import one_dragon

_PATH_NAME = "地方特产/挪德卡莱/便携轴承/01-便携轴承-叮铃哐啷蛋卷红坊-9个"


def test_read_user_script_group_tolerates_path_like_name(tmp_path):
    assert one_dragon.read_user_script_group(tmp_path, "sid", "uid", _PATH_NAME) == {}


def test_read_script_group_tolerates_path_like_name(tmp_path):
    assert one_dragon.read_script_group(tmp_path, _PATH_NAME) == {}


def test_write_user_script_group_skips_path_like_name(tmp_path):
    # 路径类引用没有 per-user 副本，保存应静默跳过（返回 None），不得抛「配置组名非法」
    assert (
        one_dragon.write_user_script_group(
            tmp_path, "sid", "uid", _PATH_NAME, {"projects": []}
        )
        is None
    )


def test_file_safe_predicate_matches_resolver(tmp_path):
    assert one_dragon.is_file_safe_script_group_name("普通配置组") is True
    assert one_dragon.is_file_safe_script_group_name(_PATH_NAME) is False
    assert one_dragon.is_file_safe_script_group_name("") is False


def test_resolve_script_group_name_still_rejects_separators():
    with pytest.raises(ValueError):
        one_dragon.resolve_script_group_name(_PATH_NAME)
