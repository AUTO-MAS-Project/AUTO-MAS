#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from app.utils import (
    IS_ELEVATED,
    IS_WINDOWS,
    UnsupportedPlatformError,
    get_logger,
    process_platform,
    window,
)

from .runner import create_subprocess
from .scope import current_process_scope
from .session import desktop_process_target, process_in_scope

if TYPE_CHECKING:
    from app.utils.windows.desktop_session.process_runner import DesktopProcess

logger = get_logger("进程管理")

# 后继进程改绑的搜索窗口（秒）: 覆盖引导式启动器自更新/接力换进程的间隙
_RESEEK_TIMEOUT_SECONDS = 5.0

# 接力后继的最长「年龄」（秒）: 合法后继在原进程退出前后数秒内创建, 而检测到
# 原进程退出最多晚一个日志空闲回调周期（60s）, 留足余量后仍能把运行期间早已
# 存在的同 exe 无关实例（如用户手动打开的启动器 GUI）挡在改绑之外
_RESEEK_MAX_SUCCESSOR_AGE_SECONDS = 180.0

# 专项把「启动等待时间」填 0 时的兜底上限（秒）: 0 只表示不等画面, 不等窗口
# 会让刚拉起的游戏当场被判「窗口未就绪」, 所以窗口还是要等到这个上限
_WINDOW_READY_FALLBACK_SECONDS = 60.0

# 窗口就绪轮询间隔（秒）: 游戏窗口从首次出现到画出客户区通常在数秒内, 0.5 秒
# 足够跟手, 也不会让进程扫描占满事件循环
_WINDOW_READY_POLL_SECONDS = 0.5

# 桌面分身里等待窗口就绪时, 在用户上限之外再留给拉起 worker 进程的余量（秒）
_DESKTOP_READY_GRACE_SECONDS = 30.0


@dataclass
class ProcessInfo:
    pid: int | None = None
    name: str | None = None
    exe: str | None = None
    cmdline: list[str] | None = None


def match_process(proc: psutil.Process, target: ProcessInfo) -> bool:
    """检查进程是否与目标进程信息匹配

    ``proc.info`` 里预取的字段直接比对; ``exe`` 与 ``cmdline`` 只在目标要求时
    读取, 因为命令行在受保护进程上要等读超时, 不能整表预取。读不到的字段按
    不匹配处理。
    """

    info = proc.info
    if target.pid is not None and proc.pid != target.pid:
        return False
    if target.name is not None and info["name"] != target.name:
        return False
    if target.exe is not None:
        exe = info.get("exe") or _read_field(proc, "exe")
        if not exe or Path(exe) != Path(target.exe):
            return False
    if (
        target.cmdline is not None
        and (info.get("cmdline") or _read_field(proc, "cmdline")) != target.cmdline
    ):
        return False

    return process_in_scope(proc.pid)


def _read_field(proc: psutil.Process, field: str) -> object:
    """按需读取未预取的进程字段; 无权访问或已退出时按读不到处理。"""

    try:
        return getattr(proc, field)()
    except psutil.Error:
        return None


def is_process_running(process_name: str, *, exe: str | None = None) -> bool:
    """在调用者所在桌面查找指定进程的可见窗口。"""

    target = ProcessInfo(name=process_name, exe=exe)
    for proc in psutil.process_iter(["name", "exe"] if exe else ["name"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            if match_process(proc, target):
                # 平台不支持窗口能力时 get_window_handles 返回空列表, 循环不进入
                for hwnd in get_window_handles(proc.pid):
                    if window.is_visible(hwnd):
                        return True
    return False


async def has_process_window(process_name: str, *, exe: str | None = None) -> bool:
    """在任务所在桌面查找指定进程的可见窗口。"""
    desktop = desktop_process_target.get()
    if desktop is None:
        return is_process_running(process_name, exe=exe)

    from app.utils.windows.desktop_session.process_runner import run_desktop_action

    code, _, _ = await run_desktop_action(
        desktop, "has_process_window", {"name": process_name, "exe": exe}
    )
    return code == 0


def _is_client_ready(hwnd: int) -> bool:
    """窗口是否已经能看到内容: 可见且客户区有面积。

    只判「窗口存在」不够: 游戏窗口刚创建时已经可见, 但引擎还在初始化, 客户区
    仍是 0×0, 这时截图拿到空图会把脚本的识别结果带偏。
    """

    try:
        if not window.is_visible(hwnd):
            return False
        size = window.get_client_size(hwnd)
    except Exception:
        # 轮询期间窗口被销毁属预期状态, 按「还没就绪」处理, 下一轮重新取句柄
        return False
    return size is not None and size[0] > 0 and size[1] > 0


def _find_ready_window(target: ProcessInfo) -> int | None:
    """在调用者所在桌面找第一个已就绪的主窗口句柄。"""

    if target.pid is not None:
        # MAS 自己拉起的进程: 精确到实例, 也不会被同名的旧实例抢先
        hwnd = get_main_window_handle(target.pid)
        return hwnd if hwnd is not None and _is_client_ready(hwnd) else None

    for proc in psutil.process_iter(["pid", "name"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            if not match_process(proc, target):
                continue
            hwnd = get_main_window_handle(proc.pid)
            if hwnd is not None and _is_client_ready(hwnd):
                return hwnd
    return None


def _describe_process(target: ProcessInfo) -> str:
    if target.name is not None:
        return target.name
    if target.exe is not None:
        return Path(target.exe).name
    if target.pid is not None:
        return f"PID {target.pid}"
    return "目标进程"


async def wait_process_window_ready(
    target: ProcessInfo,
    timeout_seconds: float,
    *,
    poll_interval: float = _WINDOW_READY_POLL_SECONDS,
) -> bool:
    """等目标进程的游戏窗口真正就绪, 等不到就报错。

    「就绪」指主窗口可见且客户区有面积: 只等进程或只等窗口出现都太早, 引擎还在
    初始化时窗口已经可见、客户区却仍是 0×0, 脚本此时开跑会拿到空截图。

    Args:
        target: 目标进程信息, 至少给 ``name`` 或 ``exe`` 之一
        timeout_seconds: 等待上限（秒）。专项把「启动等待时间」填 0 时按
            ``_WINDOW_READY_FALLBACK_SECONDS`` 兜底, 因为 0 只表示不等画面稳定,
            不等窗口会让刚拉起的游戏当场被判未就绪
        poll_interval: 轮询间隔（秒）

    Returns:
        找到就绪窗口返回 True; 本平台没有窗口概念、或目标信息为空（调用方没有
        可等的东西）时返回 False, 两种情况下调用方都照常往下走

    Raises:
        RuntimeError: 超过上限仍未看到就绪窗口
    """

    if not IS_WINDOWS or not (
        target.pid or target.name or target.exe or target.cmdline
    ):
        return False

    timeout = timeout_seconds if timeout_seconds > 0 else _WINDOW_READY_FALLBACK_SECONDS

    # 桌面分身里游戏在子会话中, 主会话的进程扫描看不到它; 整体交给分身的 worker
    # 一次性等完, 避免每轮轮询都拉起一个进程
    desktop = desktop_process_target.get()
    if desktop is not None:
        from app.utils.windows.desktop_session.process_runner import run_desktop_action

        try:
            async with asyncio.timeout(timeout + _DESKTOP_READY_GRACE_SECONDS):
                code, _, _ = await run_desktop_action(
                    desktop,
                    "wait_process_window_ready",
                    {
                        "pid": target.pid,
                        "name": target.name,
                        "exe": target.exe,
                        "timeout": timeout,
                    },
                )
        except TimeoutError:
            code = 1
        if code == 0:
            return True
        raise RuntimeError(
            f"游戏窗口在 {timeout:g} 秒内未就绪（{_describe_process(target)}）"
        )

    deadline = time.monotonic() + timeout
    while True:
        if await asyncio.to_thread(_find_ready_window, target) is not None:
            return True
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(poll_interval)

    raise RuntimeError(
        f"游戏窗口在 {timeout:g} 秒内未就绪（{_describe_process(target)}）"
    )


def is_process_alive(process_name: str) -> bool:
    """检查指定进程名是否有存活实例（不依赖窗口）。

    is_process_running 要求存在可见窗口，窗口销毁后进程仍可能存活；
    需要「等待进程完全退出」的调用方（如多用户切换等待旧游戏退出）应
    用本函数按进程名判断存活。
    """

    for proc in psutil.process_iter(["name"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            if proc.info.get("name") == process_name and process_in_scope(proc.pid):
                return True
    return False


def get_window_handles(pid: int) -> list[int]:
    """获取指定进程的所有窗口句柄"""

    try:
        return window.get_window_handles(pid)
    except UnsupportedPlatformError:
        return []


def get_main_window_handle(
    pid: int,
    window_title: str | None = None,
    window_class_name: str | None = None,
) -> int | None:
    """获取指定进程的主窗口句柄

    优先按标题或类名定位, 若未命中则回退到 PID 下最合适的顶层窗口。
    平台不支持窗口能力时返回 None。
    """

    try:
        return window.get_main_window_handle(pid, window_title, window_class_name)
    except UnsupportedPlatformError:
        return None


class ProcessManager:
    """进程监视器类, 用于跟踪主进程及其所有子进程的状态"""

    def __init__(
        self,
        window_title: str | None = None,
        window_class_name: str | None = None,
        reseek_target: bool = False,
    ):
        super().__init__()

        self.process: asyncio.subprocess.Process | None = None
        self._desktop_process: DesktopProcess | None = None
        self.target_process: psutil.Process | None = None
        self.window_title = window_title
        self.window_class_name = window_class_name
        # 引导式启动器（自更新/接力时会更换进程实例）场景: 跟踪进程退出后按
        # 目标信息重新搜索后继实例改绑, 而不是直接判定运行结束
        self.reseek_target = reseek_target
        self._target_info: ProcessInfo | None = None
        self._target_create_time: float | None = None
        self._drain_tasks: list[asyncio.Task[None]] = []

    @property
    def main_pid(self) -> int | None:
        """主进程的 PID"""

        if self.target_process is not None:
            return self.target_process.pid
        if self.process is not None:
            return self.process.pid
        if self._desktop_process is not None:
            return self._desktop_process.pid
        return None

    @property
    def main_process(self) -> psutil.Process | asyncio.subprocess.Process | None:
        """主进程对象"""

        if self.target_process is not None:
            return self.target_process
        if self.process is not None:
            return self.process
        return None

    @property
    def desktop_process(self) -> "DesktopProcess | None":
        return self._desktop_process

    @property
    def launched_process(self) -> "asyncio.subprocess.Process | DesktopProcess | None":
        """由本管理器启动的进程句柄，含桌面分身代理。"""
        return self._desktop_process or self.process

    @property
    def main_hwnd(self) -> int | None:
        """主进程的主窗口句柄"""

        if self.main_pid is None:
            return None
        return get_main_window_handle(
            self.main_pid, self.window_title, self.window_class_name
        )

    async def open_process(
        self,
        program: Path | str,
        *args: str,
        cwd: Path | None = None,
        target_process: ProcessInfo | None = None,
        stdin: int = asyncio.subprocess.DEVNULL,
        stdout: int = asyncio.subprocess.DEVNULL,
        stderr: int = asyncio.subprocess.DEVNULL,
        null_stream_to_pipe: bool = False,
        elevated: bool = False,
        breakaway: bool = False,
        owned: bool = True,
        retain_desktop_descendants: bool = False,
        desktop_root_only: bool = False,
        env: dict[str, str] | None = None,
    ) -> None:
        """
        启动子进程并跟踪目标进程

        Args:
            program (Path | str): 可执行文件路径
            *args (str): 传递给可执行文件的参数
            cwd (Path | None): 可选的工作目录, 默认为可执行文件所在目录
            target_process (ProcessInfo | None): 期望目标进程信息, 用于跟踪主进程及其子进程, 默认为 None 表示跟踪直接启动的子进程
            stdin (int): 标准输入重定向选项, 默认为 asyncio.subprocess.DEVNULL
            stdout (int): 标准输出重定向选项, 默认为 asyncio.subprocess.DEVNULL
            stderr (int): 标准错误重定向选项, 默认为 asyncio.subprocess.DEVNULL
            null_stream_to_pipe (bool): 若为 True, 将设为 DEVNULL 的 stdout/stderr 替换为一条自动销毁输出的标准流管道。
            elevated (bool): 若为 True 且在 Windows 上, 以管理员权限启动进程（触发 UAC），此时不直接持有子进程句柄，依赖 target_process 追踪。
            breakaway (bool): 若为 True 且在 Windows 上, 让子进程脱离监督器的 Job Object（CREATE_BREAKAWAY_FROM_JOB）。只给游戏/模拟器这类不该随后端退出的进程用, 脚本本体、MAA、agent 等保持默认 False。
            owned (bool): 是否加入任务清理；游戏由调用方按关闭选项收尾时传 False，进程管理器仍保留跟踪及显式关闭能力。
            retain_desktop_descendants (bool): 在分身内保留启动器派生进程，直到管理器收尾。
            desktop_root_only (bool): 分身执行器收尾只停止主进程，派生进程可以继续运行。
            env (dict[str, str] | None): 子进程环境变量, 默认 None 表示继承当前进程; 传入时会整体替换, 需要保留现有环境的调用点自行并上 os.environ。elevated 走 ShellExecute, 该分支不支持指定环境。
        """

        if await self.is_running():
            raise RuntimeError("无法同时管理多个进程")

        if (
            target_process is not None
            and target_process.pid is None
            and target_process.name is None
            and target_process.cmdline is None
            and target_process.exe is None
        ):
            raise ValueError("目标进程信息不完整")

        await self.clear()

        desktop = desktop_process_target.get()
        if desktop is not None:
            if (elevated and not IS_ELEVATED) or (
                stdin not in (asyncio.subprocess.DEVNULL, asyncio.subprocess.PIPE)
                or stdout not in (asyncio.subprocess.DEVNULL, asyncio.subprocess.PIPE)
                or stderr
                not in (
                    asyncio.subprocess.DEVNULL,
                    asyncio.subprocess.PIPE,
                    asyncio.subprocess.STDOUT,
                )
            ):
                raise ValueError("桌面分身暂不支持此进程启动方式")
            from app.utils.windows.desktop_session.process_runner import (
                launch_desktop_process,
            )

            scope = current_process_scope.get()
            if scope is not None:
                scope.ensure_can_start()
            started = time.time()
            self._desktop_process = await launch_desktop_process(
                desktop,
                argv=[str(program), *args],
                cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
                owned=owned and not desktop_root_only,
                retain=(
                    retain_desktop_descendants
                    or breakaway
                    or target_process is not None
                ),
                drain=null_stream_to_pipe,
                env=env,
                stream_limit=(
                    2**16
                    if asyncio.subprocess.PIPE in (stdin, stdout, stderr)
                    else None
                ),
                merge=stderr == asyncio.subprocess.STDOUT,
                interactive=stdin == asyncio.subprocess.PIPE,
                stream_stdout=stdout == asyncio.subprocess.PIPE,
                stream_stderr=stderr == asyncio.subprocess.PIPE,
                stop_root_only=desktop_root_only,
            )
            if scope is not None and scope.closed:
                await self._desktop_process.stop()
                raise asyncio.CancelledError
            if scope is not None and owned:
                if retain_desktop_descendants and not desktop_root_only:
                    scope.retain_desktop_process(self._desktop_process.stop)
                else:
                    scope.add_check(
                        "停止桌面分身进程", self._desktop_process.stop, timeout=12
                    )
            if target_process is not None:
                try:
                    await self.search_process(
                        target_process, min_create_time=started, owned=owned
                    )
                except BaseException:
                    await self.clear()
                    raise
            return

        if elevated and process_platform.platform_process.supports_elevation:
            # 以管理员权限启动进程（触发 UAC），ShellExecute 不返回子进程句柄，
            # 因此无法直接持有 process，仅支持通过 target_process 追踪。
            open_elevated = process_platform.platform_process.prepare_elevated()
            await asyncio.get_running_loop().run_in_executor(
                None, open_elevated, program, args, cwd
            )
            if target_process is not None:
                await self.search_process(
                    target_process,
                    60.0,
                    min_create_time=time.time(),
                    owned=owned,
                )
            return

        # 若指定了 null_stream_to_pipe, 将 stdout/stderr 为 DEVNULL 的流替换为管道, 并在后台消费以防止阻塞
        drain_streams = []
        if null_stream_to_pipe:
            if stdout == asyncio.subprocess.DEVNULL:
                stdout = asyncio.subprocess.PIPE
                drain_streams.append("stdout")
            if stderr == asyncio.subprocess.DEVNULL:
                stderr = asyncio.subprocess.PIPE
                drain_streams.append("stderr")

        self.process = await create_subprocess(
            program,
            *args,
            breakaway=breakaway,
            owned=owned,
            cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=env,
        )

        # 启动协程消费管道流以防止阻塞
        if drain_streams:
            for name in drain_streams:
                stream = getattr(self.process, name)
                if stream is not None:
                    self._drain_tasks.append(asyncio.create_task(self._drain(stream)))

        if target_process is not None:
            await self.search_process(
                target_process,
                60.0,
                min_create_time=time.time(),
                owned=owned,
            )

    async def _drain(self, stream: asyncio.StreamReader) -> None:
        """
        消费子进程标准流, 丢弃写入, 防止管道背压阻塞子进程。

        Args:
            stream (asyncio.StreamReader): 子进程的标准流对象
        """

        try:
            while _ := await stream.readline():
                pass
        except (ValueError, OSError):
            # 管道读端在子进程退出后被关闭, 属正常终止; 忽略无效句柄冲突
            pass

    async def open_protocol(
        self, protocol_url: str, target_process: ProcessInfo
    ) -> None:
        """
        使用自定义协议启动子进程, 需要目标进程信息进行跟踪

        Args:
            protocol_url (str): 自定义协议 URL
            target_process (ProcessInfo): 期望目标进程信息
        """

        started = time.time()
        try:
            await process_platform.platform_process.open_protocol(protocol_url)
        except UnsupportedPlatformError:
            raise
        except Exception as e:
            raise RuntimeError(f"无法启动协议 {protocol_url}: {e}") from e

        await self.search_process(
            target_process,
            60.0,
            min_create_time=started,
        )

    async def search_process(
        self,
        target_process: ProcessInfo,
        timeout_seconds: float = 60.0,
        min_create_time: float | None = None,
        *,
        owned: bool = True,
    ) -> None:
        """查找目标进程

        Args:
            target_process: 期望目标进程信息
            timeout_seconds: 搜索超时秒数，按单调时钟计量，不受系统时钟跳变影响
            min_create_time: 进程创建时间下限（epoch 秒），早于该时刻创建的同名进程视为
                启动前的残留实例并跳过，避免错误跟踪旧进程（留 2 秒容差吸收时间戳偏差）
            owned: 明确接管时登记任务清理归属；仅观察已有窗口时传 False。
        """

        def _scan() -> tuple[psutil.Process, float | None] | None:
            # cmdline 对受保护进程每次都要等读超时，整表预取会把一次扫描拖到
            # 数秒，发现游戏太晚；只预取轻量字段，cmdline 等筛选命中后再读。
            attrs = ["pid", "name", "create_time"]
            if target_process.exe is not None:
                attrs.append("exe")
            for proc in psutil.process_iter(attrs):
                if not match_process(proc, target_process):
                    continue
                create_time = proc.info["create_time"]
                if min_create_time is not None and (
                    create_time is None or create_time < min_create_time - 2
                ):
                    continue
                return proc, create_time
            return None

        # 全量进程扫描放到线程里, 避免阻塞事件循环
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            found = await asyncio.to_thread(_scan)
            if found is not None:
                proc, create_time = found
                self.target_process = proc
                scope = current_process_scope.get()
                if scope is not None and owned:
                    scope.track(proc)
                # 记录目标信息与创建时间, 供 reseek_target 改绑后继进程。
                # 创建时间取扫描阶段已读到的值, 不重新查询: 进程可能在扫描后
                # 退出而抛异常, 受保护进程的创建时间也可能读不到
                self._target_info = target_process
                self._target_create_time = create_time
                return
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("未能在限定时间内找到目标进程")

    async def is_running(self) -> bool:
        """检查当前管理的进程是否仍在运行

        ``reseek_target`` 为 True 时, 跟踪进程退出先按启动时的目标信息搜索
        创建更晚的同名后继进程（引导式启动器自更新/接力换进程）, 命中则改绑
        跟踪并视为仍在运行, 找不到才判定结束。
        """

        if self.target_process is not None:
            if self.target_process.is_running():
                return True
            if self.reseek_target and await self._reseek_target():
                return True
            return False
        if self.process is not None:
            return self.process.returncode is None
        if self._desktop_process is not None:
            return self._desktop_process.running
        return False

    async def _reseek_target(self) -> bool:
        """搜索跟踪目标的后继进程（同目标信息、创建更晚且足够新）, 命中则改绑。

        后继进程由原进程接力派出, 创建时间必然晚于原进程, 以原进程创建时间为
        下限可排除早于本次启动的残留实例; 再叠加「近期创建」下限, 把运行期间
        早已存在的同 exe 无关实例（用户手动打开的启动器 GUI、指向同安装的并行
        任务）挡在改绑之外。匹配毕竟只按目标信息（name/exe）进行, 同期新起的
        同 exe 实例仍可能命中, 误改绑只会拉长等待——最终由调用方的运行超时
        判定与按路径收尾兜底。搜索窗口覆盖接力换进程的间隙。
        """

        if self._target_info is None or self._target_create_time is None:
            return False
        successor = ProcessInfo(
            name=self._target_info.name,
            exe=self._target_info.exe,
            cmdline=self._target_info.cmdline,
        )
        min_successor_create_time = max(
            self._target_create_time,
            time.time() - _RESEEK_MAX_SUCCESSOR_AGE_SECONDS,
        )
        try:
            await self.search_process(
                successor,
                _RESEEK_TIMEOUT_SECONDS,
                min_create_time=min_successor_create_time,
            )
        except RuntimeError:
            return False
        logger.info(f"原跟踪进程已退出, 改绑后继进程 PID: {self.target_process.pid}")
        return True

    async def kill(self) -> None:
        """停止监视器并中止所有跟踪的进程"""

        if self.target_process is not None and self.target_process.is_running():
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    self.target_process.terminate()
                    await asyncio.get_running_loop().run_in_executor(
                        None, self.target_process.wait, 3
                    )
                except psutil.TimeoutExpired:
                    self.target_process.kill()
                    with suppress(psutil.TimeoutExpired):
                        await asyncio.get_running_loop().run_in_executor(
                            None, self.target_process.wait, 3
                        )

        if self.process is not None and self.process.returncode is None:
            with suppress(ProcessLookupError):
                try:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    self.process.kill()
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self.process.wait(), timeout=3)

        if self._desktop_process is not None:
            await self._desktop_process.stop()
        await self.clear()

    async def clear(self, *, keep_desktop_descendants: bool = False) -> None:
        """清空跟踪的进程信息"""

        if self._desktop_process is not None:
            keep = (
                keep_desktop_descendants
                and self._desktop_process.returncode == 0
                and current_process_scope.get() is not None
            )
            if not self._desktop_process.owned:
                await self._desktop_process.release()
            elif not keep:
                await self._desktop_process.stop()
            self._desktop_process = None

        # 清理残留的排水任务, 避免泄漏
        if self._drain_tasks:
            for task in self._drain_tasks:
                if not task.done():
                    task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*self._drain_tasks, return_exceptions=True)
            self._drain_tasks = []

        self.process = None
        self.target_process = None
        self._target_info = None
        self._target_create_time = None

    async def is_visible(self) -> bool:
        """检查主进程窗口是否可见

        Returns:
            bool: 窗口是否可见
        """

        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.is_visible(hwnd)
        except Exception:
            return False

    async def show_window(self) -> bool:
        """显示主进程窗口

        Returns:
            bool: 操作是否成功
        """

        if desktop_process_target.get() is not None:
            return await self._operate_desktop_window("show_process_window")
        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.show_window(hwnd)
        except Exception:
            return False

    async def hide_window(self) -> bool:
        """隐藏主进程窗口

        Returns:
            bool: 操作是否成功
        """
        if desktop_process_target.get() is not None:
            return await self._operate_desktop_window("hide_process_window")
        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.hide_window(hwnd)
        except Exception:
            return False

    async def minimize_window(self) -> bool:
        """最小化主进程窗口

        Returns:
            bool: 操作是否成功
        """

        if desktop_process_target.get() is not None:
            return await self._operate_desktop_window("minimize_process_window")
        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.minimize_window(hwnd)
        except Exception:
            return False

    async def activate_window(self) -> bool:
        """激活主进程窗口并将其置于前台

        Returns:
            bool: 操作是否成功
        """

        if desktop_process_target.get() is not None:
            return await self._operate_desktop_window("activate_process_window")
        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.activate_window(hwnd)
        except Exception:
            return False

    async def _operate_desktop_window(self, action: str) -> bool:
        desktop = desktop_process_target.get()
        pid = self.main_pid
        if desktop is None or pid is None:
            return False
        try:
            if self.target_process is not None:
                created = self.target_process.create_time()
            elif self._desktop_process is not None:
                created = self._desktop_process.create_time
            else:
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
        if created is None:
            return False

        from app.utils.windows.desktop_session.process_runner import run_desktop_action

        code, _, _ = await run_desktop_action(
            desktop,
            action,
            {
                "pid": str(pid),
                "createTime": created,
                "title": self.window_title,
                "class": self.window_class_name,
            },
            worker_module="app.utils.windows.desktop_session.process_worker",
        )
        return code == 0

    async def close(self) -> None:
        """请被管理进程自行退出，等它走完退出时的配置保存

        启动瞬间主窗口可能还是临时的启动画面, 关闭消息打不到真正的窗口上,
        所以每轮按当前句柄再请求一次, 直到进程退出。
        """

        while await self.is_running():
            if desktop_process_target.get() is not None:
                accepted = await self._operate_desktop_window("close_process_window")
            else:
                hwnd = self.main_hwnd
                accepted = hwnd is not None and window.close_window(hwnd)
            if not accepted:
                return
            await asyncio.sleep(0.2)
