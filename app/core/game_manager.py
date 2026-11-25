"""统一游戏配置、任务订阅与设备插件生命周期。"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast, overload
from uuid import UUID

from app.config.core.node import LockTicket
from app.config.signals import CollectionChangeEvent
from app.config.wire import config_contract
from app.models.config.game import GameDeviceEntry, GameEntry
from app.models.config.game_binding import GameBindingOwner
from app.models.config.plugin_emulator import EmulatorEntry
from app.models.emulator import DeviceUpdateOptions
from app.plugin.base.emulator import EmulatorControl
from app.plugin.base.game import GameAdapterPlugin, GameControl
from app.utils import get_logger

if TYPE_CHECKING:
    from app.task.game import BoundEmulator

logger = get_logger("游戏管理")


class _GameRuntime:
    @property
    def resource_path(self) -> Path:
        from app.core import Config

        return Config.resource_path

    @property
    def update_options(self) -> DeviceUpdateOptions:
        from app.config import EncryptedValue
        from app.core import Config

        github = Config.setting.Update.Source == "GitHub"
        stored = Config.setting.effective.Update.__dict__.get("MirrorChyanCDK")
        ciphertext = (
            stored.ciphertext().removeprefix("DPAPI:").strip()
            if isinstance(stored, EncryptedValue)
            else ""
        )
        return DeviceUpdateOptions(
            source="github" if github else "mirrorchyan",
            automas_version=Config.VERSION,
            cdk_dpapi="" if github else ciphertext,
        )

    @property
    def process_environment(self) -> dict[str, str] | None:
        from app.core import Config
        from app.utils.common.proxy_env import proxy_environment

        return proxy_environment(Config.proxy)

    @property
    def silent(self) -> bool:
        """读取宿主当前静默设置，供游戏控制实例遵循统一的窗口显示策略。"""
        from app.core import Config

        return Config.setting.Function.IfSilence

    @property
    def block_ad(self) -> bool:
        """读取宿主当前广告拦截设置，供游戏控制实例决定是否启用拦截。"""
        from app.core import Config

        return Config.setting.Function.IfBlockAd


class _SerialGate:
    """进程内全局 FIFO 闸门：同一时刻至多一个不支持并行的游戏处于订阅中。

    与配置 S/X 锁正交。等待可取消：排队中的等待者被取消则从队列摘掉；
    已放行后取消由调用方 ``release``（``unsubscribe`` 路径）。
    """

    def __init__(self) -> None:
        """初始化游戏订阅的串行准入状态和先进先出等待队列。"""
        self._busy = False
        self._waiters: deque[asyncio.Event] = deque()

    async def acquire(self) -> None:
        """按排队顺序取得串行准入资格，取消等待时移除自身或将已取得的资格交给下一位。"""
        if not self._busy and not self._waiters:
            self._busy = True
            return
        ev = asyncio.Event()
        self._waiters.append(ev)
        try:
            await ev.wait()
        except asyncio.CancelledError:
            if ev in self._waiters:
                self._waiters.remove(ev)
            elif ev.is_set():
                # 已出队放行后、wait 返回前被取消：视为持有，交还以免堵死
                self.release()
            raise

    def release(self) -> None:
        """将准入资格交给下一位等待者，无等待者时将串行门恢复为空闲。"""
        if self._waiters:
            self._waiters.popleft().set()
        else:
            self._busy = False


class _GameManager:
    """对外提供订阅、搜索；add 挂载由 Config 对 GameConfig 实例级 connect 本类方法。"""

    def __init__(self) -> None:
        """初始化发现结果、设备订阅、释放锁及串行准入记录。"""
        self._found: dict[UUID, Any] = {}
        self._subs: dict[LockTicket, GameEntry] = {}
        self._release_locks: dict[LockTicket, asyncio.Lock] = {}
        self._gate = _SerialGate()
        self._gate_tokens: set[UUID] = set()

    async def get_emulator_instance(self, uid: UUID | str) -> BoundEmulator | None:
        """[兼容旧专项] 借用 L2 当前设备，资源归属及账号覆盖由会话统一决定。"""
        from app.task.game import current_emulator

        return current_emulator()

    @staticmethod
    def existing_installation(
        entry: GameEntry, *, exclude: UUID | None = None
    ) -> GameEntry | None:
        """发现及手动登记共用真实路径身份，避免升级后的安装再次导入。"""
        from app.core import Config

        path = getattr(entry.info, "path", None)
        if path is None:
            return None
        identity = os.path.normcase(str(Path(path).resolve()))
        for other in Config.GameConfig.values():
            other_path = getattr(other.info, "path", None)
            if (
                other.uid != exclude
                and type(other).__name__ == type(entry).__name__
                and other_path is not None
                and os.path.normcase(str(Path(other_path).resolve())) == identity
            ):
                return other
        return None

    async def create(self, type_key: str, data: dict) -> UUID:
        from app.core import Config, Plugin

        declaration = next(
            (
                Plugin.game_types[r.uid]
                for r in Plugin.list_plugins()
                if r.uid in Plugin.game_types
                and (plugin_class := r._plugin_cls) is not None
                and issubclass(plugin_class, GameAdapterPlugin)
                and plugin_class.game_type_key == type_key
            ),
            None,
        )
        if declaration is None:
            raise ValueError("游戏适配插件未启用")
        payload = (
            config_contract(declaration.game_class, mode="input", extra="forbid")
            .model_validate(data)
            .model_dump(exclude_unset=True)
        )
        candidate = declaration.game_class.model_validate(payload)
        if (
            data.get("info", {}).get("path")
            and getattr(candidate.info, "path", None) is None
        ):
            raise ValueError("游戏程序或安装路径无效")
        if self.existing_installation(candidate) is not None:
            raise ValueError("该安装路径已存在，请使用已有游戏目标")
        uid = Config.GameConfig.add(declaration.game_class, payload=payload)
        await Config.GameConfig.commit()
        return uid

    async def update(self, uid: UUID, data: dict) -> None:
        from app.core import Config

        entry = Config.GameConfig[uid]
        payload = (
            config_contract(type(entry), mode="input", extra="forbid")
            .model_validate(data)
            .model_dump(exclude_unset=True)
        )
        candidate = type(entry).model_validate(payload)
        if (
            data.get("info", {}).get("path")
            and getattr(candidate.info, "path", None) is None
        ):
            raise ValueError("游戏程序或安装路径无效")
        if self.existing_installation(candidate, exclude=uid) is not None:
            raise ValueError("该安装路径已存在，请使用已有游戏目标")
        if entry.actions_busy:
            raise ValueError("游戏目标正在使用，不能修改安装配置")
        ticket = await entry.try_lock_x(cascade=False)
        if ticket is None:
            raise ValueError("游戏目标正在使用，不能修改安装配置")
        try:
            await entry.update(candidate)
            if payload.get("info", {}).keys() - {"name", "concurrent_execution"}:
                control = entry._control
                try:
                    await control.teardown()
                finally:
                    self.create_control(config=entry, control_class=type(control))
        finally:
            await entry.unlock(ticket)

    async def startup_maintenance(self) -> None:
        from app.core import Config

        for entry in Config.GameConfig.values():
            try:
                await entry._control.startup()
            except Exception as error:
                logger.warning(f"设备维护恢复失败，保留材料供下次尝试：{error}")

    async def close_devices(self, *, kind: str | None = None) -> None:
        from app.core import Config

        async def close_installation(control: EmulatorControl) -> None:
            try:
                await asyncio.wait_for(control.close_all(), timeout=30)
            except Exception as error:
                logger.warning(f"关闭模拟器安装失败，继续其他设备收尾：{error}")

        await asyncio.gather(
            *(
                close_installation(entry._control)
                for entry in Config.GameConfig.values()
                if isinstance(entry._control, EmulatorControl)
                and (kind is None or entry._control.kind == kind)
            )
        )

    async def validate_binding(
        self, script_id: str, patch: dict, *, owner=None, script=None
    ) -> str | None:
        from app.core import Config
        from app.core.plugin import Plugin
        from app.models.config.plugin_script import ScriptEntry

        if script is None:
            script = Config.ScriptConfig[script_id]
        binding = patch.get("game", {})
        uid = binding.get("game_id", (owner or script).game.game_id)
        if uid == "-" and owner is not None:
            uid = script.game.game_id
        if uid == "-":
            return None
        game = Config.GameConfig.get(UUID(str(uid)))
        if game is None:
            return "所选游戏目标不存在"
        if isinstance(script, ScriptEntry):
            declaration = next(
                d for d in Plugin.script_types.values() if type(script) is d.script_type
            )
            kinds = declaration.game_kinds
        else:
            kinds = Config.script_game_kinds(script, patch)
        if kinds and game.info.type not in kinds:
            return "所选游戏目标类型与当前专项控制方式不兼容"
        if (
            isinstance(game._control, EmulatorControl)
            and game._control.kind == "avd"
            and not Config.script_supports_mod_avd(script)
        ):
            return "当前专项不支持 ModAVD"
        return None

    async def update_device(self, uid: UUID, device_uid: UUID, data: dict) -> None:
        from app.core import Config

        entry = Config.GameConfig[uid]
        if data.keys() - {"action"} and (
            entry.actions_busy or entry._control.device_usage(device_uid) is not None
        ):
            raise ValueError("设备正在使用，不能修改连接参数")
        device = entry.devices[device_uid]
        payload = (
            config_contract(type(device), mode="input", extra="forbid")
            .model_validate(data)
            .model_dump(exclude_unset=True)
        )
        await device.update(type(device).model_validate(payload))

    async def write_settings(
        self,
        uid: UUID,
        device_uid: UUID,
        changes: dict[str, int],
        expected: dict[str, int | None] | None,
    ) -> None:
        from app.core import Config
        from app.models.config.game import TRIGGER_TICKET

        entry = Config.GameConfig[uid]
        if not isinstance(entry._control, EmulatorControl):
            raise ValueError("客户端不提供模拟器实例设置")
        if entry.actions_busy:
            raise ValueError("游戏目标正在使用，不能修改实例设置")
        ticket = await entry.try_lock_x(cascade=False)
        if ticket is None:
            raise ValueError("游戏目标正在使用，不能修改实例设置")
        try:
            await entry._control.save_settings(
                device_uid, changes, expected, ticket=TRIGGER_TICKET
            )
        finally:
            await entry.unlock(ticket)

    async def configure_devices(
        self,
        uid: UUID,
        action: Literal["settings", "stable_mode", "capture"],
        *,
        devices: list[UUID] | None = None,
        changes: dict[str, int] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """同一安装下逐台操作，单台失败交回结果，其余实例继续。"""
        from app.core import Config
        from app.models.config.game import TRIGGER_TICKET

        entry = Config.GameConfig[uid]
        if not isinstance(entry._control, EmulatorControl):
            raise ValueError("此目标不提供模拟器配置维护")
        control = entry._control
        if entry.actions_busy:
            raise ValueError("游戏目标正在使用，不能修改实例设置")
        ticket = await entry.try_lock_x(cascade=False)
        if ticket is None:
            raise ValueError("游戏目标正在使用，不能修改实例设置")
        try:
            await control.refresh()
            selected = devices if devices is not None else list(entry.devices.keys())
            result: dict[str, dict[str, Any]] = {}
            for device_uid in selected:
                try:
                    device = entry.devices[device_uid]
                    if getattr(device.info, "tombstone", False):
                        continue
                    value: dict[str, Any] | list[str]
                    if action == "settings":
                        assert changes is not None
                        value = (
                            await control.save_settings(
                                device_uid, changes, None, ticket=TRIGGER_TICKET
                            )
                        ).to_dict()
                    elif action == "stable_mode":
                        value = await control.apply_stable_mode(
                            device_uid, ticket=TRIGGER_TICKET
                        )
                    elif action == "capture":
                        value = await control.capture_baseline(
                            device_uid, ticket=TRIGGER_TICKET
                        )
                    else:
                        raise ValueError("未知实例配置操作")
                    result[str(device_uid)] = {"ok": True, "data": value}
                except Exception as error:
                    logger.opt(exception=True).warning(f"实例配置操作失败：{error}")
                    result[str(device_uid)] = {"ok": False, "message": str(error)}
            return result
        finally:
            await entry.unlock(ticket)

    @staticmethod
    async def on_device_removed(sender, *, uid: UUID):
        """实际删除设备后清除共同绑定，墓碑条目仍保留原身份供用户辨认。"""
        from app.core import Config
        from app.models.script_access import script_users

        for script in Config.ScriptConfig.values():
            for item in (script, *script_users(script).values()):
                owner = cast(GameBindingOwner, item)
                if (
                    owner.game.game_id == sender.parent.uid
                    and owner.game.device_id == uid
                ):
                    await owner.update(
                        type(owner).model_validate({"game": {"device_id": "-"}})
                    )

    @staticmethod
    def create_control(
        *, config: GameEntry, control_class: type[GameControl]
    ) -> GameControl:
        """启动激活和重载共用装配入口，策略始终读当前设置。"""
        control = control_class(config=config)
        control.bind_runtime(_GameRuntime())
        config._game_control = control
        return control

    @staticmethod
    async def on_add(sender: object, event: CollectionChangeEvent) -> None:
        """GameConfig 实例级 add / init_add：按已启用声明挂管理实例。

        设备类由游戏配置子类在字段上收窄；此处不再 ``add_type``。
        ``entry`` 缺失或无匹配声明视为异常，上抛以使当次事务失败。
        """
        _ = sender
        if not isinstance(event.entry, GameEntry):
            raise TypeError(f"非 GameEntry: {event.entry}")

        from app.core import Plugin

        for decl in Plugin.game_types.values():
            if isinstance(event.entry, decl.game_class):
                control = _GameManager.create_control(
                    config=event.entry, control_class=decl.control_class
                )
                if event.kind == "add":
                    await control.initialize_devices()
                break
        else:
            raise RuntimeError(f"未找到 {type(event.entry)} 对应的 GameTypeDecl")

    @staticmethod
    async def apply_block_ad(enabled: bool) -> None:
        """全局去广告开关变更 → 逐个游戏下发，各品牌自行决定做不做。

        开关是系统级的，作用面却在各品牌的宿主机侧（缓存目录占位等），故由主入口
        统一扇出，而不是等下一次启动实例时顺带处理 —— 用户关掉开关就该立刻生效。
        单个游戏失败不连累其余：这不是事务，只记警告。
        """
        from app.core import Config

        for entry in Config.GameConfig.values():
            try:
                await entry._control.set_block_ad(enabled)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"游戏 {entry.info.name} 去广告开关下发失败: {e}")

    @overload
    async def subscribe(
        self, uid: UUID, *, kind: Literal["emulator"]
    ) -> tuple[EmulatorControl, LockTicket]:
        """校验目标为模拟器，取得主配置只读锁并返回模拟器控制器与释放票据。"""
        ...

    @overload
    async def subscribe(
        self, uid: UUID, *, kind: Literal["client"]
    ) -> tuple[GameControl[GameEntry, GameDeviceEntry], LockTicket]:
        """校验目标为游戏客户端，取得主配置只读锁并返回控制器与释放票据。"""
        ...

    @overload
    async def subscribe(
        self, uid: UUID, *, kind: None = None
    ) -> tuple[GameControl[GameEntry, GameDeviceEntry], LockTicket]:
        """订阅指定游戏主配置，不限定设备类别，返回控制器及本次订阅的释放票据。"""
        ...

    async def subscribe(
        self, uid: UUID, *, kind: Literal["emulator", "client"] | None = None
    ) -> tuple[GameControl[GameEntry, GameDeviceEntry] | EmulatorControl, LockTicket]:
        """对主配置加不覆盖子节点的只读锁，返回已挂载管理实例与解锁凭证。

        ``kind`` 为 ``emulator`` / ``client`` 时校验 ``info.type`` 与 Control 类型；
        ``kind="emulator"`` 时静态类型收窄为 ``EmulatorControl``。
        """
        from app.core import Config

        entry = Config.GameConfig.get(uid)
        if entry is None:
            raise KeyError(f"游戏不存在: {uid}")

        if kind is not None and entry.info.type != kind:
            raise TypeError(f"游戏 {uid} 类型为 {entry.info.type!r}，期望 {kind!r}")
        if kind == "emulator" and not isinstance(entry, EmulatorEntry):
            raise TypeError(f"游戏 {uid} 不是模拟器配置")

        # ``_control`` 属性：生命周期内必达，未挂载直接上抛
        ctrl = entry._control
        # 不支持并行：先拿全局闸门再订设备（闸门在 subscribe 内、设备在调用方）
        gated = False
        if not entry.info.concurrent_execution:
            await self._gate.acquire()
            gated = True
        try:
            ticket = await entry.lock_s(cascade=False)
        except BaseException:
            if gated:
                self._gate.release()
            raise
        self._subs[ticket] = entry
        self._release_locks[ticket] = asyncio.Lock()
        if gated:
            self._gate_tokens.add(ticket.token)
        return ctrl, ticket

    async def unsubscribe(self, ticket: LockTicket) -> None:
        """尝试还原后解锁；还原异常交给托管收尾，不阻断后续任务。"""
        lock = self._release_locks.get(ticket)
        if lock is None:
            return
        async with lock:
            entry = self._subs.get(ticket)
            if entry is None:
                return
            try:
                try:
                    await entry._control.unsubscribe_all(ticket)
                finally:
                    # 备份与下次重试归插件；配置恢复失败不能长期占用调度资源。
                    await entry.unlock(ticket)
                    del self._subs[ticket]
                    del self._release_locks[ticket]
            finally:
                if ticket.token in self._gate_tokens:
                    self._gate_tokens.discard(ticket.token)
                    self._gate.release()

    async def search(self) -> dict[str, dict[str, Any]]:
        """逐一调用已启用插件声明的 search，暂存未激活实例并返回目录。"""
        from app.core.plugin import Plugin

        found: dict[UUID, Any] = {}
        catalog: dict[str, dict[str, Any]] = {}
        for uid, decl in tuple(Plugin.game_types.items()):
            try:
                rows = await Plugin.search_game_adapter(uid, decl)
            except Exception as error:
                logger.opt(exception=True).warning(
                    f"{decl.game_class.__name__} 发现安装失败：{error}"
                )
                continue
            for entry in rows:
                if type(entry) is not decl.game_class:
                    logger.warning(
                        f"{decl.game_class.__name__} 返回了不属于本适配器的发现结果"
                    )
                    continue
                if self.existing_installation(entry) is not None:
                    continue
                found[entry.uid] = entry
                catalog[str(entry.uid)] = {
                    "name": entry.info.name,
                    "type": entry.info.type,
                    "path": entry.model_dump(context={"audience": "api"})
                    .get("info", {})
                    .get("path"),
                    "concurrent_execution": entry.info.concurrent_execution,
                }
        self._found = found
        return catalog

    async def add_found(self, uid: UUID) -> GameEntry:
        """在一次提交中导入搜索结果及其配置。"""
        from app.core import Config

        if uid not in self._found:
            raise KeyError(f"搜索结果不存在或已过期: {uid}")
        if uid in Config.GameConfig:
            raise ValueError(f"游戏已存在: {uid}")
        found = self._found[uid]
        if not isinstance(found, GameEntry):
            raise TypeError(f"非 GameEntry: {type(found)}")
        if self.existing_installation(found) is not None:
            raise ValueError("该安装路径已存在，请使用已有游戏目标")

        Config.GameConfig.add(
            type(found),
            uid=uid,
            payload=found.model_dump(context={"audience": "persist"}),
        )
        await Config.GameConfig.commit()
        entry = Config.GameConfig[uid]
        self._found.pop(uid)
        return entry


GameManager = _GameManager()
