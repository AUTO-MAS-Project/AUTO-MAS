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

"""宿主侧的更新编排：区服判定、三道门禁、面向用户的叙述——与具体游戏无关。

引擎（:mod:`app.services.gi_updater`）本身就是异步的，本模块只做引擎不该管的事：
把 HTTP 客户端的寿命握住、按目录判区服、在联网算出计划之后补三道只有宿主才该管的门，
并把结论翻译成调度台的一行行文案。一款游戏的门面只需把自己的短名与区服标签传进来。

三道门禁都不在引擎里，因为它们服务的是「别把用户的游戏和下不完的大包搞砸」：

- **混装目录**：不同区服的客户端不会共存于同一目录。目录里同时见得到多个可执行
  文件，说明这个路径填错了；再往下走就是往别人的安装目录里灌整客户端量级的数据。
- **只应用增量包**：拿不到增量差分包（全新安装、逐文件全量比对）就停手交给官方启动器
  ——无人值守的调度任务绝不该顺手吃掉一整份客户端的流量。
- **磁盘余量**：差分也可能不小，空间不够要提前停，不能让下载在半路写爆磁盘。

三道门禁都建立在「问得出该怎么更新」之上。联网问不出结论（协议异常、清单缺项、清单解
不开）算**无法判定**：放行，让专项照常启动，原因只留 app.log——查不到是我这边的能力
问题，不该拦住用户。

中止只来自调用方的 :data:`~app.services.gi_updater.common.AbortHook`：在文件批次边界
收工，不回滚已落盘的合法文件，也不写 ``config.ini``，重开就是接着更新。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.gi_updater import api
from app.services.gi_updater.common import (
    AbortHook,
    ProgressHook,
    summarize_size,
)
from app.services.gi_updater.games import create_updater, get_spec
from app.services.gi_updater.install import UpdateKind
from app.services.gi_updater.presets import get_profile
from app.services.gi_updater.versioning import MIN_EXECUTABLE_SIZE
from app.utils import get_logger, sanitize_log_message
from app.utils.hpatchz import ensure_hpatchz

logger = get_logger("更新引擎")

#: 区服配置项里表示「按目录里的客户端自己判」的取值
AUTO_REGION_LABEL = "自动"
#: 磁盘余量在需要量之外再多留的缓冲
_DISK_MARGIN_BYTES = 2 * 1024**3

#: 计划类型 -> 面向用户的说法
_KIND_LABELS = {
    UpdateKind.SophonInstall.value: "全新安装",
    UpdateKind.SophonPatch.value: "增量更新",
    UpdateKind.SophonUpdate.value: "差异比对更新",
    UpdateKind.Noop.value: "无需更新",
    UpdateKind.Unknown.value: "无法判定",
}


@dataclass(frozen=True)
class UpdateResult:
    """一轮客户端更新的结论。"""

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
    #: 其中有多少个文件走了整文件降级
    downgraded: int = 0


def _resolve_region(game: str, game_dir: Path, resource: str) -> str | None:
    """定下这次要按哪个区服的接口走。

    Returns:
        区服短名；``resource`` 为 ``自动`` 时按目录里在跑的那个可执行文件判定，
        判不出唯一结果时返回 ``None``。
    """
    spec = get_spec(game)
    if resource != AUTO_REGION_LABEL:
        return spec.region_for_label(str(resource).strip())

    found = [
        region
        for _, region in spec.locale_regions
        if _executable_present(game_dir, get_profile(game, region))
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        # 目录里一个可执行文件都没有：要么是新装，要么填错了。新装按默认区服走，
        # 真填错了下一道门禁会先把它拦下来。
        return spec.default_region
    return None


def _executable_present(game_dir: Path, preset: Any) -> bool:
    """某区服的可执行文件是否真实存在于该目录（体积要达标）。"""
    candidate = game_dir / str(preset.executable_name)
    try:
        return candidate.is_file() and candidate.stat().st_size > MIN_EXECUTABLE_SIZE
    except OSError:
        return False


def _looks_like_install(game: str, game_dir: Path) -> bool:
    """目录里是否有个本游戏客户端的样子（标记文件或任一区服的可执行文件）。"""
    spec = get_spec(game)
    if any((game_dir / name).is_file() for name in spec.install_marker_files):
        return True
    return any(
        _executable_present(game_dir, get_profile(game, region))
        for _, region in spec.locale_regions
    )


def _disk_has_room(game_dir: Path, needed: int) -> bool:
    """目标盘的余量够不够这次下载（外加缓冲）。

    读不出余量时放行——别因为一个探测失败就拦住正常更新。
    """
    try:
        free = shutil.disk_usage(game_dir).free
    except OSError:
        return True
    return free >= needed + _DISK_MARGIN_BYTES


async def update_client(
    game: str,
    game_path: str | Path,
    *,
    resource: str = AUTO_REGION_LABEL,
    on_progress: ProgressHook | None = None,
    should_abort: AbortHook | None = None,
) -> UpdateResult:
    """检查并按需更新指定游戏的客户端，直到落盘完成。

    Args:
        should_abort: 中止判定，在文件批次边界轮询；``None`` 表示不可中止。

    Returns:
        :class:`UpdateResult`。任何异常都转成 ``success=False`` 的结论，
        不把 traceback 抛给调度侧。
    """
    spec = get_spec(game)
    display = spec.display_name
    game_dir = Path(game_path)
    if not str(game_path).strip() or not game_dir.is_dir():
        return _stop(f"游戏目录不存在：{game_path or '（未填）'}")

    resolved = _resolve_region(game, game_dir, resource)
    if resolved is None:
        labels = "与".join(label for label, _ in spec.locale_regions)
        return _stop(f"该目录里同时存在{labels}的可执行文件，请先确认游戏目录是否填错")

    if not _looks_like_install(game, game_dir):
        markers = "、".join(spec.install_marker_files)
        return _stop(
            f"该目录里没有{display}客户端（缺 {markers} 与可执行文件）：{game_dir}"
        )

    try:
        updater = create_updater(game, resolved, str(game_dir))
    except Exception as error:  # noqa: BLE001
        # 连更新器都装配不出来（读不开 config.ini 之类）属于「我这边问不出」，不该算成
        # 用户「确知要更新却没做成」
        logger.exception(
            f"{display}客户端更新器装配失败: {type(error).__name__}: {error}"
        )
        return _undecidable(f"{type(error).__name__}: {error}")

    # 这条通道归本流程管：每次启动前都会跑一遍，不还就会一直攒着连接与套接字
    async with api.new_client() as client:
        try:
            plan = await updater.check(client)
            return await _run_plan(
                updater,
                plan,
                display=display,
                game_dir=game_dir,
                client=client,
                on_progress=on_progress,
                should_abort=should_abort,
            )
        except Exception as error:  # noqa: BLE001
            # 宿主的日志器不做 % 占位替换，写成占位符就等于把失败原因丢了
            logger.exception(f"{display}更新失败: {type(error).__name__}: {error}")
            return UpdateResult(
                success=False, message=f"{type(error).__name__}: {error}"
            )
        finally:
            kept = await updater.installer.cleanup_temp()
            if kept:
                # 只进 app.log：调度台那行已经说明了结果，路径细节是留给排查的
                _note(f"已清理本轮中间产物：{'、'.join(kept)}")


async def _run_plan(
    updater: Any,
    plan: Any,
    *,
    display: str,
    game_dir: Path,
    client: Any,
    on_progress: ProgressHook | None,
    should_abort: AbortHook | None,
) -> UpdateResult:
    """把一份计划过完三道门禁并执行掉。"""
    local = str(plan.source_version or "")
    remote = str(plan.target_version or "")

    if plan.kind == UpdateKind.Unknown:
        # 一次问不出结论不代表用户的客户端有问题，更不该拦住专项启动：留一行 app.log
        # 供排查，联网恢复的下一轮自会重新判定
        _note(f"无法判定{display}客户端要不要更新，本轮跳过：{plan.message}")
        return _undecidable(plan.message, local_version=local)

    if plan.kind == UpdateKind.Noop:
        # 常态结论：只留 app.log，不刷任务日志；预下载也落在这里——主资源没有要动的
        # 东西，拦下来只会让任务白失败一轮
        _note(f"{display}客户端已是最新（{local or '?'}）")
        return UpdateResult(
            success=True,
            noop=True,
            message=plan.message,
            local_version=local,
            remote_version=remote,
            kind=plan.kind.value,
        )

    if plan.kind == UpdateKind.SophonPatch:
        await _report(
            on_progress,
            f"{plan.state} · {label(plan.kind)} · {local or '未安装'} -> "
            f"{remote or '?'} · 待下载 {summarize_size(plan.total_size)}"
            f"（{plan.file_count} 个文件，本地已就绪 {plan.summary.ready} 个）",
        )

    blocked = await _gate(plan, display=display, game_dir=game_dir, updater=updater)
    if blocked is not None:
        return blocked

    # 只有要打增量时才会被赋值；其余计划类型没有可打的对象，execute 也不看它
    hpatchz: str | None = None
    if plan.kind == UpdateKind.SophonPatch:
        _note(
            f"增量约 {summarize_size(plan.total_size)}、单文件更新后最大 "
            f"{summarize_size(plan.summary.largest_target)}、磁盘需 "
            f"{summarize_size(plan.disk_need)}"
            + (
                f"、其中语音包 {plan.summary.voice_count} 个文件/"
                f"{summarize_size(plan.summary.voice_download)}"
                if plan.summary.voice_count
                else ""
            )
            + (
                f"、预计整文件重下 {plan.summary.downgraded} 个"
                if plan.summary.downgraded
                else ""
            )
        )
        if plan.message:
            # 例如某档语音本轮没有差分：主资源照更，这档本轮不动
            _note(f"{display}客户端本轮还有一处没动：{plan.message}")
        # 补丁工具只在确实要打增量时才取：没装过游戏、拿不到差分的轮次都用不上它，
        # 更早地失败会把一轮本不需要它的任务白白拦下
        try:
            hpatchz = str(await ensure_hpatchz(on_progress=on_progress))
        except Exception as error:  # noqa: BLE001
            # 没有补丁工具就打不出增量，只能整文件重下——那是要用户付流量的事，停手问一句
            reason = f"获取增量补丁工具失败：{error}"
            await _report(on_progress, f"{reason}，本次已停止更新")
            return UpdateResult(
                success=False,
                message=reason,
                local_version=local,
                remote_version=remote,
                kind=plan.kind.value,
            )
        await _report(
            on_progress, f"准备就绪，开始下载 {summarize_size(plan.total_size)}"
        )

    result = await updater.execute(
        plan,
        client,
        hpatchz=hpatchz,
        on_progress=on_progress,
        should_abort=should_abort,
    )
    if result.aborted:
        logger.info(f"{display}更新已中止，已落盘的文件会留给下次接着用")
        return UpdateResult(
            success=False,
            aborted=True,
            message=result.message,
            local_version=local,
            remote_version=remote,
            kind=plan.kind.value,
            download_size=result.bytes_downloaded,
            file_count=result.file_total,
            downgraded=result.downgraded,
        )

    if not result.success:
        return UpdateResult(
            success=False,
            message=result.message or str(result),
            local_version=local,
            remote_version=remote,
            kind=plan.kind.value,
            download_size=result.bytes_downloaded,
            file_count=result.file_total,
            downgraded=result.downgraded,
        )

    finished = result.version or remote
    if result.file_done:
        await _report(
            on_progress,
            f"{display}客户端更新完成 {local or '?'} -> {finished or '?'}"
            + (f"，清理旧文件 {result.removed} 个" if result.removed else ""),
        )
    return UpdateResult(
        success=True,
        noop=not result.file_done,
        message=f"更新完成 {local} -> {finished}",
        local_version=local,
        remote_version=finished,
        kind=plan.kind.value,
        download_size=result.bytes_downloaded,
        file_count=result.file_total,
        downgraded=result.downgraded,
    )


def label(kind: UpdateKind) -> str:
    """计划类型面向用户的说法。"""
    return _KIND_LABELS.get(kind.value, kind.value)


async def _gate(
    plan: Any, *, display: str, game_dir: Path, updater: Any
) -> UpdateResult | None:
    """跑门禁；被拦下时返回结论，放行时返回 ``None``。

    拦截原因只写 app.log：调度台那边由调用方薄壳汇总成一行「更新未完成：<原因>」，
    两边都写就会在任务日志里出现两条同样的话。
    """
    if not updater.installer.validate_exec_data_dir():
        return _stop(
            f"该目录疑似混装了不同区服的{display}客户端，已停止更新", kind=plan.kind
        )

    # 自动接管只应用增量差分包：拿不到差分（全新安装、逐文件全量比对）一律停手交给
    # 官方启动器，绝不在无人值守时顺手灌一整份客户端。
    if plan.kind != UpdateKind.SophonPatch:
        # 这几种结论都没有待下清单（引擎不为它们收集资产），所以不提体积——报「约 0 B」
        # 会让人以为白下一趟
        reason = f"{plan.message}，" if plan.message else ""
        return _stop(
            f"本次是{label(plan.kind)}，{reason}"
            "MAS 只自动应用增量包，已停止，请用官方启动器更新",
            kind=plan.kind,
        )

    if not _disk_has_room(game_dir, plan.disk_need):
        free = summarize_size(shutil.disk_usage(game_dir).free)
        return _stop(
            f"磁盘剩余 {free}，本次增量要同时放下差分包与更新后的文件"
            f"（约需 {summarize_size(plan.disk_need)}），请先清理后再试",
            kind=plan.kind,
        )
    return None


def _stop(message: str, *, kind: UpdateKind = UpdateKind.Noop) -> UpdateResult:
    """一条门禁拦截 -> 失败的结论，并留一行 app.log。"""
    _note(message)
    return UpdateResult(success=False, noop=True, message=message, kind=kind.value)


def _undecidable(reason: str, *, local_version: str = "") -> UpdateResult:
    """问不出结论 -> 放行但不算做过事，具体原因只留 app.log。"""
    return UpdateResult(
        success=True,
        noop=True,
        message=f"无法判定是否需要更新：{reason}",
        local_version=local_version,
        kind=UpdateKind.Unknown.value,
    )


def _note(line: str) -> None:
    """只写 app.log 的叙述行（不进调度台）。"""
    logger.info(line)


async def _report(hook: ProgressHook | None, line: str) -> None:
    """记一行日志并推给调度台。"""
    logger.info(line)
    if hook is not None:
        await hook(sanitize_log_message(line))
