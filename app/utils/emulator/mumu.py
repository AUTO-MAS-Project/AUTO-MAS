#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
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


import asyncio
import json

import psutil

from app.utils.platform import IS_WINDOWS

if IS_WINDOWS:
    import win32con
    import win32gui
    import win32process
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase, DeviceInfo, DeviceStatus
from app.utils import ProcessRunner, get_logger

logger = get_logger("MuMu模拟器管理")

MUMU_FORCE_KILL_KEYWORDS = (
    "mumunxdevice",
    "mumunxmain",
    "mumuvmmheadless",
)
# 强力清理后等进程真正退出的上限（秒），kill 是异步的，发完信号不等于已经没了
MUMU_FORCE_KILL_WAIT_SECONDS = 10
MUMU_STORE_PACKAGE = "com.mumu.store"
MUMU_STORE_OVERLAY_APP_OP = "SYSTEM_ALERT_WINDOW"


class MumuManager(DeviceBase):
    """
    基于MuMuManager.exe的模拟器管理
    """

    def __init__(self, config: EmulatorConfig) -> None:
        if not (Path(config.get("Info", "Path"))).exists():
            raise FileNotFoundError(
                f"MuMuManager.exe文件不存在: {config.get('Info', 'Path')}"
            )

        if config.get("Info", "Type") != "mumu":
            raise ValueError("配置的模拟器类型不是mumu")

        self.config = config

        self.emulator_path = Path(config.get("Info", "Path"))

    def get_adb_path(self) -> Path | None:
        adb_path = self.emulator_path.parent / "adb.exe"
        return adb_path if adb_path.exists() else None

    async def _get_app_state(self, idx: str, package_name: str) -> str | None:
        started_at = time.monotonic()
        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "control",
                "-v",
                idx,
                "app",
                "info",
                "-pkg",
                package_name,
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:
            logger.warning(
                f"获取 MuMu 应用状态失败: {e} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒"
            )
            return None

        if result.returncode != 0:
            logger.warning(f"获取 MuMu 应用状态失败: {result.stdout.strip()}")
            return None

        try:
            data = self._decode_polluted_json(
                result.stdout,
                lambda v: isinstance(v, dict) and isinstance(v.get("state"), str),
            )
        except json.JSONDecodeError as e:
            logger.warning(
                f"解析 MuMu 应用状态失败: {e} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒"
            )
            return None

        if not isinstance(data, dict) or not isinstance(data.get("state"), str):
            logger.warning(f"MuMu 应用状态返回异常: {result.stdout.strip()}")
            return None

        state = data["state"].strip().lower()
        logger.info(
            f"MuMu 应用状态: {idx} - {package_name} - {state} - 用时: "
            f"{time.monotonic() - started_at:.3f}秒"
        )
        return state

    @staticmethod
    def _is_app_foreground(data: str, package_name: str) -> bool:
        package_component = f"{package_name}/"
        foreground_markers = (
            "topResumedActivity=",
            "ResumedActivity:",
            "mResumedActivity:",
            "mCurrentFocus=",
        )
        return any(
            package_component in line
            and any(marker in line for marker in foreground_markers)
            for line in data.splitlines()
        )

    async def _wait_app_foreground(self, idx: str, package_name: str) -> bool:
        started_at = time.monotonic()
        logger.info(f"开始检查 MuMu 应用前台状态: {idx} - {package_name}")
        for attempt in range(6):
            try:
                result = await ProcessRunner.run_process(
                    self.emulator_path,
                    "adb",
                    "-v",
                    idx,
                    "shell",
                    "dumpsys",
                    "activity",
                    "activities",
                    timeout=self.config.get("Info", "MaxWaitTime"),
                    if_merge_std=True,
                    breakaway=True,
                )
            except Exception as e:
                logger.debug(f"检查 MuMu 应用前台状态失败({attempt + 1}/6): {e}")
            else:
                if result.returncode == 0 and self._is_app_foreground(
                    result.stdout, package_name
                ):
                    logger.info(
                        f"MuMu 应用已进入前台: {idx} - {package_name} - "
                        f"第 {attempt + 1}/6 次，用时: "
                        f"{time.monotonic() - started_at:.3f}秒"
                    )
                    return True
                logger.debug(
                    f"MuMu 应用未进入前台({attempt + 1}/6): "
                    f"{idx} - {package_name} - returncode={result.returncode}"
                )
                if result.returncode != 0:
                    logger.debug(f"检查 MuMu 应用前台状态失败: {result.stdout.strip()}")

            if attempt < 5:
                await asyncio.sleep(1)

        logger.warning(
            f"MuMu 应用前台检查超时: {idx} - {package_name} - 用时: "
            f"{time.monotonic() - started_at:.3f}秒"
        )
        return False

    async def _ensure_app_foreground(self, idx: str, package_name: str) -> bool:
        started_at = time.monotonic()
        logger.info(f"开始检查 MuMu 应用运行状态: {idx} - {package_name}")
        state = await self._get_app_state(idx, package_name)
        if state != "running":
            logger.info(
                f"MuMu 应用未运行，执行补启动: {idx} - {package_name} - {state}"
            )
            try:
                launch_started_at = time.monotonic()
                result = await ProcessRunner.run_process(
                    self.emulator_path,
                    "control",
                    "-v",
                    idx,
                    "app",
                    "launch",
                    "-pkg",
                    package_name,
                    timeout=self.config.get("Info", "MaxWaitTime"),
                    if_merge_std=True,
                    breakaway=True,
                )
                if result.returncode != 0:
                    logger.warning(f"MuMu 应用补启动失败: {result.stdout.strip()}")
                else:
                    logger.info(
                        f"MuMu 应用补启动命令已完成: {idx} - {package_name} - "
                        f"用时: {time.monotonic() - launch_started_at:.3f}秒"
                    )
            except Exception as e:
                logger.warning(f"MuMu 应用补启动失败: {e}")

        foreground_started_at = time.monotonic()
        if await self._wait_app_foreground(idx, package_name):
            logger.info(
                f"MuMu 应用前台补启动结束: {idx} - {package_name} - 结果: 成功 - "
                f"总用时: {time.monotonic() - started_at:.3f}秒"
            )
            return True
        logger.info(
            f"首次前台检查未通过: {idx} - {package_name} - 用时: "
            f"{time.monotonic() - foreground_started_at:.3f}秒"
        )

        logger.warning(f"MuMu 应用未进入前台，尝试使用 monkey 补启动: {package_name}")
        try:
            monkey_started_at = time.monotonic()
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "adb",
                "-v",
                idx,
                "shell",
                "monkey",
                "-p",
                package_name,
                "1",
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
            if result.returncode != 0:
                logger.warning(f"MuMu monkey 补启动失败: {result.stdout.strip()}")
            else:
                logger.info(
                    f"MuMu monkey 补启动命令已完成: {idx} - {package_name} - "
                    f"用时: {time.monotonic() - monkey_started_at:.3f}秒"
                )
        except Exception as e:
            logger.warning(f"MuMu monkey 补启动失败: {e}")

        if await self._wait_app_foreground(idx, package_name):
            logger.info(
                f"MuMu 应用前台补启动结束: {idx} - {package_name} - 结果: 成功 - "
                f"总用时: {time.monotonic() - started_at:.3f}秒"
            )
            return True

        logger.warning(
            f"MuMu 应用补启动后仍未进入前台，将继续运行: {idx} - {package_name}"
        )
        logger.info(
            f"MuMu 应用前台补启动结束: {idx} - {package_name} - 结果: 失败 - "
            f"总用时: {time.monotonic() - started_at:.3f}秒"
        )
        return False

    async def _block_store_overlay_ads(self, idx: str) -> None:
        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "adb",
                "-v",
                idx,
                "shell",
                "appops",
                "set",
                MUMU_STORE_PACKAGE,
                MUMU_STORE_OVERLAY_APP_OP,
                "deny",
                timeout=10,
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:
            logger.warning(f"屏蔽 MuMu 应用商店悬浮广告失败: {e}")
        else:
            if result.returncode == 0:
                logger.success("已屏蔽 MuMu 应用商店悬浮广告")
            else:
                logger.warning(
                    f"屏蔽 MuMu 应用商店悬浮广告失败: {result.stdout.strip()}"
                )

        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "adb",
                "-v",
                idx,
                "shell",
                "am",
                "force-stop",
                MUMU_STORE_PACKAGE,
                timeout=10,
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:
            logger.warning(f"停止 MuMu 应用商店广告进程失败: {e}")
            return

        if result.returncode == 0:
            logger.success("已停止 MuMu 应用商店广告进程")
        else:
            logger.warning(f"停止 MuMu 应用商店广告进程失败: {result.stdout.strip()}")

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        started_at = time.monotonic()
        logger.info(f"开始启动模拟器 {idx}  - {package_name}")

        from app.core import Config

        status = DeviceStatus.UNKNOWN  # 初始化status变量
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if status == DeviceStatus.ONLINE:
                logger.info(
                    f"模拟器已在线，跳过应用启动检查: {idx} - {package_name} - "
                    f"用时: {time.monotonic() - started_at:.3f}秒"
                )
                if Config.get("Function", "IfBlockAd"):
                    await self._block_store_overlay_ads(idx)
                return (await self.getInfo(idx))[idx]
            elif status == DeviceStatus.OFFLINE:
                logger.info(f"模拟器离线，开始执行启动流程: {idx} - {package_name}")
                break
            await asyncio.sleep(0.1)

        else:
            logger.warning(
                f"模拟器初始状态检查超时: {idx} - {package_name} - "
                f"当前状态: {status} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒"
            )
            raise RuntimeError(f"模拟器 {idx} 无法启动, 当前状态码: {status}")

        # 启动前强力清理要放在检查多开器窗口之前：清理会把多开器一起关掉，
        # 之后按「启动前没开多开器」的口径处理启动过程中弹出的窗口
        if self.config.get("Info", "ForceKillBeforeLaunch"):
            await self._force_clear_before_launch()

        if_close_mumu_nx = await self.find_mumu_nx_window() is None

        # 启动实例前关闭 MuMu 应用保活
        logger.info(f"关闭 MuMu 应用保活: {idx}")
        keepalive_started_at = time.monotonic()
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "setting",
            "-v",
            idx,
            "-k",
            "app_keptlive",
            "-val",
            "false",
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"设置 app_keptlive 失败: {result.failure_detail()}")

        logger.info(
            f"MuMu 应用保活设置完成: {idx} - 用时: "
            f"{time.monotonic() - keepalive_started_at:.3f}秒"
        )

        logger.info(f"执行 MuMu 启动命令: {idx} - {package_name}")
        launch_started_at = time.monotonic()
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "control",
            "-v",
            idx,
            "launch",
            *(["-pkg", package_name] if package_name else []),
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        # 参考命令 MuMuManager.exe control -v 2 launch

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.failure_detail()}")

        logger.info(
            f"MuMu 启动命令已完成，等待实例在线: {idx} - 用时: "
            f"{time.monotonic() - launch_started_at:.3f}秒"
        )
        online_started_at = time.monotonic()
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if if_close_mumu_nx:
                if_close_mumu_nx = not await self.close_mumu_nx_window()
            if Config.get("Function", "IfSilence") and status == DeviceStatus.STARTING:
                await self.setVisible(idx, False)
            elif status == DeviceStatus.ONLINE:
                logger.info(
                    f"模拟器已在线: {idx} - {package_name} - 用时: "
                    f"{time.monotonic() - online_started_at:.3f}秒"
                )
                if Config.get("Function", "IfBlockAd"):
                    await self._block_store_overlay_ads(idx)
                if package_name:
                    try:
                        await self._ensure_app_foreground(idx, package_name)
                    except Exception as e:
                        logger.warning(
                            f"MuMu 应用检查或补启动异常，将继续运行: "
                            f"{idx} - {package_name} - {e}"
                        )
                    await asyncio.sleep(
                        30 if self.config.get("Info", "MaxWaitTime") > 60 else 3
                    )
                else:
                    await asyncio.sleep(3)
                return (await self.getInfo(idx))[idx]
            await asyncio.sleep(0.1)
        else:
            diagnosis = await self._describe_launch_failure(idx)
            logger.warning(
                f"模拟器启动等待超时: {idx} - {package_name} - "
                f"当前状态: {status} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒"
            )
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(
                    f"模拟器 {idx} 启动失败, 状态码: {status}{diagnosis}"
                )
            raise RuntimeError(
                f"模拟器 {idx} 启动超时, 当前状态码: {status}{diagnosis}"
            )

    async def _describe_launch_failure(self, idx: str) -> str:
        """启动失败 / 超时报错的附加说明。旧配置不加，Emulator 2.0 的后端覆盖它。"""
        return ""

    async def close(self, idx: str) -> DeviceStatus:
        started_at = time.monotonic()
        try:
            status = await self.getStatus(idx)
            if status not in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
                logger.warning(f"设备{idx}未在线，当前状态: {status}")
                return status

            result = await ProcessRunner.run_process(
                self.emulator_path,
                "control",
                "-v",
                idx,
                "shutdown",
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
            # 参考命令 MuMuManager.exe control -v 2 shutdown

            if result.returncode != 0:
                raise RuntimeError(f"命令执行失败: {result.failure_detail()}")

            logger.info(
                f"MuMu 关闭命令已完成: {idx} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒"
            )
            deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
            while time.monotonic() < deadline:
                status = await self.getStatus(idx)
                if status == DeviceStatus.OFFLINE:
                    return DeviceStatus.OFFLINE
                await asyncio.sleep(0.1)

            else:
                if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                    raise RuntimeError(f"模拟器 {idx} 关闭失败, 状态码: {status}")
                raise RuntimeError(f"模拟器 {idx} 关闭超时, 当前状态码: {status}")
        finally:
            if self.config.get("Info", "ForceKillOnClose"):
                self._force_kill_mumu_processes()

    async def _list_running_instances(self) -> dict[str, str]:
        """列出在线或启动中的实例，返回 ``{索引: 名称}``。"""

        data_json = self._decode_polluted_json(
            await self.get_device_info("all"), self._has_device_entries
        )
        return {
            str(value["index"]): str(value["name"])
            for value in self._extract_device_entries(data_json)
            if self._get_status_from_data(value) != DeviceStatus.OFFLINE
        }

    async def _force_clear_before_launch(self) -> None:
        """启动前关闭已在运行的 MuMu 实例并强力清理残留进程。

        已有非管理员权限的实例在跑时，MuMu 会拒绝新实例以管理员身份启动，
        所以先对在线 / 启动中的实例逐个 ``control shutdown`` 并等它们下线，
        再按固定进程白名单强力清理。清理范围是整台机器上的 MuMu 进程，
        与「强力关闭」相同，会关掉全部实例。

        Raises:
            RuntimeError: 残留进程无法结束。
        """

        running = await self._list_running_instances()
        if running:
            logger.warning(
                "启动前强力清理：将关闭 MuMu 实例 "
                + "、".join(f"{index}({name})" for index, name in running.items())
            )
            for index in running:
                try:
                    result = await ProcessRunner.run_process(
                        self.emulator_path,
                        "control",
                        "-v",
                        index,
                        "shutdown",
                        timeout=self.config.get("Info", "MaxWaitTime"),
                        if_merge_std=True,
                        breakaway=True,
                    )
                except Exception as e:
                    logger.warning(f"关闭 MuMu 实例 {index} 失败: {e}")
                else:
                    if result.returncode != 0:
                        logger.warning(
                            f"关闭 MuMu 实例 {index} 失败: {result.stdout.strip()}"
                        )

            deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
            while time.monotonic() < deadline:
                # 实例退出过程中 info 偶尔会失败，和 getStatus 一样只记日志继续等
                try:
                    running = await self._list_running_instances()
                except Exception as e:
                    logger.warning(f"等待 MuMu 实例关闭时读取实例状态失败: {e}")
                else:
                    if not running:
                        logger.info("已在运行的 MuMu 实例均已关闭")
                        break
                await asyncio.sleep(1)
            else:
                logger.warning(
                    "等待 MuMu 实例关闭超时，仍在运行: "
                    + "、".join(running)
                    + "，转为强力清理"
                )
        else:
            logger.info("启动前强力清理：没有在运行的 MuMu 实例")

        alive = await self._wait_processes_exit(self._force_kill_mumu_processes())
        if alive:
            raise RuntimeError(
                "启动前强力清理失败，以下 MuMu 进程无法结束: "
                + "、".join(self._describe_process(proc) for proc in alive)
            )

    def _force_kill_mumu_processes(self) -> list[psutil.Process]:
        """按 MuMu 固定进程白名单清理残留进程。

        Returns:
            list[psutil.Process]: 命中白名单、已发过结束信号的进程；调用方要确认
            它们真的退出时用 :meth:`_wait_processes_exit` 再等一次。
        """

        targets = [
            proc
            for proc in psutil.process_iter(["pid", "name", "exe"])
            if self._is_mumu_force_kill_target(
                proc.info.get("name") or "", proc.info.get("exe") or ""
            )
        ]
        if not targets:
            logger.info("未发现需要强力清理的 MuMu 残留进程")
            return []

        logger.info(
            "强力清理 MuMu 残留进程: "
            + "、".join(self._describe_process(proc) for proc in targets)
        )
        killed_count = 0
        for proc in targets:
            try:
                killed_count += self._kill_process_tree(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
                logger.warning(f"强力清理 MuMu 残留进程失败: {e}")

        logger.info(f"MuMu 残留进程清理完成，共结束 {killed_count} 个进程")
        return targets

    @staticmethod
    async def _wait_processes_exit(
        procs: list[psutil.Process],
    ) -> list[psutil.Process]:
        """等待进程退出，返回超时仍存活的进程。

        ``is_running`` 同时比对 pid 与创建时间，多开器被 MuMu 服务保活拉起的
        新进程不会被当成没杀掉的旧进程。
        """

        deadline = time.monotonic() + MUMU_FORCE_KILL_WAIT_SECONDS
        alive = list(procs)
        while alive and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
            alive = [proc for proc in alive if proc.is_running()]
        return alive

    @staticmethod
    def _describe_process(proc: psutil.Process) -> str:
        return f"{proc.info.get('name') or '?'}({proc.pid})"

    def _kill_process_tree(self, proc: psutil.Process) -> int:
        killed_count = 0
        for child in proc.children(recursive=True):
            killed_count += self._kill_process(child)
        killed_count += self._kill_process(proc)
        return killed_count

    @staticmethod
    def _kill_process(proc: psutil.Process) -> int:
        try:
            proc.kill()
            return 1
        except psutil.NoSuchProcess:
            return 0
        except (psutil.AccessDenied, OSError) as e:
            logger.warning(f"强力清理 MuMu 残留进程失败: {e}")
            return 0

    @staticmethod
    def _is_mumu_force_kill_target(proc_name: str, proc_exe: str) -> bool:
        target_text = f"{proc_name} {proc_exe}".lower()
        return any(keyword in target_text for keyword in MUMU_FORCE_KILL_KEYWORDS)

    @staticmethod
    def _decode_polluted_json(
        text: str, prefer: Callable[[object], bool] | None = None
    ) -> object:
        """从可能被污染的命令输出里取出 JSON。

        MuMu 会把埋点 (``add record:{...}``) 和 C++ 日志
        (``[*** LOG ERROR #0001 ***] ... {bad_weak_ptr}``) 写进同一份 stdout,
        对整段裸调 ``json.loads`` 会抛 ``Extra data`` 或 ``Expecting value``,
        而其中那份设备 JSON 本身是完整可用的。

        这里逐个候选位置尝试解码, 收集输出里所有顶层 JSON 值:
        ``prefer`` 命中的优先返回 (避免把埋点对象当成设备信息),
        都不命中时退回第一个, 一个都解不出来才抛 ``JSONDecodeError``。

        Args:
            text: 命令输出原文。
            prefer: 判断某个候选值是否为期望的那一份, 为 ``None`` 时取第一个。

        Returns:
            object: 解析出的 JSON 值。

        Raises:
            json.JSONDecodeError: 输出里没有任何可解析的 JSON。
        """

        decoder = json.JSONDecoder()
        candidates: list[object] = []
        i = 0
        while i < len(text):
            if text[i] not in "{[":
                i += 1
                continue
            try:
                value, end = decoder.raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            candidates.append(value)
            i = end

        if prefer is not None:
            for value in candidates:
                if prefer(value):
                    return value
        if candidates:
            return candidates[0]
        raise json.JSONDecodeError("输出中未找到 JSON", text, 0)

    @classmethod
    def _has_device_entries(cls, value: object) -> bool:
        return bool(cls._extract_device_entries(value))

    async def getStatus(self, idx: str, data: str | None = None) -> DeviceStatus:
        if data is None:
            try:
                data = await self.get_device_info(idx)
            except Exception as e:
                logger.error(f"获取模拟器 {idx} 信息失败: {e}")
                return DeviceStatus.ERROR
        try:
            data_json = self._decode_polluted_json(data, self._has_device_entries)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            return DeviceStatus.UNKNOWN

        return self._get_status_from_data(data_json)

    @staticmethod
    def _get_status_from_data(data: dict[str, object]) -> DeviceStatus:
        if data["is_android_started"]:
            return DeviceStatus.ONLINE
        elif data["is_process_started"]:
            return DeviceStatus.STARTING
        else:
            return DeviceStatus.OFFLINE

    @staticmethod
    def _resolve_adb_address(data: dict[str, object]) -> str | None:
        host = data.get("adb_host_ip") or data.get("adb_host")
        port = data.get("adb_port")
        if host and port:
            return f"{host}:{port}"

        return None

    @staticmethod
    def _get_default_adb_address(index: str | int) -> str:
        try:
            return f"127.0.0.1:{5555 + int(index) * 2}"
        except (TypeError, ValueError):
            return "Unknown"

    @staticmethod
    def _extract_device_entries(data: object) -> list[dict[str, object]]:
        if not isinstance(data, dict):
            return []

        if "index" in data and "name" in data:
            return [data]

        return [
            value
            for value in data.values()
            if isinstance(value, dict) and "index" in value and "name" in value
        ]

    async def _get_adb_address(self, data: dict[str, object], index: str | int) -> str:
        adb_address = self._resolve_adb_address(data)
        if adb_address is not None:
            return adb_address

        # 没起来的实例问 ``adb -v N`` 只会得到 "vm not running"，结果照样是下面的兜底值，
        # 白起一个子进程；状态轮询每轮都会经过这里，关着的实例多时这笔开销很可观
        if not data.get("is_process_started"):
            return self._get_default_adb_address(index)

        try:
            adb_data = await self.get_adb_info(index)
            adb_json = self._decode_polluted_json(
                adb_data, lambda v: self._resolve_adb_address(v) is not None
            )
        except Exception as e:
            logger.debug(
                f"获取 MuMu 模拟器 {index} ADB 信息失败，使用默认端口兜底: {e}"
            )
        else:
            if isinstance(adb_json, dict):
                adb_address = self._resolve_adb_address(adb_json)
                if adb_address is not None:
                    return adb_address
            logger.debug(
                f"MuMu 模拟器 {index} ADB 信息缺少 host/port，使用默认端口兜底"
            )

        return self._get_default_adb_address(index)

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        data = await self.get_device_info(idx or "all")

        data_json = self._decode_polluted_json(data, self._has_device_entries)

        result: dict[str, DeviceInfo] = {}

        for value in self._extract_device_entries(data_json):
            index = str(value["index"])
            name = value["name"]
            status = self._get_status_from_data(value)
            adb_address = await self._get_adb_address(value, index)
            result[index] = DeviceInfo(
                title=name, status=status, adb_address=adb_address
            )

        return result

    async def list_devices(self) -> dict[str, str]:
        data_json = self._decode_polluted_json(
            await self.get_device_info("all"), self._has_device_entries
        )

        return {
            str(value["index"]): str(value["name"])
            for value in self._extract_device_entries(data_json)
        }

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status not in [DeviceStatus.STARTING, DeviceStatus.ONLINE]:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "control",
            "-v",
            idx,
            "show_window" if is_visible else "hide_window",
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.failure_detail()}")

        return await self.getStatus(idx)

    async def get_device_info(self, idx: str) -> str:
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "info",
            "-v",
            idx,
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            logger.error(f"获取模拟器 {idx} 信息失败: {result.failure_detail()}")
            raise RuntimeError(f"命令执行失败: {result.failure_detail()}")

        return result.stdout.strip()

    async def get_adb_info(self, idx: str | int) -> str:
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "adb",
            "-v",
            str(idx),
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.failure_detail()}")

        return result.stdout.strip()

    async def find_mumu_nx_window(self) -> int | None:
        """
        查找 MuMu 多开器窗口

        Returns:
            int | None: 窗口句柄，未找到返回 None
        """

        if not IS_WINDOWS:
            return None

        def enum_cb(hwnd: int, result_list: list[int | None]) -> bool:
            if result_list[0] is not None:
                return False  # 已找到，停止枚举
            if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd) != 0:
                return True
            if win32gui.GetWindowText(hwnd) != "MuMu模拟器":
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = psutil.Process(pid).name().lower()
                if proc_name == "mumunxmain.exe":
                    result_list[0] = hwnd
                    return False
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
            return True

        result: list[int | None] = [None]

        def _enum() -> None:
            with suppress(Exception):
                # EnumWindows 在回调返回 False 时抛出异常，属正常行为
                win32gui.EnumWindows(enum_cb, result)

        # 逐窗口查询进程名较慢, 整段枚举放到线程里
        await asyncio.to_thread(_enum)
        return result[0]

    async def close_mumu_nx_window(self) -> bool:
        """
        关闭 MuMu 多开器窗口
        """

        hwnd = await self.find_mumu_nx_window()
        if hwnd is not None:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.success("已关闭 MuMuNX 窗口")
            return True
        return False
