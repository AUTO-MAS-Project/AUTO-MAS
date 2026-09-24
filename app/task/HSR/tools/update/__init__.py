"""HSR 外部脚本（M7A / SRA）的更新能力。

对外只暴露两个入口：:func:`check_engine_update` 只查不装，
:func:`update_engine_if_needed` 查完就装。两者都不会抛异常给调用方——
更新失败**不应该**让任务跑不起来，除非目录真的被改坏了（见
``UpdateOutcome.blocking``）。

调用时机见 ``manager.py``：更新只在任务正常跑完后触发一次（AfterRun），
``prepare()` 只做一件事——把上一轮崩在中途的 journal 回滚掉。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.utils.logger import get_logger

from .apply import (
    HSRUpdateApplyError,
    apply_package,
    has_pending_journal,
    rollback,
)
from .discover import DiscoveryResult, HSRUpdateError, discover
from .download import AbortFn, HSRUpdateAborted
from .engines import (
    EngineSpec,
    find_seven_zip,
    get_spec,
    read_installed_version,
)
from .guards import (
    check_disk_space,
    check_no_process_running,
    check_writable,
    expanded_size_of_zip,
)

logger = get_logger("HSR 更新")

LogFn = Callable[[str], None]


@dataclass(frozen=True)
class UpdateOutcome:
    """一次更新尝试的结果。"""

    engine: str
    checked: bool
    updated: bool
    current_version: str | None = None
    latest_version: str | None = None
    update_available: bool = False
    message: str = ""
    #: 目录可能处于中间状态——调用方应让本轮脚本进入异常态，别继续跑。
    blocking: bool = False


def _noop(_: str) -> None:
    return None


async def check_engine_update(
    engine: str,
    install_root: Path,
    *,
    source: str,
    channel: str = "stable",
    cdk: str = "",
    proxy: httpx.Proxy | None = None,
) -> DiscoveryResult:
    """只查版本，不下载、不改动目录。供 API 的「检查更新」按钮使用。"""

    spec = get_spec(engine)
    current = await asyncio.to_thread(read_installed_version, spec, install_root)
    return await discover(
        spec,
        current_version=current,
        source=_coerce_source(spec, source),
        channel=channel,
        cdk=cdk,
        proxy=proxy,
        seven_zip_available=find_seven_zip(install_root) is not None,
    )


async def update_engine_if_needed(
    engine: str,
    install_root: Path,
    *,
    source: str,
    channel: str = "stable",
    cdk: str = "",
    proxy: httpx.Proxy | None = None,
    download_dir: Path,
    send_log: LogFn | None = None,
    should_abort: AbortFn | None = None,
) -> UpdateOutcome:
    """查、下、装。任何可预期失败都收敛成 ``UpdateOutcome``，不向上抛。

    ``should_abort`` 供调用方在下载途中喊停（收尾期的更新跑在 shield 里，
    取消传不进来）。装包阶段不再询问——那一段是事务，中途停下比跑完更危险。
    """

    log = send_log or _noop
    spec = get_spec(engine)
    label = spec.display_name

    if not install_root.is_dir():
        return UpdateOutcome(engine, checked=False, updated=False)

    try:
        result = await check_engine_update(
            engine,
            install_root,
            source=source,
            channel=channel,
            cdk=cdk,
            proxy=proxy,
        )
    except HSRUpdateError as exc:
        log(f"{label} 更新检查失败，按现有版本继续：{exc}")
        return UpdateOutcome(engine, checked=False, updated=False, message=str(exc))
    except Exception as exc:  # noqa: BLE001 - 检查失败绝不能拖垮任务
        logger.opt(exception=True).warning(f"HSR 更新：{label} 检查更新时出错")
        log(f"{label} 更新检查异常，按现有版本继续：{exc}")
        return UpdateOutcome(engine, checked=False, updated=False, message=str(exc))

    base = {
        "engine": engine,
        "checked": True,
        "current_version": result.current_version,
        "latest_version": result.latest_version,
        "update_available": result.update_available,
    }

    if not result.update_available:
        log(f"{label} 已是最新版本（{result.current_version or '未知'}）")
        return UpdateOutcome(**base, updated=False)

    if result.blocked_reason:
        log(
            f"{label} 有新版本 {result.latest_version}，但无法安装：{result.blocked_reason}"
        )
        return UpdateOutcome(**base, updated=False, message=result.blocked_reason)

    candidate = result.candidate
    assert candidate is not None  # installable 为真时必然存在

    # ── 前置门：任一不过就跳过本轮，目录一动不动 ──
    # 进程扫描要遍历整张进程表（实测 ~250ms），API 手动更新走的是事件循环，
    # 得丢线程；写探针是同步 IO，顺手一起。
    for failure in (
        await asyncio.to_thread(check_no_process_running, install_root),
        await asyncio.to_thread(check_writable, install_root),
    ):
        if failure:
            log(f"{label} 跳过更新：{failure.reason}")
            return UpdateOutcome(**base, updated=False, message=failure.reason)

    log(f"{label} 发现新版本 {candidate.latest_version}，开始下载")

    package = (
        download_dir
        / f"{spec.mirrorchyan_rid}-{candidate.latest_version}{_suffix(candidate)}"
    )
    try:
        package = await _download_with_space_check(
            candidate,
            package,
            install_root=install_root,
            download_dir=download_dir,
            proxy=proxy,
            log=log,
            should_abort=should_abort,
        )
    except HSRUpdateAborted as exc:
        log(f"{label} {exc}")
        return UpdateOutcome(**base, updated=False, message=str(exc))
    except HSRUpdateError as exc:
        log(f"{label} 下载失败，按现有版本继续：{exc}")
        return UpdateOutcome(**base, updated=False, message=str(exc))

    if package is None:
        return UpdateOutcome(**base, updated=False, message="磁盘余量不足，已跳过更新")

    # 下载完才知道解压后的确切体积，装之前再核一次安装卷。
    if candidate.asset_kind == "zip":
        try:
            expanded = await asyncio.to_thread(expanded_size_of_zip, package)
        except Exception:  # noqa: BLE001 - 读不出就沿用粗估
            expanded = None
        if expanded is not None:
            failure = check_disk_space(
                install_root=install_root,
                download_dir=download_dir,
                package_bytes=0,
                expanded_bytes=expanded,
            )
            if failure:
                log(f"{label} 跳过更新：{failure.reason}")
                return UpdateOutcome(**base, updated=False, message=failure.reason)

    log(f"{label} 下载完成，开始应用更新")
    try:
        applied = await asyncio.to_thread(
            apply_package,
            package,
            install_root,
            engine=engine,
            from_version=candidate.current_version,
            to_version=candidate.latest_version,
            seven_zip=find_seven_zip(install_root),
        )
    except HSRUpdateApplyError as exc:
        log(f"{label} 更新失败：{exc}")
        return UpdateOutcome(
            **base,
            updated=False,
            message=str(exc),
            blocking=not exc.rolled_back,
        )
    except HSRUpdateError as exc:
        log(f"{label} 更新失败，目录未改动：{exc}")
        return UpdateOutcome(**base, updated=False, message=str(exc))
    finally:
        _discard(package)

    message = f"{label} 已更新到 {applied.to_version}（{applied.changed_files} 个文件）"
    log(message)
    logger.success(f"HSR 更新：{message}")
    return UpdateOutcome(
        **{**base, "current_version": applied.to_version},
        updated=True,
        message=message,
    )


async def rollback_pending(
    install_root: Path, *, send_log: LogFn | None = None
) -> bool:
    """回滚上一轮崩在中途的更新。在 ``prepare()`` 里调用，不联网。"""

    log = send_log or _noop
    if not install_root.is_dir() or not has_pending_journal(install_root):
        return False
    try:
        done = await asyncio.to_thread(rollback, install_root)
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=True).error(f"HSR 更新：回滚 {install_root} 失败")
        log(f"发现未完成的更新但回滚失败：{exc}")
        return False
    if done:
        log(f"已回滚上一次未完成的更新：{install_root}")
    return done


async def _download_with_space_check(
    candidate,
    package: Path,
    *,
    install_root: Path,
    download_dir: Path,
    proxy: httpx.Proxy | None,
    log: LogFn,
    should_abort: AbortFn | None = None,
) -> Path | None:
    from .download import download_package

    # Mirror 酱给的是一次性直链，HEAD 预检也算一次消费，会把真正的下载打空。
    # 其余源可以先问一下体积，好在动手前就把磁盘不足挡掉。
    if candidate.source != "MirrorChyan":
        size = await _remote_size(candidate.download_url, proxy=proxy)
        if size:
            failure = check_disk_space(
                install_root=install_root,
                download_dir=download_dir,
                package_bytes=size,
            )
            if failure:
                log(f"跳过更新：{failure.reason}")
                return None

    return await download_package(
        candidate, package, proxy=proxy, should_abort=should_abort
    )


async def _remote_size(url: str, *, proxy: httpx.Proxy | None) -> int:
    """取远端体积用于磁盘预检。取不到就返回 0，跳过粗估这一步。"""

    try:
        async with httpx.AsyncClient(
            proxy=proxy, follow_redirects=True, timeout=30.0
        ) as client:
            response = await client.head(url, headers={"User-Agent": "AutoMasGui"})
            if response.status_code >= 400:
                return 0
            return int(response.headers.get("Content-Length") or 0)
    except Exception:  # noqa: BLE001 - 预检失败不该阻止下载
        return 0


def _coerce_source(spec: EngineSpec, source: str) -> str:
    """把配置里的源字符串收敛到该引擎真正支持的集合。

    与 ``OptionsValidator`` 同口径：非法值回退到首项，而不是静默换源到别的
    合法值——首项就是该引擎的默认源。
    """

    value = str(source or "").strip()
    if value in spec.sources:
        return value
    logger.warning(
        f"HSR 更新：{spec.display_name} 不支持下载源 {value!r}，回退到 {spec.sources[0]}"
    )
    return spec.sources[0]


def _suffix(candidate) -> str:
    return ".7z" if candidate.asset_kind == "7z" else ".zip"


def _discard(package: Path) -> None:
    try:
        package.unlink()
    except OSError:
        pass


__all__ = [
    "UpdateOutcome",
    "check_engine_update",
    "rollback_pending",
    "update_engine_if_needed",
]
