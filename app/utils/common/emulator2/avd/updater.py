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

"""ModAVD 更新：MAS 只调根目录里的 ``modavd update``（:meth:`.cli.ModAvdCli.update`），自己不下载、
不动文件。

本模块是薄薄一层，调用 ``status`` / ``update`` / ``startup`` 须显式传入 ``UpdateHost``；MAS 应用入口
统一使用 :mod:`app.core.emulator_manager.update`，由宿主装配配置、代理环境和进度发布。

- **查更新**（:func:`status` 带 ``check``）：``modavd update check``。结果按根目录记在内存里（更新源一改
  就作废），之后不带 ``check`` 的状态查询（``modavd update status``，不联网）照样给出最新版本。
- **更新**（:func:`update`）：本根目录有实例开着或正在开机就直接拒绝、请用户先关掉。否则在后台依次
  ``modavd update prepare``（下载、核对、暂存，这时实例照样能开）和 ``modavd update install``（换上）。
  换上前再按 ``modavd list`` 和 MAS 正在开机的实例看一次，有就停在「已下载好」，下次直接换上。
  只有 ``install`` 运行期间算「正在更新」（:func:`update_in_progress`）：这时这个根目录不许开机、新建、
  改设置、删除、装 APK、重启，查询不起 modavd，按换上前那次 ``list`` 给中性结果。
- **启动恢复**（:func:`startup`）：每个纳管的根目录跑一次 ``update status``，``phase`` 是 ``swapping``
  （上次换上被打断）时再跑 ``update recover``。

更新源、Mirror 酱 CDK 每次用 ``--source`` / ``--cdk-dpapi`` 传 MAS 的设置（CDK 是 DPAPI 密文，MAS 不解密，
不进日志）；旧命令行没有这两个选项时不传，用 modavd 自己的设置。进度来自 modavd 的 stderr 日志，经主
WebSocket 推（``id=EmulatorManager``、``type=emulator2.avd-update.progress``），界面另用 HTTP 快照兜底。
别的程序（图形管理器、另一个 modavd）在更新时 modavd 报 ``busy``，原样显示它的说明。
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils import get_logger

from .cli import (
    CLI_EXE_RELATIVE_PATH,
    CLIError,
    ModAvdCli,
    ModAvdUnavailable,
    UpdateProgressEvent,
    resolve_cli,
)
from .components import root_key

logger = get_logger("ModAVD 更新")

#: 进度消息最密多久发一条（阶段变了照样等这么久，最后的结果不等）。
_PUBLISH_INTERVAL_SECONDS = 0.5
#: modavd 的 ``update.Status.phase``：换上做到一半（上次被打断）。
_PHASE_SWAPPING = "swapping"
_NUMBERS = re.compile(r"\d+")
#: 传了 Mirror 酱 CDK 的密文、modavd 却报 ``invalid_argument``（密文在这台机器上解不开）时，用空 CDK 再跑
#: 一次（更新源照旧，没有 CDK 时 modavd 从 GitHub 下），结果的提示里加上这一句。
CDK_UNREADABLE_NOTICE = "Mirror 酱 CDK 读不出，这次改从 GitHub 下载"


@dataclass
class UpdateProgress:
    """推给界面的进度：``stage`` 是当前在做的事，``status`` 是 running / success / failed / idle。"""

    stage: str = "idle"
    status: str = "idle"
    message: str = ""
    percent: float | None = None
    downloadedBytes: int | None = None
    totalBytes: int | None = None
    speedBytesPerSec: float | None = None


@dataclass(frozen=True)
class UpdateSettings:
    """宿主当前的更新设置；CDK 密文不进对象表示和日志。

    ``source`` 是 ``github`` / ``mirrorchyan``；``cdk_dpapi`` 是 Mirror 酱 CDK 的 DPAPI 密文的 base64
    （MAS 配置里存的 ``DPAPI:<base64>`` 去掉前缀），空串表示不用 CDK。"""

    source: str
    automas_version: str
    cdk_dpapi: str = field(repr=False)


@dataclass(frozen=True)
class UpdateHost:
    """更新器所需的宿主能力，不持有配置总管、管理器或消息总线。

    ``environment`` 给 modavd 子进程的整份环境（带上 MAS 设的代理），``None`` 继承 MAS 的环境。"""

    settings: Callable[[], UpdateSettings]
    environment: Callable[[], Mapping[str, str] | None]
    managed_roots: Callable[[], list[Path]]
    opening_instances: Callable[[Path], list[str]]
    publish_progress: Callable[[Path, UpdateProgress], Awaitable[None]]


@dataclass(frozen=True)
class _Checked:
    """最近一次查更新的结果（``modavd update check`` 或 prepare / install 里顺带查的）。"""

    source: str
    latest_version: str = ""
    required_automas: str = ""
    check_error: str = ""


class _Runtime:
    """一个根目录在本进程里的更新状态：同一时刻只跑一次更新。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.job: asyncio.Task[None] | None = None
        self.progress = UpdateProgress()
        self.checked: _Checked | None = None
        #: 最近一次的状态快照：更新进行中不起 modavd，查状态时给它
        self.snapshot: dict[str, Any] | None = None

    @property
    def busy(self) -> bool:
        return self.job is not None and not self.job.done()


_runtimes: dict[str, _Runtime] = {}
#: MAS 自己起的 ``modavd update install`` 正在跑的根目录。
_installing: set[str] = set()
#: 换上前最后一次 ``modavd list`` 的实例（原样的对象），换上期间给只读查询用。
_instance_snapshots: dict[str, list[dict[str, Any]]] = {}


def _runtime(root: Path) -> _Runtime:
    key = root_key(root)
    runtime = _runtimes.get(key)
    if runtime is None:
        runtime = _runtimes[key] = _Runtime(root)
    return runtime


def update_in_progress(root: str | Path) -> bool:
    """MAS 自己起的 ``modavd update install`` 正在换这个根目录：会改东西的操作一律拒绝，查询不起 modavd。"""
    return root_key(root) in _installing


def instances_snapshot(root: str | Path) -> list[dict[str, Any]]:
    """换上期间用的实例列表：换上前最后一次 ``modavd list`` 的 ``instances``，没有就空。"""
    return list(_instance_snapshots.get(root_key(root), []))


# ---- 小工具 ----------------------------------------------------------------


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _numbers(text: str) -> list[int]:
    return [int(part) for part in _NUMBERS.findall(text)[:4]]


def _version_less(a: str, b: str) -> bool:
    """按数字段比较两个版本（``v0.9.0`` < ``v0.10.0``，``v5.8.0`` < ``5.10``），预发布标记不管。"""
    x, y = _numbers(a), _numbers(b)
    width = max(len(x), len(y))
    return x + [0] * (width - len(x)) < y + [0] * (width - len(y))


def _display(version: str) -> str:
    """给人看的版本写法：去掉开头的 ``v``。"""
    return re.sub(r"^v(?=\d)", "", version)


def _as_status(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CLIError("internal", "modavd update 返回的数据不是对象")
    return data


def _error_text(error: CLIError) -> str:
    """modavd 的错误说明（message 原样，再带上建议）。"""
    return f"{error.message}（建议：{error.advice}）" if error.advice else error.message


def _last_result(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("action"), str):
        return None
    return {
        "action": value["action"],
        "ok": value.get("ok") is not False,
        "version": _text(value.get("version")),
        "error": _text(value.get("error")),
    }


def _caller_options(settings: UpdateSettings) -> dict[str, str]:
    return {
        "automas_version": settings.automas_version,
        "source": settings.source,
        "cdk_dpapi": settings.cdk_dpapi,
    }


async def _caller_update(
    cli: ModAvdCli,
    action: str,
    settings: UpdateSettings,
    *,
    env: Mapping[str, str] | None,
    on_progress: Callable[[UpdateProgressEvent], None] | None = None,
) -> tuple[dict[str, Any], str]:
    """带上 MAS 的更新源和 CDK 跑 ``modavd update <action>``，返回 ``(状态, 提示)``。

    传了 CDK 而 modavd 报 ``invalid_argument``（解不开）时用空 CDK 重试一次，提示是
    :data:`CDK_UNREADABLE_NOTICE`；别的错误、或重试又失败都原样抛。"""
    options = _caller_options(settings)
    try:
        data = await cli.update(action, **options, env=env, on_progress=on_progress)
        return _as_status(data), ""
    except CLIError as error:
        if error.code != "invalid_argument" or not settings.cdk_dpapi:
            raise
        logger.warning(
            f"{cli.root} 的 modavd 解不开 MAS 设置里的 Mirror 酱 CDK（update {action}），"
            "这次用空 CDK 重试"
        )
    data = await cli.update(
        action, **{**options, "cdk_dpapi": ""}, env=env, on_progress=on_progress
    )
    return _as_status(data), CDK_UNREADABLE_NOTICE


def _with_notice(message: str, notice: str) -> str:
    return f"{message}；{notice}" if message and notice else (message or notice)


def _remember_check(runtime: _Runtime, data: Mapping[str, Any], source: str) -> None:
    """记下 modavd 这次查到的最新版本（没查就不动之前记的）。"""
    if data.get("checked") is True:
        runtime.checked = _Checked(
            source,
            latest_version=_text(data.get("latest_version")),
            required_automas=_text(data.get("required_automas")),
        )
    elif _text(data.get("check_error")):
        runtime.checked = _Checked(source, check_error=_text(data["check_error"]))


def _is_running(item: Mapping[str, Any]) -> bool:
    status = _text(item.get("status")).lower()
    return (
        item.get("running") is True
        or bool(_text(item.get("busy")))
        or status in {"online", "starting", "creating"}
    )


def _instance_items(listing: object) -> list[dict[str, Any]]:
    items = listing.get("instances") if isinstance(listing, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _running_indices(items: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(item["index"])
        for item in items
        if item.get("index") is not None and _is_running(item)
    )


# ---- 根目录 ----------------------------------------------------------------


async def _managed(root: str, *, host: UpdateHost) -> Path:
    """只认 Emulator 2.0 里已经加进来的 ModAVD 根目录。"""
    text = str(root or "").strip()
    if not text or not Path(text).is_absolute():
        raise ValueError("请给出 ModAVD 根目录的完整路径")
    key = root_key(text)
    for managed in await asyncio.to_thread(host.managed_roots):
        if root_key(managed) == key:
            return managed
    raise ValueError(f"{text} 还没有作为 ModAVD 加进模拟器管理，不能更新")


async def _require_cli(root: Path) -> ModAvdCli:
    cli = await resolve_cli(root)
    if cli is None:
        raise ValueError(f"这个根目录里没有 {CLI_EXE_RELATIVE_PATH}，不能更新")
    return cli


# ---- 状态快照 --------------------------------------------------------------


def _snapshot(
    root: Path,
    runtime: _Runtime,
    data: Mapping[str, Any],
    *,
    settings: UpdateSettings,
    running: int = 0,
) -> dict[str, Any]:
    """把 modavd 的 ``update.Status`` 换成 ``/avd/update/status`` 的响应。

    modavd 给不出的几项填中性值：``belowMinimum`` 恒为 false、``minimumBuild`` / ``minimumVersion`` /
    ``latestBuild`` 空串、``assetSize`` 0。"""
    updatable = data.get("updatable") is True
    checked = runtime.checked
    if checked is not None and checked.source != settings.source:
        checked = None
    current = _text(data.get("current_version"))
    latest = checked.latest_version if checked else ""
    available = bool(updatable and latest) and (
        not current or _version_less(current, latest)
    )
    required = checked.required_automas if checked else ""
    too_old = bool(
        available
        and required
        and settings.automas_version
        and _version_less(settings.automas_version, required)
    )
    return {
        "root": str(root),
        "updatable": updatable,
        "notUpdatableReason": ""
        if updatable
        else _text(data.get("not_updatable_reason")),
        "currentVersion": current,
        "currentBuild": _text(data.get("current_build")),
        "belowMinimum": False,
        "minimumBuild": "",
        "minimumVersion": "",
        "checkError": checked.check_error if checked else "",
        "latestVersion": latest,
        "latestBuild": "",
        "updateAvailable": available,
        "requiredAutoMas": required if too_old else "",
        "assetSize": 0,
        "phase": _text(data.get("phase")) or "idle",
        "preparedVersion": _text(data.get("prepared_version")) if updatable else "",
        "runningInstances": running if updatable else 0,
        "busy": runtime.busy,
        "progress": asdict(runtime.progress),
        "lastResult": _last_result(data.get("last_result")),
    }


def _unusable(root: Path, runtime: _Runtime, reason: str) -> dict[str, Any]:
    """命令行没有或用不了：不能更新，原因照实写。"""
    return {
        **_snapshot(root, runtime, {}, settings=UpdateSettings("", "", "")),
        "notUpdatableReason": reason,
    }


async def _running(cli: ModAvdCli) -> tuple[list[str], list[dict[str, Any]]]:
    items = _instance_items(await cli.list())
    return _running_indices(items), items


async def status(root: str, *, check: bool = False, host: UpdateHost) -> dict[str, Any]:
    """一个根目录的更新现状。``check`` 为真时（界面上的「检查更新」）先 ``modavd update check``（查不到
    写在 ``checkError``，不算接口失败）。更新进行中不起 modavd，给最近一次的快照和进度。"""
    path = await _managed(root, host=host)
    runtime = _runtime(path)
    if runtime.busy:
        return {
            **(runtime.snapshot or _unusable(path, runtime, "")),
            "busy": True,
            "progress": asdict(runtime.progress),
        }
    settings = host.settings()
    if runtime.checked is not None and runtime.checked.source != settings.source:
        runtime.checked = None  # 更新源改了：之前查到的不作数
    try:
        cli = await _require_cli(path)
    except (ValueError, ModAvdUnavailable) as e:
        return _unusable(path, runtime, str(e))
    data: dict[str, Any] | None = None
    if check:
        try:
            data, notice = await _caller_update(
                cli, "check", settings, env=host.environment()
            )
            _remember_check(runtime, data, settings.source)
            if notice:
                runtime.progress = UpdateProgress(message=notice)
        except CLIError as e:
            logger.warning(f"检查 ModAVD 更新失败: {e.message}")
            runtime.checked = _Checked(settings.source, check_error=_error_text(e))
    try:
        if data is None:
            data = _as_status(await cli.update("status"))
    except CLIError as e:
        return _unusable(path, runtime, _error_text(e))
    running = 0
    if data.get("updatable") is True:
        try:
            indices, _ = await _running(cli)
            running = len(set(indices) | set(host.opening_instances(path)))
        except CLIError as e:
            logger.warning(f"{path} 查开着的实例失败，按没有算: {e.message}")
            running = len(host.opening_instances(path))
    result = _snapshot(path, runtime, data, settings=settings, running=running)
    runtime.snapshot = result
    return result


# ---- 更新 ------------------------------------------------------------------


class _Reporter:
    """把 modavd 的进度日志换成 :class:`UpdateProgress`，按 :data:`_PUBLISH_INTERVAL_SECONDS` 节流
    依次发出去（只发最新的那条，不并发、不乱序）。"""

    def __init__(self, runtime: _Runtime, host: UpdateHost) -> None:
        self.runtime = runtime
        self.host = host
        self._dirty = asyncio.Event()
        self._task = asyncio.create_task(
            self._loop(), name=f"avd-update-progress:{runtime.root}"
        )
        self._download: tuple[float, int] | None = None
        self._speed: float | None = None

    def set(self, stage: str, message: str, **fields: Any) -> None:
        self.runtime.progress = UpdateProgress(
            stage=stage, status="running", message=message, **fields
        )
        self._dirty.set()

    def __call__(self, event: UpdateProgressEvent) -> None:
        known = event.total_bytes > 0
        if event.stage == "downloading" and known:
            now = time.monotonic()
            if self._download is not None and now > self._download[0]:
                delta = event.done_bytes - self._download[1]
                if delta >= 0:
                    self._speed = delta / (now - self._download[0])
            self._download = (now, event.done_bytes)
        self.set(
            event.stage or "running",
            event.message,
            percent=event.percent if event.percent >= 0 else None,
            downloadedBytes=event.done_bytes if known else None,
            totalBytes=event.total_bytes if known else None,
            speedBytesPerSec=self._speed if event.stage == "downloading" else None,
        )

    async def _loop(self) -> None:
        while True:
            await self._dirty.wait()
            self._dirty.clear()
            try:
                await self.host.publish_progress(
                    self.runtime.root, self.runtime.progress
                )
            except Exception as e:  # noqa: BLE001 - 推不出去不影响更新
                logger.warning(f"推送 ModAVD 更新进度失败: {e}")
            await asyncio.sleep(_PUBLISH_INTERVAL_SECONDS)

    async def close(self) -> None:
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task


def _finish(runtime: _Runtime, stage: str, status_text: str, message: str) -> None:
    runtime.progress = UpdateProgress(stage=stage, status=status_text, message=message)


def _cannot_swap(version: str, count: int) -> str:
    return (
        f"{_display(version)} 已下载并核对好，但现在不能换上：这个 ModAVD 还有 {count} 台实例开着，"
        "请先关掉。处理好后再点「更新」直接换上，不用重新下载"
    )


async def _prepare(
    runtime: _Runtime,
    cli: ModAvdCli,
    settings: UpdateSettings,
    env: Mapping[str, str] | None,
    reporter: _Reporter,
) -> tuple[dict[str, Any], str]:
    """``update prepare``，返回 ``(状态, 提示)``；查不了新版本但之前已经准备好一版时，照样拿那一版去换上。"""
    try:
        data, notice = await _caller_update(
            cli, "prepare", settings, env=env, on_progress=reporter
        )
    except CLIError as error:
        with suppress(CLIError):
            local = _as_status(await cli.update("status"))
            if _text(local.get("prepared_version")):
                logger.warning(
                    f"{runtime.root} 这次没准备成（{error.message}），换上之前准备好的 "
                    f"{_display(local['prepared_version'])}"
                )
                return local, ""
        raise
    _remember_check(runtime, data, settings.source)
    return data, notice


async def _run_update(runtime: _Runtime, cli: ModAvdCli, host: UpdateHost) -> None:
    root = runtime.root
    settings = host.settings()
    env = host.environment()
    reporter = _Reporter(runtime, host)
    step = "prepare"
    notice = ""
    try:
        reporter.set("checking", "正在查最新版本")
        data, notice = await _prepare(runtime, cli, settings, env, reporter)
        prepared = _text(data.get("prepared_version"))
        if not prepared:
            _finish(
                runtime, "idle", "idle", _text(data.get("message")) or "已经是最新版本"
            )
            return
        running, items = await _running(cli)
        if running or host.opening_instances(root):
            count = len(set(running) | set(host.opening_instances(root)))
            _finish(runtime, "staged", "failed", _cannot_swap(prepared, count))
            return
        key = root_key(root)
        # 从这里到起 install 之间没有 await：先登记「正在更新」（之后开机一律被拒），再看有没有正在开机的。
        # 和开机（open 先登记自己、_open 再看「正在更新」）互斥，两边总有一边看得见另一边
        _installing.add(key)
        _instance_snapshots[key] = items
        try:
            opening = host.opening_instances(root)
            if opening:
                _finish(
                    runtime, "staged", "failed", _cannot_swap(prepared, len(opening))
                )
                return
            step = "install"
            reporter.set("installing", "正在换上新版")
            data, install_notice = await _caller_update(
                cli, "install", settings, env=env, on_progress=reporter
            )
            notice = notice or install_notice
        finally:
            _installing.discard(key)
            _instance_snapshots.pop(key, None)
        _remember_check(runtime, data, settings.source)
        message = _text(data.get("message"))
        if data.get("updated") is True:
            _finish(runtime, "installed", "success", message or "已更新")
        else:
            _finish(runtime, "idle", "idle", message or "已经是最新版本")
    except CLIError as e:
        logger.warning(
            f"{root} 更新 ModAVD 没成（{e.code}）: {e.message} {e.details or ''}"
        )
        if e.code == "busy":
            # install 报 busy：新版已经下好、核对过，留着下次直接换上；别人在更新时 prepare 也报 busy
            _finish(
                runtime,
                "staged" if step == "install" else "failed",
                "failed",
                _error_text(e),
            )
        else:
            _finish(runtime, "failed", "failed", f"更新失败：{_error_text(e)}")
    except Exception as e:  # noqa: BLE001 - 失败如实交给界面
        logger.opt(exception=True).warning(f"{root} 更新 ModAVD 失败: {e}")
        _finish(runtime, "failed", "failed", f"更新失败：{e}")
    finally:
        await reporter.close()
        if notice:
            runtime.progress.message = _with_notice(runtime.progress.message, notice)
        with suppress(Exception):
            await host.publish_progress(root, runtime.progress)


def _action(
    reason: str, message: str, *, ok: bool = False, running: int = 0
) -> dict[str, Any]:
    return {
        "ok": ok,
        "reason": reason,
        "message": message,
        "runningInstances": running,
    }


async def update(root: str, *, host: UpdateHost) -> dict[str, Any]:
    """「更新」：后台 ``modavd update prepare`` 再 ``install``，立刻返回，进度看 WebSocket / 状态快照。

    本根目录有实例开着或正在开机就什么都不动，返回 ``instances_running``，请用户先关掉。"""
    path = await _managed(root, host=host)
    runtime = _runtime(path)
    if runtime.busy:
        return _action("busy", "正在更新，请稍候")
    cli = await _require_cli(path)
    data = _as_status(await cli.update("status"))
    if data.get("updatable") is not True:
        raise ValueError(
            _text(data.get("not_updatable_reason")) or "这个根目录不能更新"
        )
    running, _ = await _running(cli)
    if runtime.busy:
        return _action("busy", "正在更新，请稍候")
    busy = sorted(set(running) | set(host.opening_instances(path)))
    if busy:
        return _action(
            "instances_running",
            f"这个 ModAVD 还有 {len(busy)} 台实例开着，请先关闭再更新",
            running=len(busy),
        )
    runtime.job = asyncio.create_task(
        _run_update(runtime, cli, host), name=f"avd-update:{path}"
    )
    return _action("started", "已开始", ok=True)


# ---- 启动 ------------------------------------------------------------------


async def _recover_root(root: Path) -> None:
    try:
        cli = await resolve_cli(root)
    except ModAvdUnavailable as e:
        logger.info(f"{root} 的 modavd 用不了，跳过更新恢复: {e}")
        return
    if cli is None or _runtime(root).busy:
        return
    data = _as_status(await cli.update("status"))
    if data.get("phase") != _PHASE_SWAPPING:
        return
    data = _as_status(await cli.update("recover"))
    logger.warning(
        f"{root} 的 ModAVD 更新：{_text(data.get('recovered')) or _text(data.get('message'))}"
    )


async def startup(*, host: UpdateHost) -> None:
    """MAS 启动时收拾上次没做完的换上（要在定时器拉起实例之前）。各根目录一起做，失败只记日志。"""
    roots = await asyncio.to_thread(host.managed_roots)

    async def one(root: Path) -> None:
        try:
            await _recover_root(root)
        except Exception as e:  # noqa: BLE001 - 一个根目录恢复失败不影响别的
            logger.opt(exception=True).error(f"{root} 的 ModAVD 更新恢复失败: {e}")

    await asyncio.gather(*(one(root) for root in roots))


__all__ = [
    "UpdateHost",
    "UpdateProgress",
    "UpdateSettings",
    "instances_snapshot",
    "startup",
    "status",
    "update",
    "update_in_progress",
]
