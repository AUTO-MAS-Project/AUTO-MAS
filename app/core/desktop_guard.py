"""保证桌面上始终有真实的显示输出。

所有真实输出都断开时，Windows 不会让桌面消失，而是保留一块占位的**幻影屏**。它照旧
上报一个分辨率（实测甚至会继承上一块屏的模式），`EnumDisplayMonitors` 看起来一切正常，
但那块屏背后没有任何输出：游戏能否正常渲染、截图链路是否可靠都没有保证，DXGI 桌面复制
在这种屏上尤其容易出问题。

冷启动时更糟——没有输出的情况下 Windows 会以一个很小的安全分辨率起来，被托管的 PC 端
游戏窗口跟着被压小，脚本侧的分辨率闸门把整轮任务打掉；游戏还会把这个坏尺寸记进自己的
配置，而自动运行每轮只活几十秒，游戏来不及纠正自己，于是坏值一直留着，之后每天都在
同一处失败。

所以判据不是「桌面够不够大」而是「有没有真实输出」：前者要挑阈值，而且幻影屏报的尺寸
本来就不可信；后者是个二值事实。

设计取舍：

- **跟着显示输出走，不跟着任务边界走。** 后端在跑就一直守着：没有任何真实输出就挂一块
  虚拟屏，真实显示器一回来就把自己那块拆掉。早先是「整轮任务开一次、结束拆一次」，
  于是任务之外的时间桌面仍旧只有一块幻影屏——游戏窗口是在那段时间里被压坏并被游戏
  自己记住的，等下一轮任务开跑才插屏已经晚了。
- **只拆自己挂的那块。** 判「真实显示器回来了」用的是 `real_display_devices()` 里除掉
  自己设备名之后还剩不剩东西，不是「有没有真实输出」——我们自己挂的那块本身就算真实
  输出，拿它当判据会永远认为显示器已经回来。
- **真实显示器一回来就拆，任务在不在跑都一样。** 早先这一档在任务期间推迟到任务结束，
  怕拆屏把正按坐标点的脚本打掉。实际撞上的是另一面：多用户串行队列一跑近两小时，用户
  早上开屏几乎必然落在任务里，而虚拟屏是主显示器，回来的真实屏只是第二块——任务栏和
  所有窗口都留在看不见的那块上，推迟又不写日志，用户只能重启。人坐到机器前比任何一轮
  任务都重要，被打掉的那轮还有重试兜底。
- **判据要连续成立才动手。** 拓扑变更本身带中间态（切模式、驱动重载、KVM 切换、睡眠
  恢复），单次采样为真就插拔会来回抖，而每次插拔都会移动用户已经打开的窗口。
- **用轮询而不是 `WM_DISPLAYCHANGE`。** 收窗口消息要自己开 message-only 窗口和消息泵，
  而两个判据都只是几次 user32 调用，几秒一次的代价可以忽略。
- **进程被强杀会留下孤儿屏，必须主动清理。** 上游文档称停止心跳约 1 秒后虚拟屏会自动
  拔掉，实测不成立（杀掉进程 6 秒后屏仍在）。因此挂屏时把 index 记进状态文件，下次启动
  时若记录还在、而记录里的进程已经死了，就先把那块孤儿拆掉。只拆自己记过的 index——
  同一个驱动可能同时被 Parsec 本体或别的程序使用。
- **只在没有任何真实输出时才插**，显示器正常时绝不凭空多挂一块。实测无头时挂上虚拟屏，
  幻影屏是**被替换**而不是并存，所以桌面上仍然只有一块屏，没有多屏歧义。
- **插完立刻重验**，不满足就拆掉——驱动可能因为被显卡驱动更新搞坏、或与其它虚拟显示
  驱动冲突而「插上了但没生效」。
- **失败之后要退避。** 没装驱动的用户不该每几秒被探测一次，同一条失败原因也只说一遍。
- 任何一步失败都只记日志、照常往下跑：这一层是尽力而为的改善项，不该反过来把本来
  能跑的任务打掉。
"""

import asyncio
import json
import os
import time
from contextlib import suppress
from pathlib import Path

from app.core import Config
from app.utils import get_logger
from app.utils.platform import IS_WINDOWS

logger = get_logger("桌面保障")

# 目标客户区。取脚本侧常见的最低要求：够放下一个 1280x720 的窗口就算够用。
DESKTOP_MIN_CLIENT = (1280, 720)
# 记账文件。落在受保护的 data/ 下，和 MaaFW job 文件同级。
STATE_FILE = Path("data") / "virtual_display.json"

# 轮询间隔（秒）。
POLL_INTERVAL = 5.0
# 拓扑判据要连续成立几次才动手。开关被用户关掉不走这条路，那是明示的意图，立即生效。
CONFIRM_TICKS = 2
# 挂载失败后的静默期（秒）。
FAILURE_BACKOFF = 300.0

# 一次巡检得出的动作。
IDLE = "idle"
ATTACH = "attach"  # 没有真实输出，挂一块
DETACH = "detach"  # 真实显示器回来了，拆掉自己那块
RELEASE = "release"  # 开关被关掉，拆掉自己那块
LOST = "lost"  # 自己那块屏已经不在桌面上，就地认账


_warned: set[str] = set()


def _warn_once(message: str) -> None:
    """同一条巡检期故障只说一遍。

    守卫每几秒跑一次，底层查询若持续失败，不去重会把日志刷爆。
    """

    if message in _warned:
        return
    if len(_warned) > 32:
        _warned.clear()
    _warned.add(message)
    logger.warning(message)


def _write_state(index: int) -> None:
    """记下「本进程挂了哪块屏」。进程被强杀时靠它清理孤儿。"""

    with suppress(Exception):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps({"index": index, "pid": os.getpid()}, ensure_ascii=False),
            encoding="utf-8",
        )


def _clear_state() -> None:
    with suppress(Exception):
        STATE_FILE.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        # 判断不了就当它还活着：宁可留下孤儿，也不要误拆别人的屏。
        return True


def cleanup_orphan_display() -> None:
    """清理上一次进程留下的虚拟屏。

    只拆自己记过的 index，且只在记录里的进程确实已经死了的时候拆——同一个驱动可能同时
    被 Parsec 本体或别的程序使用，按 index 乱拆会拆掉别人的屏。
    """

    try:
        raw = STATE_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except Exception as exc:
        logger.warning(f"读取虚拟显示器记账文件失败: {exc}")
        return

    try:
        state = json.loads(raw)
        index = int(state["index"])
        pid = int(state["pid"])
    except Exception:
        logger.warning("虚拟显示器记账文件无法解析，已丢弃")
        _clear_state()
        return

    if pid == os.getpid() or _pid_alive(pid):
        # 还活着说明不是孤儿——可能是同一台机器上另一个 MAS 实例正在用。
        return

    from app.utils.platform.vdd import remove_display_index

    if remove_display_index(index):
        logger.info(f"已清理上次遗留的虚拟显示器（index={index}, pid={pid}）")
    _clear_state()


def _has_real_output() -> bool:
    """桌面上有没有真实输出。查不到信息时按「有」处理，宁可不插屏也不乱动拓扑。"""

    from app.utils.platform.display import has_real_display

    try:
        return has_real_display()
    except Exception as exc:
        _warn_once(f"查询显示输出失败，按有真实输出处理: {exc}")
        return True


def _real_devices() -> set[str] | None:
    """当前有真实输出的显示设备名。**查询失败返回 None，本轮不做判断。**

    不能回落到空集：挂着屏的时候空集会被 `decide()` 判成「自己那块屏没了」，于是把一块
    好好的屏拆掉再重挂一遍。查不到就什么都别做。
    """

    from app.utils.platform.display import real_display_devices

    try:
        return real_display_devices()
    except Exception as exc:
        _warn_once(f"枚举显示设备失败: {exc}")
        return None


def _desktop_has_room() -> bool:
    """插屏之后用：新挂的屏放不放得下目标窗口。"""

    from app.utils.platform.display import find_host_monitor

    try:
        return find_host_monitor(*DESKTOP_MIN_CLIENT) is not None
    except Exception as exc:
        logger.warning(f"查询显示器失败，按可用处理: {exc}")
        return True


def _describe() -> str:
    from app.utils.platform.display import describe_monitors

    try:
        return describe_monitors()
    except Exception as exc:
        return f"（读取失败: {exc}）"


def parse_mode(text: str) -> tuple[int, int, int]:
    """把配置里的 `1920x1080@60` 解析成 (宽, 高, 刷新率)。

    解析失败时回落到默认模式而不是抛错：这一层不该因为一个配置字符串把任务打掉。
    """

    from app.utils.platform.vdd import DEFAULT_VDD_MODE

    try:
        size, _, refresh = text.partition("@")
        width, _, height = size.partition("x")
        return int(width), int(height), int(refresh)
    except (AttributeError, ValueError):
        logger.warning(f"虚拟显示器模式配置无法解析，按默认处理: {text!r}")
        return DEFAULT_VDD_MODE


def decide(
    *,
    enabled: bool,
    holding: str | None,
    has_real_output: bool,
    real_devices: set[str],
) -> tuple[str, str]:
    """由一次观测决定下一步动作，返回 (动作, 原因)。

    `holding` 是自己挂的那块屏的设备名（`\\\\.\\DISPLAYn`），没挂时为 None。

    拆分成纯函数是因为判据本身才是这一层容易出错的地方：挂上之后自己那块屏也算「真实
    输出」，继续拿 `has_real_output` 当判据会永远认为显示器已经回来，于是插一块拆一块
    地空转。挂着的时候只看「除自己以外还有没有真实输出」。
    """

    if holding is None:
        if not enabled or has_real_output:
            return IDLE, ""
        return ATTACH, "桌面上没有任何真实显示输出"
    if not enabled:
        # 关开关是用户明示的意图，任务在不在跑都照办——否则开关看着像坏了。
        return RELEASE, "虚拟显示器开关已关闭"
    if holding not in real_devices:
        return LOST, "自己挂的虚拟显示器已不在桌面上"
    if real_devices - {holding}:
        return DETACH, "真实显示输出已恢复"
    return IDLE, ""


class _DesktopGuard:
    """常驻的显示输出守卫。后端生命周期内单例。"""

    def __init__(self) -> None:
        self._display = None
        self._task: asyncio.Task | None = None
        # 与设置页的「检测」按钮互斥：那个按钮会真的插一块屏再拆掉，和巡检撞车会让
        # 驱动进入坏状态（实测快速反复插拔后 VDD_IOCTL_ADD 报 WinError 31）。
        self._lock = asyncio.Lock()
        # 正在跑的挂屏任务。它不随调用方一起被取消，见 `_attach`。
        self._attaching: asyncio.Task | None = None
        self._pending: tuple[str, str] = (IDLE, "")
        self._pending_ticks = 0
        self._quiet_until = 0.0
        self._last_failure = ""

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    @property
    def device(self) -> str | None:
        """自己挂的那块屏的设备名；没挂时为 None。"""

        display = self._display
        return display.device if display is not None else None

    def describe_holding(self) -> str | None:
        """给设置页用的一行说明；没挂时为 None。"""

        display = self._display
        if display is None or display.device is None:
            return None
        mode = display.applied_mode
        if mode is None:
            return f"{display.device}"
        return f"{display.device} {mode[0]}x{mode[1]}@{mode[2]}"

    async def start(self) -> None:
        if not IS_WINDOWS or self._task is not None:
            return
        # 孤儿清理放在开关判断**之前**、也放在第一次巡检之前：用户在崩溃之后把开关关掉，
        # 那块没人认领的屏同样得能被清掉；而孤儿本身就算「真实输出」，不先清掉的话
        # 巡检判据会一路放行。清理只动自己记账过、且记录进程已死的 index。
        with suppress(Exception):
            await asyncio.to_thread(cleanup_orphan_display)
        self._task = asyncio.create_task(self._loop(), name="desktop-guard")
        logger.info("桌面显示输出守卫已启动")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        attaching, self._attaching = self._attaching, None
        if attaching is not None and not attaching.done():
            # **不能 cancel 它**：线程已经在插屏了，取消只会让我们不知道结果，屏照样插上。
            # 等它把 `_display` 赋好，下面的 `_teardown` 才拆得掉。
            with suppress(Exception):
                await attaching
        # 后端要退出了，没人会再来收尾这块屏，必须自己拆掉。
        async with self._lock:
            await self._teardown("后端正在退出")

    async def ensure_now(self) -> None:
        """立刻巡检一次并等它落定。

        任务开跑前调用：轮询有几秒的窗口，而任务一旦在幻影屏上起来，游戏就会把坏掉的
        窗口尺寸记进自己的配置，事后再插屏也纠正不回来。所以「挂上」这一档在这里免防抖，
        「拆除」不免——一次误判就会把任务脚下的屏抽掉。
        """

        if not IS_WINDOWS:
            return
        async with self._lock:
            await self._tick(confirm=False)

    async def _loop(self) -> None:
        while True:
            try:
                async with self._lock:
                    await self._tick(confirm=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 守卫本身绝不能因为一次异常就停摆——它一停，后面所有无人值守的轮次
                # 都会退回到幻影屏上，而且没有任何迹象。
                logger.warning(f"桌面显示输出巡检出错，下一轮继续: {exc}")
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self, *, confirm: bool) -> None:
        enabled = bool(Config.get("Display", "IfEnableVirtualDisplay"))
        holding = self.device

        has_real = True
        real: set[str] = set()
        # 开关关着时一次显示查询都不做：没挂就什么都不用判（最常见的一档），挂着就直接
        # 走 RELEASE——那是用户明示的意图，不能让一次枚举失败把它挡在后面。
        if enabled:
            if holding is None:
                has_real = await asyncio.to_thread(_has_real_output)
            else:
                devices = await asyncio.to_thread(_real_devices)
                if devices is None:
                    # 查询不可信，这一轮什么都不做。
                    self._pending, self._pending_ticks = (IDLE, ""), 0
                    return
                real = devices

        action, reason = decide(
            enabled=enabled,
            holding=holding,
            has_real_output=has_real,
            real_devices=real,
        )

        if action == IDLE:
            self._pending, self._pending_ticks = (IDLE, ""), 0
            return
        if action == RELEASE:
            # 用户明示的意图，不等防抖。
            self._pending, self._pending_ticks = (IDLE, ""), 0
            await self._teardown(reason)
            return

        # 只有「挂上」这一档能免防抖：任务马上要跑了，没时间等判据连续成立。拆除反过来——
        # 一次误判就会把任务脚下的屏抽掉，宁可晚几秒。
        if confirm or action != ATTACH:
            if (action, reason) == self._pending:
                self._pending_ticks += 1
            else:
                self._pending, self._pending_ticks = (action, reason), 1
            if self._pending_ticks < CONFIRM_TICKS:
                return
        self._pending, self._pending_ticks = (IDLE, ""), 0

        if action == LOST:
            logger.warning(f"{reason}，已就地释放（可能是驱动重载或睡眠恢复）")
            await self._teardown(reason)
            return
        if action == DETACH:
            # 记下是哪块屏回来的：拆屏会把用户开着的窗口全部挪过去，事后排查「窗口怎么跑到
            # 那边去了」全靠这一行；拆完再报一次桌面现状，拆前的描述里还带着自己那块。
            returned = ", ".join(sorted(real - {holding}))
            await self._teardown(f"{reason}: {returned}")
            logger.info(f"当前桌面: {await asyncio.to_thread(_describe)}")
            return
        await self._attach(reason)

    async def _attach(self, reason: str) -> None:
        if self._attaching is not None and not self._attaching.done():
            # 上一次挂屏还在跑。调用方被取消了不代表它停了（见 `_insert`），等它落定再说。
            return
        if time.monotonic() < self._quiet_until:
            return

        from app.utils.platform.vdd import VddStatus, probe

        result = await asyncio.to_thread(probe)
        if result.status is not VddStatus.OK:
            self._fail(
                f"无法挂载虚拟显示器（{_probe_hint(result)}）。"
                "没有真实显示输出时 Windows 只保留一块占位的幻影屏，游戏渲染与截图都可能不可靠；"
                "请接回显示器、使用显示器假负载，或安装 Parsec 虚拟显示驱动"
            )
            return

        # 详情放在探测通过之后再说：没装驱动的用户每个静默期都被刷一行幻影屏概况没有意义，
        # 该说的话 `_fail` 里已经说了，而且那条会去重。
        logger.warning(
            f"{reason}，当前只有系统占位的幻影屏: {await asyncio.to_thread(_describe)}"
        )

        mode = parse_mode(Config.get("Display", "VirtualDisplayMode"))
        # 挂屏跑在守卫自己的任务里，用 shield 隔开调用方的取消。
        #
        # 任务开跑前的强制巡检是从 `TaskManager` 里 await 的，用户点「停止」会 cancel 掉
        # 那条任务；而 `asyncio.to_thread` 被取消**不会**打断已经跑起来的线程——
        # `__enter__` 照常把屏插上（光是 settle 就要 1.5 秒）。若让取消把 `_attach` 打断，
        # `self._display` 永远赋不上、记账也不写，桌面上就留下一块守卫不认、下次启动的
        # 孤儿清理也捡不到的屏，而且它本身算「真实输出」，此后每轮巡检都会放行。
        self._attaching = asyncio.create_task(self._insert(display_mode=mode))
        await asyncio.shield(self._attaching)

    async def _insert(self, *, display_mode: tuple[int, int, int]) -> None:
        from app.utils.platform.vdd import VirtualDisplay

        mode = display_mode
        display = VirtualDisplay(mode=mode)
        try:
            await asyncio.to_thread(display.__enter__)
        except Exception as exc:
            # `__enter__` 可能在屏已经插上之后才失败（认不出对应的显示设备）。这时屏就在
            # 桌面上，而记账还没写，既没人认领也清不掉——必须由我们就地收尾。
            with suppress(Exception):
                await asyncio.to_thread(display.close)
            self._fail(f"挂载虚拟显示器失败，按原样继续: {exc}")
            return

        self._display = display
        if display.index is not None:
            # 记账必须在挂上之后立刻写：进程随时可能被强杀，写晚了这块屏就成了没人认领的孤儿。
            await asyncio.to_thread(_write_state, display.index)

        effective = await asyncio.to_thread(
            _has_real_output
        ) and await asyncio.to_thread(_desktop_has_room)
        if not effective:
            # 调得动不等于有效果：这一步才是「检测通过」的真正判据。
            detail = await asyncio.to_thread(_describe)
            self._silence()
            await self._teardown(f"挂上了但桌面仍不满足要求: {detail}")
            return

        if display.applied_mode != mode:
            # 分辨率没切成不致命（默认模式本来就是 1920x1080@60），但必须说出来，
            # 否则用户选了 30Hz 却静默跑在 60Hz 上。
            logger.warning(
                f"虚拟显示器未能切换到 {mode[0]}x{mode[1]}@{mode[2]}，"
                f"实际为 {display.applied_mode}"
            )
        self._quiet_until = 0.0
        self._last_failure = ""
        logger.info(f"已挂载虚拟显示器: {await asyncio.to_thread(_describe)}")

    async def _teardown(self, reason: str) -> None:
        display, self._display = self._display, None
        if display is None:
            return
        with suppress(Exception):
            await asyncio.to_thread(display.close)
        _clear_state()
        logger.info(f"已拆除虚拟显示器（{reason}）")

    def _silence(self) -> None:
        """进入静默期。失败之后不该每几秒重试一次。"""

        self._quiet_until = time.monotonic() + FAILURE_BACKOFF

    def _fail(self, message: str) -> None:
        """记一次失败并进入静默期。同一条原因只说一遍。"""

        self._silence()
        if message != self._last_failure:
            self._last_failure = message
            logger.warning(message)


DesktopGuard = _DesktopGuard()


async def ensure_desktop_available() -> None:
    """任务开跑前强制巡检一次。守卫没启动时也能安全调用。"""

    await DesktopGuard.ensure_now()


def _probe_hint(result) -> str:
    from app.utils.platform.vdd import VddStatus

    if result.status is VddStatus.NOT_INSTALLED:
        return "未安装 Parsec 虚拟显示驱动"
    if result.status is VddStatus.ACCESS_DENIED:
        # 与「未安装」是两种完全不同的故障，提示必须分开。
        return "驱动已安装但当前权限打不开设备"
    return f"驱动异常: {result.detail}"


async def probe_virtual_display_driver():
    """只跑前两段（装没装 / 能不能调），不改变桌面拓扑。

    供设置页在打开时自动调用，用来决定开关能不能打开。实测一次 0.2ms，所以**不缓存也
    不持久化**：存下来的状态只会变陈旧（驱动可能被卸载、被显卡驱动更新搞坏、或者配置
    被同步到另一台机器），而实时问一次永远是对的。
    """

    from app.models.schema import (
        VirtualDisplayCheckOut,
        VirtualDisplayCheckResultItem,
    )

    def item(stage: str, passed: bool, message: str):
        return VirtualDisplayCheckResultItem(
            stage=stage, passed=passed, message=message
        )

    if not IS_WINDOWS:
        return VirtualDisplayCheckOut(
            message="虚拟显示器仅支持 Windows",
            results=[item("installed", False, "当前系统不支持")],
        )

    from app.utils.platform.vdd import VddStatus, probe

    result = await asyncio.to_thread(probe)
    if result.status is VddStatus.NOT_INSTALLED:
        return VirtualDisplayCheckOut(
            message="未安装 Parsec 虚拟显示驱动",
            results=[item("installed", False, "未找到驱动，请先安装")],
        )
    if result.status is not VddStatus.OK:
        return VirtualDisplayCheckOut(
            message=_probe_hint(result),
            results=[
                item("installed", True, "驱动已安装"),
                item("openable", False, _probe_hint(result)),
            ],
        )
    return VirtualDisplayCheckOut(
        message="驱动可用",
        driverVersion=result.version,
        results=[
            item("installed", True, "驱动已安装"),
            item("openable", True, f"握手成功，驱动版本 0.{result.version}"),
        ],
    )


async def check_virtual_display_driver():
    """设置页「检测」按钮的三段式检查。

    第三段会真的插一块屏再拆掉，改变桌面拓扑，所以只在用户手动触发时跑。
    检测结果**不做持久化**：驱动可能被卸载、或被显卡驱动更新搞坏，一个永久的
    「检测通过」标记就是下一个假信号来源。运行时每次重新探测前两段，第三段由
    实际挂载后的重验代替。

    守卫此刻正挂着屏时不再插第二块：那既是多余的拓扑变更，又会让「除自己以外还有没有
    真实输出」的判据在检测期间成立，守卫紧接着就把自己那块拆了。直接拿现挂的那块报结果。
    """

    from app.models.schema import (
        VirtualDisplayCheckOut,
        VirtualDisplayCheckResultItem,
    )

    def item(stage: str, passed: bool, message: str):
        return VirtualDisplayCheckResultItem(
            stage=stage, passed=passed, message=message
        )

    if not IS_WINDOWS:
        return VirtualDisplayCheckOut(
            message="虚拟显示器仅支持 Windows",
            results=[item("installed", False, "当前系统不支持")],
        )

    from app.utils.platform.vdd import VddStatus, VirtualDisplay, probe

    async with DesktopGuard.lock:
        result = await asyncio.to_thread(probe)
        monitors = await asyncio.to_thread(_describe)

        if result.status is VddStatus.NOT_INSTALLED:
            return VirtualDisplayCheckOut(
                message="未安装 Parsec 虚拟显示驱动",
                monitors=monitors,
                results=[item("installed", False, "未找到驱动，请先安装后再检测")],
            )
        if result.status is not VddStatus.OK:
            return VirtualDisplayCheckOut(
                message=_probe_hint(result),
                monitors=monitors,
                results=[
                    item("installed", True, "驱动已安装"),
                    item("openable", False, _probe_hint(result)),
                ],
            )

        results = [
            item("installed", True, "驱动已安装"),
            item("openable", True, f"握手成功，驱动版本 0.{result.version}"),
        ]

        holding = DesktopGuard.describe_holding()
        if holding is not None:
            results.append(
                item("effective", True, f"当前正挂载着虚拟显示器（{holding}）")
            )
            return VirtualDisplayCheckOut(
                message="检测通过（当前没有真实显示输出，虚拟显示器正在使用中）",
                driverVersion=result.version,
                monitors=monitors,
                results=results,
            )

        mode = parse_mode(Config.get("Display", "VirtualDisplayMode"))
        display = VirtualDisplay(mode=mode)
        try:
            await asyncio.to_thread(display.__enter__)
        except Exception as exc:
            with suppress(Exception):
                await asyncio.to_thread(display.close)
            results.append(item("effective", False, f"挂载失败: {exc}"))
            return VirtualDisplayCheckOut(
                message="驱动可调用，但挂载虚拟显示器失败",
                driverVersion=result.version,
                monitors=monitors,
                results=results,
            )

        try:
            applied = display.applied_mode
            monitors = await asyncio.to_thread(_describe)
            if applied == mode:
                results.append(
                    item(
                        "effective",
                        True,
                        f"已挂载 {applied[0]}x{applied[1]}@{applied[2]} 并成功拆除",
                    )
                )
                message = "检测通过"
            else:
                results.append(
                    item(
                        "effective",
                        False,
                        f"挂载成功但模式为 {applied}，与所选的 "
                        f"{mode[0]}x{mode[1]}@{mode[2]} 不一致",
                    )
                )
                message = "驱动不支持所选的分辨率或刷新率，请换一档"
        finally:
            await asyncio.to_thread(display.close)

    return VirtualDisplayCheckOut(
        message=message,
        driverVersion=result.version,
        monitors=monitors,
        results=results,
    )
