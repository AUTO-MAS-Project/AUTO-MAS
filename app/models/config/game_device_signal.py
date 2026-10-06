"""游戏设备删除：各游戏 ``devices`` 集合 remove → 统一信号。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from uuid import UUID

from blinker import Signal

from app.config.core.collection import ConfigCollection
from app.config.signals import CollectionChangeEvent
from app.models.config.game import GameDeviceEntry, GameEntry


@dataclass(frozen=True)
class GameDeviceRemoved:
    """某游戏下一条设备配置被移除。"""

    game_id: UUID
    device_id: UUID


# 统一设备删除信号：订阅方不必逐游戏订 devices.remove
game_device_removed: Signal = Signal("game_device_removed")


async def _dispatch_removed(event: GameDeviceRemoved) -> None:
    for _receiver, result in game_device_removed.send(None, event=event):
        if inspect.isawaitable(result):
            await result


async def _forward_devices_remove(sender: object, event: object) -> None:
    if getattr(event, "kind", None) != "remove":
        return
    if not isinstance(sender, ConfigCollection):
        return
    device_id = getattr(event, "uid", None)
    if not isinstance(device_id, UUID):
        return
    entry = getattr(event, "entry", None)
    if entry is not None and not isinstance(entry, GameDeviceEntry):
        return
    game = sender.parent
    if not isinstance(game, GameEntry):
        return
    await _dispatch_removed(GameDeviceRemoved(game_id=game.uid, device_id=device_id))


def bind_game_devices_remove_signal(game: GameEntry) -> None:
    """把 ``game.devices`` 的 runtime remove 转发到 ``game_device_removed``。"""
    devices = game.devices
    type(devices)._connect_impl(
        _forward_devices_remove,
        phase="runtime",
        kind="remove",
        group=None,
        field=None,
        sender=devices,
    )
