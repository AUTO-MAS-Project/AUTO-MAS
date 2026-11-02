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

"""魔改 AVD 的服务层：根目录状态与开机前检查、电源操作前关实例。

添加流程：``status``（组件齐不齐、电脑检查）→ 齐了按普通路径纳管（Emulator 2.0 的 ``paths/add``）。
组件全部随模拟器内测包提供，MAS 不下载；缺了只说缺哪一项。实例的新建 / 删除 / 启停走 Emulator 2.0
原有接口。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from app.models.config import EmulatorConfig
from app.utils import get_logger

from ..detect import avd_root_of
from ..facade import load_paths
from . import cli as modavd_cli
from . import components, precheck, updater
from .constants import POWER_CLOSE_TIMEOUT_SECONDS

logger = get_logger("魔改 AVD 服务")


def _cli_status_result(root: Path, data: object) -> dict[str, Any]:
    """把 modavd ``check --json`` 映射成现有 ``/avd/status`` 响应。"""
    if not isinstance(data, dict):
        raise RuntimeError("modavd check 返回的数据不是对象")
    raw_components = data.get("components")
    raw_items = data.get("items")
    if not isinstance(raw_components, list) or not isinstance(raw_items, list):
        raise RuntimeError("modavd check 缺少 components 或 items")
    components_out: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw in raw_components:
        if not isinstance(raw, dict):
            continue
        installed = bool(raw.get("installed", False))
        optional = bool(raw.get("optional", False))
        item = {
            "id": raw.get("id", ""),
            "name": raw.get("name", ""),
            "version": raw.get("version", "") or "",
            "build": raw.get("build") or None,
            "outdatedTestPackage": False,
            "installed": installed,
            "optional": optional,
            "localSdk": bool(raw.get("local_sdk", False)),
            "testPackage": installed and raw.get("id") == "emulator",
            "needsTestPackage": (not installed) and raw.get("id") == "emulator",
        }
        components_out.append(item)
        if not optional and not installed:
            missing.append(str(item["name"]))
    acceleration = next(
        (
            item
            for item in raw_items
            if isinstance(item, dict) and item.get("id") == "acceleration"
        ),
        None,
    )
    acceleration_ok = acceleration.get("ok") if acceleration else None
    acceleration_detail = ""
    if isinstance(acceleration, dict):
        reason = str(acceleration.get("reason") or "")
        advice = str(acceleration.get("advice") or "")
        acceleration_detail = f"{reason}。{advice}" if advice else reason
    return {
        "root": str(data.get("root") or root),
        # 现有 API 的 ready 只表示根目录组件齐全，电脑检查失败仍允许先把根目录纳管；
        # CLI 的 CheckResult.ready 还会把硬件 / 内存拦截项算进去，不能直接照搬。
        "ready": not missing,
        "components": components_out,
        "missing": missing,
        "accelerationOk": acceleration_ok,
        "accelerationDetail": acceleration_detail,
        "prechecks": raw_items,
    }


def _normalize_root(root: str) -> Path:
    path = Path(str(root or "").strip())
    if not str(path) or not path.is_absolute():
        raise ValueError("请选择一个完整路径的文件夹作为魔改 AVD 根目录")
    if path.exists() and not path.is_dir():
        raise ValueError(f"{path} 不是文件夹")
    return path


async def status(
    root: str, *, check_acceleration: bool = True, refresh: bool = False
) -> dict[str, Any]:
    """根目录现状：组件、硬件加速、开机前电脑检查。只读。"""
    path = _normalize_root(root)
    # 更新器换包时，任何 CLI 查询都会把 tools\\modavd.exe 算作占用；状态接口本身
    # 不需要 CLI，直接返回文件组件快照，避免面板轮询挡住换包。
    if updater.update_in_progress(path):
        result = await asyncio.to_thread(components.install_status, path)
        result["accelerationOk"] = None
        result["accelerationDetail"] = ""
        result["prechecks"] = []
        return result
    cli = await modavd_cli.resolve_cli(path)
    if cli is not None:
        return _cli_status_result(path, await cli.check())
    result = await asyncio.to_thread(components.install_status, path)
    result["accelerationOk"] = None
    result["accelerationDetail"] = ""
    result["prechecks"] = []
    if check_acceleration:
        # 内存按默认档实例估（各实例实际开机时按它要传的 -memory 再查一次）
        items = await precheck.run_prechecks(path, refresh=refresh)
        result["prechecks"] = [item.as_dict() for item in items]
        accel = next(item for item in items if item.id == "acceleration")
        result["accelerationOk"] = accel.ok
        if accel.ok is not None:
            result["accelerationDetail"] = accel.reason if accel.ok else accel.message()
    return result


# ---- 关机 / 重启 / 注销前 ---------------------------------------------------


def managed_roots(configs: Iterable[EmulatorConfig]) -> list[Path]:
    """Emulator 2.0 配置里纳管的全部魔改 AVD 根目录（去重）。"""
    roots: dict[str, Path] = {}
    for config in configs:
        try:
            if config.Info.Type != "emulator2":
                continue
            paths = load_paths(config.Info.Paths)
        except Exception as e:  # noqa: BLE001 - 一条配置读不出不影响其余
            logger.warning(f"读取模拟器配置失败，跳过: {e}")
            continue
        for path in paths:
            if path.type == "avd":
                root = avd_root_of(path.install_path)
                roots.setdefault(components.root_key(root), root)
    return list(roots.values())


async def close_instances(
    targets: list[tuple[str, Callable[[], Awaitable[object]]]], *, timeout: float
) -> dict[str, str]:
    """并发跑一组关机动作，整体不超过 ``timeout`` 秒。单个失败 / 超时只记日志。

    返回 ``{名字: closed / failed / timeout}``。超时的动作被取消（不等它）。
    """
    if not targets:
        return {}
    tasks = {
        asyncio.create_task(action(), name=f"avd-close-{name}"): name
        for name, action in targets
    }
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    results: dict[str, str] = {}
    for task in done:
        name = tasks[task]
        error = task.exception()
        if error is None:
            results[name] = "closed"
        else:
            results[name] = "failed"
            logger.warning(f"魔改 AVD 实例 {name} 关机失败: {error}")
    for task in pending:
        name = tasks[task]
        task.cancel()
        results[name] = "timeout"
        logger.warning(f"魔改 AVD 实例 {name} 未在 {timeout:.0f} 秒内关完，放弃等待")
    return results


async def close_running_instances(
    configs: Iterable[EmulatorConfig], *, timeout: float = POWER_CLOSE_TIMEOUT_SECONDS
) -> dict[str, str]:
    """关机 / 重启 / 注销前关闭所有魔改 AVD。

    CLI 根目录一次调用 ``stop --all``，避免未登记实例被逐台 stop 时漏掉 sync；CLI 不可用时，
    按用户定的例外退回 Python 的 sync + emu kill 路径。

    每个根目录的「探测 CLI → stop --all / 退回 Python」整个放进一个并发动作，共用 ``timeout`` 秒：
    某个根目录的 modavd 卡在 ``version`` 上，不会推迟别的根目录开始关机，也不会让关机多等。
    ``stop --all`` 有实例没关掉时这个根目录记 ``failed``，不报成 ``closed``。
    """
    roots = await asyncio.to_thread(managed_roots, list(configs))
    targets: list[tuple[str, Callable[[], Awaitable[object]]]] = [
        (str(root), lambda root_path=root: _close_root(root_path, timeout=timeout))
        for root in roots
    ]
    if not targets:
        return {}
    logger.info(
        f"关机前先正常关闭 {len(targets)} 个魔改 AVD 根目录的实例（安卓正常关机）"
    )
    return await close_instances(targets, timeout=timeout)


async def _close_root(root: Path, *, timeout: float) -> object:
    """一个根目录的关机前收尾，见 :func:`close_running_instances`。"""
    if updater.update_in_progress(root):
        # 换包期间不起 modavd（它会占着 tools\\modavd.exe）；这时本来就没有实例开着，只按进程扫一遍
        return await _close_python_root(root, timeout=timeout)
    try:
        cli = await modavd_cli.resolve_cli(root)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"{root} 的 modavd 不可用，关机前退回 Python sync + emu kill: {e}"
        )
        return await _close_python_root(root, timeout=timeout)
    if cli is None:
        return await _close_python_root(root, timeout=timeout)
    try:
        result = await cli.stop_all()
    except (modavd_cli.CLIError, modavd_cli.ModAvdUnavailable) as e:
        logger.warning(
            f"{root} 的 modavd stop --all 失败，退回 Python sync + emu kill: {e}"
        )
        return await _close_python_root(root, timeout=timeout)
    failed = result.get("failed", []) if isinstance(result, dict) else []
    if failed:
        raise RuntimeError(f"modavd stop --all 有 {len(failed)} 台没关掉: {failed}")
    return result


async def _close_python_root(root: Path, *, timeout: float) -> dict[str, str]:
    """单根目录的旧 Python 关机例外。"""
    from .components import manager_key_exe
    from .manager import _AvdCore

    manager = _AvdCore(
        manager_exe=manager_key_exe(root),
        max_wait_time=60,
        force_kill_on_close=False,
    )
    running = await asyncio.to_thread(manager._scan_processes)
    targets = [
        (f"{root}#{idx}", lambda m=manager, i=idx: m.close(i)) for idx in running
    ]
    return await close_instances(targets, timeout=timeout)
