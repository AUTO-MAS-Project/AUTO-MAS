"""临时复用 OK-WW 多账号文件契约；上游提供批次接口后替换。"""

import json
import uuid
from contextlib import suppress
from datetime import datetime

from app.models.task import LogRecord, UserItem
from app.utils import LOG_TYPE_NORMAL, get_logger, log_box
from app.utils import constants as _utils_constants

from . import push_log
from .AutoProxy import AutoProxyTask, _okww_mas_config_dir
from .tools.batch_config import (
    DAILY_TASK,
    completed_accounts,
    normalize_account_key,
    write_attempt,
)
from .tools.batch_logs import account_log_context

logger = get_logger("OK-WW 批次")


class BatchProxyTask(AutoProxyTask):
    def __init__(
        self, script_info, script_config, user_config, game_manager, *, participants
    ):
        super().__init__(script_info, script_config, user_config, game_manager)
        self.cur_user_item = UserItem(
            user_id=self.cur_user_item.user_id,
            name=self.cur_user_item.name if len(participants) == 1 else "OK-WW 批次",
            status="等待",
        )
        self.participants = participants
        self.succeeded = set()
        self.pending = set()
        self.accounts = []
        self.account_users = {}
        self.batch_records = {}
        self.batch_nodes_collected = False
        self.before_started = set()
        self.account_failures = {}
        self.attempted_accounts = set()

    async def check(self):
        result = await super().check()
        if result != "Pass":
            return result
        identifiers = set()
        for user in self.participants:
            config = self.user_config[uuid.UUID(user.user_id)]
            try:
                key = normalize_account_key(config.Info.Id)
            except ValueError as error:
                return f"用户「{user.name}」无法使用 ok-ww 切号：{error}"
            if key in identifiers:
                return f"用户「{user.name}」的账号与其他用户转换后的 ok-ww 标识重复，请检查账号设置"
            identifiers.add(key)
        return "Pass"

    async def prepare(self):
        await super().prepare()
        today = datetime.now(tz=_utils_constants.UTC4)
        for user in self.participants:
            config = self.user_config[uuid.UUID(user.user_id)]
            if config.Data.LastProxyDate.date() != today.date():
                config.Data.LastProxyDate = today
                config.Data.ProxyTimes = 0
                await config.commit()
        self.task_name = "MultiAccountConfigTask"
        self.okww_args = ["-t", self.task_name, "-e"]
        self.task_index = 0
        # 原始账号历史独立于节点推送开关，关闭节点时也需保留日志。
        if self._log_source is None:
            self._prepare_log_details(
                self.script_log_path,
                mode=self.cur_user_config.Notify.PushLogMode,
                enabled=True,
                rotated_name=f"{self.script_log_path.stem}.%Y-%m-%d{self.script_log_path.suffix}",
            )
        for user in self.participants:
            config = self.user_config[uuid.UUID(user.user_id)]
            root = (
                self.script_config_path
                if config.Info.Base == "native"
                else _okww_mas_config_dir(
                    self.script_info.script_id, user.user_id, config.Info.Base
                )
            )
            daily = root / "DailyTask.json"
            values = (
                json.loads(daily.read_text(encoding="utf-8-sig"))
                if daily.exists()
                else {}
            )
            if not isinstance(values, dict):
                raise ValueError(f"日常配置格式错误: {daily}")
            if config.Info.IfQuickConfig:
                values.update(
                    {
                        "Which to Farm": config.Task.WhichToFarm,
                        "Which Tacet Suppression to Farm": config.Task.WhichTacetSuppressionToFarm,
                        "Which Forgery Challenge to Farm": config.Task.WhichForgeryChallengeToFarm,
                        "Material Selection": config.Task.MaterialSelection,
                        "Farm Nightmare Nest for Daily Echo": config.Task.FarmNightmareNestForDailyEcho,
                        "Additional Tasks to Run After Daily Task": config.Task.AdditionalTasks,
                    }
                )
            key = normalize_account_key(config.Info.Id)
            self.account_users[key] = user
            self.accounts.append(
                {
                    "account_key": key,
                    "enabled": True,
                    "task": DAILY_TASK,
                    "config": values,
                }
            )
            await user.set_state(status="运行")
            self.user_state(user).push_log_mode = config.Notify.PushLogMode
            record = await user.add_log_record(self.log_start_time, LogRecord())
            self.batch_records[user.user_id] = record

    async def run_user_scripts_before(self):
        original = self.cur_user_config
        try:
            for user in self.participants:
                self.cur_user_config = self.user_config[uuid.UUID(user.user_id)]
                self.before_started.add(user.user_id)
                await super().run_user_scripts_before()
        finally:
            self.cur_user_config = original

    async def set_okww(self):
        # 换入 base 或清空结果失败时，不得把旧文件当成本轮结果。
        self.pending.clear()
        await super().set_okww()
        accounts = [
            account
            for account in self.accounts
            if account["account_key"] not in self.succeeded
        ]
        write_attempt(self.script_config_path, accounts)
        self.pending = {account["account_key"] for account in accounts}

    async def check_log(self, log_content, latest_time):
        await super().check_log(log_content, latest_time)
        # 失败原因独立于节点采集开关，关闭详情时仍须保留账号结论。
        for key, stage, line in account_log_context(log_content):
            if key in self.account_users:
                self.attempted_accounts.add(key)
                if "MultiAccountConfigTask:info_set 状态 执行失败" in line:
                    self.account_failures[key] = f"OK-WW {stage}失败"
        completed = completed_accounts(self.script_config_path, self.pending)
        self.succeeded.update(completed)
        for key in completed:
            await self.account_users[key].set_state(status="完成")
        if "info_set 状态 执行失败" in "".join(log_content):
            await self.cur_user_log.set_state(status="OK-WW 部分账号执行失败")
            self.wait_event.set()
        if self.cur_user_log.status == "Success!" and not self.pending.issubset(
            self.succeeded
        ):
            await self.cur_user_log.set_state(
                status="OK-WW 未取得全部账号的本轮成功结果"
            )
            self.wait_event.set()

    async def _collect_log_details(self):
        try:
            await self._collect_batch_log_details()
        except Exception:
            logger.opt(exception=True).warning(
                "批次节点采集失败，继续账号历史与配置收尾"
            )

    async def _collect_batch_log_details(self):
        if self.batch_nodes_collected:
            return
        self.batch_nodes_collected = True
        pipelines = {}
        for key, user in self.account_users.items():
            pipeline = log_box.LogPipeline()
            for rule in push_log.OKWW_PUSH_RULES:
                pipeline.add_rule(*rule)
            pipeline.postprocessors.append(push_log.okww_resolve)
            pipelines[key] = pipeline
        if self._log_source is not None:
            for current, stage, line in account_log_context(
                self._log_source.read_new()
            ):
                if current in pipelines:
                    self.attempted_accounts.add(current)
                    # OCR 回退警告不能代替上游终态失败。
                    if "MultiAccountConfigTask:info_set 状态 执行失败" in line:
                        self.account_failures[current] = f"OK-WW {stage}失败"
                        pipelines[current].results.append(
                            (LOG_TYPE_NORMAL, f"❌ 失败: {stage}", None)
                        )
                    pipelines[current].feed(line, timestamp=None)
                    await self.batch_records[
                        self.account_users[current].user_id
                    ].append_content(line)
        for key, pipeline in pipelines.items():
            user = self.account_users[key]
            if self.user_state(user).push_log_mode != "关闭":
                for entry in pipeline.finish():
                    self.user_state(user).push_log.append(
                        (entry.log_type, entry.text, entry.timestamp)
                    )

    async def final_task(self):
        # 原始参与名单贯穿全部补跑；成功账号只在最终收尾计数一次。
        maintenance_skipped = self.user_state(self.cur_user_item).maintenance_skipped
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process(kill_game=self._game_management_enabled())
        # 中止可能发生在上游写回成功后、下一次日志回调前。
        if self.pending:
            try:
                self.succeeded.update(
                    completed_accounts(self.script_config_path, self.pending)
                )
            except (OSError, ValueError):
                logger.opt(exception=True).warning(
                    "无法读取本轮最终账号结果，保留已确认结果并继续收尾"
                )
        await self._close_log_details()
        for user in self.participants:
            self.cur_user_item = user
            self.cur_user_uid = uuid.UUID(user.user_id)
            self.cur_user_config = self.user_config[self.cur_user_uid]
            self.cur_user_log = self.batch_records.get(user.user_id)
            if self.cur_user_log is None:
                self.cur_user_log = await user.add_log_record(
                    datetime.now().astimezone(), LogRecord()
                )
            self.run_book = (
                normalize_account_key(self.cur_user_config.Info.Id) in self.succeeded
            )
            skipped = maintenance_skipped and not self.run_book
            self.user_state(user).maintenance_skipped = skipped
            await user.set_state(
                status="完成" if self.run_book else "跳过" if skipped else "异常"
            )
            if self.run_book:
                status = "Success!"
            elif skipped:
                status = self._maintenance_reason or "鸣潮正在维护"
            elif self.stopped_manually:
                status = "任务被用户手动中止"
            else:
                key = normalize_account_key(self.cur_user_config.Info.Id)
                status = self.account_failures.get(
                    key,
                    "OK-WW 账号未完成"
                    if key in self.attempted_accounts
                    else "OK-WW 账号尚未执行（批次提前结束）",
                )
            await self.cur_user_log.set_state(status=status)
            self._user_scripts_started = user.user_id in self.before_started
            await super().final_task()
