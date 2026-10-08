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

"""魔改 AVD 的服务层：根目录状态与开机前检查、实例选项、安装 APK、电源操作前关实例。

添加流程：``status``（组件齐不齐、电脑检查）→ 齐了按普通路径纳管（Emulator 2.0 的 ``paths/add``）。
组件全部随模拟器内测包提供，MAS 不下载；缺了只说缺哪一项。实例的新建 / 删除 / 启停走 Emulator 2.0
原有接口。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.utils import get_logger

from . import components, precheck
from .constants import POWER_CLOSE_TIMEOUT_SECONDS

logger = get_logger("魔改 AVD 服务")


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


def _avd_roots() -> list[Path]:
    """Emulator 2.0 配置里纳管的全部魔改 AVD 根目录（去重）。"""
    from app.core import Config

    from ..detect import avd_root_of
    from ..facade import load_paths

    roots: dict[str, Path] = {}
    for config in list(Config.EmulatorConfig.values()):
        try:
            if config.get("Info", "Type") != "emulator2":
                continue
            paths = load_paths(config.get("Info", "Paths"))
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
    *, timeout: float = POWER_CLOSE_TIMEOUT_SECONDS
) -> dict[str, str]:
    """关机 / 重启 / 注销前，对正在跑的魔改 AVD 实例逐个走 ``close``（先 ``sync`` 再关）。

    电源路径之后会按进程名强杀模拟器，强杀不走客体关机流程，页缓存里没写回的数据会丢（10-03 星铁
    热更新清单变 0 字节）。这里整体限时，不让关机卡住；出任何错都只记日志。
    """
    from .components import manager_key_exe
    from .manager import AvdManager

    targets: list[tuple[str, Callable[[], Awaitable[object]]]] = []
    for root in await asyncio.to_thread(_avd_roots):
        try:
            manager = AvdManager(manager_key_exe(root), 60, False)
            running = await asyncio.to_thread(manager._scan_processes)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"列出 {root} 的魔改 AVD 实例失败: {e}")
            continue
        for idx in running:
            targets.append((f"{root}#{idx}", lambda m=manager, i=idx: m.close(i)))
    if not targets:
        return {}
    logger.info(f"关机前先正常关闭 {len(targets)} 台魔改 AVD 实例（先 sync）")
    return await close_instances(targets, timeout=timeout)


# ---- 实例选项 -------------------------------------------------------------


async def _backend(emulator_id: str, slot: str):
    from ..service import build_manager
    from .manager import AvdManager

    manager = await build_manager(emulator_id)
    path, record = manager.resolve_slot(str(slot))
    if path.type != "avd":
        raise ValueError("该设备不是魔改 AVD")
    backend = await manager.manager_for(path)
    assert isinstance(backend, AvdManager)
    return backend, record.native_index


async def instance_options(emulator_id: str, slot: str) -> dict[str, Any]:
    backend, native_index = await _backend(emulator_id, slot)
    return backend.instance_options(native_index)


async def set_instance_options(
    emulator_id: str,
    slot: str,
    *,
    memory_mb: int | None = None,
    balloon: bool | None = None,
) -> dict[str, Any]:
    """只改传了的项（``None`` = 不改）。"""
    backend, native_index = await _backend(emulator_id, slot)
    return backend.set_instance_options(
        native_index,
        memory_mb=memory_mb,
        balloon=balloon,
    )


async def install_apk(emulator_id: str, slot: str, apk_path: str) -> dict[str, Any]:
    """在开着的实例里装一个本地 ``.apk``。只认 ``.apk``；``.xapk`` / 拆分包不支持。

    只收完整路径：相对路径会按后端的工作目录解析，装进去的未必是用户选的那个文件。"""
    text = str(apk_path or "").strip().strip('"')
    if not text:
        raise ValueError("请选择要安装的 APK 文件")
    apk = Path(text)
    if not apk.is_absolute():
        raise ValueError(f"请给出安装包的完整路径（{text}）")
    if apk.suffix.lower() != ".apk":
        raise ValueError(f"{apk.name} 不是 .apk 安装包（.xapk、拆分安装包暂不支持）")
    if not await asyncio.to_thread(apk.is_file):
        raise ValueError(f"找不到安装包 {apk}")
    backend, native_index = await _backend(emulator_id, slot)
    result = await backend.install_apk(native_index, apk)
    return {
        "ok": True,
        "reason": "ok",
        "message": f"已安装 {apk.name}",
        "result": result,
    }
