"""托管持有游戏票据，账号仅借用；恢复异常不改写账号执行结果。"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.models.config.game_binding import GameBindingOwner
from app.plugin.base.emulator import EmulatorControl
from app.plugin.base.game import DeviceSubscribeError
from app.utils import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from app.config import LockTicket
    from app.models.emulator import (
        DeviceInfo,
        DeviceRef,
        DeviceStatus,
        EmulatorAdbInfo,
        HostAdb,
    )
    from app.models.task import TaskScriptItem
    from app.plugin.base.emulator import EmulatorExpect
    from app.plugin.base.game import GameControl

logger = get_logger("游戏会话")

current_game_session: ContextVar[GameSession | None] = ContextVar(
    "game_session", default=None
)


def selected_game_session() -> GameSession | None:
    """已选定的当前会话；会话已建但尚未选定时（旧专项上锁前的检查、维护模式）
    只读查询按配置回落，与会话外一致。"""
    session = current_game_session.get()
    if session is None:
        return None
    if not session.selected:
        logger.debug(f"游戏会话尚未选定，按托管配置读取：{session.script.info.name}")
        return None
    return session


def game_is_emulator(owner: GameBindingOwner) -> bool:
    """控制器选择只把模拟器目标算作 ADB 输入，不把客户端绑定误判为模拟器。"""
    from app.core import Config

    session = selected_game_session()
    if session is not None:
        return isinstance(session.control, EmulatorControl)
    uid = owner.game.game_id
    target = Config.GameConfig.get(uid) if uid != "-" else None
    return target is not None and target.info.type == "emulator"


@dataclass(frozen=True)
class DeviceDetails:
    idx: str
    pid: int


class BoundEmulator:
    """[兼容旧专项] 将已取得的设备票转成存量调用面，不另行占用资源。"""

    def __init__(self, session: GameSession) -> None:
        if (
            not isinstance(session.control, EmulatorControl)
            or session.device_uid is None
        ):
            raise TypeError("本次托管未选择模拟器实例")
        assert session.ticket is not None
        self.control = session.control
        self.ticket = session.ticket
        self.device_uid = str(session.device_uid)

    def _uid(self, index: str | UUID | int) -> UUID:
        if str(index) != self.device_uid:
            raise ValueError("请求的设备与当前账号已订阅设备不一致")
        return UUID(self.device_uid)

    async def open(
        self,
        index: str | UUID | int,
        package_name: str = "",
        *,
        allow_mod_avd: bool = False,
        manual: bool = False,
    ) -> DeviceInfo:
        uid = self._uid(index)
        if self.resolve_device(index).emulator_type == "avd" and not allow_mod_avd:
            raise ValueError("当前专项不支持 ModAVD")
        await self.control.open(uid, package_name or None, ticket=self.ticket)
        return await self.control.device_info(uid)

    async def close(self, index: str | UUID | int) -> DeviceStatus:
        uid = self._uid(index)
        await self.control.close(uid, ticket=self.ticket)
        return (await self.control.device_info(uid)).status

    async def getInfo(
        self, index: str | UUID | int | None = None
    ) -> dict[str, DeviceInfo]:
        uid = UUID(self.device_uid) if index is None else self._uid(index)
        return {str(uid): await self.control.device_info(uid)}

    async def getStatus(self, index: str | UUID | int) -> DeviceStatus:
        return (await self.control.device_info(self._uid(index))).status

    async def setVisible(
        self, index: str | UUID | int, is_visible: bool
    ) -> DeviceStatus:
        uid = self._uid(index)
        operation = self.control.show if is_visible else self.control.hide
        await operation(uid, ticket=self.ticket)
        return (await self.control.device_info(uid)).status

    def get_adb_path(self) -> Path | None:
        return self.control.get_adb_path()

    def resolve_device(self, index: str | UUID | int) -> DeviceRef:
        return self.control.resolve_device(self._uid(index))

    def installation_root(self, index: str | UUID | int) -> Path:
        return self.control.installation_root(self._uid(index))

    async def get_device_info(
        self, index: str | UUID | int
    ) -> dict[str, DeviceDetails]:
        uid = self._uid(index)
        ref = self.control.resolve_device(uid)
        info = await self.control.device_info(uid)
        return {str(uid): DeviceDetails(idx=ref.native_index, pid=info.process_id or 0)}

    async def avd_adb_info(self, index: str | UUID | int) -> EmulatorAdbInfo | None:
        return await self.control.adb_info(self._uid(index))

    async def maafw_adb_extra(self, index: str | UUID | int) -> dict[str, object]:
        return await self.control.maafw_adb_extra(self._uid(index))

    def supports_maafw_adb_extra_version(self, version: str | None) -> bool | None:
        return self.control.supports_maafw_adb_extra_version(version)

    async def host_adb(self, index: str | UUID | int) -> HostAdb | None:
        return await self.control.host_adb(self._uid(index))

    async def process_env(self, index: str | UUID | int) -> dict[str, str] | None:
        return await self.control.process_env(self._uid(index))


class GameSession:
    """L2 持有会话，L3 在账号锁内选择已确认的覆盖目标。"""

    def __init__(
        self,
        script: TaskScriptItem,
        config: GameBindingOwner,
        expect: EmulatorExpect | None = None,
    ):
        self.script = script
        self.config = config
        self.expect = expect
        self.control: GameControl | None = None
        self.ticket: LockTicket | None = None
        self.device_uid: UUID | None = None
        self.game_uid: UUID | None = None
        self.close_emulator_on_release = False
        self.cleanup_failed = False
        self._account_override = False
        # 选定过一次即为真，释放不复位：绑定为「-」或目标非本地客户端时 control 同样为空，
        # 不能拿 control 判断是否已选定。
        self.selected = False

    @property
    def emulator(self) -> BoundEmulator | None:
        return (
            BoundEmulator(self)
            if isinstance(self.control, EmulatorControl) and self.device_uid is not None
            else None
        )

    async def select(self, owner: GameBindingOwner | None = None) -> None:
        from app.core import Config, GameManager

        self.selected = True
        self._account_override = owner is not None and owner.game.game_id != "-"
        binding = (
            owner.game
            if owner is not None and self._account_override
            else self.config.game
        )
        if binding.unavailable_reason:
            raise ValueError(binding.unavailable_reason)
        uid = binding.game_id if binding.game_id != "-" else None
        device_uid = binding.device_id if binding.device_id != "-" else None
        if self.game_uid == uid and self.device_uid == device_uid:
            return
        await self.release()
        if uid is None:
            return
        refusal = await GameManager.validate_binding(
            str(self.config.uid), {"game": {"game_id": uid}}, owner=owner
        )
        if refusal:
            raise ValueError(refusal)
        game_name = Config.GameConfig[uid].info.name
        self.script.current.log += f"等待获取游戏实例「{game_name}」。\n"
        logger.info(f"等待获取游戏实例「{game_name}」")
        await self.script.set_state(status="等待")
        self.control, self.ticket = await GameManager.subscribe(uid)
        self.game_uid = uid
        # 控制器装配后刷新可提供首次离线设备；所选设备不存在则明确失败。
        await self.control.refresh()
        game = Config.GameConfig.get(uid)
        if game is None:
            raise ValueError("所选游戏目标已删除")
        if device_uid is not None:
            device = game.devices.get(device_uid)
            if device is None:
                raise ValueError("所选设备已失效")
            device_name = device.info.name
            last_usage = None
            while True:
                try:
                    await self.control.subscribe_device(
                        self.ticket,
                        device_uid,
                        self.script.info.name,
                        self.expect
                        if isinstance(self.control, EmulatorControl)
                        else None,
                    )
                    break
                except DeviceSubscribeError as error:
                    if error.usage is None:
                        raise
                    if error.usage != last_usage:
                        self.script.current.log += (
                            f"等待获取游戏实例「{game_name}」的设备「{device_name}」，"
                            f"当前占用：{error.usage}。\n"
                        )
                        await self.script.commit()
                        last_usage = error.usage
                    await asyncio.sleep(1)
            self.device_uid = device_uid
        self.script.current.log += f"已获取游戏实例「{game_name}」。\n"
        logger.info(f"已获取游戏实例「{game_name}」")
        await self.script.set_state(status="运行")

    async def release_account(self) -> None:
        if self._account_override:
            await self.release()
            self._account_override = False

    async def release(self) -> None:
        from app.core import GameManager

        if self.ticket is None:
            return
        ticket = self.ticket
        try:
            try:
                if self.close_emulator_on_release and self.emulator is not None:
                    async with asyncio.timeout(30):
                        await self.emulator.close(str(self.device_uid))
            finally:
                self.close_emulator_on_release = False
                await GameManager.unsubscribe(ticket)
        except Exception as error:
            self.cleanup_failed = True
            await self.script.set_log(
                f"设备配置恢复失败，已记录并留待下次尝试：{error}"
            )
            await self.script.set_state(status="异常")
        finally:
            self.ticket = None
            self.control = None
            self.game_uid = None
            self.device_uid = None


def current_emulator() -> BoundEmulator | None:
    session = current_game_session.get()
    if session is None:
        raise RuntimeError("模拟器操作不在已订阅的托管会话内")
    return session.emulator


def game_target_id(owner: GameBindingOwner) -> str:
    """取得当前已锁账号的目标，配置检查阶段读取托管绑定。"""
    session = current_game_session.get()
    return str(
        session.game_uid
        if session is not None and session.game_uid is not None
        else owner.game.game_id
    )


def game_device_id(owner: GameBindingOwner) -> str:
    session = current_game_session.get()
    return str(
        session.device_uid
        if session is not None and session.device_uid is not None
        else owner.game.device_id
    )
