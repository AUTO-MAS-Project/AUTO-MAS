#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.services import System
from app.utils import get_logger, ProcessManager
from app.utils.io import read_file, write_file
from .config import (
    is_src_config_available,
    read_src_installation_id,
    validate_src_installation,
)
from .poor_yaml import poor_yaml_read


logger = get_logger("SRC 进程清理")

_WEBUI_LISTENER_RETRY_INTERVAL = 0.2


@dataclass(frozen=True, slots=True)
class SrcProcessState:
    """一次 SRC 启动的进程清理状态。"""

    script_id: str
    src_root_path: Path
    installation_id: str
    webui_port: int | None
    config_user_id: str | None = None


def validate_src_cleanup_paths(
    src_root_path: Path,
    src_exe_path: Path,
    src_set_path: Path,
    *,
    expected_installation_id: str | None = None,
) -> tuple[Path, Path, Path]:
    """校验清理范围是一个具体 SRC 安装目录，而非宽泛系统路径。"""

    resolved_root_path = src_root_path.resolve()
    resolved_exe_path = src_exe_path.resolve()
    resolved_set_path = src_set_path.resolve()
    expected_exe_path = resolved_root_path / "src.exe"
    expected_set_path = resolved_root_path / "config"

    if resolved_exe_path != expected_exe_path:
        raise ValueError(f"SRC 可执行文件不属于清理根目录: {resolved_exe_path}")
    if resolved_set_path != expected_set_path:
        raise ValueError(f"SRC 配置目录不属于清理根目录: {resolved_set_path}")

    sensitive_paths = {
        Path.cwd().resolve(),
        Path.home().resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    system_paths: set[Path] = set()
    for env_name in (
        "SystemRoot",
        "windir",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramData",
        "USERPROFILE",
    ):
        env_path = os.environ.get(env_name)
        if env_path:
            resolved_env_path = Path(env_path).resolve()
            sensitive_paths.add(resolved_env_path)
            if env_name in ("SystemRoot", "windir"):
                system_paths.add(resolved_env_path)

    root_anchor = Path(resolved_root_path.anchor).resolve()
    if resolved_root_path == root_anchor or any(
        sensitive_path == resolved_root_path
        or sensitive_path.is_relative_to(resolved_root_path)
        for sensitive_path in sensitive_paths
    ):
        raise ValueError(f"SRC 清理根目录范围过宽: {resolved_root_path}")
    if any(resolved_root_path.is_relative_to(path) for path in system_paths):
        raise ValueError(f"SRC 清理根目录位于系统目录内: {resolved_root_path}")
    if not resolved_root_path.exists():
        return resolved_root_path, expected_exe_path, expected_set_path
    if not expected_exe_path.is_file():
        raise ValueError(f"SRC 清理根目录缺少 src.exe: {resolved_root_path}")
    if expected_installation_id is not None:
        validate_src_installation(resolved_root_path, expected_installation_id)
    backup_set_path = expected_set_path.with_name(expected_set_path.name + ".old")
    config_identity_available = False
    for config_path in (expected_set_path, backup_set_path):
        if config_path.exists() and config_path.resolve() != config_path:
            raise ValueError(f"SRC 配置目录指向清理根目录之外: {config_path}")
        if is_src_config_available(config_path):
            config_identity_available = True
    if not config_identity_available:
        raise ValueError(f"SRC 清理根目录缺少配置特征: {resolved_root_path}")
    nested_src_exe_path = next(
        (
            path
            for path in resolved_root_path.rglob("src.exe")
            if path.resolve() != expected_exe_path
        ),
        None,
    )
    if nested_src_exe_path is not None:
        raise ValueError(f"SRC 清理根目录包含嵌套安装: {nested_src_exe_path.parent}")

    return resolved_root_path, expected_exe_path, expected_set_path


def read_src_process_state(
    state_path: Path,
    *,
    expected_script_id: str | None = None,
) -> SrcProcessState | None:
    """读取上一次 SRC 启动时使用的根目录和 WebUI 端口。"""

    if not state_path.exists():
        return None

    state = read_file(state_path)
    if (
        not isinstance(state, dict)
        or "script_id" not in state
        or "src_root_path" not in state
        or "webui_port" not in state
    ):
        raise ValueError(f"SRC 进程状态文件无效: {state_path}")

    script_id = state["script_id"]
    if not isinstance(script_id, str) or not script_id.strip():
        raise ValueError(f"SRC 进程状态脚本无效: {script_id}")
    if expected_script_id is not None and script_id != expected_script_id:
        raise ValueError(f"SRC 进程状态所属脚本无效: {script_id}")

    src_root_path = state["src_root_path"]
    if not isinstance(src_root_path, str) or not src_root_path.strip():
        raise ValueError(f"SRC 进程状态根目录无效: {src_root_path}")
    stored_root_path = Path(src_root_path)
    if not stored_root_path.is_absolute():
        raise ValueError(f"SRC 进程状态根目录不是绝对路径: {src_root_path}")

    webui_port = state["webui_port"]
    if webui_port is not None and (
        not isinstance(webui_port, int)
        or isinstance(webui_port, bool)
        or not 1 <= webui_port <= 65535
    ):
        raise ValueError(f"SRC 进程状态端口无效: {webui_port}")
    config_user_id = state.get("config_user_id")
    if config_user_id is not None and (
        not isinstance(config_user_id, str) or not config_user_id.strip()
    ):
        raise ValueError(f"SRC 脚本设置用户无效: {config_user_id}")
    installation_id = state.get("installation_id")
    if not isinstance(installation_id, str) or not installation_id.strip():
        raise ValueError(f"SRC 进程状态安装标识无效: {installation_id}")
    return SrcProcessState(
        script_id=script_id,
        src_root_path=stored_root_path.resolve(),
        installation_id=installation_id,
        webui_port=webui_port,
        config_user_id=config_user_id,
    )


def write_src_process_state(
    state_path: Path,
    *,
    script_id: str,
    src_root_path: Path,
    webui_port: int | None,
    installation_id: str | None = None,
    config_user_id: str | None = None,
) -> None:
    """原子记录本次 SRC 启动时使用的根目录和 WebUI 端口。"""

    if not isinstance(script_id, str) or not script_id.strip():
        raise ValueError(f"SRC 进程状态脚本无效: {script_id}")
    if webui_port is not None and (
        not isinstance(webui_port, int)
        or isinstance(webui_port, bool)
        or not 1 <= webui_port <= 65535
    ):
        raise ValueError(f"SRC WebUI 启动端口无效: {webui_port}")
    if config_user_id is not None and (
        not isinstance(config_user_id, str) or not config_user_id.strip()
    ):
        raise ValueError(f"SRC 脚本设置用户无效: {config_user_id}")
    if installation_id is None:
        installation_id = read_src_installation_id(src_root_path)
    elif not isinstance(installation_id, str) or not installation_id.strip():
        raise ValueError(f"SRC 进程状态安装标识无效: {installation_id}")
    write_file(
        state_path,
        {
            "script_id": script_id,
            "src_root_path": str(src_root_path.resolve()),
            "installation_id": installation_id,
            "webui_port": webui_port,
            "config_user_id": config_user_id,
        },
    )


def read_src_webui_port(src_set_path: Path) -> int | None:
    """读取并校验 SRC WebUI 端口。

    Args:
        src_set_path (Path): SRC 配置目录。

    Returns:
        int | None: 有效端口；未配置或配置无效时返回 None。
    """

    deploy_path = src_set_path / "deploy.yaml"
    if not deploy_path.exists():
        return None

    webui_port = poor_yaml_read(deploy_path).get("WebuiPort")
    if webui_port is None:
        logger.debug("SRC 未配置 WebUI 端口, 跳过端口进程清理")
        return None
    if not isinstance(webui_port, int) or isinstance(webui_port, bool):
        logger.warning(f"SRC WebUI 端口无效, 跳过端口进程清理: {webui_port}")
        return None
    if not 1 <= webui_port <= 65535:
        logger.warning(f"SRC WebUI 端口超出范围, 跳过端口进程清理: {webui_port}")
        return None

    return webui_port


async def _kill_src_root_processes(src_root_path: Path) -> bool:
    """中止可执行文件位于 SRC 根目录内的残留辅助进程。"""

    src_root_path = src_root_path.resolve()
    success = True
    try:
        executable_names = {
            executable_path.name.casefold()
            for executable_path in src_root_path.rglob("*.exe")
        }
        processes = psutil.process_iter(["pid", "name", "exe"])
        for process in processes:
            try:
                process_info = process.info
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except (psutil.AccessDenied, OSError) as e:
                success = False
                logger.warning(f"读取 SRC 辅助进程信息失败: {e}")
                continue

            process_path = process_info.get("exe")
            process_pid = process_info.get("pid")
            if not isinstance(process_pid, int):
                continue
            if not process_path:
                process_name = process_info.get("name")
                if process_name and str(process_name).casefold() in executable_names:
                    success = False
                    logger.warning(
                        "无法确认同名 SRC 辅助进程路径，拒绝判定清理成功 "
                        f"PID: {process_pid}, 进程名: {process_name}"
                    )
                continue
            if process_pid == os.getpid():
                continue

            try:
                resolved_process_path = Path(process_path).resolve()
                resolved_process_path.relative_to(src_root_path)
            except ValueError:
                continue
            except OSError as e:
                success = False
                logger.warning(
                    f"解析 SRC 辅助进程路径失败 PID: {process_pid}, 原因: {e}"
                )
                continue

            try:
                logger.info(
                    f"中止 SRC 根目录辅助进程: {resolved_process_path}, "
                    f"PID: {process_pid}"
                )
                if not await System.kill_process_by_pid(process_pid):
                    success = False
            except Exception as e:
                success = False
                logger.opt(exception=True).warning(
                    f"中止 SRC 根目录辅助进程失败 PID: {process_pid}, 原因: {e}"
                )
    except (psutil.AccessDenied, OSError) as e:
        success = False
        logger.warning(f"扫描 SRC 根目录辅助进程失败: {e}")

    return success


async def kill_src_processes(
    process_manager: ProcessManager,
    *,
    src_exe_path: Path,
    src_root_path: Path,
    src_set_path: Path,
    webui_port: int | None = None,
    listener_wait_timeout: float | None = None,
    expected_installation_id: str | None = None,
) -> bool:
    """独立中止 SRC 跟踪进程、主进程和 WebUI 进程。

    Args:
        process_manager (ProcessManager): SRC 进程管理器。
        src_exe_path (Path): SRC 主程序路径。
        src_root_path (Path): SRC 根目录。
        src_set_path (Path): SRC 配置目录。
        webui_port (int | None): 本次 SRC 启动时使用的 WebUI 端口；未提供时读取当前配置。
        listener_wait_timeout (float | None): 等待延迟监听进程的秒数；未提供时按跟踪状态决定。
        expected_installation_id (str | None): 持久化的 SRC 安装实例标识。

    Returns:
        bool: 所有清理步骤均成功时返回 True。
    """

    success = True
    tracked_pid = process_manager.main_pid
    tracked_tree_killed = False

    # 已跟踪 PID 由本次任务直接启动，不依赖磁盘配置特征来证明归属。
    # 即使 SRC 运行期间写坏了配置，也必须先尽力终止该进程树。
    if tracked_pid is not None:
        try:
            if await process_manager.is_running():
                tracked_tree_killed = await System.kill_process_by_pid(tracked_pid)
                if not tracked_tree_killed:
                    success = False
        except Exception as e:
            success = False
            logger.opt(exception=True).warning(
                f"按进程树中止 SRC 跟踪进程失败 PID: {tracked_pid}, 原因: {e}"
            )

    try:
        src_root_path, src_exe_path, src_set_path = validate_src_cleanup_paths(
            src_root_path,
            src_exe_path,
            src_set_path,
            expected_installation_id=expected_installation_id,
        )
    except (OSError, ValueError) as e:
        logger.warning(f"拒绝不安全的 SRC 进程清理范围: {e}")
        if tracked_pid is not None:
            try:
                await process_manager.kill()
            except Exception as cleanup_error:
                logger.opt(exception=True).warning(
                    f"中止 SRC 跟踪进程失败: {cleanup_error}"
                )
        return False

    if not src_root_path.exists() and tracked_pid is None:
        logger.info(f"SRC 历史清理根目录已不存在，跳过进程扫描: {src_root_path}")
        return success

    try:
        if not await System.kill_process(src_exe_path):
            success = False
    except Exception as e:
        success = False
        logger.opt(exception=True).warning(f"按路径中止 SRC 进程失败: {e}")

    try:
        if not await _kill_src_root_processes(src_root_path):
            success = False
    except Exception as e:
        success = False
        logger.opt(exception=True).warning(f"中止 SRC 根目录辅助进程失败: {e}")

    try:
        await process_manager.kill()
    except Exception as e:
        success = False
        logger.opt(exception=True).warning(f"中止 SRC 跟踪进程失败: {e}")

    try:
        if listener_wait_timeout is None:
            listener_wait_timeout = (
                2.0 if tracked_pid is not None and not tracked_tree_killed else 0.0
            )
        if not await kill_src_webui_process(
            src_root_path,
            src_set_path,
            webui_port=webui_port,
            listener_wait_timeout=listener_wait_timeout,
        ):
            success = False
    except Exception as e:
        success = False
        logger.opt(exception=True).warning(f"中止 SRC WebUI 进程失败: {e}")

    # 端口等待期间仍可能有已脱离主进程、但尚未开始监听的辅助进程启动。
    # 恢复配置前再扫描一次 SRC 根目录，避免将这类进程误判为已清理。
    try:
        if not await _kill_src_root_processes(src_root_path):
            success = False
    except Exception as e:
        success = False
        logger.opt(exception=True).warning(f"复查 SRC 根目录辅助进程失败: {e}")

    return success


async def kill_src_webui_process(
    src_root_path: Path,
    src_set_path: Path,
    *,
    webui_port: int | None = None,
    listener_wait_timeout: float = 0.0,
) -> bool:
    """中止占用 SRC WebUI 端口且可执行文件位于 SRC 目录内的进程。

    Args:
        src_root_path (Path): SRC 根目录。
        src_set_path (Path): SRC 配置目录。
        webui_port (int | None): 本次 SRC 启动时使用的 WebUI 端口；未提供时读取当前配置。
        listener_wait_timeout (float): 等待延迟启动的 WebUI 监听进程的最长秒数。

    Returns:
        bool: 端口查询和匹配进程清理均未失败时返回 True。
    """

    try:
        if webui_port is None:
            webui_port = read_src_webui_port(src_set_path)
    except Exception as e:
        logger.opt(exception=True).warning(f"读取 SRC WebUI 端口失败: {e}")
        return False

    if webui_port is None:
        return True

    src_root_path = src_root_path.resolve()
    deadline = asyncio.get_running_loop().time() + max(listener_wait_timeout, 0.0)
    while True:
        try:
            connections = await asyncio.to_thread(psutil.net_connections, kind="tcp")
        except (psutil.AccessDenied, OSError) as e:
            logger.warning(f"查询 SRC WebUI 端口进程失败: {e}")
            return False

        handled_pids: set[int] = set()
        matched_listener = False
        success = True
        for connection in connections:
            if (
                connection.pid is None
                or connection.pid in handled_pids
                or connection.status != psutil.CONN_LISTEN
                or connection.laddr.port != webui_port
            ):
                continue
            handled_pids.add(connection.pid)

            try:
                process_path = Path(psutil.Process(connection.pid).exe()).resolve()
            except psutil.NoSuchProcess:
                continue
            except (psutil.AccessDenied, OSError) as e:
                success = False
                logger.warning(
                    f"无法确认 SRC WebUI 端口进程路径 PID: {connection.pid}, 原因: {e}"
                )
                continue

            try:
                process_path.relative_to(src_root_path)
            except ValueError:
                continue

            matched_listener = True
            try:
                logger.info(
                    f"中止 SRC WebUI 端口进程: {process_path}, 端口: {webui_port}"
                )
                if not await System.kill_process_by_pid(connection.pid):
                    success = False
            except Exception as e:
                success = False
                logger.opt(exception=True).warning(f"中止 SRC WebUI 端口进程失败: {e}")

        if not success or matched_listener:
            return success
        if asyncio.get_running_loop().time() >= deadline:
            return True
        await asyncio.sleep(_WEBUI_LISTENER_RETRY_INTERVAL)
