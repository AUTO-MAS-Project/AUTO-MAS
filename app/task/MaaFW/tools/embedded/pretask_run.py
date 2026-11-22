"""项目的运行前设置（interface ``pretask``）：在宿主上按顺序跑完一次尝试里的全部 pretask。

与 ``plan_run``（跑一份计划）是同一种做法，两者共用子进程输出解码、去色、进程树快照的结束与
单行上限（都从 ``plan_run`` 拿，只留一份）：

- **只收普通数据**（``MaaFWPretaskRunRequest``）：计划里的 pretask、工作目录、时限、要盖上的进程
  环境（``PI_*`` 与 ModAVD 的 adb server 端口）、要打码的写法、是否在桌面分身里跑。不接收脚本配置、
  账号配置或任务类实例，也不回头碰调用方的对象。
- **输出只经同一种事件出口**（``plan_run.MaaFWPlanRunSink``）：这里只发账号日志
  （``MaaFWPlanRunLog``，失败类的行 ``warning`` 为真）。失败经 ``MaaFWPretaskError`` 抛出，文案可直接
  给用户看。

保护全在这里：全部 pretask 合计受整轮时限（``RunTimeLimit``）限制；输出按行实时进账号日志、逐行
打码（半行不单独交出）；等的是 pretask 进程退出而不是输出管道 EOF（它拉起的游戏 / 启动器常常
继承管道）；超时或停止只结束 pretask 进程和它下面一路都是脚本解释器的后代，游戏、启动器不碰。

``MaaFWPretaskRunner`` 跨尝试共用一份：停止与清理的状态要跨尝试保留。项目预约的释放要等这边的
进程确认退出——``exit_confirmation`` 记下此刻要等的清理与进程、返回等待入口。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from app.task.MaaFW.tools.core.controller_win32.service import (
    controller_has_window_rules,
)
from app.task.MaaFW.tools.core.interface.host_path import path_without_host_venv
from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.runner.models import (
    MaaFWPretaskRunPlan,
    MaaFWRunPlan,
)
from app.task.MaaFW.tools.core.runtime_pool.host_environment import (
    strip_host_python_environment,
)
from app.utils import get_logger
from app.utils.common.process.operations import managed_process, terminate_process
from app.utils.common.process.runner import create_subprocess, observe_process_exit
from app.utils.common.process.scope import current_process_scope

from .device_config import find_controller, match_windows_in_session, optional_int
from .plan_run import (
    WORKER_STREAM_LINE_LIMIT,
    MaaFWPlanRunLog,
    MaaFWPlanRunSink,
    clean_framework_output,
    decode_subprocess_output,
    terminate_process_snapshot,
)
from .run_redaction import redact_secret_text

# 与任务类同一个名字：后端日志里这段流程的行照旧记在「MaaFW 插件自动代理」下
logger = get_logger("MaaFW 插件自动代理")

# 运行前设置（interface pretask）进程退出后，管道里剩下的输出最多再读这么久。pretask 常常
# 拉起启动器 / 游戏，它们可能继承了 pretask 的输出管道句柄，管道要等它们退出才到 EOF，
# 所以等待以 pretask 进程退出为准、不等 EOF（见 ``MaaFWPretaskRunner.run``）。
_PRETASK_OUTPUT_DRAIN_SECONDS = 2.0
# 等 pretask 进程退出时查一次退出码的间隔：asyncio 的 ``Process.wait()`` 要等管道全部
# 关闭才返回，会被继承了管道的游戏卡住，只能看 ``returncode``。
_PRETASK_EXIT_POLL_SECONDS = 0.2
# 运行前设置输出的行尾：与 ``str.splitlines()`` 对这三种写法同口径，\r\n 算一次换行
_PRETASK_LINE_END_RE = re.compile(rb"\r\n|\r|\n")
# 超时或停止时，跟 pretask 进程一起结束的后代：只认这些脚本解释器，且一路往下只穿过
# 脚本解释器。游戏、启动器以及它们再起的任何进程都不碰（游戏的生命周期交给客户端）。
_PRETASK_SCRIPT_HOST_NAMES = frozenset(
    {
        "python.exe",
        "pythonw.exe",
        "py.exe",
        "pyw.exe",
        "cmd.exe",
        "powershell.exe",
        "pwsh.exe",
        "wscript.exe",
        "cscript.exe",
    }
)
# 管道在 pretask 退出后仍被别的程序占着时，把剩下的输出读完的后台任务（只写后端日志）。
# 不读的话那个程序写满管道缓冲就会卡在写输出上；任务要有强引用，不然会被回收。
_PRETASK_BACKGROUND_DRAINS: set[asyncio.Task[None]] = set()
# 判断运行前设置留下的半行有没有看得见的内容时要去掉的部分：完整或被截断的 CSI 控制序列
# （含 \x1b[?25h 这类带私有参数的）与其余控制字符
_PRETASK_TAIL_NOISE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]?|[\x00-\x1f\x7f]")


class MaaFWPretaskError(RuntimeError):
    """项目运行前设置失败，文案可直接显示给用户。"""


@dataclass(frozen=True)
class MaaFWPretaskRunRequest:
    """跑一次尝试里全部运行前设置要的输入。

    - ``project_path``：工作目录（计划的 ``path``，即项目根）。
    - ``run_time_limit_minutes``：全部 pretask 合计的时限（分钟），沿用托管的「单次运行时间限制」；
      0 / 空按 120 分钟。
    - ``plan_env``：计划的 ``PI_*`` 环境变量；``extra_env``：再盖在上面的进程环境（ModAVD 的 adb
      server 端口）。两者都盖在去掉宿主 Python 环境的进程环境上。
    - ``secrets``：输出里要打码的写法。
    - ``desktop``：在桌面分身里跑时的目标（``desktop_process_target`` 的值），None 是普通子进程。
    """

    project_path: str
    pretasks: Sequence[MaaFWPretaskRunPlan]
    run_time_limit_minutes: Any = 0
    plan_env: Mapping[str, str] = field(default_factory=dict)
    extra_env: Mapping[str, str] = field(default_factory=dict)
    secrets: Sequence[str] = ()
    desktop: Any | None = None


def pretask_display_name(pretask: MaaFWPretaskRunPlan) -> str:
    """日志与报错里的称呼：建计划时解析好的 label；没有、或以 ``$`` 开头（没解析的键）用 name。"""

    label = pretask.label
    if isinstance(label, str) and label.strip() and not label.lstrip().startswith("$"):
        return label.strip()
    return str(pretask.name)


async def pretasks_need_rerun(
    plan: MaaFWRunPlan | None,
    interface: MaaFWInterface | None,
    *,
    client_reset: bool,
    configured_hwnd: Any,
    emit: MaaFWPlanRunSink,
) -> bool:
    """重试前判断要不要再跑一遍已经成功过的运行前设置。

    只在客户端已经不在时重跑：MAS 刚关掉自己起的游戏 / 模拟器（``client_reset``），或者 Win32 下
    控制器的窗口已经找不到（游戏由运行前设置拉起、被队列里的「关闭游戏」任务关掉，
    MAS 不知道它是谁起的）。游戏还开着时不重跑，免得项目的启动脚本对着已在运行的
    游戏再走一遍。固定 HWnd（``configured_hwnd`` 是 ``Device.HWnd`` 的原值）、控制器没有窗口规则
    这两种只是「看不出窗口在不在」，不挡前一种：MAS 自己关掉的客户端一定不在了。
    """

    if plan is None or not plan.pretasks:
        return False
    if client_reset:
        emit(MaaFWPlanRunLog("游戏/模拟器已在上一次失败后关闭，重新应用运行前设置"))
        return True
    if plan.controllerType != "Win32" or interface is None:
        return False
    if optional_int(configured_hwnd):
        return False
    controller = find_controller(interface, plan.controllerName)
    if not controller_has_window_rules(controller):
        return False
    if await match_windows_in_session(controller):
        return False
    emit(MaaFWPlanRunLog("未找到游戏窗口，重新应用运行前设置"))
    return True


class MaaFWPretaskRunner:
    """一个账号这一轮的运行前设置。``run`` 每次尝试调一次；``stop`` 随时可调。"""

    def __init__(self, emit: MaaFWPlanRunSink) -> None:
        self._emit = emit
        # 正在跑的 pretask 进程（退出后清空）
        self._process: Any | None = None
        self._process_desktop = False
        # 正在进行的清理（见 ``stop``）
        self._cleanup: asyncio.Task[None] | None = None
        # 即使清理入口先清空 _process，也要保留退出观察句柄；
        # 停止确认超时或 native 强杀失败时不能提前放开项目预约。
        self._stopping: Any | None = None
        self._stopping_desktop = False

    def _log(self, message: str, *, warning: bool = False) -> None:
        self._emit(MaaFWPlanRunLog(message, warning))

    def exit_confirmation(self) -> Callable[[], Awaitable[bool]]:
        """记下此刻要等的清理与正在结束的进程，返回等待入口。

        等待入口返回真表示都确认退出了；清理本身出错时记一句、返回假（调用方保留项目预约）。
        """

        cleanup = self._cleanup
        process = self._stopping
        desktop = self._stopping_desktop

        async def confirm() -> bool:
            if cleanup is not None:
                try:
                    await asyncio.shield(cleanup)
                except Exception as error:
                    logger.warning(f"MaaFW 运行前设置清理未确认，保留占用: {error}")
                    return False
            if process is not None:
                # pretask 的 stdout 可能由游戏继承，不能用 process.wait()
                # 等其管道 EOF；只检查真正的进程退出状态。
                if desktop:
                    await process.wait_exit()
                else:
                    await observe_process_exit(process)
            return True

        return confirm

    async def run(self, request: MaaFWPretaskRunRequest) -> None:
        """按顺序跑完 ``request.pretasks``；失败、超时抛 ``MaaFWPretaskError``。"""

        # 宿主的 VIRTUAL_ENV、PYTHON* 等不往下传，PATH 去掉宿主 venv 的脚本目录（Runtime 经
        # uv run 起后端时它排最前）：pretask 脚本里再起 python 不该落到 MAS 自己的环境上
        env = strip_host_python_environment()
        if "PATH" in env:
            env["PATH"] = path_without_host_venv(env["PATH"]) or ""
        # 与 agent 同口径（runner._build_agent_env）：pretask 多是项目自带 Python 跑的
        # 脚本，输出与读文件都按 UTF-8；对非 Python 程序这两个变量无害。
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.update(request.plan_env)
        # ModAVD 实例：pretask 若用 adb，也走脚本专用 server（同 worker）
        env.update(request.extra_env)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # 运行前设置没有自己的时限设置：沿用本托管的「单次运行时间限制」（RunTimeLimit），
        # 一次尝试里全部运行前设置合计不超过它（MaaFW 豁免了 HardTimeLimit，这里是它缺的外层兜底；
        # worker 那一段另起计时，见 ``plan_run.MaaFWPlanRun.run``）。
        limit_minutes = request.run_time_limit_minutes or 120
        loop = asyncio.get_running_loop()
        pretasks_started_at = loop.time()
        deadline = pretasks_started_at + float(limit_minutes) * 60
        secret_variants = request.secrets
        desktop = request.desktop
        for pretask in request.pretasks:
            display_name = pretask_display_name(pretask)
            if loop.time() >= deadline:
                # 前面的运行前设置已经用完时限：这一条不再启动（启动了也只会被立刻结束）
                self._log(
                    f"运行前设置合计已用 {int(loop.time() - pretasks_started_at)} 秒，"
                    f"超过单次运行时间限制（{limit_minutes} 分钟），"
                    f"不再启动运行前设置 {display_name}",
                    warning=True,
                )
                raise MaaFWPretaskError(
                    f"运行前设置「{display_name}」未启动：运行前设置合计已超过单次运行时间限制 "
                    f"{limit_minutes} 分钟"
                )
            self._log(f"开始应用运行前设置: {display_name}")
            started_at = loop.time()
            if desktop is not None:
                from app.utils.windows.desktop_session.process_runner import (
                    launch_desktop_process,
                )

                scope = current_process_scope.get()
                if scope is not None:
                    scope.ensure_can_start()
                process = await launch_desktop_process(
                    desktop,
                    argv=[str(pretask.executable), *pretask.args],
                    cwd=Path(request.project_path),
                    env=env,
                    merge=True,
                    retain=scope is not None,
                    stream_limit=WORKER_STREAM_LINE_LIMIT,
                )
                if scope is not None:
                    scope.retain_desktop_process(process.stop)
            else:
                process = await create_subprocess(
                    pretask.executable,
                    *pretask.args,
                    cwd=request.project_path,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=creationflags,
                )
            self._process = process
            self._process_desktop = desktop is not None
            # 输出按行实时进运行日志（以前 communicate() 要等进程结束才一次性写出）；末尾
            # 若干行另留一份，失败时从里面摘原因。
            tail: list[str] = []

            def write_line(text: str, tail: list[str] = tail) -> None:
                tail.append(text)
                if len(tail) > 200:
                    del tail[:-200]
                self._log(f"[运行前设置] {text}")

            # 打码放在 pump 里做：detach 之后改写后端日志的输出也要过同一套打码
            pump = _PretaskOutputPump(
                write_line,
                redact=lambda line: redact_secret_text(line, secret_variants),
            )
            reader = asyncio.create_task(pump.run(process.stdout))
            timed_out = False
            held = False
            try:
                exited = await _wait_pretask_exit(process, deadline - loop.time())
                if not exited:
                    timed_out = True
                    self._log(
                        f"运行前设置 {display_name} 运行了 "
                        f"{int(loop.time() - started_at)} 秒仍未结束，运行前设置合计已用 "
                        f"{int(loop.time() - pretasks_started_at)} 秒，超过单次运行时间限制"
                        f"（{limit_minutes} 分钟），结束它（它启动的游戏 / 启动器不受影响）",
                        warning=True,
                    )
                    await self.stop()
            except asyncio.CancelledError:
                # 停止：进程由调用方经 ``stop`` 结束；输出交给后台读完，不在这里等。
                pump.detach(display_name)
                _keep_pretask_drain(reader)
                raise
            finally:
                if process.returncode is not None and self._process is process:
                    self._process = None

            try:
                done, _ = await asyncio.wait(
                    {reader}, timeout=_PRETASK_OUTPUT_DRAIN_SECONDS
                )
            except asyncio.CancelledError:
                pump.detach(display_name)
                _keep_pretask_drain(reader)
                raise
            if reader in done:
                if not reader.cancelled() and reader.exception() is not None:
                    logger.warning(
                        f"读取运行前设置 {display_name} 的输出失败: {reader.exception()}"
                    )
            else:
                # 还没换行的半行不在这里写出（可能是被拆开的密码前半段），留着和之后的
                # 输出拼成整行、打码后写后端日志
                held = pump.detach(display_name)
                _keep_pretask_drain(reader)
                self._log(
                    f"运行前设置 {display_name} 已退出，但输出管道仍被它启动的程序"
                    "（多半是游戏或启动器）占用，不再等待之后的输出"
                    + (
                        "；最后一行还没换行，输出完整后连同之后的输出写进后端日志"
                        if held
                        else ""
                    )
                )
            detail = "\n".join(tail).strip()
            if timed_out:
                raise MaaFWPretaskError(
                    f"运行前设置「{display_name}」超时（运行前设置合计超过单次运行时间限制 "
                    f"{limit_minutes} 分钟仍未结束，已结束）"
                )
            if process.returncode != 0:
                self._log(
                    f"运行前设置 {display_name} 执行失败（退出码 {process.returncode}）",
                    warning=True,
                )
                # 半行还留在缓冲里时，tail 的最后一行是更早的输出（可能是「成功」那一行），
                # 不拿它冒充失败原因；半行本身也不写（可能是密码前半段）
                reason = (
                    "最后一行输出还没换行，完整内容稍后写进后端日志"
                    if held
                    else _pretask_failure_reason(detail)
                )
                raise MaaFWPretaskError(f"运行前设置「{display_name}」失败：{reason}")
            self._log(f"运行前设置完成: {display_name}")

    async def stop(self) -> None:
        """结束正在跑的 pretask 及其脚本解释器后代（超时、停止时）；没有在跑的就什么都不做。"""

        # 清理放进独立任务、用 shield 等：超时分支正在清理时用户点了停止（调用方被取消），
        # 清理照样做完；随后进来的停止会等同一个清理任务，而不是看到
        # _process 已清空就直接返回，留下没结束的 pretask 或脚本子进程。
        cleanup = self._cleanup
        if cleanup is None or cleanup.done():
            process = self._process
            desktop = self._process_desktop
            self._process = None
            if process is None or process.returncode is not None:
                return
            self._stopping = process
            self._stopping_desktop = desktop
            cleanup = asyncio.create_task(
                _kill_pretask_process(process, self._log, desktop=desktop)
            )
            self._cleanup = cleanup
            # 进程核对可能仍在 to_thread() 中。统一取消仅可打断等待，
            # 不能取消真正负责清理的任务，否则后续释放预约永远等不到。
            scope = current_process_scope.get()
            if scope is not None:
                scope.retain_worker(cleanup)
        await asyncio.shield(cleanup)


# ---------------------------------------------------------------------------
# 进程退出与结束
# ---------------------------------------------------------------------------


def _snapshot_pretask_script_descendants(pid: int) -> list[tuple[int, float, str]]:
    """运行前设置进程下面、要随它一起结束的脚本解释器后代：``(pid, 创建时间, 进程名)``。

    从 pretask 进程往下走，只认 ``_PRETASK_SCRIPT_HOST_NAMES`` 里的脚本解释器（python、cmd、
    powershell……），并且只穿过它们继续往下：pretask 直接或经脚本间接起的游戏、启动器
    不在名单里，它们自己再起的任何进程（哪怕也是 python）都不会走到。宁可少结束，
    不误杀本应继续运行的游戏。
    """

    found: list[tuple[int, float, str]] = []
    try:
        pending = list(psutil.Process(pid).children())
    except psutil.Error:
        return []
    while pending:
        child = pending.pop()
        try:
            name = child.name()
            if name.casefold() not in _PRETASK_SCRIPT_HOST_NAMES:
                continue
            found.append((child.pid, child.create_time(), name))
            pending.extend(child.children())
        except psutil.Error:
            continue
    return found


async def _wait_pretask_exit(process: Any, timeout: float) -> bool:
    """等运行前设置进程退出，返回是否在 ``timeout`` 秒内退出。

    只看退出码，不用 ``process.wait()``：asyncio 的 wait() 要等输出管道全部关闭才返回，
    pretask 拉起的游戏 / 启动器继承了管道句柄时，它会一直等到游戏退出。
    """

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(timeout, 0.0)
    while process.returncode is None:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(_PRETASK_EXIT_POLL_SECONDS, remaining))
    return True


async def _kill_pretask_process(
    process: Any, append_log: Callable[[str], None], *, desktop: bool
) -> None:
    """结束运行前设置进程本身，以及它下面一路都是脚本解释器的后代。"""

    # 先记下要一起结束的脚本解释器后代（pretask 一死，按父子关系就查不到了）。只认
    # 一路都是脚本解释器的那一支：游戏 / 启动器以及它们起的进程都不在其中。
    scripts = await asyncio.to_thread(_snapshot_pretask_script_descendants, process.pid)
    # 不用 process.wait()：它要等输出管道关闭才返回，继承了管道的游戏不退它就不返回。
    try:
        if process.returncode is None:
            if not desktop:
                process.terminate()
            elif target := managed_process(process.pid):
                terminate_process(target)
        if not await _wait_pretask_exit(process, 5):
            if not desktop:
                process.kill()
            else:
                await process.stop()
            if not await _wait_pretask_exit(process, 5):
                logger.warning(
                    f"MaaFW 运行前设置进程（pid {process.pid}）强制结束后 5 秒仍未退出"
                )
    except ProcessLookupError:
        pass
    except Exception as exc:
        logger.warning(f"MaaFW 运行前设置进程清理失败: {exc}")

    if scripts:
        names = "、".join(f"{name}（pid {pid}）" for pid, _created, name in scripts)
        append_log(
            f"一并结束运行前设置启动的脚本进程：{names}；它启动的游戏 / 启动器不受影响"
        )
        await asyncio.to_thread(
            terminate_process_snapshot,
            [(pid, created) for pid, created, _name in scripts],
            owner="MaaFW 运行前设置",
        )


# ---------------------------------------------------------------------------
# 输出泵
# ---------------------------------------------------------------------------


class _PretaskOutputPump:
    """把运行前设置的输出按行交给 ``sink``（stdout 与 stderr 已合并）。

    按块读、自己分帧：``readline()`` 遇到超过 64 KB 的一行会抛错。行尾与原来整段
    ``splitlines()`` 同口径：``\\n``、单独的 ``\\r``（进度条原地刷新）、``\\r\\n`` 各算一次
    换行；``\\r`` 一到就把这一段交出去（进度实时可见），紧跟着的 ``\\n``（哪怕在下一块里）
    并进同一个换行。每行单独解码（与原来整段解码同一套编码顺序），先过 ``redact`` 打码
    再交出去。空白行与原来整段 ``strip()`` 后逐行写的口径一致：开头和结尾的空白行不写，
    夹在中间的照写。

    **打码边界**：只有遇到行尾（或 EOF，此时剩下的就是完整的最后一行）的段落才算完整
    片段，打码后交出；还没到行尾的部分一直留在缓冲里，不单独发布——密码可能正好被拆在
    两次读之间，两段各自做整串替换都匹配不上，拼起来就是明文。进程退出后管道还被别的
    程序占着时，``detach`` 只切换 sink：缓冲里的半行留着，和之后的输出拼成完整一行、
    打码后改写后端日志，读到 EOF 为止。
    """

    def __init__(
        self,
        sink: Callable[[str], None],
        *,
        redact: Callable[[str], str] = lambda line: line,
    ) -> None:
        self._sink = sink
        self._redact = redact
        self._pending = b""
        # 上一块以 \r 结尾、那一段已经交出：下一块开头的 \n 是同一个 \r\n，吞掉
        self._after_cr = False
        self._seen_text = False
        self._blank_lines = 0

    async def run(self, stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                break
            self._feed(chunk)
        # EOF：之后不会再有输出，剩下的就是完整的最后一行
        pending, self._pending = self._pending, b""
        if pending:
            self._emit_line(pending)

    def _feed(self, chunk: bytes) -> None:
        if self._after_cr and chunk.startswith(b"\n"):
            chunk = chunk[1:]
        self._after_cr = False
        # 缓冲里没有行尾（有就已经交出了），只需在新块里找
        start = 0
        for match in _PRETASK_LINE_END_RE.finditer(chunk):
            self._emit_line(self._pending + chunk[start : match.start()])
            self._pending = b""
            start = match.end()
        self._after_cr = start == len(chunk) and chunk.endswith(b"\r")
        self._pending += chunk[start:]

    def detach(self, display_name: str) -> bool:
        """之后的输出改写后端日志；返回缓冲里是否有还没到行尾、留待拼接的半行。"""

        def to_backend_log(line: str) -> None:
            logger.info(f"[运行前设置 {display_name} 退出后的输出] {line}")

        self._sink = to_backend_log
        # 只剩空白或颜色 / 光标控制码的尾巴（很多命令行程序退出前补一个不带换行的复位码）
        # 不算半行：它不含报错正文，失败原因照常从已写出的行里摘
        visible = _PRETASK_TAIL_NOISE_RE.sub(
            "", decode_subprocess_output(self._pending)
        )
        return bool(visible.strip())

    def _emit_line(self, raw: bytes) -> None:
        text = decode_subprocess_output(raw)
        if not text.strip():
            # 空白行先记数：后面还有内容才补写（夹在中间），到结尾都没有就不写
            if self._seen_text:
                self._blank_lines += 1
            return
        for _ in range(self._blank_lines):
            self._sink("")
        self._blank_lines = 0
        self._seen_text = True
        # 先对整段打码再去尾空白：密码可以以空白结尾，先去尾空白会把它截短而匹配不上
        self._sink(self._redact(text).rstrip())


def _keep_pretask_drain(reader: asyncio.Task[None]) -> None:
    """让读管道的任务在后台读到 EOF（见 ``_PRETASK_BACKGROUND_DRAINS``）。"""

    if reader.done():
        return
    _PRETASK_BACKGROUND_DRAINS.add(reader)

    def finished(task: asyncio.Task[None]) -> None:
        _PRETASK_BACKGROUND_DRAINS.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning(f"后台读取运行前设置输出失败: {task.exception()}")

    reader.add_done_callback(finished)


# ---------------------------------------------------------------------------
# 失败原因
# ---------------------------------------------------------------------------


_PRETASK_LOG_HEADER_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\s+"
    r"(?:TRC|DBG|INF|WRN|ERR|FTL|PNC|TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+"
    r"(?:.+?:\d+\s+>\s*)?(?P<body>.+)$"
)
_PRETASK_LOG_FIELD_RE = re.compile(
    r"""(?:^|\s)(?P<key>[A-Za-z_][\w.-]*)=(?P<value>"(?:\\.|[^"\\])*"|'[^']*'|\S+)"""
)


def _pretask_failure_reason(output: str) -> str:
    """只简化认得出的结构化日志；其余输出去色后原样保留。"""

    line = next(
        (
            cleaned
            for raw in reversed(output.splitlines())
            if (cleaned := clean_framework_output(raw).strip())
        ),
        "",
    )
    if not line:
        return "没有输出错误详情"
    match = _PRETASK_LOG_HEADER_RE.fullmatch(line)
    if match is None:
        return line
    body = match["body"]
    fields = list(_PRETASK_LOG_FIELD_RE.finditer(body))
    if not fields:
        return body
    reason = body[: fields[0].start()].rstrip()
    for field_match in fields:
        if field_match["key"] != "error":
            continue
        value = field_match["value"]
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif value.startswith("'"):
            value = value[1:-1]
        if value:
            # 只有字段没有正文时，error 的值本身就是原因，不再套括号
            reason = f"{reason}（{value}）" if reason else value
    return reason or line


__all__ = [
    "MaaFWPretaskError",
    "MaaFWPretaskRunRequest",
    "MaaFWPretaskRunner",
    "pretask_display_name",
    "pretasks_need_rerun",
]
