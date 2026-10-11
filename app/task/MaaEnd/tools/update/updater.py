#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""终末地客户端更新入口：检查、前置门、下载与落地编排。

自动任务和手动按钮共用 ensure_game_updated。模块分工：
- common：数据结构、共用常量和日志。
- protocol：客户端身份、官方响应和差量清单。
- checks：路径、基线、磁盘和进程检查。
- download：分卷下载、续传和签名刷新。
- install：读取差量包、打补丁和提交文件。
- staging：暂存目录、跨轮续传状态与「留不留给下一轮」的判定。
游戏更新属于先行补位，边界与移除条件见 ../../AGENTS.md。"""

from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

import httpx
import pyzipper

from app.utils.game_update import GameUpdateResult, is_client_outdated
from app.utils.hpatchz import ensure_hpatchz
from app.utils.update_files import (
    directory_lock,
)

from .checks import (
    _busy_processes,
    _check_baselines,
    _disk_shortfall,
    _landing_need,
    _release_install_dir,
    _write_probe,
)
from .common import (
    _CONFIG_MEMBER,
    _CONNECT_TIMEOUT,
    _DOWNLOAD_CHUNK,
    _READ_TIMEOUT,
    UNKNOWN_SERVER_MESSAGE,
    DeltaPlan,
    EndfieldUpdateError,
    ProgressFn,
    logger,
)
from .download import _download_release, _prefetch_package
from .install import (
    _apply_delta,
    _build_delta_plan,
    _describe_os_error,
    _read_package_manifests,
    _SplicedStream,
)
from .protocol import (
    _fetch_patch_manifest,
    _fetch_release,
    _log_unknown_server,
    _match_preset,
    read_install_identity,
    read_installed_version,
)
from .staging import (
    _clear_residual,
    _half_landed_block,
    _residual_state,
    _Staging,
)

_RESERVE_BYTES = 256 * 1024**2
"""除下载与落地体积外额外要求的余量：盘刚好占满会把问题转移到下一次运行。"""


async def ensure_game_updated(
    game_exe: Path,
    *,
    time_limit_minutes: int,
    progress: ProgressFn | None = None,
    entry: str = "自动",
) -> GameUpdateResult:
    """对外入口：跑一轮判定，并把开始、过程与结论都写进 `debug/app.log`。

    时限包住「核对基线 + 退出客户端 + 下载差量 + 落地」四段；进度行只往调度台推，同一行
    由本函数写进 `debug/app.log`；`entry` 只进日志，用来区分自动门与脚本页手动按钮。
    """

    logger.info(
        f"{entry}发起终末地客户端更新检查: 安装目录 {game_exe.parent}"
        f"（限时 {time_limit_minutes} 分钟）"
    )
    outcome = ("已取消", "本轮更新被取消（用户点了停止，或看门狗下发了中止）")
    lock = directory_lock(game_exe.parent)
    try:
        if lock.locked():
            # 同一目录上的第二轮只会跟第一轮互删暂存与分卷，这一轮不发起，也不排队等：
            # 一轮落地要几十分钟，排队会让调度轮和手动按钮一起挂住
            result = GameUpdateResult(
                "NeedManualUpdate",
                "已有一轮终末地客户端更新正在这个目录上进行，本轮不再发起，"
                "请等它结束后再运行",
            )
        else:
            async with lock:
                result = await _ensure_game_updated(
                    game_exe, time_limit_minutes=time_limit_minutes, progress=progress
                )
    except Exception as error:
        outcome = ("异常", f"未得出结论文案：{type(error).__name__}: {error}")
        raise
    else:
        outcome = (result.status, result.message)
    finally:
        logger.info(f"终末地客户端更新结论（{entry}）: {outcome[0]} - {outcome[1]}")
    return result


async def _ensure_game_updated(
    game_exe: Path,
    *,
    time_limit_minutes: int,
    progress: ProgressFn | None,
) -> GameUpdateResult:
    """检查并在需要时由 MAS 接管终末地 PC 客户端的差量更新。

    对外承诺不抛异常：判不了的走 `Skipped`（读不到本地版本、问不动服务端），确认要更新
    却做不到的走 `NeedManualUpdate`（这条基线没有差量、本地基线与清单不符、下载或落地
    失败），意外异常也归到后者——调用方据此决定放行还是阻断，不需要再猜目录有没有被动
    过。不做整包兜底：判不了就不动，动不了就停下提示手动更新。
    """

    if not game_exe.is_file():
        return GameUpdateResult("Skipped", f"未找到终末地客户端: {game_exe}")

    install_dir = game_exe.parent
    identity = read_install_identity(install_dir)
    # 上一轮留在暂存里的状态：它决定「本轮判不了」时放行还是阻断
    residual = _residual_state(install_dir)
    # 只有真读到版本号、且与残留记的不同，才能断言「客户端已换代」（用户或启动器修好了）。
    # 版本读不出来时不能这么断言：那可能只是 config.ini 被占用或损坏，而此刻客户端正停在
    # 半新半旧——当成换代就会清掉续传现场，还放行一轮跑在坏客户端上的任务
    if (
        residual is not None
        and identity.version
        and residual.request_version != identity.version
    ):
        logger.info(
            f"续传状态记的是本地 {residual.request_version or '未知'}，"
            f"现在是 {identity.version}，残留作废"
        )
        residual = None
        _clear_residual(install_dir)
    if not identity.version:
        block = _half_landed_block(residual)
        if block is not None:
            return GameUpdateResult("NeedManualUpdate", block)
        return GameUpdateResult(
            "Skipped",
            f"读不到终末地客户端的版本号（{install_dir / _CONFIG_MEMBER}），跳过检查",
        )
    preset = _match_preset(identity)
    if preset is None:
        _log_unknown_server(identity)
        block = _half_landed_block(residual)
        if block is not None:
            return GameUpdateResult("NeedManualUpdate", block)
        return GameUpdateResult("Skipped", UNKNOWN_SERVER_MESSAGE)

    try:
        release = await _fetch_release(identity, preset=preset)
    except (httpx.HTTPError, EndfieldUpdateError, ValueError) as error:
        logger.warning(f"检查终末地客户端更新失败，跳过检查: {error}")
        block = _half_landed_block(residual)
        if block is not None:
            return GameUpdateResult("NeedManualUpdate", block)
        return GameUpdateResult(
            "Skipped", f"未能获取终末地客户端版本信息（{error}），跳过检查"
        )

    logger.info(
        f"本地版本 {identity.version}，客户端登记 "
        f"appcode={identity.appcode} channel={identity.channel}"
        f" sub_channel={identity.sub_channel}，匹配到 {preset['label']}，"
        f"服务端给出 {release.version}"
    )

    latest = f"终末地客户端已是最新版本 {identity.version}"

    def up_to_date(message: str) -> GameUpdateResult:
        """不需要更新就顺手把残留清了：客户端已是目标版本，那份暂存再没有用处。"""

        if residual is not None:
            _clear_residual(install_dir)
        return GameUpdateResult("UpToDate", message)

    if identity.version == release.version:
        # 服务端给的差量卷可能是按别的基线算的：本地已是目标版就什么都不做，否则基线
        # 核对注定失败，把没动过的客户端说成「被改过」是冤枉
        return up_to_date(latest)
    if not release.parts:
        # 空差量段：要么已是最新，要么这条基线没有差量
        if not is_client_outdated(identity.version, release.version):
            return up_to_date(latest)
        return GameUpdateResult(
            "NeedManualUpdate",
            f"终末地客户端版本落后（已安装 {identity.version}，最新 {release.version}），"
            f"但官方没有 {identity.version} 这一路的增量包，请用启动器手动更新一次",
        )
    if not is_client_outdated(identity.version, release.version):
        logger.warning(
            f"服务端给出差量但本地版本不比它旧（本地 {identity.version}，"
            f"目标 {release.version}）"
        )
        return up_to_date(
            f"终末地客户端不比目标旧（本地 {identity.version}，目标 {release.version}），"
            "未做任何改动"
        )

    outdated = (
        f"终末地客户端版本落后（已安装 {identity.version}，最新 {release.version}）"
    )
    staging = _Staging(install_dir, release, identity.version)
    abort = threading.Event()
    landed = 0
    done_entries: set[str] = set()

    async def report(line: str) -> None:
        """每条播报同时进 `debug/app.log` 与调度台：前者才是用户反馈时会带来的那份。"""

        logger.info(line)
        if progress is not None:
            await progress(line)

    try:
        # 清暂存、建目录都在 try 内：本函数对外承诺不抛，暂存名被占成文件、盘只读这类
        # 情况也要落成一条看得懂的结论，而不是让任务直接异常
        staging.prepare()
        reused_bytes = await staging.claim_reusable()
        remaining_download = release.download_size - reused_bytes
        if reused_bytes:
            await report(
                f"接着上轮继续：已下好 {reused_bytes / 1024**3:.1f} GB，"
                f"本轮还需下载 {remaining_download / 1024**3:.1f} GB"
            )
        # 磁盘门排在清理之后：上一轮删不动的残卷压着同一分区的 free，先判后清就每轮都
        # 是「放不下」，而那一轮根本走不到清理。续传时只按还要下的那部分判：已下好的
        # 分卷本来就占着盘，再按全量要一次余量会把明明放得下的续传拦在门外
        short = _disk_shortfall(
            install_dir,
            remaining_download + _RESERVE_BYTES,
            "游戏目录（下载差量包）",
        )
        if short:
            return GameUpdateResult("NeedManualUpdate", f"{outdated}，{short}")
        async with asyncio.timeout(time_limit_minutes * 60):
            await report(
                f"{outdated}\n按 {preset['label']} 的服务器参数核对官方差量清单"
                f"（差量 {len(release.parts)} 卷 / "
                f"{release.download_size / 1024**3:.1f} GB）"
            )
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
                follow_redirects=True,
            ) as client:
                specs = await _fetch_patch_manifest(
                    client, release.patch_info_url, release.patch_info_md5
                )
                prefetched, sizes = await _prefetch_package(
                    client, release, specs, report
                )

            done_entries, bad = await _check_baselines(
                specs, prefetched, install_dir, report, abort
            )
            if bad:
                shown = "、".join(Path(path).name for path in bad[:5])
                return GameUpdateResult(
                    "NeedManualUpdate",
                    f"{outdated}，本地 {len(bad)} 个文件与官方基线不符（{shown}"
                    f"{' 等' if len(bad) > 5 else ''}），MAS 不覆盖改动过的客户端，"
                    "请用启动器手动更新一次",
                )
            if done_entries:
                await report(f"上轮已落地 {len(done_entries)} 个文件，本轮接着做剩下的")
            # 展开体积只算本轮还要打的那几条：上一轮已经改名就位的差量不会再展开进暂存
            expanded = (
                max(
                    (
                        sizes[spec.member]
                        for spec in specs
                        if spec.path not in done_entries
                    ),
                    default=0,
                )
                if prefetched is not None and sizes is not None
                else None
            )
            if prefetched is not None and expanded is not None:
                # 下载与落地共用一个盘，两笔体积必须在这一刻一起算：卷要读到最后一刻
                # 才清，落地那一刻暂存卷还压在同一个目录里
                landing_need = _landing_need(
                    [spec for spec in specs if spec.path not in done_entries],
                    [entry for entry in prefetched if entry.path not in done_entries],
                    install_dir,
                    expanded,
                )
                short = _disk_shortfall(
                    install_dir,
                    remaining_download + landing_need + _RESERVE_BYTES,
                    "游戏目录（下载与落地）",
                )
                if short:
                    return GameUpdateResult(
                        "NeedManualUpdate",
                        f"{outdated}，本轮尚未开始下载，暂存卷还没占盘："
                        f"下载差量包约 {remaining_download / 1024**3:.1f} GB，"
                        f"落地还要在游戏目录净腾出约 {landing_need / 1024**3:.1f} GB，"
                        f"再加一份固定余量。{short}",
                    )

            # 核对通过才动游戏目录：先探可写，再退出正在运行的客户端
            unwritable = _write_probe(install_dir)
            if unwritable:
                return GameUpdateResult("NeedManualUpdate", f"{outdated}，{unwritable}")
            blocked = await _release_install_dir(game_exe)
            if blocked:
                return GameUpdateResult("NeedManualUpdate", f"{outdated}，{blocked}")

            hpatchz = await ensure_hpatchz(on_progress=report)
            files = await _download_release(
                release, staging.path, report, identity, staging.reusable
            )
            # 下载要花几分钟，期间用户完全可能自己把游戏开回去；UE 客户端锁着
            # .ucas/.pak，这时候开写就是 PermissionError。只检测不强杀：那是用户在
            # MAS 不知情下自己开的窗口，没被授权关掉它
            busy = await _busy_processes(install_dir)
            if busy:
                raise EndfieldUpdateError(
                    f"下载期间游戏被重新启动（{', '.join(busy)}），本轮不覆盖，"
                    "请退出游戏后重试"
                )

            stream = _SplicedStream(files, [part.size for part in release.parts])
            try:
                archive = pyzipper.AESZipFile(
                    io.BufferedReader(stream, buffer_size=4 * _DOWNLOAD_CHUNK)
                )
                # 差量包是 WinZip AES-256；口令就是服务端的 patch.cd_key
                archive.setpassword(release.cd_key.encode())
                members = {
                    info.filename for info in archive.infolist() if not info.is_dir()
                }
                moves, deletes = _read_package_manifests(archive, members)
                plan = _build_delta_plan(specs, members, moves, deletes)
                # 上一轮已经落地的不再做第二遍：新文件指纹对得上就是完成，重打一遍只会
                # 把同一份内容再写一次，还平白多占一轮时间
                plan = DeltaPlan(
                    patches=tuple(
                        job for job in plan.patches if job.path not in done_entries
                    ),
                    moves=tuple(
                        job for job in plan.moves if job.path not in done_entries
                    ),
                    deletes=plan.deletes,
                )
                # 落地中途这条差量要先整份解到暂存目录；包已经打开，这份体积是准数
                max_expanded = max(
                    (archive.getinfo(job.member).file_size for job in plan.patches),
                    default=0,
                )
                landing = _disk_shortfall(
                    install_dir,
                    _landing_need(plan.patches, plan.moves, install_dir, max_expanded)
                    + _RESERVE_BYTES,
                    "游戏目录（差量落地）",
                )
                if landing:
                    raise EndfieldUpdateError(landing)
                await report(
                    f"差量包就位，开始覆盖安装目录：{len(plan.patches)} 个打补丁 + "
                    f"{len(plan.moves)} 个整文件，共 "
                    f"{plan.expanded_bytes / 1024**3:.1f} GB"
                )
                landed = await _apply_delta(
                    archive,
                    plan,
                    install_dir,
                    staging.path,
                    hpatchz,
                    report,
                    abort,
                    mark_landing_started=staging.mark_landing_started,
                )
                archive.close()
            finally:
                stream.close()
    except TimeoutError:
        abort.set()
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated}，MAS 更新超过 {time_limit_minutes} 分钟已中止，"
            "请放宽游戏更新超时限制或手动更新一次",
        )
    except asyncio.CancelledError:
        # 用户点了停止：CancelledError 不是 Exception，不进下面的兜底，必须自己把中止
        # 标志递下去，让正在拷贝成员的工作线程停下。版本号还没提交，游戏目录停在旧版，
        # 下一轮按同一份清单重新判定；没改名的临时文件会被下一轮回收。
        abort.set()
        raise
    except (EndfieldUpdateError, httpx.HTTPError, OSError) as error:
        detail = (
            _describe_os_error(error, "游戏目录")
            if isinstance(error, OSError)
            else str(error)
        )
        logger.warning(f"终末地差量更新失败: {error}")
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated}，MAS 自动更新失败（{detail}），请手动更新游戏后重试",
        )
    except Exception as error:
        # 兜底：本函数对外承诺不抛，调用方才能拿 status 决定放行还是阻断。走到这里
        # 说明有没预料到的异常类型（包内解析、线程池等），一律按「需要手动更新」处理。
        # 异常类型与原文只留在这一行日志里；落地途中抛出时客户端已经部分改动，所以给
        # 用户的那句只说该做什么，不承诺目录还是原样
        logger.opt(exception=True).warning(
            f"终末地差量更新出现未预料的异常（{type(error).__name__}: {error}）"
        )
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated}，MAS 自动更新中途停手，原因记在该脚本的运行日志里；"
            "请用启动器手动更新一次，若反复出现请带上日志反馈",
        )
    finally:
        # 收尾按「安装目录里的版本号是不是已经是目标」决定留不留：config.ini 是本轮最后
        # 一次原子改名，它报出新版本等价于其余文件都已落盘，这时才该把暂存清干净；其余
        # 情况（取消、超时、失败、门禁拦住）一律留着，下一轮接着下、接着写。
        # 中止那条路上可能仍有工作线程攥着卷句柄，那种文件在 Windows 上删不动，收尾
        # 不断言清干净了，下一轮开头会再清一遍
        staging.finish(completed=read_installed_version(install_dir) == release.version)
        if abort.is_set():
            logger.info("本轮差量更新已中止")

    committed = read_installed_version(install_dir)
    if committed != release.version:
        return GameUpdateResult(
            "NeedManualUpdate",
            f"MAS 已完成差量落地，但游戏版本号仍是 {committed or '未知'}"
            f"（目标 {release.version}），请手动更新一次后重试；若反复出现请反馈",
        )
    note = (
        f"（本轮写了 {landed} 个文件"
        + (f"，沿用上轮已落地的 {len(done_entries)} 个" if done_entries else "")
        + f"，共 {release.download_size / 1024**3:.1f} GB 差量）"
    )
    return GameUpdateResult("Updated", f"MAS 已将终末地客户端更新至 {committed}{note}")
