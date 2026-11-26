"""托管所属插件不可用时原样保留，插件回来后还原：任何时刻落盘都不丢 uid、顺序和引用。"""

import asyncio
from pathlib import Path
from typing import Annotated
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    config_manager,
    ref,
)
from app.utils import io as config_io

pytestmark = pytest.mark.asyncio

TARGET = "UnresolvedMemberTargets"


class _Info(ConfigGroup):
    Name: str = ""
    Count: int = 0


class KnownEntry(ConfigEntry):
    Info: _Info = Field(default_factory=_Info)


class PluginEntry(ConfigEntry):
    """所属插件可能不在场的托管类型。"""

    Info: _Info = Field(default_factory=_Info)


class _RefInfo(ConfigGroup):
    Target: Annotated[UUID | str, ref(TARGET, default="-", allow_values=("-",))] = (
        Field(default_factory=lambda: "-")
    )


class Pointer(ConfigEntry):
    """队列项、计划引用这类指向托管的配置。"""

    Info: _RefInfo = Field(default_factory=_RefInfo)


class Profile:
    """盘上一个托管文件（插件类型夹在中间）和一个引用全部托管的文件。"""

    def __init__(self, root: Path, *, unreadable: int | None = None) -> None:
        self.ids = [str(uuid4()) for _ in range(4)]
        types = ["KnownEntry", "PluginEntry", "KnownEntry", "PluginEntry"]
        data = {
            uid: {"Info": {"Name": f"n{index}", "Count": index}}
            for index, uid in enumerate(self.ids)
        }
        if unreadable is not None:
            data[self.ids[unreadable]]["Info"]["Count"] = "oops"
        self.document = {
            "order": [
                {"uid": uid, "type": name}
                for uid, name in zip(self.ids, types, strict=True)
            ],
            "data": data,
        }
        self.path = root / "scripts.yaml"
        config_io.write_file(self.path, self.document)
        self.original = self.path.read_bytes()
        pointer_ids = [str(uuid4()) for _ in self.ids]
        self.pointers_path = root / "queues.yaml"
        config_io.write_file(
            self.pointers_path,
            {
                "order": [{"uid": uid, "type": "Pointer"} for uid in pointer_ids],
                "data": {
                    uid: {"Info": {"Target": target}}
                    for uid, target in zip(pointer_ids, self.ids, strict=True)
                },
            },
        )
        self.roots: list[ConfigCollection] = []

    async def start(self, types: list[type[ConfigEntry]]):
        """一次启动：从盘上读托管和引用它的集合。须在独立的 ref 池里调用。"""
        for root in self.roots:
            config_manager.unregister_root(root)
        scripts = ConfigCollection.build(types, keep_unknown_types=True)
        config_manager.register_root(scripts, self.path)
        config_manager.register_collection(TARGET, scripts)
        pointers = ConfigCollection.build([Pointer])
        config_manager.register_root(pointers, self.pointers_path)
        self.roots = [scripts, pointers]
        await scripts.activate()
        await pointers.activate()
        return scripts, pointers

    async def start_without_plugin(self):
        scripts, pointers = await self.start([KnownEntry])
        assert [str(item.uid) for item in scripts.unresolved()] == [
            self.ids[1],
            self.ids[3],
        ]
        return scripts, pointers

    def saved(self) -> dict:
        return config_io.read_dict_file(self.path)

    def saved_targets(self) -> list[str]:
        document = config_io.read_dict_file(self.pointers_path)
        return [
            str(document["data"][item["uid"]]["Info"]["Target"])
            for item in document["order"]
        ]

    def saved_keeps(self, uid: str) -> bool:
        """盘上这一条在原位：要么是原文，要么是还原后的正式条目，内容都与原文一致。"""
        saved = self.saved()
        return [item["uid"] for item in saved["order"]] == self.ids and saved[
            "data"
        ].get(uid) == self.document["data"][uid]

    async def assert_restart_intact(self) -> None:
        """插件在场时重启：uid、顺序、内容和引用都在。"""
        with patch.dict(config_manager._collections, clear=True):
            scripts, pointers = await self.start([KnownEntry, PluginEntry])
            assert [str(uid) for uid in scripts.keys()] == self.ids
            assert scripts.unresolved() == ()
            assert [str(item.Info.Target) for item in pointers.values()] == self.ids
            await config_manager.flush()
        assert self.saved() == self.document
        assert self.saved_targets() == self.ids


@pytest.fixture(autouse=True)
def isolated_ref_pool():
    with patch.dict(config_manager._collections):
        yield


async def _plugin_back(scripts: ConfigCollection) -> None:
    """插件重新可用：类型登记回集合。"""
    scripts.add_type(PluginEntry)
    await scripts.commit()


def _hold_save_at_export(collection: ConfigCollection):
    """让对 ``collection`` 的保存停在导出这一步，直到放行；用来把保存夹进还原中间。"""
    original = ConfigCollection.to_dict
    entered, release = asyncio.Event(), asyncio.Event()

    async def to_dict(self, *args, **kwargs):
        if self is collection and not release.is_set():
            entered.set()
            await release.wait()
        return await original(self, *args, **kwargs)

    return patch.object(ConfigCollection, "to_dict", to_dict), entered, release


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def test_unavailable_members_saved_in_place_with_references(tmp_path):
    profile = Profile(tmp_path)
    scripts, pointers = await profile.start_without_plugin()

    assert [str(uid) for uid in scripts.keys()] == [profile.ids[0], profile.ids[2]]
    assert [str(item.Info.Target) for item in pointers.values()] == profile.ids

    await scripts[profile.ids[0]].update(
        KnownEntry.model_validate({"Info": {"Name": "changed"}})
    )
    await config_manager.flush()

    saved = profile.saved()
    assert saved["order"] == profile.document["order"]
    for uid in (profile.ids[1], profile.ids[3]):
        assert saved["data"][uid] == profile.document["data"][uid]
    assert saved["data"][profile.ids[0]]["Info"]["Name"] == "changed"
    assert profile.saved_targets() == profile.ids


async def test_save_during_restore_keeps_every_member_on_disk(tmp_path):
    profile = Profile(tmp_path)
    scripts, _pointers = await profile.start_without_plugin()
    await _plugin_back(scripts)
    held, entered, release = _hold_save_at_export(scripts)
    with held:
        saving = asyncio.create_task(config_manager.flush())
        await entered.wait()
        restoring = asyncio.create_task(scripts.materialize_unresolved("PluginEntry"))
        await _settle()
        release.set()
        await saving
        assert profile.saved_keeps(profile.ids[1])
        assert profile.saved_keeps(profile.ids[3])
        assert await restoring == [UUID(profile.ids[1]), UUID(profile.ids[3])]
    await config_manager.flush()

    assert scripts.unresolved() == ()
    assert [str(uid) for uid in scripts.keys()] == profile.ids
    assert profile.saved() == profile.document


async def test_restore_cancelled_while_queued_keeps_original(tmp_path):
    profile = Profile(tmp_path)
    scripts, _pointers = await profile.start_without_plugin()
    await _plugin_back(scripts)
    held, release = asyncio.Event(), asyncio.Event()

    async def busy_config() -> None:
        async with config_manager.transaction():
            held.set()
            await release.wait()

    holder = asyncio.create_task(busy_config())
    await held.wait()
    restoring = asyncio.create_task(scripts.materialize_unresolved("PluginEntry"))
    await _settle()
    restoring.cancel()
    with pytest.raises(asyncio.CancelledError):
        await restoring
    release.set()
    await holder

    assert [str(item.uid) for item in scripts.unresolved()] == [
        profile.ids[1],
        profile.ids[3],
    ]
    await config_manager.flush()
    assert profile.path.read_bytes() == profile.original
    await profile.assert_restart_intact()


async def test_member_unreadable_by_returned_plugin_stays_aside(tmp_path):
    profile = Profile(tmp_path, unreadable=1)
    scripts, _pointers = await profile.start_without_plugin()
    await _plugin_back(scripts)

    assert await scripts.materialize_unresolved("PluginEntry") == [UUID(profile.ids[3])]

    (left,) = scripts.unresolved()
    assert str(left.uid) == profile.ids[1]
    assert left.reason == "load_failed"
    assert [str(uid) for uid in scripts.keys()] == [
        profile.ids[0],
        profile.ids[2],
        profile.ids[3],
    ]
    await config_manager.flush()
    assert profile.saved() == profile.document
    assert profile.saved_targets() == profile.ids


async def test_unreadable_member_detail_omits_input_value(tmp_path):
    """读不了的成员只记字段路径和错误类别：激活时隔离、插件回来后还原失败两条路都一样。"""
    secret = "token-LEAK-0123456789abcdef"
    profile = Profile(tmp_path, unreadable=1)
    profile.document["data"][profile.ids[1]]["Info"]["Count"] = secret
    profile.document["data"][profile.ids[2]]["Info"]["Count"] = secret
    config_io.write_file(profile.path, profile.document)
    scripts, _pointers = await profile.start([KnownEntry])
    await _plugin_back(scripts)
    await scripts.materialize_unresolved("PluginEntry")

    details = {str(item.uid): item.detail for item in scripts.unresolved()}
    assert set(details) == {profile.ids[1], profile.ids[2]}
    for detail in details.values():
        assert secret not in detail
        assert detail == "ValidationError: Count（int_parsing）"
    await config_manager.flush()
    assert profile.saved() == profile.document


async def test_discarded_member_reaches_disk_without_exit_flush(tmp_path):
    """删掉旁挂成员后，后台的防抖保存就要把它从盘上去掉，不能只等退出时的 flush。"""
    profile = Profile(tmp_path)
    scripts, _pointers = await profile.start_without_plugin()
    await config_manager.flush()
    gone = profile.ids[1]

    await scripts.discard_unresolved(gone)
    for _ in range(100):
        if gone not in profile.saved()["data"]:
            break
        await asyncio.sleep(0.02)

    saved = profile.saved()
    assert gone not in saved["data"]
    assert [item["uid"] for item in saved["order"]] == [
        uid for uid in profile.ids if uid != gone
    ]
