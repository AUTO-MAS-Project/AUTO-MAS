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

"""配置恢复基座的最小回归测试：池声明的上下文绑定与按 key 分发。

专项只声明池表（普通函数，显式收 RestoreContext），基座
``build_restore_service`` 是唯一的闭包绑定处——本文件验证绑定语义
（上下文透传、参数转发、kind 校验）与 Target 缺省能力的行为。
"""

import asyncio
from pathlib import Path

import pytest

from app.utils.config_restore import (
    ConfigRestorePool,
    RestoreContext,
    build_restore_service,
)


async def _list(ctx) -> list[str]:
    return ["t2", "t1"]


async def _preview(ctx, ts: str) -> dict:
    return {"time": ts, "marker": ctx.script_id}


async def _restore(ctx, ts: str) -> object:
    return {"restored": ts, "user": ctx.user_id}


async def _snapshot(ctx) -> dict:
    return {"created": True, "time": "t2"}


POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",
        list_backups=_list,
        preview=_preview,
        restore=_restore,
        snapshot=_snapshot,
    ),
    ConfigRestorePool(key="native", kind="script", list_backups=_list),
]


def _ctx() -> RestoreContext:
    return RestoreContext(
        config=None,
        script_config={"marker": "s1"},
        script_id="s1",
        user_id="u1",
    )


def test_build_validates_table() -> None:
    """空池表与非法 kind 都在构建期拒绝。"""

    with pytest.raises(ValueError):
        build_restore_service(_ctx(), "测试", [])
    bad = [ConfigRestorePool(key="x", kind="other", list_backups=_list)]
    with pytest.raises(ValueError):
        build_restore_service(_ctx(), "测试", bad)


def test_binding_and_dispatch() -> None:
    """绑定语义：ctx 透传、位置参数转发、按 key 分发、顺序即池表顺序。"""

    service = build_restore_service(_ctx(), "测试", POOLS)
    assert service.target_keys == ["mas", "native"]
    assert asyncio.run(service.list("mas")) == ["t2", "t1"]
    assert asyncio.run(service.preview("mas", "t1")) == {
        "time": "t1",
        "marker": "s1",
    }
    assert asyncio.run(service.restore("mas", "t1")) == {
        "restored": "t1",
        "user": "u1",
    }
    assert asyncio.run(service.ensure("mas")) == {"created": True, "time": "t2"}


def test_dispatch_rejects_unknown_and_missing() -> None:
    """未知 target 与未声明的能力统一抛 ValueError（HTTP 层转 400）。"""

    service = build_restore_service(_ctx(), "测试", POOLS)
    with pytest.raises(ValueError):
        service.get_target("nope")
    with pytest.raises(ValueError):
        asyncio.run(service.preview("native", "t1"))
    with pytest.raises(ValueError):
        asyncio.run(service.restore("native", "t1"))
    with pytest.raises(ValueError):
        asyncio.run(service.ensure("native"))


async def _decl_files(ctx) -> dict[str, str] | None:
    if ctx.script_id == "no-content":
        return None
    return {"_mas_overlay.json": '{"Mode": "用户"}'}


async def _decl_root(ctx) -> Path | None:
    if ctx.script_id == "no-root":
        return None
    return Path.cwd() / "data" / ctx.script_id / "test-decl"


DECL_POOL = ConfigRestorePool(
    key="decl",
    kind="user",
    files=_decl_files,
    backup_root=_decl_root,
    restore=_restore,
)


def test_declarative_derivation(tmp_path, monkeypatch) -> None:
    """声明式派生：files+backup_root → list/snapshot/read_file/files 兜底注入。"""

    monkeypatch.chdir(tmp_path)
    ctx = _ctx()
    service = build_restore_service(ctx, "测试", [DECL_POOL])

    # snapshot 落盘 → list 出现 → preview 注入标准 files → read_file 可读
    created = asyncio.run(service.ensure("decl"))
    assert created["created"] is True and created["time"]
    assert asyncio.run(service.list("decl")) == [created["time"]]
    payload = asyncio.run(service.preview("decl", created["time"]))
    assert payload["files"] == [
        {
            "path": "_mas_overlay.json",
            "size": len('{"Mode": "用户"}'.encode("utf-8")),
        }
    ]
    content = asyncio.run(
        service.read_backup_file("decl", created["time"], "_mas_overlay.json")
    )
    assert '"Mode"' in content["content"]

    # 无可归档内容：snapshot 报无变化（不产生条目）
    no_content = build_restore_service(
        RestoreContext(ctx.config, ctx.script_config, "no-content", ctx.user_id),
        "测试",
        [DECL_POOL],
    )
    assert asyncio.run(no_content.ensure("decl")) == {"created": False, "time": ""}


def test_declarative_none_root_is_silent(tmp_path, monkeypatch) -> None:
    """backup_root 返回 None（如脚本路径未配置）：list 空 / snapshot 无变化 /
    preview 不注入不炸 / read_file 报无可读——而不是 TypeError。"""

    monkeypatch.chdir(tmp_path)
    no_root = build_restore_service(
        RestoreContext(_ctx().config, _ctx().script_config, "no-root", "u1"),
        "测试",
        [DECL_POOL],
    )
    assert asyncio.run(no_root.list("decl")) == []
    assert asyncio.run(no_root.ensure("decl")) == {"created": False, "time": ""}
    assert asyncio.run(no_root.preview("decl", "whatever")) == {}
    with pytest.raises(ValueError):
        asyncio.run(no_root.read_backup_file("decl", "whatever", "x.json"))
    # restore 是显式回调（专项语义），不依赖声明式 root，正常执行
    assert asyncio.run(no_root.restore("decl", "whatever")) == {
        "restored": "whatever",
        "user": "u1",
    }
