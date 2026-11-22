#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""内置专项的托管属主入口：按**确切类型**认领自己名下的托管（专项一侧）。

项目更新一侧（``tools/embedded/owners.py``）只经这里交出的普通数据知道托管还在不在、读写项目记录；
它不拿配置类，也不拿配置对象。三个内置专项各登记一个（通用 MFW 在 ``app/task/MaaFW/registration.py``，
M9A、MSS 在各自的 ``registration.py``）：认领用 ``type(config) is <类型>``，类型每次现取，不靠继承——
以后 M9A、MSS 的配置类不再继承 ``MaaFWConfig``，这里不用改。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from app.task.MaaFW.tools.embedded.owners import (
    OWNER_PROTOCOL,
    UNSET,
    ManagedRecord,
    OwnerListing,
    PathCheck,
    ReadResult,
    RecordPatch,
    WriteResult,
)


def _host_config() -> Any:
    from app.core import Config

    return Config


def _record(uid: str, config: Any, order: int) -> ManagedRecord:
    return ManagedRecord(
        uid=uid,
        kind=type(config).__name__.removesuffix("Config"),
        order=order,
        name=config.Info.Name,
        source_path=config.Info.Path,
        report=config.Embedded.Report,
        source_version=config.Embedded.SourceVersion,
        imported_at=config.Embedded.ImportedAt,
        follow_source=_follow_source(config),
        channel=config.Update.Channel,
        update_source=config.Update.Source,
        auto_update_mode=config.Update.AutoUpdateMode,
        package_mode=config.Update.PackageMode,
        proxy_address=config.Update.ProxyAddress,
        mirror_cdk=config.Update.MirrorChyanCDK,
        flavor_spec=getattr(type(config), "FLAVOR", None),
        running=bool(getattr(config, "is_locked", False)),
    )


def _follow_source(config: Any) -> bool:
    try:
        return bool(config.Embedded.FollowSource)
    except Exception:  # noqa: BLE001 - 老配置没有这一项就是没开
        return False


def _patch_data(patch: RecordPatch) -> dict[str, Any]:
    """写回补丁 → 配置的分组字典；只放给了值的项，形状与原先各处直接写回时一致。"""

    data: dict[str, Any] = {}
    if patch.source_path is not UNSET:
        data.setdefault("Info", {})["Path"] = patch.source_path
    embedded: dict[str, Any] = {}
    if patch.report is not UNSET:
        embedded["Report"] = json.dumps(patch.report, ensure_ascii=False)
    if patch.source_version is not UNSET:
        embedded["SourceVersion"] = patch.source_version
    if patch.imported_at is not UNSET:
        embedded["ImportedAt"] = patch.imported_at
    if embedded:
        data["Embedded"] = embedded
    if patch.channel is not UNSET:
        data.setdefault("Update", {})["Channel"] = patch.channel
    return data


class BuiltinConfigOwner:
    """宿主托管表里某一种确切类型的托管的属主入口。"""

    owner_protocol = OWNER_PROTOCOL

    def __init__(
        self,
        name: str,
        config_type: Callable[[], type],
        *,
        host: Callable[[], Any] = _host_config,
    ) -> None:
        self.name = name
        self._config_type = config_type
        self._host = host
        self._tickets: dict[str, tuple[str, Any]] = {}

    def _mine(self, config: Any) -> bool:
        return type(config) is self._config_type()

    def _lookup(self, script_id: str) -> tuple[str, Any] | ReadResult:
        try:
            uid = uuid.UUID(str(script_id))
        except ValueError as exc:
            return ReadResult("invalid_id", detail=str(exc))
        try:
            config = self._host().ScriptConfig[uid]
        except KeyError as exc:
            return ReadResult("missing", detail=str(exc))
        except ValueError as exc:
            return ReadResult("invalid_id", detail=str(exc))
        if not self._mine(config):
            return ReadResult("not_mine")
        return str(uid), config

    # -- 读 -----------------------------------------------------------------

    def list_managed(self) -> OwnerListing:
        host = self._host()
        ready = bool(host.script_config_loaded_intact())
        items = tuple(
            _record(str(uid), config, order)
            for order, (uid, config) in enumerate(host.ScriptConfig.items())
            if self._mine(config)
        )
        return OwnerListing(ready=ready, items=items)

    def read_managed(self, script_id: str) -> ReadResult:
        found = self._lookup(script_id)
        if isinstance(found, ReadResult):
            return found
        uid, config = found
        order = next(
            (
                index
                for index, key in enumerate(self._host().ScriptConfig.keys())
                if str(key) == uid
            ),
            0,
        )
        return ReadResult("mine", record=_record(uid, config, order))

    def check_source_path(self, script_id: str, path: str) -> PathCheck:
        found = self._lookup(script_id)
        if isinstance(found, ReadResult):
            return PathCheck("error", found.detail or "托管不存在")
        _uid, config = found
        try:
            validated = type(config.Info).model_validate({"Path": path})
        # 路径里的符号链接成环时，Python 3.12 的 Path.resolve 抛 RuntimeError
        except (ValueError, RuntimeError) as exc:
            return PathCheck("error", str(exc))
        if validated.Path is None:
            return PathCheck("cleared")
        return PathCheck("ok")

    # -- 写 -----------------------------------------------------------------

    async def lock_managed(self, script_id: str) -> str | None:
        found = self._lookup(script_id)
        if isinstance(found, ReadResult):
            return None
        uid, config = found
        ticket = await config.try_lock_x()
        if ticket is None:
            return None
        ticket_id = uuid.uuid4().hex
        self._tickets[ticket_id] = (uid, ticket)
        return ticket_id

    async def unlock_managed(self, script_id: str, ticket_id: str) -> None:
        uid, ticket = self._tickets.pop(ticket_id)
        if uid != str(uuid.UUID(str(script_id))):
            raise ValueError("导入锁票据与托管不符")
        await self._host().ScriptConfig[uuid.UUID(uid)].unlock(ticket)

    async def write_record(
        self, script_id: str, patch: RecordPatch, *, ticket: str | None = None
    ) -> WriteResult:
        data = _patch_data(patch)
        if ticket is not None:
            # 调用方持着这个托管的 X 票：直接提交原节点；Config.update_script 的外部编辑入口
            # 会拒绝一切已锁节点，不能用于持票的内部写回。
            uid, _ticket = self._tickets[ticket]
            if uid != str(uuid.UUID(str(script_id))):
                raise ValueError("导入锁票据与托管不符")
            config = self._host().ScriptConfig[uuid.UUID(uid)]
            await config.update(type(config).model_validate(data))
            return WriteResult(True)
        found = self._lookup(script_id)
        if isinstance(found, ReadResult):
            if found.status == "missing":
                return WriteResult(False, "not_found", found.detail)
            return WriteResult(False, "rejected", found.detail or "托管不归这个属主")
        try:
            # 托管 id 原样交给宿主（它会记进日志）
            await self._host().update_script(str(script_id), data)
        except RuntimeError as exc:
            return WriteResult(False, "rejected", str(exc))
        except KeyError as exc:
            return WriteResult(False, "not_found", str(exc))
        return WriteResult(True)


__all__ = ["BuiltinConfigOwner"]
