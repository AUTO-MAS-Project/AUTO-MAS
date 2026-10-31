import ctypes
import subprocess
import threading
from collections.abc import Callable

from app.utils import get_logger

logger = get_logger("电源管理")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
MOUSEEVENTF_MOVE = 0x0001


def _wake_display() -> None:
    """把已经熄掉的屏叫醒：鼠标原地挪 1 像素再挪回来。

    `ES_DISPLAY_REQUIRED` 只保证从此不熄，屏已经熄了能不能叫亮没有把握；模拟一次输入是
    2026-10-18 实测叫得醒的办法。锁屏（安全桌面）下注入会被拒，失败无所谓。
    """

    user32 = ctypes.windll.user32
    user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)


class WindowsDisplayHold:
    """一份「保持显示开启」的请求，`release()` 撤掉。

    执行状态是按线程记的：放在事件循环线程上会和「阻止休眠」那一份互相覆盖，并发的
    几份也没法各自撤销。所以每份请求单独起一条线程持有，撤销时由那条线程清掉自己的状态
    再退出；系统对各线程的请求取并集。进程退出或关机时请求随之消失，不改任何电源设置。
    """

    def __init__(
        self, owner: str, on_release: Callable[["WindowsDisplayHold"], None]
    ) -> None:
        self.owner = owner
        self._on_release = on_release
        self._released = threading.Event()
        self._release_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name=f"display-hold:{owner}", daemon=True
        )

    @property
    def active(self) -> bool:
        return not self._released.is_set()

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        # 线程还没跑起来就被撤了（比如紧接着要关机）：不再请求、也不再叫醒。
        if self._released.is_set():
            return
        kernel32 = ctypes.windll.kernel32
        if not kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED):
            logger.warning(f"请求保持显示开启失败（{self.owner}）")
            # 没生效就别装作生效：`active` 变假，桌面保障下一轮会重新请求。
            self.release()
            return
        if not self._released.is_set():
            try:
                _wake_display()
            except Exception as exc:
                logger.warning(f"唤醒显示失败（{self.owner}）: {exc}")
        self._released.wait()
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    def release(self) -> None:
        with self._release_lock:
            if self._released.is_set():
                return
            self._released.set()
        self._on_release(self)


class WindowsPowerController:
    supported = True
    supported_actions = frozenset(
        {"Shutdown", "ShutdownForce", "Reboot", "Hibernate", "Sleep", "Logoff"}
    )

    def __init__(self) -> None:
        self._display_holds: set[WindowsDisplayHold] = set()
        self._display_holds_lock = threading.Lock()

    async def execute(self, action: str) -> None:
        commands = {
            "Shutdown": ["shutdown", "/s", "/t", "0"],
            "ShutdownForce": ["shutdown", "/s", "/t", "0", "/f"],
            "Reboot": ["shutdown", "/r", "/t", "0"],
            "Hibernate": ["shutdown", "/h"],
            "Sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "Logoff": ["shutdown", "/l"],
        }
        # MAS 自己执行电源操作之前先撤掉「保持显示开启」，恢复系统原本的熄屏规则。
        self.release_display_holds()
        subprocess.run(commands[action])

    async def set_sleep_prevention(self, enabled: bool) -> None:
        state = 0x80000000 | (0x00000001 if enabled else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(state)

    def hold_display(self, owner: str) -> WindowsDisplayHold:
        """开始保持显示开启（屏已熄就先叫醒），直到返回值被 `release()`。"""

        hold = WindowsDisplayHold(owner, self._forget_display_hold)
        with self._display_holds_lock:
            self._display_holds.add(hold)
        hold.start()
        logger.info(f"开始保持显示开启：{owner}")
        return hold

    def release_display_holds(self) -> None:
        with self._display_holds_lock:
            holds = list(self._display_holds)
        for hold in holds:
            hold.release()

    def _forget_display_hold(self, hold: WindowsDisplayHold) -> None:
        with self._display_holds_lock:
            self._display_holds.discard(hold)
        logger.info(f"已撤销保持显示开启：{hold.owner}")


power = WindowsPowerController()
