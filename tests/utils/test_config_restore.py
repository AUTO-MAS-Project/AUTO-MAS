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

from app.utils.common.config import archive as _utils_config_archive
from app.utils.common.config import restore as _utils_config_restore
from tests.config_support import group_view


async def _list(ctx) -> list[str]:
    return ["t2", "t1"]


async def _preview(ctx, ts: str) -> dict:
    return {"time": ts, "marker": ctx.script_id}


async def _restore(ctx, ts: str) -> object:
    return {"restored": ts, "user": ctx.user_id}


async def _snapshot(ctx) -> dict:
    return {"created": True, "time": "t2"}


POOLS = [
    _utils_config_restore.ConfigRestorePool(
        key="mas",
        kind="user",
        list_backups=_list,
        preview=_preview,
        restore=_restore,
        snapshot=_snapshot,
    ),
    _utils_config_restore.ConfigRestorePool(
        key="native", kind="script", list_backups=_list
    ),
]


def _ctx() -> _utils_config_restore.RestoreContext:
    return _utils_config_restore.RestoreContext(
        config=None, script_config={"marker": "s1"}, script_id="s1", user_id="u1"
    )


def test_build_validates_table() -> None:
    """空池表与非法 kind 都在构建期拒绝。"""
    with pytest.raises(ValueError):
        _utils_config_restore.build_restore_service(_ctx(), [])
    bad = [
        _utils_config_restore.ConfigRestorePool(
            key="x", kind="other", list_backups=_list
        )
    ]
    with pytest.raises(ValueError):
        _utils_config_restore.build_restore_service(_ctx(), bad)


def test_binding_and_dispatch() -> None:
    """绑定语义：ctx 透传、位置参数转发、按 key 分发、顺序即池表顺序。"""
    service = _utils_config_restore.build_restore_service(_ctx(), POOLS)
    assert service.target_keys == ["mas", "native"]
    assert [item["time"] for item in asyncio.run(service.list("mas"))] == ["t2", "t1"]
    assert [item["base"] for item in asyncio.run(service.list("mas"))] == [None, None]
    assert asyncio.run(service.preview("mas", "t1")) == {"time": "t1", "marker": "s1"}
    asyncio.run(service.restore("mas", "t1"))
    assert asyncio.run(service.ensure("mas")) == {"created": True, "time": "t2"}


def test_dispatch_rejects_unknown_and_missing() -> None:
    """未知 target 与未声明的能力统一抛 ValueError（HTTP 层转 400）。"""
    service = _utils_config_restore.build_restore_service(_ctx(), POOLS)
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
    return {"_mas_overlay.json": '{"Base": "independent"}'}


async def _decl_root(ctx) -> Path | None:
    if ctx.script_id == "no-root":
        return None
    return Path.cwd() / "data" / ctx.script_id / "test-decl"


DECL_POOL = _utils_config_restore.ConfigRestorePool(
    key="decl", kind="user", files=_decl_files, backup_root=_decl_root, restore=_restore
)


def test_declarative_derivation(tmp_path, monkeypatch) -> None:
    """声明式派生：files+backup_root → list/snapshot/read_file/files 兜底注入。"""
    monkeypatch.chdir(tmp_path)
    ctx = _ctx()
    service = _utils_config_restore.build_restore_service(ctx, [DECL_POOL])
    created = asyncio.run(service.ensure("decl"))
    assert created["created"] is True and created["time"]
    items = asyncio.run(service.list("decl"))
    assert [item["time"] for item in items] == [created["time"]]
    assert items[0]["base"] is None
    payload = asyncio.run(service.preview("decl", created["time"]))
    assert payload["files"] == [
        {
            "path": "_mas_overlay.json",
            "size": len('{"Base": "independent"}'.encode("utf-8")),
        }
    ]
    content = asyncio.run(
        service.read_backup_file("decl", created["time"], "_mas_overlay.json")
    )
    assert '"Base"' in content["content"]
    no_content = _utils_config_restore.build_restore_service(
        _utils_config_restore.RestoreContext(
            ctx.config, ctx.script_config, "no-content", ctx.user_id
        ),
        [DECL_POOL],
    )
    assert asyncio.run(no_content.ensure("decl")) == {"created": False, "time": ""}


def test_declarative_none_root_is_silent(tmp_path, monkeypatch) -> None:
    """backup_root 返回 None（如脚本路径未配置）：list 空 / snapshot 无变化 /
    preview 不注入不炸 / read_file 报无可读——而不是 TypeError。"""
    monkeypatch.chdir(tmp_path)
    no_root = _utils_config_restore.build_restore_service(
        _utils_config_restore.RestoreContext(
            _ctx().config, _ctx().script_config, "no-root", "u1"
        ),
        [DECL_POOL],
    )
    assert asyncio.run(no_root.list("decl")) == []
    assert asyncio.run(no_root.ensure("decl")) == {"created": False, "time": ""}
    assert asyncio.run(no_root.preview("decl", "whatever")) == {}
    with pytest.raises(ValueError):
        asyncio.run(no_root.read_backup_file("decl", "whatever", "x.json"))
    asyncio.run(no_root.restore("decl", "whatever"))


class _BaseUser:
    @classmethod
    def model_validate(cls, value):
        return value

    """三态桩用户：支持 ``get("Info", "Base")`` 与 ``async update``（记录写回）。"""

    def __init__(self, base: str):
        self._base = base
        self.Info = group_view(self, "Info")
        self.updated: list[dict] = []

    def get(self, group: str, key: str):
        return self._base if (group, key) == ("Info", "Base") else None

    async def update(self, grouped: dict) -> None:
        self.updated.append(grouped)
        base = grouped.get("Info", {}).get("Base")
        if base:
            self._base = base


async def _tri_files(ctx) -> dict[str, str] | None:
    return {"config.json": '{"x": 1}', "_mas_overlay.json": '{"Base": "independent"}'}


def _tri_root_path(ctx: _utils_config_restore.RestoreContext) -> Path:
    return Path.cwd() / "data" / ctx.script_id / "tri-decl"


async def _tri_root(ctx: _utils_config_restore.RestoreContext) -> Path:
    return _tri_root_path(ctx)


def _tri_ctx(
    script_id: str, base: str
) -> tuple[_utils_config_restore.RestoreContext, _BaseUser]:
    """构造 tri_state 上下文：UserData 支持 ``get("Info", "Base")`` 与写回。"""
    uid = uuid.uuid4()
    user = _BaseUser(base)
    script_config = SimpleNamespace(UserData={uid: user})
    return (
        _utils_config_restore.RestoreContext(
            config=None,
            script_config=script_config,
            script_id=script_id,
            user_id=str(uid),
        ),
        user,
    )


def _tri_pool(recorder: dict) -> _utils_config_restore.ConfigRestorePool:
    """tri_state 声明式池：restore / set_base 调用顺序记录到 recorder。"""

    async def restore(ctx: _utils_config_restore.RestoreContext, ts: str) -> object:
        recorder["restored"].append(ts)
        return {"restored": ts}

    async def set_base(ctx: _utils_config_restore.RestoreContext, base: str) -> None:
        recorder["set_bases"].append(base)
        user = ctx.script_config.UserData[uuid.UUID(ctx.user_id)]
        await user.update(type(user).model_validate({"Info": {"Base": base}}))

    return _utils_config_restore.ConfigRestorePool(
        key="tri",
        kind="user",
        mas_base="tri_state",
        files=_tri_files,
        backup_root=_tri_root,
        restore=restore,
        set_base=set_base,
    )


def _user_only_pool(recorder: dict) -> _utils_config_restore.ConfigRestorePool:
    """user_only 声明式池：备份恒标注独立来源，无跨来源校验。"""

    async def restore(ctx: _utils_config_restore.RestoreContext, ts: str) -> object:
        recorder["restored"].append(ts)
        return {"restored": ts}

    return _utils_config_restore.ConfigRestorePool(
        key="tri",
        kind="user",
        mas_base="user_only",
        files=_tri_files,
        backup_root=_tri_root,
        restore=restore,
    )


def _sidecar_only_pool(recorder: dict) -> _utils_config_restore.ConfigRestorePool:
    """sidecar_only 声明式池：备份标注实际 base 供列表标签，无目录迁移校验。"""

    async def restore(ctx: _utils_config_restore.RestoreContext, ts: str) -> object:
        recorder["restored"].append(ts)
        return {"restored": ts}

    return _utils_config_restore.ConfigRestorePool(
        key="tri",
        kind="user",
        mas_base="sidecar_only",
        files=_tri_files,
        backup_root=_tri_root,
        restore=restore,
    )


def test_tristate_backup_base_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """三态标注：ensure 归档后写 _mas_base（tri_state=Info.Base 值 / user_only=恒
    独立来源 / sidecar_only=实际 base / 未声明=None），``service.list`` 项带 base。"""
    monkeypatch.chdir(tmp_path)
    ctx, _ = _tri_ctx("tri-anno-a", "shared")
    service = _utils_config_restore.build_restore_service(
        ctx, [_tri_pool({"restored": [], "set_bases": []})]
    )
    created = asyncio.run(service.ensure("tri"))
    assert created["created"] is True
    backup_dir = _utils_config_archive.get_backup_dir(
        _tri_root_path(ctx), created["time"]
    )
    assert backup_dir is not None
    assert _utils_config_archive.read_backup_base(backup_dir) == "shared"
    item = asyncio.run(service.list("tri"))[0]
    assert item["time"] == created["time"] and item["base"] == "shared"
    ctx_u, _ = _tri_ctx("tri-anno-b", "native")
    only = _utils_config_restore.build_restore_service(
        ctx_u, [_user_only_pool({"restored": []})]
    )
    created_u = asyncio.run(only.ensure("tri"))
    backup_dir_u = _utils_config_archive.get_backup_dir(
        _tri_root_path(ctx_u), created_u["time"]
    )
    assert backup_dir_u is not None
    assert _utils_config_archive.read_backup_base(backup_dir_u) == "independent"
    assert asyncio.run(only.list("tri"))[0]["base"] == "independent"
    ctx_s, _ = _tri_ctx("tri-anno-d", "native")
    side = _utils_config_restore.build_restore_service(
        ctx_s, [_sidecar_only_pool({"restored": []})]
    )
    created_s = asyncio.run(side.ensure("tri"))
    backup_dir_s = _utils_config_archive.get_backup_dir(
        _tri_root_path(ctx_s), created_s["time"]
    )
    assert backup_dir_s is not None
    assert _utils_config_archive.read_backup_base(backup_dir_s) == "native"
    assert asyncio.run(side.list("tri"))[0]["base"] == "native"
    ctx_p, _ = _tri_ctx("tri-anno-c", "shared")
    plain = _utils_config_restore.build_restore_service(ctx_p, [DECL_POOL])
    created_p = asyncio.run(plain.ensure("decl"))
    backup_dir_p = _utils_config_archive.get_backup_dir(
        Path.cwd() / "data" / ctx_p.script_id / "test-decl", created_p["time"]
    )
    assert backup_dir_p is not None
    assert _utils_config_archive.read_backup_base(backup_dir_p) is None
    assert asyncio.run(plain.list("decl"))[0]["base"] is None


def test_tristate_ensure_dedup_ignores_base_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """指纹去重：_mas_base 是归档后元数据，不破坏同内容二次 ensure 的去重。"""
    monkeypatch.chdir(tmp_path)
    ctx, _ = _tri_ctx("tri-dedup", "independent")
    service = _utils_config_restore.build_restore_service(
        ctx, [_tri_pool({"restored": [], "set_bases": []})]
    )
    first = asyncio.run(service.ensure("tri"))
    assert first["created"] is True
    second = asyncio.run(service.ensure("tri"))
    assert second["created"] is False
    assert second["time"] == first["time"]
    assert len(asyncio.run(service.list("tri"))) == 1


def test_tristate_cross_source_restore_switches_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """跨来源恢复：备份 base ≠ 当前 base 时自动 set_base 切回备份时点再执行；
    同 base / user_only / sidecar_only / 旧备份（无 _mas_base）直接执行。
    ``service.current_base`` 只在 tri_state 池返回当前来源（前端比对用）。"""
    monkeypatch.chdir(tmp_path)
    ctx, user = _tri_ctx("tri-cross", "shared")
    recorder = {"restored": [], "set_bases": []}
    service = _utils_config_restore.build_restore_service(ctx, [_tri_pool(recorder)])
    created = asyncio.run(service.ensure("tri"))
    assert (
        _utils_config_archive.read_backup_base(
            _utils_config_archive.get_backup_dir(_tri_root_path(ctx), created["time"])
        )
        == "shared"
    )
    assert asyncio.run(service.current_base("tri")) == "shared"
    user._base = "independent"
    assert asyncio.run(service.current_base("tri")) == "independent"
    asyncio.run(service.restore("tri", created["time"]))
    assert recorder["set_bases"] == ["shared"]
    assert user.updated[-1] == {"Info": {"Base": "shared"}}
    assert recorder["restored"] == [created["time"]]
    asyncio.run(service.restore("tri", created["time"]))
    assert recorder["set_bases"] == ["shared"]
    assert recorder["restored"] == [created["time"], created["time"]]
    ctx_u, _ = _tri_ctx("tri-cross-u", "shared")
    rec_u = {"restored": []}
    only = _utils_config_restore.build_restore_service(ctx_u, [_user_only_pool(rec_u)])
    created_u = asyncio.run(only.ensure("tri"))
    assert (
        _utils_config_archive.read_backup_base(
            _utils_config_archive.get_backup_dir(
                _tri_root_path(ctx_u), created_u["time"]
            )
        )
        == "independent"
    )
    assert asyncio.run(only.current_base("tri")) is None
    asyncio.run(only.restore("tri", created_u["time"]))
    assert rec_u["restored"] == [created_u["time"]]
    ctx_s, user_s = _tri_ctx("tri-cross-s", "shared")
    rec_s = {"restored": []}
    side = _utils_config_restore.build_restore_service(
        ctx_s, [_sidecar_only_pool(rec_s)]
    )
    created_s = asyncio.run(side.ensure("tri"))
    user_s._base = "native"
    assert asyncio.run(side.current_base("tri")) is None
    asyncio.run(side.restore("tri", created_s["time"]))
    assert rec_s["restored"] == [created_s["time"]]
    ctx_old, _ = _tri_ctx("tri-cross-old", "independent")
    rec_old = {"restored": []}
    old_service = _utils_config_restore.build_restore_service(
        ctx_old, [_tri_pool(rec_old)]
    )
    legacy = _utils_config_archive.archive_files(
        asyncio.run(_tri_files(ctx_old)), _tri_root_path(ctx_old)
    )
    assert legacy is not None
    assert _utils_config_archive.read_backup_base(legacy) is None
    asyncio.run(old_service.restore("tri", legacy.name))
    assert rec_old["restored"] == [legacy.name]
    plain = _utils_config_restore.build_restore_service(_ctx(), [DECL_POOL])
    assert asyncio.run(plain.current_base("decl")) is None
