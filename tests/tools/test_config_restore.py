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
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.config_archive import archive_files, get_backup_dir, read_backup_mode
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
        build_restore_service(_ctx(), [])
    bad = [ConfigRestorePool(key="x", kind="other", list_backups=_list)]
    with pytest.raises(ValueError):
        build_restore_service(_ctx(), bad)


def test_binding_and_dispatch() -> None:
    """绑定语义：ctx 透传、位置参数转发、按 key 分发、顺序即池表顺序。"""

    service = build_restore_service(_ctx(), POOLS)
    assert service.target_keys == ["mas", "native"]
    # list 项为 dict（time + 三态 mode 标注；未声明三态 mode=None）
    assert [item["time"] for item in asyncio.run(service.list("mas"))] == [
        "t2",
        "t1",
    ]
    assert [item["mode"] for item in asyncio.run(service.list("mas"))] == [None, None]
    assert asyncio.run(service.preview("mas", "t1")) == {
        "time": "t1",
        "marker": "s1",
    }
    asyncio.run(service.restore("mas", "t1"))
    assert asyncio.run(service.ensure("mas")) == {"created": True, "time": "t2"}


def test_dispatch_rejects_unknown_and_missing() -> None:
    """未知 target 与未声明的能力统一抛 ValueError（HTTP 层转 400）。"""

    service = build_restore_service(_ctx(), POOLS)
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
    service = build_restore_service(ctx, [DECL_POOL])

    # snapshot 落盘 → list 出现 → preview 注入标准 files → read_file 可读
    created = asyncio.run(service.ensure("decl"))
    assert created["created"] is True and created["time"]
    items = asyncio.run(service.list("decl"))
    assert [item["time"] for item in items] == [created["time"]]
    assert items[0]["mode"] is None  # 未声明三态：无 Mode 标注
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
        [DECL_POOL],
    )
    assert asyncio.run(no_content.ensure("decl")) == {"created": False, "time": ""}


def test_declarative_none_root_is_silent(tmp_path, monkeypatch) -> None:
    """backup_root 返回 None（如脚本路径未配置）：list 空 / snapshot 无变化 /
    preview 不注入不炸 / read_file 报无可读——而不是 TypeError。"""

    monkeypatch.chdir(tmp_path)
    no_root = build_restore_service(
        RestoreContext(_ctx().config, _ctx().script_config, "no-root", "u1"),
        [DECL_POOL],
    )
    assert asyncio.run(no_root.list("decl")) == []
    assert asyncio.run(no_root.ensure("decl")) == {"created": False, "time": ""}
    assert asyncio.run(no_root.preview("decl", "whatever")) == {}
    with pytest.raises(ValueError):
        asyncio.run(no_root.read_backup_file("decl", "whatever", "x.json"))
    # restore 是显式回调（专项语义），不依赖声明式 root，正常执行
    asyncio.run(no_root.restore("decl", "whatever"))


# ═══════════════ 三态增强回归（mas_mode 标注 / 指纹去重 / 跨来源校验） ═══════════════


class _ModeUser:
    """三态桩用户：支持 ``get("Info", "Mode")`` 与 ``async update``（记录写回）。"""

    def __init__(self, mode: str):
        self._mode = mode
        self.updated: list[dict] = []

    def get(self, group: str, key: str):
        return self._mode if (group, key) == ("Info", "Mode") else None

    async def update(self, grouped: dict) -> None:
        self.updated.append(grouped)
        mode = grouped.get("Info", {}).get("Mode")
        if mode:
            self._mode = mode


async def _tri_files(ctx) -> dict[str, str] | None:
    return {"config.json": '{"x": 1}', "_mas_overlay.json": '{"Mode": "用户"}'}


def _tri_root_path(ctx: RestoreContext) -> Path:
    return Path.cwd() / "data" / ctx.script_id / "tri-decl"


async def _tri_root(ctx: RestoreContext) -> Path:
    return _tri_root_path(ctx)


def _tri_ctx(script_id: str, mode: str) -> tuple[RestoreContext, _ModeUser]:
    """构造 tri_state 上下文：UserData 支持 ``get("Info", "Mode")`` 与写回。"""

    uid = uuid.uuid4()
    user = _ModeUser(mode)
    script_config = SimpleNamespace(UserData={uid: user})
    return (
        RestoreContext(
            config=None,
            script_config=script_config,
            script_id=script_id,
            user_id=str(uid),
        ),
        user,
    )


def _tri_pool(recorder: dict) -> ConfigRestorePool:
    """tri_state 声明式池：restore / set_mode 调用顺序记录到 recorder。"""

    async def restore(ctx: RestoreContext, ts: str) -> object:
        recorder["restored"].append(ts)
        return {"restored": ts}

    async def set_mode(ctx: RestoreContext, mode: str) -> None:
        recorder["set_modes"].append(mode)
        user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
        await user.update({"Info": {"Mode": mode}})

    return ConfigRestorePool(
        key="tri",
        kind="user",
        mas_mode="tri_state",
        files=_tri_files,
        backup_root=_tri_root,
        restore=restore,
        set_mode=set_mode,
    )


def _user_only_pool(recorder: dict) -> ConfigRestorePool:
    """user_only 声明式池：备份恒标注「用户」，无跨来源校验。"""

    async def restore(ctx: RestoreContext, ts: str) -> object:
        recorder["restored"].append(ts)
        return {"restored": ts}

    return ConfigRestorePool(
        key="tri",
        kind="user",
        mas_mode="user_only",
        files=_tri_files,
        backup_root=_tri_root,
        restore=restore,
    )


def _sidecar_only_pool(recorder: dict) -> ConfigRestorePool:
    """sidecar_only 声明式池：备份标注实际 Mode 供列表标签，无目录迁移校验。"""

    async def restore(ctx: RestoreContext, ts: str) -> object:
        recorder["restored"].append(ts)
        return {"restored": ts}

    return ConfigRestorePool(
        key="tri",
        kind="user",
        mas_mode="sidecar_only",
        files=_tri_files,
        backup_root=_tri_root,
        restore=restore,
    )


def test_tristate_backup_mode_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """三态标注：ensure 归档后写 _mas_mode（tri_state=Info.Mode 值 / user_only=恒
    「用户」/ sidecar_only=实际 Mode / 未声明=None），``service.list`` 项带 mode。"""

    monkeypatch.chdir(tmp_path)

    # tri_state：备份时点 Mode = UserData.Info.Mode
    ctx, _ = _tri_ctx("tri-anno-a", "脚本")
    service = build_restore_service(
        ctx, [_tri_pool({"restored": [], "set_modes": []})]
    )
    created = asyncio.run(service.ensure("tri"))
    assert created["created"] is True
    backup_dir = get_backup_dir(_tri_root_path(ctx), created["time"])
    assert backup_dir is not None
    assert read_backup_mode(backup_dir) == "脚本"
    item = asyncio.run(service.list("tri"))[0]
    assert item["time"] == created["time"] and item["mode"] == "脚本"

    # user_only：恒标注「用户」，与 Info.Mode 无关
    ctx_u, _ = _tri_ctx("tri-anno-b", "直控")
    only = build_restore_service(ctx_u, [_user_only_pool({"restored": []})])
    created_u = asyncio.run(only.ensure("tri"))
    backup_dir_u = get_backup_dir(_tri_root_path(ctx_u), created_u["time"])
    assert backup_dir_u is not None
    assert read_backup_mode(backup_dir_u) == "用户"
    assert asyncio.run(only.list("tri"))[0]["mode"] == "用户"

    # sidecar_only：标注实际 Mode（纯字段侧车，无目录语义，直控态同样标注）
    ctx_s, _ = _tri_ctx("tri-anno-d", "直控")
    side = build_restore_service(ctx_s, [_sidecar_only_pool({"restored": []})])
    created_s = asyncio.run(side.ensure("tri"))
    backup_dir_s = get_backup_dir(_tri_root_path(ctx_s), created_s["time"])
    assert backup_dir_s is not None
    assert read_backup_mode(backup_dir_s) == "直控"
    assert asyncio.run(side.list("tri"))[0]["mode"] == "直控"

    # 未声明三态：不写 _mas_mode，list 项 mode=None
    ctx_p, _ = _tri_ctx("tri-anno-c", "脚本")
    plain = build_restore_service(ctx_p, [DECL_POOL])
    created_p = asyncio.run(plain.ensure("decl"))
    backup_dir_p = get_backup_dir(
        Path.cwd() / "data" / ctx_p.script_id / "test-decl", created_p["time"]
    )
    assert backup_dir_p is not None
    assert read_backup_mode(backup_dir_p) is None
    assert asyncio.run(plain.list("decl"))[0]["mode"] is None


def test_tristate_ensure_dedup_ignores_mode_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """指纹去重：_mas_mode 是归档后元数据，不破坏同内容二次 ensure 的去重。"""

    monkeypatch.chdir(tmp_path)
    ctx, _ = _tri_ctx("tri-dedup", "用户")
    service = build_restore_service(
        ctx, [_tri_pool({"restored": [], "set_modes": []})]
    )
    first = asyncio.run(service.ensure("tri"))
    assert first["created"] is True
    second = asyncio.run(service.ensure("tri"))
    assert second["created"] is False  # 内容一致 → 去重，不新建条目
    assert second["time"] == first["time"]
    assert len(asyncio.run(service.list("tri"))) == 1


def test_tristate_cross_source_restore_switches_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """跨来源恢复：备份 Mode ≠ 当前 Mode 时自动 set_mode 切回备份时点再执行；
    同 Mode / user_only / sidecar_only / 旧备份（无 _mas_mode）直接执行。
    ``service.current_mode`` 只在 tri_state 池返回当前来源（前端比对用）。"""

    monkeypatch.chdir(tmp_path)

    # 备份时点 Mode=脚本；随后用户切到「用户」态
    ctx, user = _tri_ctx("tri-cross", "脚本")
    recorder = {"restored": [], "set_modes": []}
    service = build_restore_service(ctx, [_tri_pool(recorder)])
    created = asyncio.run(service.ensure("tri"))
    assert (
        read_backup_mode(get_backup_dir(_tri_root_path(ctx), created["time"])) == "脚本"
    )
    assert asyncio.run(service.current_mode("tri")) == "脚本"
    user._mode = "用户"
    assert asyncio.run(service.current_mode("tri")) == "用户"

    # 跨来源（脚本→用户）：先 set_mode 写回备份时点，再执行专项 restore
    asyncio.run(service.restore("tri", created["time"]))
    assert recorder["set_modes"] == ["脚本"]
    assert user.updated[-1] == {"Info": {"Mode": "脚本"}}  # 桩记录 Mode 已写回
    assert recorder["restored"] == [created["time"]]

    # 同 Mode：不再重复 set_mode，直接执行
    asyncio.run(service.restore("tri", created["time"]))
    assert recorder["set_modes"] == ["脚本"]
    assert recorder["restored"] == [created["time"], created["time"]]

    # user_only 池跨 Mode：无来源概念，current_mode 为 None、直接执行
    ctx_u, _ = _tri_ctx("tri-cross-u", "脚本")
    rec_u = {"restored": []}
    only = build_restore_service(ctx_u, [_user_only_pool(rec_u)])
    created_u = asyncio.run(only.ensure("tri"))
    assert (
        read_backup_mode(get_backup_dir(_tri_root_path(ctx_u), created_u["time"]))
        == "用户"
    )
    assert asyncio.run(only.current_mode("tri")) is None
    asyncio.run(only.restore("tri", created_u["time"]))
    assert rec_u["restored"] == [created_u["time"]]

    # sidecar_only 池跨 Mode：纯字段回填、无目录迁移，同样直接执行
    ctx_s, user_s = _tri_ctx("tri-cross-s", "脚本")
    rec_s = {"restored": []}
    side = build_restore_service(ctx_s, [_sidecar_only_pool(rec_s)])
    created_s = asyncio.run(side.ensure("tri"))
    user_s._mode = "直控"
    assert asyncio.run(side.current_mode("tri")) is None
    asyncio.run(side.restore("tri", created_s["time"]))
    assert rec_s["restored"] == [created_s["time"]]

    # 旧备份（无 _mas_mode）：读不到标注 → 无来源切换，直接执行
    ctx_old, _ = _tri_ctx("tri-cross-old", "用户")
    rec_old = {"restored": []}
    old_service = build_restore_service(ctx_old, [_tri_pool(rec_old)])
    legacy = archive_files(asyncio.run(_tri_files(ctx_old)), _tri_root_path(ctx_old))
    assert legacy is not None
    assert read_backup_mode(legacy) is None  # 未写 _mas_mode 的旧备份
    asyncio.run(old_service.restore("tri", legacy.name))
    assert rec_old["restored"] == [legacy.name]

    # 声明式池（未声明三态）：current_mode 为 None（不参与跨来源比对）
    plain = build_restore_service(_ctx(), [DECL_POOL])
    assert asyncio.run(plain.current_mode("decl")) is None
