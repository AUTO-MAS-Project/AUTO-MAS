"""Win32 桌面游戏的启停：MAS 拉起 / 接管游戏、等窗口、前置，收尾时关掉 MAS 开的那份。

运行这一块（三个专项的账号流程都用它）。它就是一台「设备」：一个账号一份
``MaaFWDesktopGame``，状态（开没开过、游戏刚启动的时刻、链接拉起的时刻、临时改过的 Unity 分辨率、
AttachOnly 兜底关闭的分界）全是它自己的、跨尝试保留；什么时候开、什么时候关由流程决定。

- **只收普通数据**：配置里的原值由流程在每个调用点现取，装进 ``MaaFWDesktopGameSpec``；interface 的
  控制器模型、桌面分身目标（``desktop_process_target.get()``）作参数传入。不读脚本 / 账号配置，不碰调用方。
- **输出只有两条路**：返回值，与 ``plan_run`` 同形的事件出口（``MaaFWPlanRunSink``）——账号日志一行
  （``MaaFWPlanRunLog``，失败类的 ``warning`` 为真）、运行进度点（``MaaFWPlanRunPoint``：``start_game`` 的
  entered / succeeded / failed / cancelled 与 ``run_flow.operation`` 同义，``stop_game`` 照原来的先后）。
  只进 app.log 的行仍记在「MaaFW 插件自动代理」下。
- 「不是 Win32 就不管」留在流程里；``opened`` 与「是不是 MAS 管启动」的判断在这里。
- ``started_at``（首任务闸门的起算时刻）只在游戏是刚启动的时候置：MAS 拉起后等出窗口、接管时窗口是
  等出来的、链接拉起后等出窗口；``close`` 里清空。流程下发计划时 Win32 用它。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil

from app.task.client import ClientProcess
from app.task.MaaFW.tools.core.controller_win32.service import (
    controller_has_window_rules,
)
from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.utils import ProcessInfo, get_logger
from app.utils.common.game_resolution import UnityGameResolutionOverride
from app.utils.common.process.operations import (
    iter_processes,
    managed_process,
    terminate_process,
)
from app.utils.common.process.session import desktop_process_target

from .device_config import (
    find_controller,
    list_desktop_window_matches,
    match_controller_windows,
    match_windows_in_session,
    optional_int,
)
from .plan_run import MaaFWPlanRunLog, MaaFWPlanRunPoint, MaaFWPlanRunSink

if TYPE_CHECKING:
    from app.task.run_flow import PointState, RunStage

# 与任务类同一个名字：后端日志里这段流程的行照旧记在「MaaFW 插件自动代理」下
logger = get_logger("MaaFW 插件自动代理")

# 启动/附着游戏后定位其窗口的等待秒数
WINDOW_SEARCH_TIMEOUT_SECONDS = 5.0
# Game.WaitTime 填 0 时等游戏窗口出现的上限（秒）
_WINDOW_READY_FALLBACK_SECONDS = 60
# URL 模式打开链接后找游戏进程的最短时限（秒）：Steam 冷启动要先起客户端再拉游戏
_URL_LAUNCH_MIN_TIMEOUT_SECONDS = 60
# 按创建时间认「本次运行期间打开的进程」时的容差（秒），与 ProcessManager.search_process 一致
_PROCESS_CREATE_TIME_TOLERANCE_SECONDS = 2.0
# 兜底关闭进程时 terminate 之后等它自己退出的秒数，到点仍在就 kill
_PROCESS_TERMINATE_GRACE_SECONDS = 3.0


@dataclass(frozen=True)
class MaaFWDesktopGameSpec:
    """桌面游戏启停用到的配置原值，流程在每个调用点现取。

    - ``launch_mode``：``Game.LaunchMode``，DirectExe / URL / AttachOnly（``str(值 or "DirectExe").strip()``）；
    - ``game_path``：客户端绑定的游戏 exe（``client_executable_path``，空串为 None）：DirectExe 下 MAS 启动它，
      URL / AttachOnly 下只用来认出游戏；
    - ``launcher_path``：AttachOnly 下可选的启动器 exe，MAS 兜底关闭时一并关它；
    - ``url``：``Game.URL`` 去空白；``arguments``：``Game.Arguments`` 原值；``wait_seconds``：``Game.WaitTime`` 原值；
    - ``unity_resolution``：``Game.UnityResolution`` 选了尺寸就是 (宽, 高)，Off 为 None；
    - ``close_mode``：``Game.CloseMode``（``str(值 or "OnFailure").strip()``）；``configured_hwnd``：``Device.HWnd`` 原值。
    """

    launch_mode: str
    game_path: Path | None
    launcher_path: Path | None
    url: str
    arguments: Any
    wait_seconds: Any
    unity_resolution: tuple[int, int] | None
    close_mode: str
    configured_hwnd: Any


def desktop_launch_managed(spec: MaaFWDesktopGameSpec) -> bool:
    """MAS 是否负责启动/关闭游戏。

    三种模式：DirectExe（默认；MAS 按 exe 启动，结束后由 MAS 关闭）、URL（MAS 打开
    链接拉起游戏，游戏 exe 只用来认出它，结束后同样由 MAS 关闭）与 AttachOnly（脚本或
    用户自己启动，MAS 只接管窗口；结束后关不关看 ``Game.CloseMode``，见
    ``MaaFWDesktopGame.close_after_run``）。
    """

    return spec.launch_mode != "AttachOnly"


def describe_desktop_launch_error(spec: MaaFWDesktopGameSpec) -> str | None:
    """MAS 负责启动游戏时缺了什么配置；不缺返回 None。会读盘，调用方放在工作线程里。"""

    game_path = spec.game_path
    if spec.launch_mode == "URL":
        if not spec.url:
            return "启动方式为通过链接启动，请在托管管理页填写启动链接"
        if game_path is None or not game_path.is_file():
            return "启动方式为通过链接启动，请在托管管理页选择游戏 exe（用来识别和关闭游戏）"
        return None
    if game_path is None or not game_path.is_file():
        return (
            "当前 MaaFW controller 需要由 MAS 启动游戏，请在托管管理页选择实际游戏 exe"
        )
    return None


def desktop_close_wanted(
    spec: MaaFWDesktopGameSpec, *, controller_type: str | None, failed: bool
) -> bool:
    """AttachOnly 下最终收尾要不要由 MAS 兜底关闭（``Game.CloseMode``）。"""

    if spec.launch_mode != "AttachOnly":
        return False
    if controller_type != "Win32":
        return False
    mode = spec.close_mode
    return mode == "Always" or (mode == "OnFailure" and failed)


class MaaFWDesktopGame:
    """一个账号这次运行的桌面游戏：开、等窗口、前置、关。"""

    def __init__(self, emit: MaaFWPlanRunSink, *, process: Any | None = None) -> None:
        self._emit = emit
        self.process = process if process is not None else ClientProcess()
        #: MAS 这次开了游戏（DirectExe 拉起、URL 打开了链接）；收尾与重试据此关
        self.opened = False
        #: 本轮游戏刚启动的单调时钟时刻，据此算首个任务的最早下发时刻。只在游戏是刚启动的才记：
        #: 窗口出现那一刻（MAS 拉起、或接管时等到窗口冒出来）。None 表示游戏早就在跑。
        self.started_at: float | None = None
        # 启动游戏前临时改写的 Unity 注册表分辨率，游戏关闭后恢复；None 表示没改
        self._resolution_override: UnityGameResolutionOverride | None = None
        # URL 模式本轮打开链接的时刻（epoch 秒）：Steam 拉起的游戏不是 MAS 的子进程、还可能
        # 自我重启换 PID，关游戏时据此兜底结束这之后出现的同 exe 进程。None 表示没经链接拉起
        self._launched_at: float | None = None
        # URL 模式本次运行**第一次**打开链接的时刻：重试之间不清，只在最终收尾用完清空。
        # Steam 冷启动 / 更新超过等待时限时，游戏会在 MAS 放弃之后才出现，下一轮又按「已在
        # 运行」接管、不算 MAS 开的；收尾按它再扫一遍，MAS 拉起的游戏不会留在外面
        self._url_first_launched_at: float | None = None
        # 本账号这次运行开始的时刻（epoch 秒，第一次尝试的运行前设置之前）：AttachOnly 下由
        # MAS 兜底关闭时只关这之后才出现的进程，收尾做过一次就清空（见 _close_attached_game）
        self._run_started_at: float | None = None

    def mark_run_started(self, at: float) -> None:
        """AttachOnly 兜底关闭的分界：之后才出现的游戏 / 启动器才算本次运行打开的。"""

        self._run_started_at = at

    def _log(self, message: str, *, warning: bool = False) -> None:
        self._emit(MaaFWPlanRunLog(message, warning))

    def _point(self, stage: RunStage, state: PointState = "entered") -> None:
        self._emit(MaaFWPlanRunPoint(stage, state))

    @contextmanager
    def _operation(self, stage: RunStage) -> Iterator[None]:
        """同 ``run_flow.operation``：只包以异常表示失败的动作。"""

        self._point(stage)
        try:
            yield
        except asyncio.CancelledError:
            self._point(stage, "cancelled")
            raise
        except Exception:
            self._point(stage, "failed")
            raise
        else:
            self._point(stage, "succeeded")

    async def ensure_started(
        self,
        spec: MaaFWDesktopGameSpec,
        *,
        interface: MaaFWInterface | None,
        controller_name: str | None,
        desktop: Any,
    ) -> None:
        """由 MAS 负责启动/激活桌面游戏客户端，供后续窗口解析使用（调用方只在 Win32 下调）。"""

        if self.opened:
            return
        if not desktop_launch_managed(spec):
            # AttachOnly：游戏由脚本或用户自己起，MAS 只负责找窗口。窗口找不到时
            # device_config.resolve_window_handle 会给出「未找到匹配 MaaFW Win32 controller
            # 的窗口」，比在这里索要一个本模式用不上的 exe 更贴题。
            return

        config_error = await asyncio.to_thread(describe_desktop_launch_error, spec)
        game_path = spec.game_path
        if config_error is not None or game_path is None:
            raise RuntimeError(
                config_error
                or "当前 MaaFW controller 需要由 MAS 启动游戏，请在托管管理页选择实际游戏 exe"
            )

        if interface is not None:
            controller = find_controller(interface, controller_name)
            matches = await match_windows_in_session(controller)
            if matches:
                selected = matches[0]
                self._log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                self._note_resolution_override_skipped(spec)
                self._note_launch_arguments_skipped(spec)
                await self._activate_window(game_path)
                return

        if await asyncio.to_thread(_is_process_path_running, game_path):
            # 走账号日志（它同样写 app.log）：直接改 script_info.log 会整块替换日志
            # 窗口，这一行也不进账号日志与 history，下一条日志一来就没了。
            self._log(
                f"检测到游戏进程已在运行，跳过由 MAS 重复启动游戏: {game_path.name}"
            )
            self._note_resolution_override_skipped(spec)
            self._note_launch_arguments_skipped(spec)
            if await self._wait_ready(
                spec,
                game_path,
                interface=interface,
                controller_name=controller_name,
                desktop=desktop,
            ):
                # 进程在、窗口是等出来的：游戏正在启动，和 MAS 自己拉起的一样要等画面
                self.started_at = time.monotonic()
            await self._activate_window(game_path)
            return

        if spec.launch_mode == "URL":
            with self._operation("start_game"):
                await self._launch_by_url(
                    spec,
                    game_path,
                    interface=interface,
                    controller_name=controller_name,
                    desktop=desktop,
                )
            await self._activate_window(game_path)
            return

        game_arguments = shlex.split(str(spec.arguments or "").strip())
        logger.info(f"启动游戏: {game_path} - {spec.arguments}")
        # 注册表必须在进程起来之前改好：Unity 播放器只在启动时读一次这些值
        await self._apply_resolution_override(spec, game_path)
        try:
            with self._operation("start_game"):
                await self.process.open_process(
                    game_path,
                    *game_arguments,
                    cwd=game_path.parent,
                    breakaway=True,
                )
                # 进程一起来就算 MAS 开的：等窗口时被停止（CancelledError 不是 Exception，
                # 下面接不住），收尾的 close 要看到它才会关游戏。
                self.opened = True
                await self._wait_ready(
                    spec,
                    game_path,
                    interface=interface,
                    controller_name=controller_name,
                    desktop=desktop,
                )
            self.started_at = time.monotonic()
        except Exception:
            self.opened = False
            with suppress(Exception):
                await self.process.kill()
            await self._restore_resolution_override()
            raise

        await self._activate_window(game_path)

    async def _launch_by_url(
        self,
        spec: MaaFWDesktopGameSpec,
        game_path: Path,
        *,
        interface: MaaFWInterface | None,
        controller_name: str | None,
        desktop: Any,
    ) -> None:
        """URL 模式：打开链接拉起游戏，再按游戏 exe 找到本次启动后出现的进程、等窗口。

        游戏不是 MAS 的子进程（Steam 等转一手），只能按 exe + 创建时间认；``Game.Arguments``
        不用，参数要写进链接。Steam 冷启动慢，找进程的时限不少于
        ``_URL_LAUNCH_MIN_TIMEOUT_SECONDS``。
        """

        url = spec.url
        timeout = max(int(spec.wait_seconds or 0), _URL_LAUNCH_MIN_TIMEOUT_SECONDS)
        logger.info(f"通过链接启动游戏: {url} - {game_path}")
        # 注册表必须在进程起来之前改好：Unity 播放器只在启动时读一次这些值
        await self._apply_resolution_override(spec, game_path)
        launched_at = time.time()
        try:
            await _open_launch_url(url)
        except Exception as exc:
            # 被停止（取消）时不在这里恢复：收尾的 close 见 opened 为假也会恢复
            await self._restore_resolution_override()
            raise RuntimeError(f"无法打开启动链接 {url}: {exc}") from exc
        # 链接一打开就算 MAS 开的（同 DirectExe）：之后等不到、被停止，收尾都要关
        self.opened = True
        self._launched_at = launched_at
        if self._url_first_launched_at is None:
            self._url_first_launched_at = launched_at
        self._log(
            f"已打开启动链接，等待游戏进程启动（最多 {timeout}s）: {game_path.name}"
        )
        try:
            try:
                await self.process.search_process(
                    ProcessInfo(exe=str(game_path.resolve())),
                    timeout,
                    min_create_time=launched_at,
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    f"打开启动链接后 {timeout}s 内没有等到游戏进程: {game_path.name}"
                ) from exc
            await self._wait_ready(
                spec,
                game_path,
                interface=interface,
                controller_name=controller_name,
                desktop=desktop,
            )
            self.started_at = time.monotonic()
        except Exception:
            await self.close(spec)
            raise

    def _note_resolution_override_skipped(self, spec: MaaFWDesktopGameSpec) -> None:
        """游戏已在运行时不能中途改分辨率，选了尺寸的用户要知道这轮没改。"""

        if spec.unity_resolution is not None:
            self._log("检测到游戏已在运行，本轮不会中途修改分辨率")

    def _note_launch_arguments_skipped(self, spec: MaaFWDesktopGameSpec) -> None:
        """游戏已在运行时不会重复启动，配了启动参数的用户要知道这轮没生效。"""

        if spec.launch_mode == "URL":
            # URL 模式本来就不用启动参数（参数写在链接里）
            return
        arguments = str(spec.arguments or "").strip()
        if arguments:
            self._log(f"检测到游戏已在运行，本轮不会应用启动参数（{arguments}）")

    async def _apply_resolution_override(
        self, spec: MaaFWDesktopGameSpec, game_path: Path
    ) -> None:
        """按 exe 反查 Unity 注册表并临时写入所选尺寸的窗口模式。

        失败不阻断启动：这只是帮用户过脚本侧的分辨率闸门，改不成就按当前分辨率
        启动，闸门该报什么由脚本自己报，比在这里把整轮打掉更贴题。
        """

        target = spec.unity_resolution
        if target is None:
            return
        override = UnityGameResolutionOverride.for_executable(game_path, *target)
        if override is None:
            self._log(
                f"未找到 {game_path.name} 的 Unity app.info，无法反查注册表，"
                "跳过临时固定分辨率（只有 Unity 引擎的游戏支持）"
            )
            return
        # 先记下再写：写注册表在工作线程里，等它时被停止（取消）的话，收尾的
        # close 仍要能把它恢复回去
        self._resolution_override = override
        try:
            await asyncio.to_thread(override.apply)
        except Exception as exc:
            self._resolution_override = None
            logger.warning(f"MaaFW 临时固定游戏分辨率失败: {exc}")
            self._log(f"临时固定游戏分辨率失败，按当前分辨率启动: {exc}")
            return
        self._log(
            f"已尝试把 HKCU\\{override.registry_path} 的分辨率临时设为 "
            f"{override.label} 窗口模式，游戏关闭后恢复原值"
        )

    async def _restore_resolution_override(self) -> None:
        override = self._resolution_override
        if override is None:
            return
        self._resolution_override = None
        try:
            restored = await asyncio.to_thread(override.restore)
        except Exception as exc:
            logger.warning(f"MaaFW 恢复游戏分辨率注册表失败: {exc}")
            self._log(f"恢复游戏分辨率注册表失败: {exc}")
            return
        if restored:
            self._log("已恢复启动前的游戏分辨率注册表")

    async def _wait_ready(
        self,
        spec: MaaFWDesktopGameSpec,
        game_path: Path,
        *,
        interface: MaaFWInterface | None,
        controller_name: str | None,
        desktop: Any,
        poll_interval: float = 1.0,
    ) -> bool:
        """等到游戏窗口（或配置了句柄时等到进程）就绪。

        返回窗口是不是**等出来的**：第一轮就在的算 False（游戏早就在跑），至少睡过
        一轮才出现的算 True（游戏正在启动）。调用方据此决定要不要再等画面稳定。
        """

        wait_time = max(0, int(spec.wait_seconds or 0))
        if wait_time <= 0:
            # 「等待时间」填 0 只表示不等画面稳定；窗口还是要等出来，否则刚拉起的游戏
            # 当场判「窗口未就绪」、被关掉重试，次次如此
            wait_time = _WINDOW_READY_FALLBACK_SECONDS
        if interface is None:
            raise RuntimeError("MaaFW 运行计划未完成初始化")

        explicit_hwnd = optional_int(spec.configured_hwnd)
        controller = find_controller(interface, controller_name)

        self._log(
            f"正在等待游戏客户端窗口就绪，最大等待时间 {wait_time}s: {game_path.name}"
        )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_time

        async def match_before_deadline():
            if desktop is None:
                return await match_windows_in_session(controller)
            try:
                async with asyncio.timeout_at(deadline):
                    return await match_windows_in_session(controller)
            except TimeoutError as exc:
                raise RuntimeError(
                    f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}"
                ) from exc

        waited = False
        process_detected = False
        while loop.time() < deadline:
            if not explicit_hwnd:
                matches = await match_before_deadline()
                if matches:
                    selected = matches[0]
                    self._log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return waited

            if await asyncio.to_thread(_is_process_path_running, game_path):
                if not process_detected:
                    self._log(f"检测到游戏进程已启动: {game_path.name}")
                    process_detected = True

                if explicit_hwnd:
                    self._log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                    return waited

                matches = await match_before_deadline()
                if matches:
                    selected = matches[0]
                    self._log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return waited

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(poll_interval, remaining))
            waited = True

        if desktop is not None:
            raise RuntimeError(f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}")

        if not explicit_hwnd:
            matches = await match_windows_in_session(controller)
            if matches:
                selected = matches[0]
                self._log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return True

        if await asyncio.to_thread(_is_process_path_running, game_path):
            if explicit_hwnd:
                self._log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return True

            matches = await match_windows_in_session(controller)
            if matches:
                selected = matches[0]
                self._log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return True

            raise RuntimeError(f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}")

        raise RuntimeError(f"游戏进程在 {wait_time}s 内未启动: {game_path.name}")

    async def _activate_window(self, game_path: Path) -> None:
        try:
            # 第二个参数是**秒数**，不是截止时刻。dev 的 #473 把计时改成单调时钟后
            # 内部是 `time.monotonic() + timeout_seconds`，传 datetime 会直接
            # TypeError（真机上表现为「游戏进程已启动，但定位窗口失败」，窗口没被
            # 前置，随后第一个任务识别不到而失败）。
            await self.process.search_process(
                ProcessInfo(exe=str(game_path.resolve())),
                WINDOW_SEARCH_TIMEOUT_SECONDS,
                owned=self.opened,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 定位游戏进程窗口失败: {exc}")
            self._log(f"游戏进程已启动，但定位窗口失败: {exc}")
            return

        activate_end_time = datetime.now() + timedelta(seconds=5)
        while datetime.now() < activate_end_time:
            if await self.process.activate_window():
                self._log("游戏窗口已置于前台")
                return
            await asyncio.sleep(0.5)

        self._log("游戏窗口前置失败，将继续启动 MaaFW 任务")

    async def close(self, spec: MaaFWDesktopGameSpec) -> bool:
        """关闭由 MAS 启动的游戏，返回是否关成（本来就没开过算关成）。

        只看 ``opened``：由 MAS 启动的（DirectExe、URL）一律关，其他方式启动（AttachOnly、
        或发现游戏已在运行而没重复启动）的这里不碰——AttachOnly 的兜底关闭只在最终收尾做，
        见 ``close_after_run``。URL 模式另按游戏 exe 兜底扫一遍：游戏不是 MAS 的子进程，
        有的还会自我重启换 PID，跟踪的那一个关掉了不等于游戏关掉了。
        """

        if not self.opened:
            await self._restore_resolution_override()
            return True

        launched_at = self._launched_at
        closed = True
        self._point("stop_game")
        try:
            try:
                await self.process.kill()
            except Exception as exc:
                logger.warning(f"MaaFW 清理时关闭游戏失败: {exc}")
                closed = False
            else:
                if launched_at is not None:
                    # 链接拉起的游戏不是 MAS 的子进程，写一行让用户知道是 MAS 关的
                    self._log("已关闭本次通过链接打开的游戏")
            game_path = spec.game_path
            if launched_at is not None and game_path is not None:
                try:
                    if not await self._end_processes_started_since(
                        launched_at, exes=[game_path]
                    ):
                        closed = False
                except Exception as exc:
                    logger.warning(f"MaaFW 清理时关闭链接拉起的游戏失败: {exc}")
                    closed = False
            self._point("stop_game", "succeeded" if closed else "failed")
            return closed
        finally:
            self.opened = False
            self.started_at = None
            self._launched_at = None
            await self._restore_resolution_override()

    async def close_after_run(
        self,
        spec: MaaFWDesktopGameSpec,
        *,
        interface: MaaFWInterface | None,
        controller_name: str | None,
        controller_type: str | None,
        failed: bool,
        desktop: Any,
    ) -> None:
        """最终收尾关游戏：MAS 启动的照常关，AttachOnly 再按 ``Game.CloseMode`` 兜底。

        ``failed`` 为真表示本次运行没正常完成（失败、超时、停止、``on_crash``）。重试之间
        流程只调 ``close``，不经这里，AttachOnly 下不关。
        """

        await self.close(spec)
        await self._close_url_game_left_behind(spec)
        await self._close_attached_game(
            spec,
            interface=interface,
            controller_name=controller_name,
            controller_type=controller_type,
            failed=failed,
            desktop=desktop,
        )

    async def _close_url_game_left_behind(self, spec: MaaFWDesktopGameSpec) -> None:
        """URL 模式最终收尾：按本次运行第一次打开链接的时刻，再扫一遍同 exe 的进程。

        覆盖「等进程超时之后游戏才出现」：那一轮 close 时还没有进程可关，之后的
        尝试按「已在运行」接管（opened 为假），没有这一步就会留在外面。运行前就开着
        的游戏不会进 URL 分支（直接接管），所以这个时刻之后出现的同 exe 进程都是 MAS 拉起的。
        """

        since = self._url_first_launched_at
        self._url_first_launched_at = None
        game_path = spec.game_path
        if since is None or game_path is None:
            return
        try:
            await self._end_processes_started_since(since, exes=[game_path])
        except Exception as exc:
            logger.warning(f"MaaFW 收尾关闭链接拉起的游戏失败: {exc}")
            self._log(f"关闭游戏失败: {exc}", warning=True)

    async def _close_attached_game(
        self,
        spec: MaaFWDesktopGameSpec,
        *,
        interface: MaaFWInterface | None,
        controller_name: str | None,
        controller_type: str | None,
        failed: bool,
        desktop: Any,
    ) -> None:
        """AttachOnly 下由 MAS 兜底关闭本次运行期间打开的游戏与启动器。

        只关创建时间不早于本次运行开始（``mark_run_started``，容差 2s）的进程，运行前就开着的
        一律不碰。候选三路：控制器窗口匹配到的窗口所属进程、游戏 exe、启动器 exe。每次运行只做
        一次（做过即清空分界时刻），``on_crash`` 与正常收尾先后来时不会重复关、重复写日志。
        """

        since = self._run_started_at
        self._run_started_at = None
        if since is None or not desktop_close_wanted(
            spec, controller_type=controller_type, failed=failed
        ):
            return
        try:
            if desktop is not None and interface is not None:
                controller = find_controller(interface, controller_name)
                pids = {
                    int(row[3]) for row in await list_desktop_window_matches(controller)
                }
            else:
                pids = await asyncio.to_thread(
                    self._attached_game_window_pids, interface, controller_name
                )
            exes = [
                path
                for path in (spec.game_path, spec.launcher_path)
                if path is not None
            ]
            await self._end_processes_started_since(
                since, exes=exes, pids=pids, log_kept=True
            )
        except Exception as exc:
            logger.warning(f"MaaFW 收尾关闭游戏失败: {exc}")
            self._log(f"关闭游戏失败: {exc}", warning=True)

    @staticmethod
    def _attached_game_window_pids(
        interface: MaaFWInterface | None, controller_name: str | None
    ) -> set[int]:
        """控制器窗口匹配到的窗口所属进程；没有窗口规则、扫不了窗口时返回空集。"""

        if interface is None:
            return set()
        try:
            controller = find_controller(interface, controller_name)
            if not controller_has_window_rules(controller):
                return set()
            windows = match_controller_windows(controller)
        except Exception as exc:
            logger.warning(f"MaaFW 收尾查找游戏窗口失败: {exc}")
            return set()
        pids: set[int] = set()
        for window in windows:
            pid = _window_process_id(int(window.hWnd))
            if pid:
                pids.add(pid)
        return pids

    async def _end_processes_started_since(
        self,
        since: float,
        *,
        exes: list[Path],
        pids: set[int] | None = None,
        log_kept: bool = False,
    ) -> bool:
        """结束候选里创建时间不早于 ``since``（容差 2s）的进程，每个写一行运行日志。

        候选是 pid 在 ``pids`` 里、或 exe 等于 ``exes`` 之一的进程。``log_kept`` 为真时，
        运行前就在的候选也各写一行说明为什么不关。返回该关的是否都关掉了；没关掉的
        （多半是游戏以管理员身份运行、MAS 没有）写一行警告进运行日志。
        """

        closing, kept = await asyncio.to_thread(
            _find_processes_started_since, since, exes=exes, pids=pids or set()
        )
        if log_kept:
            for process in kept:
                self._log(f"{process.label} 在运行开始前就已打开，不关闭")
        if not closing:
            return True
        ended, failed = await asyncio.to_thread(_end_processes, closing)
        for process in ended:
            self._log(f"已关闭本次运行期间打开的 {process.label}")
        for process in failed:
            self._log(
                f"没能关闭 {process.label}，可能需要以管理员身份运行 AUTO-MAS",
                warning=True,
            )
        return not failed


def _is_process_path_running(executable_path: Path) -> bool:
    target_path = executable_path.resolve()
    for proc in iter_processes(["exe"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            raw_exe = proc.info.get("exe") or proc.exe()
            if raw_exe and Path(raw_exe).resolve() == target_path:
                return True
    return False


async def _open_launch_url(url: str) -> None:
    """用系统默认处理程序打开启动链接（Windows 上是 ShellExecute）。"""
    if (desktop := desktop_process_target.get()) is not None:
        from app.utils.windows.desktop_session.process_runner import open_in_desktop

        await open_in_desktop(desktop, url)
        return

    from app.utils import process_platform

    await process_platform.platform_process.open_protocol(url)


@dataclass(frozen=True)
class _ProcessSnapshot:
    """兜底关闭用的进程快照：exe 读不到时为空串，创建时间读不到时为 None。"""

    pid: int
    exe: str
    create_time: float | None

    @property
    def label(self) -> str:
        name = Path(self.exe).name if self.exe else "进程"
        return f"{name}（pid={self.pid}）"


def _normalized_exe(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _snapshot_processes() -> list[_ProcessSnapshot]:
    snapshots: list[_ProcessSnapshot] = []
    for proc in iter_processes(["pid", "exe", "create_time"]):
        info = proc.info
        snapshots.append(
            _ProcessSnapshot(
                pid=int(info.get("pid") or proc.pid),
                exe=str(info.get("exe") or ""),
                create_time=info.get("create_time"),
            )
        )
    return snapshots


def _window_process_id(hwnd: int) -> int | None:
    """窗口所属进程的 pid；拿不到（窗口已销毁、非 Windows）返回 None。"""

    try:
        import win32process

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None
    return int(pid) or None


def _find_processes_started_since(
    since: float, *, exes: list[Path], pids: set[int]
) -> tuple[list[_ProcessSnapshot], list[_ProcessSnapshot]]:
    """按 pid 或 exe 找候选，按创建时间分成（本次之后才出现的, 之前就在的）。

    创建时间读不到的算「之前就在」：宁可漏关，不误关用户自己开着的进程。本进程不算候选。
    """

    targets: set[str] = set()
    for path in exes:
        with suppress(OSError):
            path = path.resolve()
        targets.add(_normalized_exe(path))
    own_pid = os.getpid()
    closing: list[_ProcessSnapshot] = []
    kept: list[_ProcessSnapshot] = []
    for snapshot in _snapshot_processes():
        if snapshot.pid == own_pid:
            continue
        matched = snapshot.pid in pids or (
            bool(snapshot.exe) and _normalized_exe(snapshot.exe) in targets
        )
        if not matched:
            continue
        if (
            snapshot.create_time is not None
            and snapshot.create_time >= since - _PROCESS_CREATE_TIME_TOLERANCE_SECONDS
        ):
            closing.append(snapshot)
        else:
            kept.append(snapshot)
    return closing, kept


def _end_processes(
    targets: list[_ProcessSnapshot],
    grace_seconds: float = _PROCESS_TERMINATE_GRACE_SECONDS,
) -> tuple[list[_ProcessSnapshot], list[_ProcessSnapshot]]:
    """先 terminate，``grace_seconds`` 后仍在的 kill；返回（已结束的, 没能结束的）。

    结束前按创建时间再核一次：快照之后 pid 被别的进程复用了就不碰它（两边都不算）。
    已经自己退出的也不算失败。
    """

    started: dict[psutil.Process, _ProcessSnapshot] = {}
    failed: list[_ProcessSnapshot] = []
    for target in targets:
        try:
            proc = managed_process(target.pid, expected_create_time=target.create_time)
            if proc is None:
                continue
            if not terminate_process(proc):
                if proc.is_running():
                    logger.warning(f"MaaFW 未能结束进程: {target.label}")
                    failed.append(target)
                continue
        except psutil.NoSuchProcess:
            continue
        except ProcessLookupError:
            logger.warning(f"MaaFW 结束进程时无法确认目标归属: {target.label}")
            failed.append(target)
            continue
        except (psutil.AccessDenied, OSError) as exc:
            logger.warning(f"MaaFW 结束进程失败 {target.label}: {exc}")
            failed.append(target)
            continue
        started[proc] = target
    if not started:
        return [], failed
    _, alive = psutil.wait_procs(list(started), timeout=grace_seconds)
    for proc in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            terminate_process(proc, force=True)
    if alive:
        _, alive = psutil.wait_procs(alive, timeout=grace_seconds)
    for proc in alive:
        logger.warning(f"MaaFW 结束进程后仍在运行: {started[proc].label}")
        failed.append(started[proc])
    return [snapshot for proc, snapshot in started.items() if proc not in alive], failed


__all__ = [
    "WINDOW_SEARCH_TIMEOUT_SECONDS",
    "MaaFWDesktopGame",
    "MaaFWDesktopGameSpec",
    "desktop_close_wanted",
    "desktop_launch_managed",
    "describe_desktop_launch_error",
]
