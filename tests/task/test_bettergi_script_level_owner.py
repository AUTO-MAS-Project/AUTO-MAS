"""BetterGI 脚本级共享配置：owner 解析与保留 id 的安全边界。"""

import uuid
from pathlib import Path

import pytest

from app.task.BetterGI.tools import one_dragon
from app.task.proxy_helpers import (
    CONFIG_BASE_INDEPENDENT,
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
)


def test_script_source_uses_script_level_owner() -> None:
    user_id = str(uuid.uuid4())
    assert (
        one_dragon.owner_user_id(user_id, CONFIG_BASE_SHARED)
        == one_dragon.SCRIPT_LEVEL_OWNER
    )


@pytest.mark.parametrize("base", [CONFIG_BASE_INDEPENDENT, CONFIG_BASE_NATIVE])
def test_other_sources_keep_the_user_owner(base: str) -> None:
    user_id = str(uuid.uuid4())
    assert one_dragon.owner_user_id(user_id, base) == user_id


def test_script_level_copy_is_shared_while_user_copy_is_not() -> None:
    """一条链路的本质：选「共享」的两个用户命中同一份副本，选「独立」的各归各。"""

    script_id = str(uuid.uuid4())
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())

    shared_a = one_dragon.per_user_script_group_path(
        script_id, one_dragon.owner_user_id(user_a, CONFIG_BASE_SHARED), "我的组"
    )
    shared_b = one_dragon.per_user_script_group_path(
        script_id, one_dragon.owner_user_id(user_b, CONFIG_BASE_SHARED), "我的组"
    )
    own_a = one_dragon.per_user_script_group_path(
        script_id, one_dragon.owner_user_id(user_a, CONFIG_BASE_INDEPENDENT), "我的组"
    )

    assert shared_a == shared_b
    assert own_a != shared_a
    assert shared_a.relative_to(Path.cwd()).parts == (
        "data",
        script_id,
        one_dragon.SCRIPT_LEVEL_OWNER,
        "ScriptGroup",
        "我的组.json",
    )


def test_script_level_owner_is_accepted() -> None:
    assert one_dragon._validate_user_id(one_dragon.SCRIPT_LEVEL_OWNER) == "Default"
    # 前后空白先 strip 再比对，避免 " Default " 绕过或误判
    assert one_dragon._validate_user_id(" Default ") == "Default"


@pytest.mark.parametrize(
    "bad",
    ["", "Defaultx", "default", "../Default", "Default/../x", "a\\b", "Default/"],
)
def test_illegal_user_ids_are_still_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        one_dragon._validate_user_id(bad)
