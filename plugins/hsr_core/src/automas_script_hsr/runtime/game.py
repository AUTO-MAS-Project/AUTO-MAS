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


import asyncio
import shlex
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.services.system import System
from app.utils import ProcessInfo, get_logger, is_process_running

from .log_detect import has_screenshot_window_unavailable_output


logger = get_logger("HSR 切号")

HSR_GAME_READY_DELAY_SECONDS = 5
HSR_GAME_FOREGROUND_SETTLE_SECONDS = 2
HSR_SCRIPT_SWITCH_DELAY_SECONDS = 5
HSR_SRA_WINDOW_RECOVERY_MIN_INTERVAL_SECONDS = 5
HSR_GAME_PROCESS_NAME = "StarRail.exe"


def _is_config_value_readable(user_config: Any, group: str, key: str) -> bool:
    """检查配置项当前存储值是否能通过自身 validator。"""

    item = user_config._config_item_index[group][key]
    return item.validator.validate(item.value)


def resolve_game_executable_path(script_config: Any) -> Path:
    """从配置解析实际要启动的 StarRail.exe 路径。"""

    raw_path = str(script_config.get("Game", "Path") or "").strip()
    path = Path(raw_path) if raw_path else Path(HSR_GAME_PROCESS_NAME)
    if path.suffix.lower() == ".exe":
        return path
    return path / HSR_GAME_PROCESS_NAME


def resolve_sra_start_mode_from_credentials(
    account_id: str,
    password: str,
    user_name: str,
) -> str:
    """根据账号密码明文选择 SRA StartGame 模式。"""

    if account_id.strip() and password.strip():
        return "switch"

    logger.warning(
        f"用户「{user_name}」未配置账号或密码，"
        f"SRA StartGame 将使用当前已记住账号进入游戏；"
        f"若客户端停在登录页，需要手动登录，否则任务会失败。"
    )
    return "remembered"


def resolve_sra_start_mode(user_config: Any, user_name: str) -> str:
    """根据用户账号密码情况选择 SRA StartGame 模式。"""

    return resolve_sra_start_mode_from_credentials(
        user_config.get("SRA", "Id") or "",
        user_config.get("SRA", "Password") or "",
        user_name,
    )


def user_needs_account_switch(user_config: Any) -> bool:
    """判断用户是否配置了可用于切号的账号密码。"""

    plain_id = user_config.get("SRA", "Id") or ""
    plain_pw = user_config.get("SRA", "Password") or ""
    return bool(plain_id.strip() and plain_pw.strip())


def check_user_credentials(user_config: Any, user_name: str) -> str:
    """校验账号密码密文可读；空账号密码时交给 SRA 当前登录态。"""

    if not _is_config_value_readable(user_config, "SRA", "Id"):
        return (
            f"用户「{user_name}」的账号密文损坏或当前 Windows 用户无法解密，"
            "请重新设置账号"
        )
    decrypted_id = user_config.get("SRA", "Id")
    if not decrypted_id or not decrypted_id.strip():
        logger.warning(
            f"用户「{user_name}」的账号为空，SRA StartGame 将使用当前已记住账号进入游戏"
        )
        return "Pass"

    if not _is_config_value_readable(user_config, "SRA", "Password"):
        return (
            f"用户「{user_name}」的密码密文损坏或当前 Windows 用户无法解密，"
            "请重新设置密码"
        )
    decrypted_pw = user_config.get("SRA", "Password")
    if not decrypted_pw or not decrypted_pw.strip():
        logger.warning(
            f"用户「{user_name}」的密码为空，SRA StartGame 将使用当前已记住账号进入游戏"
        )
        return "Pass"

    logger.debug(f"用户「{user_name}」的账号密码校验通过（已确认可解密）")
    return "Pass"


async def stop_external_processes(
    runtime: Any,
    append_log: Callable[[str], None],
    script_config: Any | None = None,
) -> None:
    """停止当前仍在运行的 SRA/M7A 子进程。"""

    stopped = False
    if runtime.m7a_runner is not None:
        try:
            stopped = (
                await runtime.m7a_runner.terminate_current_process() or stopped
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"终止 M7A 当前子进程失败：{e}")
            append_log(f"终止 M7A 当前子进程失败：{e}")

    if runtime.sra_process_registry is not None:
        try:
            stopped = (
                await runtime.sra_process_registry.terminate_current_process()
                or stopped
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"终止 SRA 当前子进程失败：{e}")
            append_log(f"终止 SRA 当前子进程失败：{e}")

    path_checked = False
    if script_config is not None:
        effective_engines = set(
            getattr(script_config, "_hsr_effective_engines", ())
        )
        m7a_path = str(script_config.get("M7A", "Path") or "").strip()
        if m7a_path and "M7A" in effective_engines:
            m7a_exe_path = Path(m7a_path) / "March7th Assistant.exe"
            try:
                await System.kill_process(m7a_exe_path)
                path_checked = True
            except Exception as e:  # noqa: BLE001
                logger.warning(f"按路径清理 M7A 进程失败：{m7a_exe_path} - {e}")
                append_log(f"按路径清理 M7A 进程失败：{e}")

        sra_path = str(script_config.get("SRA", "Path") or "").strip()
        if sra_path and "SRA" in effective_engines:
            sra_exe_path = Path(sra_path) / "SRA-cli.exe"
            try:
                await System.kill_process(sra_exe_path)
                path_checked = True
            except Exception as e:  # noqa: BLE001
                logger.warning(f"按路径清理 SRA 进程失败：{sra_exe_path} - {e}")
                append_log(f"按路径清理 SRA 进程失败：{e}")

    if stopped:
        append_log("已向 SRA/M7A 外部进程发送停止信号")
    if path_checked:
        append_log("已按路径清理 SRA/M7A 外部进程")


async def close_game_if_needed(
    runtime: Any,
    script_config: Any,
    append_log: Callable[[str], None],
) -> None:
    """任务结束后关闭由 MAS 本次启动的游戏。"""

    if not runtime.game_started_by_mas:
        return

    game_exe_path = runtime.game_exe_path or resolve_game_executable_path(
        script_config
    )
    append_log("任务结束，正在关闭由 MAS 启动的游戏")
    try:
        await System.kill_process(game_exe_path)
        await runtime.game_process_manager.clear()
        append_log("游戏进程已关闭")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"关闭 HSR 游戏进程失败：{e}")
        append_log(f"关闭游戏进程失败：{e}")


class HSRAccountSwitcher:
    """HSR 启动游戏与 SRA StartGame 切号运行器。"""

    def __init__(
        self,
        *,
        script_config: Any,
        runtime: Any,
        append_log: Callable[[str], None],
    ) -> None:
        self.script_config = script_config
        self.runtime = runtime
        self._append_log = append_log
        self._last_sra_window_recovery_at: datetime | None = None

    @staticmethod
    def split_game_arguments(raw_arguments: object) -> list[str]:
        """解析脚本页填写的游戏启动参数。"""

        value = str(raw_arguments or "").strip()
        if not value:
            return []
        return shlex.split(value, posix=False)

    async def wait_before_external_script(
        self,
        script: str,
        user_name: str = "",
        *,
        track_last_script: bool = True,
    ) -> None:
        """SRA/M7A 交替执行前留出缓冲，切换时重启游戏避免状态污染。"""

        previous = self.runtime.last_external_script
        if previous is not None and previous != script:
            self._append_log(
                f"外部脚本从 {previous} 切换到 {script}，"
                f"等待 {HSR_SCRIPT_SWITCH_DELAY_SECONDS}s 后重启游戏"
            )
            await asyncio.sleep(HSR_SCRIPT_SWITCH_DELAY_SECONDS)
            # 切换时由 MAS 关闭并重新拉起游戏，避免上一个脚本遗留的页面
            # 状态导致下一个脚本无法初始化（例如 SRA 找不到 enter.png）。
            await self._restart_game_after_script_switch(user_name)
        if track_last_script:
            self.runtime.last_external_script = script
        if script == "M7A":
            self.runtime.game_session_clean = False

    async def _restart_game_after_script_switch(self, user_name: str) -> None:
        """M7A/SRA 切换时由 MAS 关闭并重新启动游戏。"""

        game_exe_path = resolve_game_executable_path(self.script_config)
        process_name = HSR_GAME_PROCESS_NAME

        self._append_log(
            f"用户「{user_name}」外部脚本切换，正在由 MAS 关闭并重新启动游戏"
        )

        self.runtime.game_exe_path = game_exe_path
        self.runtime.game_launch_checked = False
        self.runtime.game_started_by_mas = False
        self.runtime.game_session_clean = False
        self.runtime.last_external_script = None
        self.runtime.game_transitioning = True

        try:
            await System.kill_process(game_exe_path)
            await self.runtime.game_process_manager.clear()
            self._append_log(
                f"已请求关闭游戏，等待 "
                f"{HSR_GAME_READY_DELAY_SECONDS}s 后重新启动"
            )
            await asyncio.sleep(HSR_GAME_READY_DELAY_SECONDS)
            if process_name and is_process_running(process_name):
                self._append_log(
                    f"等待后仍检测到游戏进程运行（{process_name}），"
                    "将交由 ensure_game_started_by_mas 继续处理"
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"脚本切换时关闭 HSR 游戏失败：{e}")
            self._append_log(f"脚本切换时关闭游戏失败：{e}")
            # 关闭失败不抛错，让 ensure_game_started_by_mas 继续尝试

        try:
            await self.ensure_game_started_by_mas()
        finally:
            self.runtime.game_transitioning = False

    async def ensure_game_started_by_mas(self) -> None:
        """在 SRA/M7A 接手前由 MAS 统一启动游戏。"""

        if self.runtime.game_launch_checked:
            return
        self.runtime.game_launch_checked = True

        game_exe_path = resolve_game_executable_path(self.script_config)
        self.runtime.game_exe_path = game_exe_path
        process_name = HSR_GAME_PROCESS_NAME
        if process_name and is_process_running(process_name):
            self._append_log(
                f"检测到游戏进程已在运行（{process_name}），跳过重复启动"
            )
            await self._wait_after_game_process_detected(process_name)
            return

        wait_time = max(0, int(self.script_config.get("Game", "WaitTime") or 60))

        if not game_exe_path.exists():
            raise RuntimeError(f"游戏启动文件不存在：{game_exe_path}")

        game_args = self.split_game_arguments(
            self.script_config.get("Game", "Arguments")
        )
        args_text = f"，参数：{' '.join(game_args)}" if game_args else ""
        self._append_log(f"正在由 MAS 启动游戏：{game_exe_path}{args_text}")
        await self.runtime.game_process_manager.open_process(
            game_exe_path,
            *game_args,
            cwd=game_exe_path.parent,
        )
        self.runtime.game_started_by_mas = True

        await self._wait_for_game_process_after_launch(process_name, wait_time)

    async def prepare_game_for_account_switch(self, user_name: str) -> None:
        """需要切换账号前，确保游戏按完整启动链路重开。"""

        game_exe_path = resolve_game_executable_path(self.script_config)
        process_name = HSR_GAME_PROCESS_NAME

        self.runtime.game_exe_path = game_exe_path
        self.runtime.game_launch_checked = False
        self.runtime.game_started_by_mas = False
        self.runtime.game_session_clean = False
        self.runtime.last_external_script = None
        self.runtime.game_transitioning = True

        try:
            if process_name and is_process_running(process_name):
                self._append_log(
                    f"用户「{user_name}」需要登录/切号，检测到游戏正在运行，"
                    f"正在关闭游戏并等待 {HSR_GAME_READY_DELAY_SECONDS}s 后重启"
                )
                try:
                    await System.kill_process(game_exe_path)
                    await self.runtime.game_process_manager.clear()
                    await asyncio.sleep(HSR_GAME_READY_DELAY_SECONDS)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"登录/切号前关闭 HSR 游戏失败：{e}")
                    self._append_log(f"登录/切号前关闭游戏失败，将继续尝试启动流程：{e}")

            await self.ensure_game_started_by_mas()
        finally:
            self.runtime.game_transitioning = False

    async def close_game_if_needed(self) -> None:
        await close_game_if_needed(self.runtime, self.script_config, self._append_log)

    async def run_sra_task(
        self,
        sra_exe_path: Path,
        task_class: str,
        temp_path: Path,
        user_name: str,
        module_name: str,
        timeout_seconds: int | None = None,
        module_key: str = "",
        track_script_switch: bool = True,
    ) -> Any:
        """执行一条 SRA 单任务并同步调度台日志。"""

        from automas_hsr_adapter_sra.runner import run_sra_single_task

        await self.wait_before_external_script(
            "SRA",
            user_name,
            track_last_script=track_script_switch,
        )
        self._append_log(
            f"用户「{user_name}」开始执行 SRA {module_name}（{task_class}）"
        )
        result = await run_sra_single_task(
            sra_exe_path,
            task_class,
            temp_path,
            timeout=timeout_seconds or 600,
            process_registry=self.runtime.sra_process_registry,
            log_callback=self._append_log,
            output_line_callback=self.recover_game_window_if_screenshot_blocked,
            module_key=module_key,
        )
        if result.success:
            self._append_log(
                f"用户「{user_name}」SRA {module_name} 执行完成"
            )
        else:
            self._append_log(
                f"用户「{user_name}」SRA {module_name} 执行失败"
            )
        return result

    async def run_start_game(
        self,
        *,
        user_config: Any,
        user_name: str,
        user_id: str,
        script_id: str,
        sra_exe_path: Path,
        module_key: str,
        temp_files: list[Path],
        timeout_seconds: int,
    ) -> Any:
        """只运行 SRA StartGameTask，用于自动代理前置切号与人工检查。"""

        from automas_hsr_adapter_sra.runner import (
            build_sra_start_game_config,
            write_sra_temp_config,
        )

        await self.ensure_game_started_by_mas()
        start_mode = resolve_sra_start_mode(user_config, user_name)
        start_cfg = build_sra_start_game_config(
            self.script_config,
            user_config,
            mode=start_mode,
        )
        temp_path = write_sra_temp_config(
            start_cfg,
            script_id,
            user_id,
            module_key,
        )
        temp_files.append(temp_path)
        result = await self.run_sra_task(
            sra_exe_path,
            "StartGameTask",
            temp_path,
            user_name,
            "登录/切号",
            timeout_seconds=timeout_seconds,
            track_script_switch=False,
        )
        self.runtime.game_session_clean = bool(result.success)
        return result

    async def _wait_after_game_process_detected(self, process_name: str) -> None:
        self._append_log(
            f"检测到游戏进程（{process_name}），"
            f"等待 {HSR_GAME_READY_DELAY_SECONDS}s 后前置游戏窗口"
        )
        await asyncio.sleep(HSR_GAME_READY_DELAY_SECONDS)
        if await self._activate_game_window(process_name):
            self._append_log(
                f"游戏窗口已置于前台，等待 {HSR_GAME_FOREGROUND_SETTLE_SECONDS}s "
                "后启动外部脚本"
            )
        else:
            self._append_log(
                f"游戏窗口前置失败，等待 {HSR_GAME_FOREGROUND_SETTLE_SECONDS}s "
                "后仍继续启动外部脚本"
            )
        await asyncio.sleep(HSR_GAME_FOREGROUND_SETTLE_SECONDS)

    async def recover_game_window_if_screenshot_blocked(self, line: str) -> None:
        """外部脚本因窗口不可截图卡住时，尝试重新前置游戏窗口。"""

        if not has_screenshot_window_unavailable_output(line):
            return

        now = datetime.now()
        if (
            self._last_sra_window_recovery_at is not None
            and now - self._last_sra_window_recovery_at
            < timedelta(seconds=HSR_SRA_WINDOW_RECOVERY_MIN_INTERVAL_SECONDS)
        ):
            return
        self._last_sra_window_recovery_at = now

        self._append_log("检测到外部脚本无法截图游戏窗口，正在重新前置游戏窗口")
        if await self._activate_game_window(HSR_GAME_PROCESS_NAME):
            self._append_log(
                f"游戏窗口已重新前置，等待 {HSR_GAME_FOREGROUND_SETTLE_SECONDS}s "
                "后让外部脚本继续识别"
            )
            await asyncio.sleep(HSR_GAME_FOREGROUND_SETTLE_SECONDS)
        else:
            self._append_log("重新前置游戏窗口失败，SRA 可能继续等待窗口恢复")

    async def _activate_game_window(self, process_name: str) -> bool:
        manager = self.runtime.game_process_manager
        if manager.main_pid is None or manager.main_hwnd is None:
            try:
                await manager.search_process(
                    ProcessInfo(name=process_name),
                    datetime.now() + timedelta(seconds=5),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"定位 HSR 游戏进程窗口失败：{e}")
                return False

        return await manager.activate_window()

    async def _wait_for_game_process_after_launch(
        self,
        process_name: str,
        wait_time: int,
        poll_interval: int = 5,
    ) -> None:
        if wait_time <= 0:
            self._append_log("游戏启动等待时间为 0s，继续执行 M7A/SRA 任务")
            return

        self._append_log(
            f"正在等待游戏完成启动，最大启动等待时间 {wait_time}s，"
            f"每 {poll_interval}s 检查一次进程"
        )
        waited = 0
        while waited < wait_time:
            sleep_seconds = min(poll_interval, wait_time - waited)
            await asyncio.sleep(sleep_seconds)
            waited += sleep_seconds
            if process_name and is_process_running(process_name):
                await self._wait_after_game_process_detected(process_name)
                return

        self._append_log(
            f"已达到最大启动等待时间 {wait_time}s，继续执行 M7A/SRA 任务"
        )
