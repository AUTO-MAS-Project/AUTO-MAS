"""MuMu 管理实例：门控 1Hz 刷新 + 单执行器（适配器内样例，不进 base）。

``info`` 官方 JSON 原样写入设备 ``_raw``；通行面读虚拟字段。
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Awaitable
from contextlib import suppress
from pathlib import Path
from typing import Any, TypeVar, cast
from uuid import UUID

import psutil

from auto_mas_core import (
    DeviceStatus,
    EmulatorControl,
    EmulatorExpect,
    LockTicket,
)
from auto_mas_core.utils import ProcessResult, ProcessRunner, get_logger

from .config import MuMuDevice, MuMuGame
from .constants import (
    FORCE_KILL_KEYWORDS,
    STORE_PACKAGE,
    _BUSY_INTERVAL,
    _FOREGROUND_MARKERS,
    _RESOLUTION_MODE_KEY,
    _SPLASH_ADS_PATHS,
    _STORE_OVERLAY_OP,
    _SYNC_INTERVAL,
    _WINDOW_SEC,
    _WRITE_KEYS,
)

logger = get_logger("MuMu模拟器")

# execute 的返回值类型：create_instance 要它把新 uid 带回来
T = TypeVar("T")


class MuMuControl(EmulatorControl):
    """MuMu：门控 sync（闲时 1Hz、忙时提速）+ 控制器级单 job。"""

    def __init__(self, config: MuMuGame | None = None) -> None:
        super().__init__(config=config)
        self._touched_at: float = 0.0
        # 节拍器：等待期间阻塞，每轮同步完成放行一次。等一下它即保证读到的是新数据。
        # 只在「窗内或 busy」的那几轮放行 —— 操作函数都在 ``execute`` 下跑，
        # 那时 busy 必为真、循环必同步，故等不到挂住。
        # 凡等 ``devices`` / ``_raw`` 上的值变（状态、可见性、增删实例）一律等它：
        # 干睡一拍未必等来新数据，白跑一轮。自己去取信息的（问窗口 API、跑
        # dumpsys、枚举进程）才用 ``asyncio.sleep`` —— 那与同步节奏无关。
        self._synced = asyncio.Event()
        self._job: asyncio.Task[Any] | None = None
        # 构造常在配置事务内（add / 启用），继承其上下文会让同步写进永不提交的暂存视图
        self._timer = asyncio.get_running_loop().create_task(
            self._loop(), context=contextvars.Context()
        )

    @property
    def config(self) -> MuMuGame:
        entry = super().config
        if not isinstance(entry, MuMuGame):
            raise TypeError("配置不是 MuMuGame")
        return entry

    # ── 执行器：控制器级单 job ──

    @property
    def busy(self) -> bool:
        job = self._job
        return job is not None and not job.done()

    async def execute(self, aw: Awaitable[T]) -> T:
        """唯一执行器：已有未完成 job 则上抛。

        实现之间互相调用直接走 ``_`` 方法（如 ``_open`` 调 ``_launch_app``），
        不从这里绕第二圈 —— 故这里无需给「自己 job 内的嵌套」开口子。
        """
        if self.busy:
            if asyncio.iscoroutine(aw):
                aw.close()
            raise RuntimeError("操作进行中")
        job = asyncio.ensure_future(aw)
        self._job = job
        try:
            return await job
        finally:
            self._job = None

    async def _run(
        self, *args: str | int, timeout: float | None = None
    ) -> ProcessResult:
        path = self.config.info.path
        if path is None:
            raise FileNotFoundError("MuMuManager.exe 未设置")
        return await ProcessRunner.run_process(
            path,
            *[str(a) for a in args],
            timeout=timeout if timeout is not None else self.config.info.max_wait_time,
            if_merge_std=True,
            breakaway=True,
        )

    # ── 门控刷新：闲时 1Hz、忙时提速 ──

    async def _loop(self) -> None:
        """唯一的刷新出口：忙时少等、闲时多等，每轮同步完成敲一下节拍器。

        操作函数不自己 sync —— 它们只读 ``devices`` 上的状态、等到期待值为止，
        故这里的间隔就是它们的时延下限：``busy`` 期间缩短让等待尽快收敛。
        取数失败也放行：那是下游等待逻辑该兜的事，不是把调用方永久挂住的理由。
        """
        while True:
            self._synced.clear()
            await asyncio.sleep(_BUSY_INTERVAL if self.busy else _SYNC_INTERVAL)
            # busy 或公开 refresh 后的 10min 窗口内才 sync
            if self.busy or time.monotonic() - self._touched_at <= _WINDOW_SEC:
                try:
                    await self._sync_devices()
                    self._synced.set()
                except Exception as e:
                    logger.warning(f"MuMu 周期同步失败: {e}")

    async def _sync_devices(self) -> None:
        """``info -v all`` → 增删 devices、挂 ``_raw``、对齐顺序。

        官方 ``all`` 以实例 index 为键、行内 ``index`` 与键一致，故直接以键为身份，
        不再逐行校验类型或回写 index。
        """
        if self.config.info.path is None:
            logger.debug("MuMuManager.exe 未设置，跳过 sync")
            return
        result = await self._run("info", "-v", "all")
        if result.returncode != 0:
            raise RuntimeError(f"info 失败: {result.stdout.strip()}")
        rows = cast(dict[str, Any], json.loads(result.stdout))
        by_index = {dev.info.index: dev for dev in self.config.devices.values()}
        # 补缺
        for idx in rows:
            if idx not in by_index:
                uid = self.config.devices.add(
                    MuMuDevice, payload={"info": {"index": idx}}
                )
                await self.config.devices.commit()
                by_index[idx] = self.config.devices[uid]
        # 删多
        for idx in by_index:
            if idx not in rows:
                self.config.devices.remove(by_index.pop(idx).uid)
        # CLI 行原样挂上，不落盘、不整理
        for idx, dev in by_index.items():
            dev._raw = rows[idx]
        # 顺序对齐官方列表, 无变化不 stage
        order = [by_index[idx].uid for idx in rows]
        if order != list(self.config.devices.keys()):
            self.config.devices.set_order(order)
        await self.config.devices.commit()

    async def refresh(self) -> None:
        """公开刷新：打开 10min 窗口"""
        self._touched_at = time.monotonic()

    # ── 通行面薄入口：校凭据 → 交执行器；实现全在下面 ──

    async def open(
        self, device_uid: UUID, package: str | None = None, *, ticket: LockTicket
    ) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._open(device_uid, package))

    async def close(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._close(device_uid))

    async def show(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._set_visible(device_uid, True))

    async def hide(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._set_visible(device_uid, False))

    async def minimize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._window_state(device_uid, minimized=True))

    async def maximize(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._window_state(device_uid, minimized=False))

    async def launch_app(
        self, device_uid: UUID, package: str, *, ticket: LockTicket
    ) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._launch_app(device_uid, package))

    async def open_store(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        await self.launch_app(device_uid, STORE_PACKAGE, ticket=ticket)

    async def create_instance(self, name: str | None = None) -> UUID:
        return await self.execute(self._create(name))

    async def delete_instance(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._delete(device_uid))

    async def install_app(
        self, device_uid: UUID, path: Path, *, ticket: LockTicket
    ) -> None:
        self.check_subscription(device_uid, ticket)
        await self.execute(self._install(device_uid, path))

    # ── 品牌钩子：订阅备份 / 退订还原 / 去广告开关 ──

    async def _on_device_subscribed(
        self, device_uid: UUID, expect: object | None
    ) -> None:
        """订阅实例：备份 ``-aw`` 原状，写稳定项与任务要求的分辨率。

        备份先落盘再写第一笔 —— 否则中间崩溃就永久丢了原值。
        订阅登记与失败撤销由基类管，这里只做品牌侧的备份与写入。
        ``expect`` 为 ``None`` 时只备份：任务没提期望，就没有该改的键。
        """
        if expect is not None and not isinstance(expect, EmulatorExpect):
            raise TypeError(f"expect 须为 EmulatorExpect，收到 {type(expect).__name__}")
        dev = self.config.devices[device_uid]
        idx = dev.info.index

        # ── 备份：-aw 一次拉齐全部可写配置，值原样保留 ──
        try:
            result = await self._run("setting", "-v", idx, "-aw")
            raw = json.loads(result.stdout or "")
        except Exception as e:
            raise RuntimeError(f"实例 {idx} 设置读不出，拒绝订阅: {e}") from e
        if not isinstance(raw, dict) or not raw:
            raise RuntimeError(f"实例 {idx} 设置读不出，拒绝订阅")
        data = {str(k): v for k, v in cast(dict[object, Any], raw).items()}
        dev.session.backup = data
        await dev.commit()

        # expect 为 None：任务不提期望，只备份与还原，一个键都不写
        if expect is None:
            return

        # ── 写入：期望字段 → 官方键，分辨率与稳定项同一套逻辑 ──
        # None 不做要求，该键不出现；元组是容许值表，当前档在表内就不动，
        # 越界写表首；其余按值直写，不看厂商当前是什么。
        writes: dict[str, str] = {}
        for field, key in _WRITE_KEYS.items():
            want = getattr(expect, field)
            if want is None:
                continue
            if isinstance(want, tuple):
                allowed = cast(tuple[str, ...], want)
                if not allowed:
                    continue
                current = str(data.get(key, "")).strip().casefold()
                if current in {v.strip().casefold() for v in allowed}:
                    continue
                writes[key] = allowed[0]
            else:
                writes[key] = str(want).casefold()
        # 单写 .custom 是死的，必须把模式键一起打到 custom。
        # 只这一个门：不写 cpu/内存，就不碰 performance_mode。
        writes[_RESOLUTION_MODE_KEY] = "custom"
        args: list[str | int] = ["setting", "-v", idx]
        for key, value in writes.items():
            args.extend(["-k", key, "-val", value])
        result = await self._run(*args)
        if result.returncode != 0:
            raise RuntimeError(f"写设置失败: {result.stdout}")
        logger.info(f"实例 {idx} 订阅写入: {sorted(writes)}")

    async def _on_device_unsubscribed(self, device_uid: UUID) -> None:
        """计数归零退订：整份写回备份并清空。

        不管实例是否在运行 —— 不替用户关实例；MuMu 的设置下次启动生效。
        逐键 ``-k/-val`` 会在中途失败时留下半改状态，故走官方批量入口
        ``setting -p``：一次调用要么成要么败，文件按官方要求写 UTF-8。
        写回失败则**保留**备份并记警告：那是原值的唯一记录，下次启动清扫再试。
        """
        dev = self.config.devices[device_uid]
        backup: dict[str, Any] = dev.session.backup
        if not backup:
            return
        idx = str(dev.info.index)
        tmp = Path(tempfile.gettempdir()) / f"mumu_restore_{idx}_{os.getpid()}.json"
        try:
            tmp.write_text(
                json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = await self._run("setting", "-v", idx, "-p", str(tmp))
            if result.returncode != 0:
                raise RuntimeError(f"整份写回失败: {result.stdout}")
        except Exception as e:
            logger.warning(f"实例 {idx} 配置还原失败，备份保留待下次清扫: {e}")
            return
        finally:
            with suppress(OSError):
                tmp.unlink()
        dev.session.backup = {}
        await dev.commit()
        logger.info(f"实例 {idx} 配置已还原")

    async def sweep_backups(self) -> None:
        """启动清扫：上次进程没走完退订路径时，凭落盘备份补做还原。"""
        # 进程刚起来，既不 busy 也没开窗口，门控循环不会动；这里要设备表才能干活，
        # 故直接取一次 —— 它不是操作函数，等不到「期待值」。
        await self._sync_devices()
        for dev in self.config.devices.values():
            if not dev.session.backup:
                continue
            try:
                await self._on_device_unsubscribed(dev.uid)
            except Exception as e:
                logger.warning(f"清扫实例 {dev.info.index} 残留备份失败: {e}")

    async def set_block_ad(self, enabled: bool) -> None:
        """开关切换时由 ``GameManager`` 下发：宿主机侧开屏图缓存目录占位。

        开着：目录整个删掉、原地放一个同名空文件，MuMu 就写不进缓存图。
        关着：只删我们放的那个空文件，目录留给 MuMu 自己重建。
        与实例运行状态无关，也不需要模拟器在跑 —— 反而必须赶在启动之前落位，
        实例一起来 MuMu 就把图写进去了。故挂开关信号，不挂启动路径。
        纯本地文件活，任何一处失败只记警告，继续处理下一处。
        """
        for ads_path in _SPLASH_ADS_PATHS:
            try:
                if enabled:
                    if ads_path.is_dir():
                        await asyncio.to_thread(shutil.rmtree, ads_path)
                    # 目录不在也要落位：全新安装 / 已被清过时 MuMu 会自己建回来，
                    # 那时图就写进去了。父目录一并建 —— 同非插件版口径。
                    ads_path.parent.mkdir(parents=True, exist_ok=True)
                    ads_path.touch(exist_ok=True)
                elif ads_path.is_file():
                    ads_path.unlink()
            except OSError as e:
                logger.warning(f"设置 MuMu 开屏广告占位失败: {ads_path} - {e}")

    # ── 实现：不自己校凭据、不自己进执行器，只干活 ──

    async def _open(self, device_uid: UUID, package: str | None) -> None:
        from auto_mas_core import Config

        dev = self.config.devices[device_uid]
        idx = dev.info.index
        pkg = (package or "").strip()

        # 启动只是启动：稳定模式与配置备份都在订阅阶段做完了，这里不改配置。
        # 状态定去留，先等节拍器（本函数不自己刷新，见 ``_loop``）
        await self._synced.wait()
        launched = dev.info.status != DeviceStatus.ONLINE

        if launched:
            # ── 仅「尚未启动」可做：拉起实例，外加两件只有启动窗口才有的事 ──
            # 关 NX 壳与静默隐藏都只有实例起来那一下的时机，错过就不再出现，
            # 之后每拍重判纯属空转；故各自独立成任务轮询，触发一次即退出。
            deadline = time.monotonic() + self.config.info.max_wait_time
            # 启动前就有 NX 壳 → 那是用户自己开的，不去关它
            nx_task = (
                asyncio.create_task(self._close_nx_shell(deadline))
                if (await self._nx_hwnd()) is None
                else None
            )
            hide_task = (
                asyncio.create_task(self._hide_when_starting(dev, deadline))
                if Config.setting.function.if_silence
                else None
            )
            try:
                result = await self._run("control", "-v", idx, "launch")
                if result.returncode != 0:
                    raise RuntimeError(f"启动失败: {result.stdout}")
                while time.monotonic() < deadline:
                    if dev.info.status == DeviceStatus.ONLINE:
                        break
                    elif dev.info.status in (DeviceStatus.ERROR, DeviceStatus.UNKNOWN):
                        raise RuntimeError(
                            f"模拟器 {idx} 启动失败, 状态: {dev.info.status} {dev.diagnosis()}"
                        )
                    await self._synced.wait()
                else:
                    raise RuntimeError(
                        f"模拟器 {idx} 启动超时, 状态: {dev.info.status} {dev.diagnosis()}"
                    )
                # 静默启动的承诺是「返回时窗口已经藏好」，故等它落地才走 ——
                # 它的触发条件（STARTING/ONLINE）不晚于本函数的退出条件，最多一拍；
                # 自带 deadline，等不到也会自己退，不会把启动挂住。
                # 不等就会被下面的 cancel 抢在触发之前，窗口白冒出来。
                if hide_task is not None:
                    with suppress(Exception):
                        await hide_task
            finally:
                # NX 壳可能整局都不露面，等不得；到此为止，别拖到下一次启动。
                # 取消后收一次：否则任务里的异常会留成「从未取回」的告警
                side = [t for t in (nx_task, hide_task) if t is not None]
                for task in side:
                    task.cancel()
                await asyncio.gather(*side, return_exceptions=True)

        # ── 以下与「刚拉起来」还是「本来就在跑」无关，两条路都要走 ──
        if Config.setting.function.if_block_ad:
            # 实例侧去广告：拦悬浮窗权限 + 掐掉商店进程，得等设备在线才做得了。
            # 两步都是尽力而为 —— 失败只记警告，不拦启动。
            # 宿主机侧的开屏图占位不在这里：那是启动前的文件活，见 set_block_ad。
            try:
                result = await self._run(
                    "adb", "-v", idx, "shell", "appops", "set", STORE_PACKAGE,
                    _STORE_OVERLAY_OP, "deny", timeout=10, # fmt: skip
                )
            except Exception as e:
                logger.warning(f"屏蔽 MuMu 应用商店悬浮广告失败: {e}")
            else:
                if result.returncode == 0:
                    logger.info("已屏蔽 MuMu 应用商店悬浮广告")
                else:
                    logger.warning(
                        f"屏蔽 MuMu 应用商店悬浮广告失败: {result.stdout.strip()}"
                    )
            try:
                result = await self._run(
                    "adb", "-v", idx, "shell", "am", "force-stop",
                    STORE_PACKAGE, timeout=10, # fmt: skip
                )
            except Exception as e:
                logger.warning(f"停止 MuMu 应用商店广告进程失败: {e}")
            else:
                if result.returncode == 0:
                    logger.info("已停止 MuMu 应用商店广告进程")
                else:
                    logger.warning(
                        f"停止 MuMu 应用商店广告进程失败: {result.stdout.strip()}"
                    )

        if pkg:
            # 拉应用只有 ``_launch_app`` 一份实现，这里直接调它：凭据在 ``open``
            # 入口已校过，执行器也已是本函数占着，不必再绕一圈公开面。
            # 拉不起不算启动失败 —— 模拟器已在线，应用可以让任务自己再试。
            with suppress(Exception):
                await self._launch_app(device_uid, pkg)
        if launched:
            # 刚起来的实例缓一口气：系统服务还在起，立刻交给任务会撞上卡顿。
            # 带包名时等得更久 —— 应用自身也要加载。
            await asyncio.sleep(
                30 if pkg or self.config.info.max_wait_time >= 300 else 3
            )

    async def _close(self, device_uid: UUID) -> None:
        dev = self.config.devices[device_uid]
        idx = str(dev.info.index)
        # 状态定去留，先等节拍器（本函数不自己刷新，见 ``_loop``）
        await self._synced.wait()
        try:
            if dev.info.status not in (DeviceStatus.ONLINE, DeviceStatus.STARTING):
                logger.warning(f"设备 {idx} 未在线，当前状态: {dev.info.status}")
                return
            result = await self._run("control", "-v", idx, "shutdown")
            if result.returncode != 0:
                raise RuntimeError(f"关闭失败: {result.stdout}")
            deadline = time.monotonic() + self.config.info.max_wait_time
            while time.monotonic() < deadline:
                # 同上：Virtual 不受「已是 ONLINE/STARTING」分支收窄
                status = cast(DeviceStatus | None, dev.info.status)
                if status == DeviceStatus.OFFLINE:
                    break
                elif status in (DeviceStatus.ERROR, DeviceStatus.UNKNOWN):
                    raise RuntimeError(f"模拟器 {idx} 关闭失败, 状态: {status}")
                await self._synced.wait()
            else:
                raise RuntimeError(f"模拟器 {idx} 关闭超时, 状态: {dev.info.status}")
            # 关闭不改配置：还原在退订实例时整份做
        finally:
            # ── 强杀残留：shutdown 返回了但 NX 进程树常留着，下次启动会撞上 ──
            # 按名字/路径关键字认进程，连子进程一起收；认不出来的一个都不碰。
            if self.config.info.force_kill:
                killed = 0
                for proc in psutil.process_iter(["pid", "name", "exe"]):
                    try:
                        info = proc.info
                        blob = f"{info.get('name') or ''} {info.get('exe') or ''}"
                        if not any(k in blob.lower() for k in FORCE_KILL_KEYWORDS):
                            continue
                        for child in proc.children(recursive=True):
                            with suppress(
                                psutil.NoSuchProcess, psutil.AccessDenied, OSError
                            ):
                                child.kill()
                                killed += 1
                        with suppress(psutil.NoSuchProcess):
                            proc.kill()
                            killed += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
                        logger.warning(f"强力清理 MuMu 残留进程失败: {e}")
                if killed:
                    logger.info(f"MuMu 残留进程清理完成，共结束 {killed} 个进程")

    async def _set_visible(self, device_uid: UUID, visible: bool) -> None:
        dev = self.config.devices[device_uid]
        idx = str(dev.info.index)
        cmd = "show_window" if visible else "hide_window"
        result = await self._run("control", "-v", idx, cmd)
        if result.returncode != 0:
            raise RuntimeError(f"{cmd} 失败: {result.stdout}")
        deadline = time.monotonic() + float(self.config.info.max_wait_time)
        while time.monotonic() < deadline:
            if dev.data.window_visible is visible:
                return
            # 等的是同步刷出来的可见性，故等节拍器而非干睡
            await self._synced.wait()
        logger.warning(f"设备 {idx} {cmd} 后可见性未达预期: {dev.data.window_visible}")

    async def _window_state(self, device_uid: UUID, *, minimized: bool) -> None:
        """最小化 / 最大化：官方 CLI 只有 show_window / hide_window 两档，
        没有最小化与最大化，故直接对主窗句柄下 ``ShowWindow``。

        句柄取 ``data.main_wnd``（官方 info 原文，十六进制），**不按 pid 搜窗** ——
        同 ``data.window_visible`` 的口径：认不出来就报错，不去猜哪个窗是它的。
        显隐仍走官方 CLI（``_set_visible``）：那是 MuMu 自己的托盘语义，
        跟窗口的最小化 / 最大化不是一回事。
        """
        if sys.platform != "win32":
            raise RuntimeError("最小化 / 最大化仅 Windows 可用")
        import win32con
        import win32gui

        dev = self.config.devices[device_uid]
        wnd = dev.data.main_wnd
        try:
            hwnd = int(str(wnd), 16)
        except ValueError:
            raise RuntimeError(f"设备 {dev.info.index} 无主窗句柄: {wnd!r}") from None
        if not win32gui.IsWindow(hwnd):
            raise RuntimeError(f"设备 {dev.info.index} 主窗句柄已失效: {wnd}")

        await asyncio.to_thread(
            win32gui.ShowWindow,
            hwnd,
            win32con.SW_MINIMIZE if minimized else win32con.SW_MAXIMIZE,
        )
        # 跨进程 ShowWindow 是投递消息后即返回，故给对方一小段时间处理。
        # 验的是 placement 里的 showCmd 而非 IsIconic：后者的反面只是「没最小化」，
        # 普通窗口也满足，最大化会被误判成成功。``IsZoomed`` pywin32 未导出。
        want = win32con.SW_SHOWMINIMIZED if minimized else win32con.SW_SHOWMAXIMIZED
        # 窗口状态直接问系统，不经 devices，故干睡即可（不必等节拍器）
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if win32gui.GetWindowPlacement(hwnd)[1] == want:
                return
            await asyncio.sleep(_BUSY_INTERVAL)
        label = "最小化" if minimized else "最大化"
        logger.warning(f"设备 {dev.info.index} {label}后窗口状态未达预期")

    async def _launch_app(self, device_uid: UUID, package: str) -> None:
        """拉应用：官方 ``app launch`` 为主、``monkey`` 兼底，最后以前台为准。

        启动带包名时 ``_open`` 也转过来 —— 「把应用弄到前台」只该有一份实现。
        每一步失败都只记警告：官方接口报什么不算数，前台里真出现了才算。
        """
        idx = self.config.devices[device_uid].info.index
        prefix = f"{package}/"

        async def wait_fg() -> bool:
            """轮询 dumpsys 判该包是否已在前台：前台标记行里同时出现包名才算。"""
            for attempt in range(6):
                try:
                    result = await self._run(
                        "adb", "-v", idx,
                        "shell", "dumpsys", "activity", "activities", # fmt: skip
                    )
                except Exception as e:
                    logger.debug(f"前台检查失败({attempt + 1}/6): {e}")
                else:
                    if result.returncode == 0 and any(
                        prefix in line and any(m in line for m in _FOREGROUND_MARKERS)
                        for line in result.stdout.splitlines()
                    ):
                        return True
                if attempt < 5:
                    await asyncio.sleep(1)
            return False

        try:
            result = await self._run(
                "control", "-v", idx, "app", "info", "-pkg", package
            )
            state = None
            if result.returncode == 0:
                state = str(json.loads(result.stdout)["state"]).strip().lower()
            if state != "running":
                await self._run("control", "-v", idx, "app", "launch", "-pkg", package)
        except Exception as e:
            logger.warning(f"应用补启动失败 {idx} {package}: {e}")

        if await wait_fg():
            return
        with suppress(Exception):
            await self._run("adb", "-v", idx, "shell", "monkey", "-p", package, "1")
        if not await wait_fg():
            logger.warning(f"应用补启动后仍未进前台，继续运行: {idx} {package}")

    async def _create(self, name: str | None) -> UUID:
        """新建多开，返回新设备 uid。

        官方 ``create`` 不告诉你新实例是哪个，故拿前后的 index 集差集认。
        """
        before = {str(d.info.index) for d in self.config.devices.values()}
        result = await self._run("create", "-n", "1")
        if result.returncode != 0:
            raise RuntimeError(f"创建多开失败: {result.stdout}")
        # 新实例由门控循环同步进 devices（此刻 busy，它在加速档），不自己刷新
        deadline = time.monotonic() + float(self.config.info.max_wait_time)
        while time.monotonic() < deadline:
            created = {
                str(d.info.index): d
                for d in self.config.devices.values()
                if str(d.info.index) not in before
            }
            if not created:
                # 新实例要靠同步才进 devices，故等节拍器
                await self._synced.wait()
                continue
            native = min(created, key=lambda x: int(x) if x.isdecimal() else 0)
            if name:
                # 改名只动 _raw 上的显示名，下一拍同步自会带上
                with suppress(Exception):
                    await self._run("rename", "-v", native, "-n", name)
            return created[native].uid
        raise RuntimeError("创建多开后未找到新设备")

    async def _delete(self, device_uid: UUID) -> None:
        dev = self.config.devices[device_uid]
        # 状态定去留，先等节拍器（本函数不自己刷新，见 ``_loop``）
        await self._synced.wait()
        if dev.info.status not in (DeviceStatus.OFFLINE, DeviceStatus.NOT_FOUND):
            raise RuntimeError(f"实例 {dev.info.index} 未关闭，无法删除")
        idx = str(dev.info.index)
        for _ in range(3):
            result = await self._run("delete", "-v", idx)
            if result.returncode != 0:
                raise RuntimeError(f"删除失败: {result.stdout}")
            # 等门控循环把它从 devices 里摘掉；摘不掉就再删一轮
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if all(str(d.info.index) != idx for d in self.config.devices.values()):
                    return
                await self._synced.wait()
        raise RuntimeError(f"删除实例 {idx} 失败：仍在列表中")

    async def _install(self, device_uid: UUID, path: Path) -> None:
        apk = Path(path)
        if not apk.is_file():
            raise FileNotFoundError(f"安装包不存在: {path}")
        idx = str(self.config.devices[device_uid].info.index)
        result = await self._run("adb", "-v", idx, "install", "-r", str(apk))
        if result.returncode != 0:
            raise RuntimeError(f"安装失败: {result.stdout}")

    # ── 启动期一次性副任务：触发一次即退 ──

    async def _nx_hwnd(self) -> int | None:
        """找 NX 主壳窗口（标题 + 宿主进程名；与设备 main_wnd 显隐无关）。

        两处要它：启动前判「壳是不是用户自己开的」，启动后关掉自己开出来的那个。
        故这里只负责找，关窗在 ``_close_nx_shell``。
        """
        if sys.platform != "win32":
            return None
        import win32gui
        import win32process

        found: list[int] = []

        def enum_cb(hwnd: int, _ctx: object) -> bool:
            if found:
                return False
            if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd) != 0:
                return True
            if win32gui.GetWindowText(hwnd) != "MuMu模拟器":
                return True
            with suppress(
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                OSError,
                TypeError,
                ValueError,
            ):
                # pywin32：返回 (tid, pid)；部分 stub 写成 out-list，统一 int()
                tid_pid = win32process.GetWindowThreadProcessId(hwnd)
                pid = int(tid_pid[1] if isinstance(tid_pid, tuple) else tid_pid)
                if psutil.Process(pid).name().lower() == "mumunxmain.exe":
                    found.append(int(hwnd))
                    return False

            return True

        with suppress(Exception):
            await asyncio.to_thread(win32gui.EnumWindows, enum_cb, None)
        return found[0] if found else None

    async def _close_nx_shell(self, deadline: float) -> None:
        """启动期一次性任务：等 NX 主壳冒出来关掉它，关到一次就退出。

        壳只在启动过程中露一次面，之后再找也找不到；故独立成任务自己轮询，
        不挤进 ``_open`` 的等待循环里每拍重判。
        调用方负责确认「启动前没有壳」—— 有的话是用户自己开的，不归我们关。
        """
        while time.monotonic() < deadline:
            hwnd = await self._nx_hwnd()
            if hwnd is not None:
                import win32con
                import win32gui

                try:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except Exception as e:
                    logger.warning(f"关闭 MuMu NX 壳窗口失败: {e}")
                return
            # 壳窗是自己枚举出来的，不走 devices，故干睡
            await asyncio.sleep(_BUSY_INTERVAL)

    async def _hide_when_starting(self, dev: MuMuDevice, deadline: float) -> None:
        """启动期一次性任务：实例一起来就藏窗，藏落了就退出。

        静默启动只需要在窗口冒出来的那一下按住；之后再反复隐藏就是跟用户抢窗口。
        故只在「藏完还确实看得见」时才补一次 —— 窗口比 ``STARTING``
        晚出来时第一下会落空。
        ``ONLINE`` 也认：轮询错过 ``STARTING`` 时补藏一次，好过整局不藏。
        隐藏失败不拦启动 —— 用户看得见窗口，不是启动不来。
        """
        while time.monotonic() < deadline:
            # 起没起、藏没藏都读同步刷出来的值，故整个循环以节拍器为拍
            await self._synced.wait()
            # Virtual 每次重算，循环里每拍都是新值
            if dev.info.status not in (DeviceStatus.STARTING, DeviceStatus.ONLINE):
                continue
            with suppress(Exception):
                await self._run("control", "-v", dev.info.index, "hide_window")
            # 藏完再等一笔新数据才判落没落 —— 上一笔是藏之前的。
            # 读不出可见性也算完：那时手上无句柄可凭（非 Windows / 窗口还没
            # 落到官方 info 里），再藏就是瞎猜。
            await self._synced.wait()
            if not dev.data.window_visible:
                return
