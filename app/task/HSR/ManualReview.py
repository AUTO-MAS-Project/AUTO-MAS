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
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Broadcast, Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.utils import get_logger
from app.utils.constants import UTC8
from .tools.run_model import HSRRuntimeState
from .tools.account_switch import HSRAccountSwitcher, check_user_credentials
from .tools.sra_runtime import cleanup_sra_temp_config


logger = get_logger("HSR 人工排查")


class HSRManualReviewTask(TaskExecuteBase):
    """HSR 人工检查模式：只启动游戏并通过 SRA StartGame 切号。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: HSRConfig,
        user_config: MultipleConfig[HSRUserConfig],
        user_item: UserItem,
        runtime: HSRRuntimeState,
    ) -> None:
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = user_item
        self.cur_user_uid: uuid.UUID = uuid.UUID(user_item.user_id)
        self.cur_user_config: HSRUserConfig = self.user_config[self.cur_user_uid]
        self.runtime = runtime
        self._log_lines: list[str] = runtime.log_lines
        self._account_switcher = HSRAccountSwitcher(
            script_config=self.script_config,
            runtime=self.runtime,
            append_log=self._append_log,
        )
        self.message_queue: asyncio.Queue[dict] | None = None
        self._current_user_log: LogRecord | None = None
        self.temp_files: list[Path] = []
        self.check_result: str = "-"
        self.run_book: dict[str, bool] = {"SignIn": False, "PassCheck": False}
        self.crashed: bool = False
        self.error_message: str = ""

    def _append_log(self, message: str, *, max_lines: int = 500) -> None:
        """向脚本日志和当前用户日志追加人工检查信息。"""

        text = str(message).strip()
        if not text:
            return

        now_text = datetime.now(tz=UTC8).strftime("%H:%M:%S")
        appended_lines: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                formatted = f"[{now_text}] {line}"
                self._log_lines.append(formatted)
                appended_lines.append(formatted)

        if len(self._log_lines) > max_lines:
            del self._log_lines[:-max_lines]
        self.script_info.log = "\n".join(self._log_lines)

        if self._current_user_log is not None:
            self._current_user_log.content.extend(
                f"{line}\n" for line in appended_lines
            )

    def _start_user_log(self) -> None:
        self._current_user_log = LogRecord(status="HSR 人工排查中")
        self.cur_user_item.log_record[datetime.now()] = self._current_user_log
        self.cur_user_item.status = "运行"
        self._append_log(f"开始人工排查用户「{self.cur_user_item.name}」")

    def _finish_user_log(self, log_status: str, user_status: str) -> None:
        if self._current_user_log is not None:
            self._current_user_log.status = log_status
        self.cur_user_item.status = user_status
        self._current_user_log = None

    def _start_game_timeout_seconds(self) -> int:
        minutes = int(self.script_config.get("Run", "DailyTimeLimit") or 20)
        return max(1, minutes) * 60

    async def check(self) -> str:
        """校验当前用户是否可以执行 SRA 登录/切号。"""

        sra_path = self.script_config.get("Info", "SRAPath")
        if not sra_path:
            return "人工排查需要先设置 SRA 路径"

        sra_exe = Path(sra_path) / "SRA-cli.exe"
        if not sra_exe.exists():
            return f"SRA 路径中未找到 SRA-cli.exe：{sra_exe}"

        return check_user_credentials(self.cur_user_config, self.cur_user_item.name)

    async def prepare(self) -> None:
        self.message_queue = asyncio.Queue()
        await Broadcast.subscribe(self.message_queue)

    async def _unsubscribe_broadcast(self) -> None:
        """释放人工排查消息订阅，避免旧队列持续接收广播。"""

        if self.message_queue is None:
            return

        queue = self.message_queue
        self.message_queue = None
        try:
            await Broadcast.unsubscribe(queue)
        except KeyError:
            logger.warning("HSR 人工排查消息队列已取消订阅，跳过重复清理")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"HSR 人工排查消息队列取消订阅失败：{e}")

    async def _ask_question(self, message: str) -> bool:
        message_id = str(uuid.uuid4())
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Message",
            data={
                "message_id": message_id,
                "type": "Question",
                "title": "操作提示",
                "message": message,
                "options": ["是", "否"],
            },
        )
        result = await self._wait_for_user_response(message_id)
        return bool(result.get("data", {}).get("choice", False))

    async def _wait_for_user_response(self, message_id: str) -> dict:
        """等待客户端人工确认。"""

        if self.message_queue is None:
            raise RuntimeError("人工排查消息队列未初始化")

        logger.info(f"等待客户端回应消息: {message_id}")
        while True:
            message = await self.message_queue.get()
            try:
                if (
                    message.get("id") == message_id
                    and message.get("type") == "Response"
                ):
                    logger.success(f"收到客户端回应消息: {message_id}")
                    return message
            finally:
                self.message_queue.task_done()

    async def main_task(self) -> None:
        """执行当前用户的 HSR 人工排查流程。"""

        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.cur_user_item.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={
                    "Error": (
                        f"用户 {self.cur_user_item.name} 检查未通过: "
                        f"{self.check_result}"
                    )
                },
            )
            return

        await self.prepare()
        self._start_user_log()

        sra_exe_path = Path(self.script_config.get("Info", "SRAPath")) / "SRA-cli.exe"
        while True:
            self._append_log(f"正在启动游戏并切换到用户「{self.cur_user_item.name}」")
            await self._account_switcher.prepare_game_for_account_switch(
                self.cur_user_item.name
            )
            result = await self._account_switcher.run_start_game(
                user_config=self.cur_user_config,
                user_name=self.cur_user_item.name,
                user_id=self.cur_user_item.user_id,
                script_id=self.script_info.script_id,
                sra_exe_path=sra_exe_path,
                module_key="ManualReview_StartGame",
                temp_files=self.temp_files,
                timeout_seconds=self._start_game_timeout_seconds(),
            )
            if result.success:
                self.run_book["SignIn"] = True
                self._append_log(f"用户「{self.cur_user_item.name}」登录/切号完成")
                break

            reason = result.error or result.output or f"进程退出码：{result.returncode}"
            self._append_log(
                f"用户「{self.cur_user_item.name}」登录/切号失败：{reason}"
            )
            if not await self._ask_question("HSR 登录/切号失败，是否重试？"):
                return

        if await self._ask_question(
            f"请检查当前 HSR 账号是否为「{self.cur_user_item.name}」，是否通过人工排查？"
        ):
            self.run_book["PassCheck"] = True
            self._append_log(f"用户「{self.cur_user_item.name}」已通过人工排查")
        else:
            self._append_log(f"用户「{self.cur_user_item.name}」未通过人工排查")

    async def final_task(self) -> str | None:
        """写回人工检查结果并清理临时 SRA 配置。"""

        try:
            for temp_path in self.temp_files:
                cleanup_sra_temp_config(temp_path)

            if self.check_result != "Pass":
                await self.cur_user_config.set("Data", "IfPassCheck", False)
                self._finish_user_log(self.check_result, "异常")
                return self.check_result

            if self.run_book["SignIn"] and self.run_book["PassCheck"]:
                await self.cur_user_config.set("Data", "IfPassCheck", True)
                self._finish_user_log("HSR 人工排查通过", "完成")
            else:
                await self.cur_user_config.set("Data", "IfPassCheck", False)
                self._finish_user_log("HSR 人工排查未通过", "异常")
            return None
        finally:
            await self._unsubscribe_broadcast()

    async def on_crash(self, e: Exception) -> None:
        self.crashed = True
        self.error_message = str(e)
        self.cur_user_item.status = "异常"
        if self._current_user_log is not None:
            self._current_user_log.status = f"HSR 人工排查异常: {e}"
        logger.exception(f"HSR 用户「{self.cur_user_item.name}」人工排查异常：{e}")

        try:
            await self.cur_user_config.set("Data", "IfPassCheck", False)
        except Exception as write_error:  # noqa: BLE001
            logger.warning(f"HSR 人工排查异常状态写回失败：{write_error}")

        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={
                    "Error": f"HSR 用户「{self.cur_user_item.name}」人工排查异常：{e}"
                },
            )
        except Exception as notify_error:  # noqa: BLE001
            logger.warning(f"发送 HSR 人工排查异常提示失败：{notify_error}")
        finally:
            await self._unsubscribe_broadcast()
