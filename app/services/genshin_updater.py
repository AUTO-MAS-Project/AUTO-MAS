#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""由 MAS 自行完成原神客户端更新：查版本、下载、校验、落盘、写回版本号。

引擎在 :mod:`app.services.gi_updater`，全同步（urllib + 线程 + 阻塞文件 IO）；
本模块是它接到 MAS 上的那只手：把整轮流程挪出事件循环、把下载线程里的进度
快照翻译成一行行调度台日志、并在联网算出计划之后补三道只有宿主才该管的门。

三道门禁都不在引擎里，因为它们服务的是「别把用户的游戏和下不完的大包搞砸」：

- **混装目录**：官服与国际服的客户端不会共存于同一目录。目录里同时见得到两个
  可执行文件，说明这个路径填错了；再往下走就是往别人的安装目录里灌几十 GB。
- **只应用增量包**：拿不到增量差分包（全新安装、逐文件全量比对、预下载）就停手
  交给官方启动器——无人值守的调度任务绝不该顺手吃掉几十 GB 整包流量。
- **磁盘余量**：差分也可能不小，空间不够要提前停，不能让下载在半路写爆磁盘。

取消只来自更新时限：到点往中止标志里置位，下载线程在每个数据块边界协作式收工；
中止不回滚已落盘的合法文件，也不写 ``config.ini``，重开就是续传。时限到点算一次
任务失败（要用户先看一眼为什么没更上），不是静默放过。
"""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.services.gi_updater import create_updater
from app.services.gi_updater.api.profiles import get_profile
from app.services.gi_updater.common.progress import (
    ProgressBase,
    ProgressListener,
    ProgressSnapshot,
    summarize_size,
)
from app.services.gi_updater.errors import UpdateAborted
from app.services.gi_updater.install import UpdateKind
from app.utils import get_logger, sanitize_log_message
from app.utils.hpatchz import ensure_hpatchz

logger = get_logger("原神更新")

#: 一行面向用户的进度文案
ProgressHook = Callable[[str], Awaitable[None]]

#: 「自动」区服时的判定顺序；原神一个目录只可能装其中一个
_REGION_BY_LOCALE = (("官服", "cn"), ("国际服", "global"))
#: 游戏程序文件名 -> 区服短名；只认这两个，B服与官服同名 ``YuanShen.exe`` 不做区分
_EXECUTABLE_TO_REGION = {
    "yuanshen.exe": "cn",  # 官服 / B服（国服）
    "genshinimpact.exe": "global",  # 国际服
}
#: 判定「可执行文件是真的在那儿」的最小体积，与引擎口径一致
_MIN_EXECUTABLE_SIZE = 1 << 16
#: 磁盘余量在待下载体积之外再多留的缓冲
_DISK_MARGIN_BYTES = 2 * 1024**3
#: 进度行推送的最小间隔（秒）；阶段变化不受此限
_PROGRESS_INTERVAL_SEC = 1.0
#: 文案一字不动时的心跳间隔（秒）——证明还在干活，又不把调度台刷满
_PROGRESS_HEARTBEAT_SEC = 10.0
#: 同一目录两次联网检查的最短间隔；一轮调度里多个用户共用一个客户端，
#: 而一次检查要下载并解析几万条清单，重复付这个代价没有意义
_MEMO_TTL_SEC = 600.0
#: 目录 -> ``(上次成功的单调时刻, 结论)``；只记成功与「无需更新」
_fresh_cache: dict[str, tuple[float, GenshinUpdateResult]] = {}
_cache_lock = threading.Lock()

#: 计划类型 -> 面向用户的说法
_KIND_LABELS = {
    UpdateKind.SophonInstall.value: "全新安装",
    UpdateKind.SophonPatch.value: "增量更新",
    UpdateKind.SophonUpdate.value: "差异比对更新",
    UpdateKind.SophonPreload.value: "预下载下一版本",
    UpdateKind.Noop.value: "无需更新",
}


@dataclass(frozen=True)
class GenshinUpdateResult:
    """一轮原神客户端更新的结论。"""

    success: bool
    message: str
    #: 本轮什么都没做（已是最新，或被门禁/前置校验拦下）
    noop: bool = False
    #: 被调用方的中止信号打断
    aborted: bool = False
    local_version: str = ""
    remote_version: str = ""
    kind: str = UpdateKind.Noop.value
    download_size: int = 0
    file_count: int = 0


def _cached_result(key: str) -> GenshinUpdateResult | None:
    """取该目录在短时窗口内的成功结论。

    Args:
        key: 归一化后的游戏目录。

    Returns:
        可复用的结论；没有或已过期时返回 ``None``。
    """
    with _cache_lock:
        entry = _fresh_cache.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry[0] > _MEMO_TTL_SEC:
            _fresh_cache.pop(key, None)
            return None
        return entry[1]


def _remember(key: str, result: GenshinUpdateResult) -> None:
    """记住这次成功结论，供同一目录的短时复用。

    Args:
        key: 归一化后的游戏目录。
        result: 本轮结论。
    """
    with _cache_lock:
        _fresh_cache[key] = (time.monotonic(), result)


def _format_snapshot(snapshot: ProgressSnapshot) -> str:
    """把一份进度快照压成一行调度台文案。

    Args:
        snapshot: 引擎给出的快照。

    Returns:
        形如「下载中 42.1%（0.6/1.78 GiB） · 900/1151 个文件 · 12.3 MiB/s · 剩余 31:20」
        的单行文本；复核本地文件阶段没有字节可算，改成只报条数。
    """
    parts = [snapshot.activity or "下载中"]
    # 复核阶段一个字节都不从网络取，用字节百分比表达就是钉在 0%，看不出它在干活
    show_bytes = snapshot.total_size > 0 and snapshot.stage != "verify"
    if show_bytes:
        parts.append(
            f"{snapshot.percentage:.1f}%（{summarize_size(snapshot.current_size)}"
            f"/{summarize_size(snapshot.total_size)}）"
        )
    if snapshot.total_count > 0:
        parts.append(f"{snapshot.current_count}/{snapshot.total_count} 个文件")
    if snapshot.speed > 0:
        parts.append(f"{summarize_size(snapshot.speed)}/s")
        if snapshot.time_left > 0:
            left = int(snapshot.time_left)
            parts.append(f"剩余 {left // 60:02d}:{left % 60:02d}")
    if snapshot.file_name:
        parts.append(snapshot.file_name)
    return " · ".join(parts)


class _DispatchProgressListener(ProgressListener):
    """把引擎的进度快照接到宿主回调上（在引擎的下载线程里被调用）。

    引擎自带 0.25 秒的节流，但换文件与换阶段会强制穿透，密集起来足以刷爆
    调度台；这里再压一层，规则按「有没有新信息」判：

    - 阶段或活动文案变了：立刻发，这是用户最该看到的一刻；
    - 文案变了（字节、条数、速度在动）：最快每 :data:`_PROGRESS_INTERVAL_SEC` 发一条；
    - 文案一模一样（续传时复核本地文件，字节一动不动）：降到每
      :data:`_PROGRESS_HEARTBEAT_SEC` 一条心跳，只证明还活着，不刷屏。
    """

    def __init__(
        self,
        hook: ProgressHook | None,
        loop: asyncio.AbstractEventLoop,
        abort_event: threading.Event,
    ) -> None:
        """记录回调、目标事件循环与中止标志。

        Args:
            hook: 宿主的进度回调；``None`` 表示只走日志。
            loop: 回调所归属的事件循环（引擎线程要往这里投协程）。
            abort_event: 置位后不再往外发进度，避免收尾期还在刷日志。
        """
        self._hook = hook
        self._loop = loop
        self._abort_event = abort_event
        self._lock = threading.Lock()
        self._last_emit = 0.0
        self._last_activity = ""
        self._last_text = ""

    def on_progress(self, snapshot: ProgressSnapshot) -> None:
        """收到一份进度快照。

        Args:
            snapshot: 引擎的进度快照。
        """
        if self._hook is None or self._abort_event.is_set():
            return
        text = _format_snapshot(snapshot)
        now = time.monotonic()
        with self._lock:
            # 阶段一变立刻发；文案在动就按正常节奏；文案一字不动则只发心跳
            if snapshot.activity != self._last_activity:
                limit = 0.0
            elif text != self._last_text:
                limit = _PROGRESS_INTERVAL_SEC
            else:
                limit = _PROGRESS_HEARTBEAT_SEC
            if now - self._last_emit < limit:
                return
            self._last_emit = now
            self._last_activity = snapshot.activity
            self._last_text = text
        self._post(text)

    def on_message(self, message: str, level: str = "info") -> None:
        """引擎的一条流程消息，原样转成一行进度文案。

        Args:
            message: 消息正文。
            level: 级别名；只用于日志，调度台一律按一行文案处理。
        """
        text = str(message).strip()
        if not text or self._hook is None:
            return
        getattr(logger, level if hasattr(logger, level) else "info")(text)
        self._post(text)

    def _post(self, line: str) -> None:
        """把一行文案投进事件循环，不等结果。

        Args:
            line: 已经过打码的文案。
        """
        safe = sanitize_log_message(line)
        try:
            asyncio.run_coroutine_threadsafe(self._hook(safe), self._loop)
        except RuntimeError:  # 循环已关闭：任务收尾期常见，丢就丢了
            logger.debug("进度回调已失效，丢弃一行: {}", safe)


def detect_genshin_region(game_exe: str) -> str:
    """按游戏程序文件名判定区服，两个专项宿主共用这一份口径。

    Args:
        game_exe: 「游戏路径 / 游戏程序」里选的可执行文件路径；手改配置时可能带
            包裹引号，所以先清洗再取名比对。

    Returns:
        ``"cn"`` / ``"global"``；不是原神游戏程序时返回空串。
    """
    text = str(game_exe or "").strip().strip('"').strip()
    return _EXECUTABLE_TO_REGION.get(Path(text).name.lower(), "")


def _resolve_region(game_dir: Path, resource: str) -> str | None:
    """定下这次要按哪个区服的接口走。

    Args:
        game_dir: 游戏安装目录。
        resource: 配置里的区服（``自动`` / ``官服`` / ``国际服``）。

    Returns:
        ``cn`` 或 ``global``；``resource`` 为 ``自动`` 时按目录里在跑的那个可执行
        文件判定，判不出来（空目录按官服算）之外的情形返回 ``None``。
    """
    if resource != "自动":
        return "cn" if resource == "官服" else "global"

    found = [
        region
        for _, region in _REGION_BY_LOCALE
        if _executable_present(game_dir, get_profile(region))
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        # 目录里一个可执行文件都没有：要么是新装，要么填错了。新装按官服走，
        # 真填错了后续的状态判定会报「未安装」，体积守卫会先把它拦下来。
        return "cn"
    return None


def _executable_present(game_dir: Path, preset: Any) -> bool:
    """判断某区服的可执行文件是否真实存在于该目录。

    Args:
        game_dir: 游戏安装目录。
        preset: 该区服的预设，提供 ``executable_name``。

    Returns:
        文件存在且体积超过 :data:`_MIN_EXECUTABLE_SIZE` 时为真。
    """
    candidate = game_dir / str(preset.executable_name)
    try:
        return candidate.is_file() and candidate.stat().st_size > _MIN_EXECUTABLE_SIZE
    except OSError:
        return False


def _looks_like_genshin_install(game_dir: Path) -> bool:
    """目录里是否有个原神客户端的样子。

    Args:
        game_dir: 待检查的目录。

    Returns:
        存在 ``config.ini`` 或任一区服可执行文件时为真。
    """
    if (game_dir / "config.ini").is_file():
        return True
    return any(
        _executable_present(game_dir, get_profile(region))
        for _, region in _REGION_BY_LOCALE
    )


def _disk_has_room(game_dir: Path, needed: int) -> bool:
    """目标盘还剩多少空间够不够这次下载。

    Args:
        game_dir: 游戏安装目录。
        needed: 计划要落盘的字节数。

    Returns:
        余量不小于 ``needed`` 加缓冲时为真；读不出余量时按真处理，别拦正常更新。
    """
    try:
        free = shutil.disk_usage(game_dir).free
    except OSError:
        return True
    return free >= needed + _DISK_MARGIN_BYTES


async def update_genshin_client(
    game_path: str | Path,
    *,
    resource: str = "自动",
    time_limit_min: int = 0,
    on_progress: ProgressHook | None = None,
) -> GenshinUpdateResult:
    """检查并按需更新原神客户端，直到落盘完成。

    Args:
        game_path: 游戏安装目录（``config.ini`` 与可执行文件所在的那一级）。
        resource: 区服，``自动`` / ``官服`` / ``国际服``。
        time_limit_min: 本轮时限（分钟）；``0`` 表示不限。超时按中止处理，
            等下载线程真收干净了才返回。
        on_progress: 一行行进度文案的回调。

    Returns:
        :class:`GenshinUpdateResult`。任何异常都转成 ``success=False`` 的结论，
        不把 traceback 抛给调度侧。
    """
    # 时限到了就往这里置位；下载线程在每个数据块边界轮询它
    abort_event = threading.Event()
    key = str(Path(game_path)).casefold()
    cached = _cached_result(key)
    if cached is not None:
        # 常态复用：只留 app.log 一行，不刷任务日志
        _note(
            f"{int(_MEMO_TTL_SEC // 60)} 分钟内已确认过原神客户端是最新的，本轮跳过检查"
        )
        # 复用上次的结论不等于这次又更新了一遍：按「无事发生」返回，
        # 否则任务日志会再报一次「更新完成」，用户以为又下了几十 GB
        return replace(cached, noop=True)

    runner = asyncio.create_task(
        _run_update(
            game_path,
            resource=resource,
            on_progress=on_progress,
            abort_event=abort_event,
        )
    )
    if time_limit_min > 0:
        try:
            # shield：超时不能直接掐掉协程 —— 下载线程还在写盘，
            # 只能置位后由引擎在下一个下载边界协作式收工
            result = await asyncio.wait_for(asyncio.shield(runner), time_limit_min * 60)
        except TimeoutError:
            await _report(
                on_progress, f"更新已超时（{time_limit_min} 分钟），正在停下当前下载..."
            )
            abort_event.set()
            result = await runner
    else:
        result = await runner

    if result.success:
        _remember(key, result)
    else:
        with _cache_lock:
            _fresh_cache.pop(key, None)
    return result


async def _run_update(
    game_path: str | Path,
    *,
    resource: str = "自动",
    on_progress: ProgressHook | None,
    abort_event: threading.Event,
) -> GenshinUpdateResult:
    """跑完一轮「算计划 -> 过门禁 -> 下载落盘」，同步引擎全程挪出事件循环。

    Args:
        game_path: 游戏安装目录。
        resource: 区服口径。
        on_progress: 进度回调。
        abort_event: 时限到点置位的中止标志；下载与打补丁在边界轮询它。

    Returns:
        本轮结论。
    """
    game_dir = Path(game_path)
    if not str(game_path).strip() or not game_dir.is_dir():
        message = f"游戏目录不存在：{game_path or '（未填）'}"
        _note(message)
        return GenshinUpdateResult(success=False, noop=True, message=message)

    def should_abort() -> bool:
        """引擎侧的中止判定：只看时限标志。"""
        return abort_event.is_set()

    resolved = _resolve_region(game_dir, resource)
    if resolved is None:
        message = "该目录里同时存在官服与国际服的可执行文件，请先确认游戏目录是否填错"
        _note(message)
        return GenshinUpdateResult(success=False, noop=True, message=message)

    if not _looks_like_genshin_install(game_dir):
        # 空目录不代表「要全新安装」，更可能是路径填错了。全新安装该由官方启动器做：
        # 让调度任务顺手往一个没装过游戏的目录里灌几十 GB，是不可挽回的浪费。
        message = f"该目录里没有原神客户端（缺 config.ini 与可执行文件）：{game_dir}"
        _note(message)
        return GenshinUpdateResult(success=False, noop=True, message=message)

    loop = asyncio.get_running_loop()
    listener = _DispatchProgressListener(on_progress, loop, abort_event)
    progress = ProgressBase(listener=listener)

    try:
        hpatchz = str(await ensure_hpatchz(on_progress=on_progress))
    except Exception as error:  # noqa: BLE001
        # 缺 hpatchz 只影响增量包；引擎会把它记成待处理项，不拦整轮更新
        logger.warning("获取增量补丁工具失败: {}", error)
        hpatchz = "hpatchz"

    updater = create_updater(
        resolved,
        str(game_dir),
        progress=progress,
        should_abort=should_abort,
        hdiff_executable=hpatchz,
    )

    # 走到哪儿都按「没成」起步：异常可能发生在赋值之前，收尾据此决定缓存留不留
    keep_cache = True
    try:
        # 第一步只算不做：联网枚举清单，得到要下多少、是差分还是整包
        plan = await asyncio.to_thread(updater.check)
        summary = _summarize_plan(plan)
        if plan.kind == UpdateKind.Noop:
            # 常态结论：只留 app.log，不刷任务日志
            _note(f"原神客户端已是最新（{summary['local_version'] or '?'}）")
        else:
            # 报「本轮还要下多少」而不是计划全量：续传时全量数字会让人以为要从
            # 头下一遍，而实际只剩没打完的那部分
            need = plan.space_need
            pending = need.download_left if need else plan.total_size
            counted = (
                f"（{plan.file_count} 个文件，本地已就绪 {need.already_done} 个）"
                if need
                else f"（{plan.file_count} 个文件）"
            )
            await _report(
                on_progress,
                f"{summary['state_label']} · {summary['kind_label']} · "
                f"{summary['version_line']} · 待下载 {summarize_size(pending)}"
                + counted,
            )

        blocked = await _run_gates(plan, game_dir, updater, on_progress)
        if blocked is not None:
            return blocked

        if not plan.needs_action:
            return GenshinUpdateResult(
                success=True,
                noop=True,
                message="已是最新版本",
                local_version=summary["local_version"],
                remote_version=summary["remote_version"],
                kind=plan.kind.value,
            )

        result = await asyncio.to_thread(updater.installer.execute, plan)
        # 只有真成功才清缓存；失败或中止都留着，下一次能接着下而不是从零开始
        keep_cache = not result.success
        return GenshinUpdateResult(
            success=result.success,
            message=result.message or str(result),
            local_version=summary["local_version"],
            remote_version=str(result.version or plan.target_version or ""),
            kind=plan.kind.value,
            download_size=result.bytes_downloaded,
            file_count=result.file_total,
        )
    except UpdateAborted:
        logger.info("原神更新已中止，已下载的差分缓存会留给下次")
        return GenshinUpdateResult(
            success=False,
            aborted=True,
            message="更新已中止，已完成的部分与下载缓存都会保留，下次接着更新",
        )
    except Exception as error:  # noqa: BLE001
        logger.opt(exception=True).warning(
            "原神更新失败: {}: {}", type(error).__name__, error
        )
        return GenshinUpdateResult(
            success=False, message=f"{type(error).__name__}: {error}"
        )
    finally:
        abort_event.set()
        kept = await asyncio.to_thread(
            updater.installer.cleanup_temp, keep_patch_cache=keep_cache
        )
        if kept:
            # 只进 app.log：调度台那一行已经说明了失败/中止，路径细节是给排查用的
            _note(
                "已保留下载缓存："
                + "、".join(kept)
                + "；要手工清理就直接删这些目录，不影响游戏本体，"
                "只是下次要重新下载"
            )


def _summarize_plan(plan: Any) -> dict[str, str]:
    """把计划里要给用户看的几项取成字符串。

    Args:
        plan: 引擎给出的 :class:`UpdatePlan`。

    Returns:
        含 ``state_label`` / ``kind_label`` / ``local_version`` / ``remote_version``
        / ``version_line`` 的字典。
    """
    from app.services.gi_updater.versioning import GAME_STATE_LABELS

    local_version = str(plan.source_version or "")
    remote_version = str(plan.target_version or "")
    return {
        "state_label": str(GAME_STATE_LABELS.get(plan.state, plan.state.value)),
        "kind_label": _KIND_LABELS.get(plan.kind.value, plan.kind.value),
        "local_version": local_version,
        "remote_version": remote_version,
        "version_line": f"{local_version or '未安装'} -> {remote_version or '?'}",
    }


async def _run_gates(
    plan: Any,
    game_dir: Path,
    updater: Any,
    on_progress: ProgressHook | None,
) -> GenshinUpdateResult | None:
    """跑三道宿主侧门禁。

    拦截原因只写 app.log：调度台那一边由调用方薄壳汇总成一行「更新未完成：<原因>」，
    两边都写就会在任务日志里出现两条同样的话。

    Args:
        plan: 已算出的计划。
        game_dir: 游戏安装目录。
        updater: 引擎门面对象，提供原神的混装判定。
        on_progress: 进度回调，用于告诉调度台「真的开始下载了」。

    Returns:
        被拦下时返回失败的结论；放行时返回 ``None``。
    """
    if plan.kind == UpdateKind.Noop:
        return None

    if not updater.installer.validate_exec_data_dir():
        return await _block(plan, "该目录疑似混装了不同区服的原神客户端，已停止更新")

    # 自动接管只应用增量差分包：拿不到差分（全新安装、逐文件全量比对、预下载）
    # 一律停手交给官方启动器，绝不在无人值守时顺手灌几十 GB 整包。
    if plan.kind != UpdateKind.SophonPatch:
        return await _block(
            plan,
            f"本次是{_KIND_LABELS.get(plan.kind.value, plan.kind.value)}"
            f"（约 {summarize_size(plan.total_size)}），MAS 只自动应用增量包，"
            "已停止，请用官方启动器更新",
        )

    # 门禁按真实占用算：分片是过手即删的中间物，真正长驻磁盘的是更新后的新文件，
    # 只按下载量放行会在盘紧的机器上下载到一半把盘写满。数值在算计划时一次统计好，
    # 这里只读结果，不再对上千个文件重复 stat。
    need = plan.space_need
    if need is not None:
        _note(
            f"差分空间估算：还要下 {summarize_size(need.download_left)}、"
            f"新文件净增 {summarize_size(need.write_growth)}、"
            f"在飞峰值 {summarize_size(need.peak)}、"
            f"本地已就绪 {need.already_done}/{plan.file_count} 个"
        )
        required = need.disk_need
    else:
        required = plan.total_size
    if not _disk_has_room(game_dir, required):
        free = summarize_size(shutil.disk_usage(game_dir).free)
        return await _block(
            plan,
            f"磁盘剩余 {free}，本次增量更新要同时放下差分包和更新后的文件"
            f"（约需 {summarize_size(required)}），请先清理后再试",
        )

    await _report(
        on_progress,
        f"准备就绪，开始下载 "
        f"{summarize_size(need.download_left if need else plan.total_size)}",
    )
    return None


async def _block(plan: Any, message: str) -> GenshinUpdateResult:
    """把一条门禁拦截变成失败结论，并留一行 app.log。

    Args:
        plan: 被拦下的计划。
        message: 面向用户的拦截原因。

    Returns:
        失败结论，``noop`` 为真（本轮什么都没改）。
    """
    _note(message)
    return GenshinUpdateResult(
        success=False,
        noop=True,
        message=message,
        kind=plan.kind.value,
        download_size=plan.total_size,
        file_count=plan.file_count,
    )


def _note(line: str) -> None:
    """只写 app.log 的叙述行（不进调度台）。

    Args:
        line: 面向用户的文案。
    """
    logger.info(line)


async def _report(hook: ProgressHook | None, line: str) -> None:
    """记一行日志并推给调度台。

    Args:
        hook: 进度回调；``None`` 时只记日志。
        line: 面向用户的文案。
    """
    logger.info(line)
    if hook is not None:
        await hook(sanitize_log_message(line))
