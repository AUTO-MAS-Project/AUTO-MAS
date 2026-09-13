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

"""BAAH 自动代理模式。

以子进程方式启动 BAAH 的指定配置并监控其日志，按成功/失败关键字判定结果，
失败时按配置重试。BAAH 自身没有心跳与看门狗，进程卡死只能靠日志静默与进程
存活共同判定。

运行前会写入本软件所需的托管配置项（运行结束自动退出、日志落盘等），
运行结束后恢复用户原值，详见 ``.tools.config_manager``。
"""

import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.log_box import LogCollect, LogType, log_box
from app.models.config import BAAHConfig, BAAHUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.task.proxy_helpers import append_push_log
from app.utils import LogMonitor, ProcessManager, compile_log_signs, get_logger
from app.utils.constants import UTC4

from .tools import (
    BAAH_PUSH_RULES,
    CONFIG_DIR_NAME,
    LOG_DIR_RELATIVE,
    SOFTWARE_CONFIG_RELATIVE,
    ManagedConfigBackup,
    apply_managed_config,
    baah_resolve,
    latest_log_file,
    push_notification,
    resolve_config_name,
    resolve_log_time_range,
    resolve_user_config_path,
    restore_managed_config,
)

logger = get_logger("BAAH 自动代理")

## BAAH 日志行格式为「{版本} - {分:秒} - {级别} : {消息}」，例如：
##   2.4.13 - 24:19 - INFO : 执行任务EnterGame
## 时间戳的字符切片**按首行实际排版推算**（``resolve_log_time_range``）：
## 版本号位数会随版本变化（2.4.13 / 2.4.100），写死区间会让每一行都解析失败，
## 被 LogMonitor 静默丢弃，表现为「日志文件找到了却一行都采集不到」。
## 同时，该区间是 LogMonitor 对整行做的**字符切片**（line[start:end]），
## 不是按分隔符分词后的字段下标。

## BAAH 只输出「分:秒」，不带日期与小时
BAAH_LOG_TIME_FORMAT = "%M:%S"

## 完成任务时 BAAH 固定输出的日志文本（只在成功路径出现）
BAAH_SUCCESS_LOG = "所有任务结束|All tasks are finished"

## 运行失败时 BAAH 顶层异常处理输出的日志文本
BAAH_ERROR_LOG = "运行出错:|Error occurred:"

## 等待日志文件生成的超时（秒）
_LOG_FILE_WAIT_SECONDS = 60

## 一次运行结束后等待相关进程退出的时间（秒）
_PROCESS_EXIT_WAIT_SECONDS = 10

## 命中成功标记后留给 BAAH 自行收尾的宽限时间（秒）。
## BAAH 跑完还要执行自动退出与用户配置的 POST_COMMAND，立即强杀会把后置命令截断。
_PROCESS_GRACE_SECONDS = 60


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: BAAHConfig,
        user_config: MultipleConfig[BAAHUserConfig],
        emulator_manager: DeviceBase | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"
        self.run_book = False
        self.managed_backup: ManagedConfigBackup | None = None
        self.process_manager: ProcessManager | None = None
        self.log_monitor: LogMonitor | None = None
        ## 两个总开关在 prepare() 里按脚本配置初始化，这里给出保守默认值
        self.if_manage_config = True
        self.push_log_enabled = True
        ## log_box：任务节点采集（受「推送任务节点详情」开关控制，关闭时不创建）
        self.log_collect: LogCollect | None = None
        self.script_log_path: Path | None = None
        self.emulator_adb_address: str = ""
        ## 本用户的开始时刻，用于统计信息通知
        self.user_start_time = datetime.now()

        self._resolve_paths()

    def _resolve_paths(self) -> None:
        """解析 BAAH 程序目录、配置目录与日志目录。

        BAAH 启动时会 chdir 到 exe 所在目录，其配置目录与日志目录都是相对该目录的
        固定位置，因此全部由 ``BAAHPath`` 派生，不再单独提供输入项：填错只会让托管
        项写进 BAAH 根本不读的文件，或每次都等满 60 秒「未找到日志文件」。
        """

        self.baah_path = Path(self.script_config.get("Script", "BAAHPath"))
        self.root_path = self.baah_path.parent
        self.config_dir = self.root_path / CONFIG_DIR_NAME
        self.log_dir = self.root_path / LOG_DIR_RELATIVE
        self.software_config_path = self.root_path / SOFTWARE_CONFIG_RELATIVE

    async def check(self) -> str:
        """校验 BAAH 运行所需的路径与用户配置"""

        if not self.baah_path.is_file():
            self.cur_user_item.status = "异常"
            return "未找到 BAAH 主程序, 请检查脚本配置中的主程序路径设置！"

        try:
            config_name = resolve_config_name(
                str(self.cur_user_config.get("Info", "ConfigName"))
            )
        except ValueError as e:
            self.cur_user_item.status = "异常"
            return f"{e}, 请在用户配置中填写 BAAH 配置文件名称！"

        if not resolve_user_config_path(self.config_dir, config_name).is_file():
            self.cur_user_item.status = "异常"
            return (
                f"未找到 BAAH 配置文件 {config_name}.json, "
                "请先在 BAAH 界面中创建同名配置！"
            )

        return "Pass"

    async def prepare(self):
        """运行前准备"""

        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.log_start_time = datetime.now()
        self.log_start_at = time.monotonic()

        ## 成功与失败关键字固定：成功文本只出现在 BAAH 的成功路径，
        ## 失败文本是其顶层异常处理的输出
        self.success_log = compile_log_signs(BAAH_SUCCESS_LOG, "Split")
        self.error_log = compile_log_signs(BAAH_ERROR_LOG, "Split")

        ## 日志监控器不在这里构造：它把构造时刻当作补齐 %M:%S 缺失小时的基准，
        ## 而冷启模拟器与等待日志文件可能跨过整点，提前构造会把首行算成上一个
        ## 小时而整段丢弃。等定位到日志文件之后再构造（见 _run_launched）。
        self.log_monitor = None

        ## 配置托管总开关：关闭时照常启动 BAAH，但不改动它的任何配置文件
        self.if_manage_config = bool(
            self.script_config.get("Script", "IfManageConfig")
        )
        ## 推送任务节点详情开关：关闭时**不创建 log_box**（不读日志、不匹配），
        ## 该用户 push_log 保持为空，报告自然不含 BAAH 的任务节点；任务日志记录
        ## 与结果判定都不受它影响，照常进行
        self.push_log_enabled = bool(
            self.script_config.get("Script", "PushLogEnabled")
        )
        self.log_collect = None

        config_name = resolve_config_name(
            str(self.cur_user_config.get("Info", "ConfigName"))
        )
        self.user_config_path = resolve_user_config_path(self.config_dir, config_name)

    async def main_task(self):
        """自动代理模式主逻辑"""

        self.user_start_time = datetime.now()

        ## 每日重置：跨天后代理次数归零，用户标签里的「任务」状态才会重新变成
        ## 「未代理」（通用脚本同一套口径）
        curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.warning(f"未通过配置检查: {self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}",
                ),
            )
            return

        await self.prepare()

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        for i in range(self.script_config.get("Run", "RunTimesLimit")):
            if self.run_book:
                break

            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: "
                f"{i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
            )
            self.log_start_time = datetime.now()
            self.log_start_at = time.monotonic()
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )

            await self.run_once()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.cur_user_item.status = "完成"
                logger.success(f"用户: {self.cur_user_uid} - BAAH 完成代理任务")
                break

            self.cur_user_item.status = "异常"
            logger.warning(
                f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
            )
            await asyncio.sleep(3)

    async def _ensure_emulator_online(self) -> bool:
        """由本软件拉起模拟器并等待其在线。

        模拟器的启动与关闭统一由 MAS 调度，BAAH 只负责连接；冷启动耗时较长，
        在这里等它就绪，避免占用 BAAH 自身的等待窗口。
        """

        if self.emulator_manager is None:
            return True

        self.script_info.log = "正在启动模拟器"
        ## 状态必须落在后端既有枚举（等待/运行/完成/异常）里：调度台与前端
        ## 都用 `=== '运行'` 判断任务是否在跑，自造后缀会让这些比较全部失效
        self.cur_user_item.status = "运行"

        try:
            device_info = await self.emulator_manager.open(
                str(self.script_config.get("Emulator", "Index"))
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"启动模拟器失败: {e}")
            await self.handle_pre_script_error("启动模拟器失败", e)
            return False

        self.emulator_adb_address = str(device_info.adb_address or "")
        logger.success(f"模拟器已就绪, ADB 地址: {self.emulator_adb_address}")
        return True

    def _emulator_runtime_values(self) -> dict[str, object]:
        """把模拟器调度结果折算成 BAAH 侧的托管项。

        BAAH 的目标设备有两种表达：``TARGET_IP_PATH:TARGET_PORT`` 拼成地址，
        或由 ``ADB_SEIAL_NUMBER`` 直接给串号（键名沿用上游既有拼写）。这里按
        MAS 解析出的实际地址择一写入，用户无需在 BAAH 侧维护任何一项。
        """

        address = self.emulator_adb_address.strip()
        if not address:
            return {}

        host, separator, port = address.rpartition(":")
        if not separator or not host:
            ## 形如 emulator-5554 的串号（雷电等）：按串号直连。
            ## 落回地址写法会让 BAAH 用它自己那份手填端口，静默连错设备
            return {
                "ADB_SEIAL_NUMBER": address,
                "ADB_DIRECT_USE_SERIAL_NUMBER": True,
            }

        return {
            "TARGET_IP_PATH": host,
            "TARGET_PORT": int(port) if port.isdigit() else port,
        }

    async def run_once(self) -> None:
        """执行一次 BAAH 运行。

        启动模拟器、写入托管配置、启动进程、等待日志判定，
        最后无论成功失败都恢复托管配置。
        """

        self.wait_event.clear()

        if not await self._ensure_emulator_online():
            return

        if self.if_manage_config:
            try:
                self.managed_backup = apply_managed_config(
                    self.user_config_path,
                    self.software_config_path,
                    self._emulator_runtime_values(),
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"写入 BAAH 托管配置失败: {e}")
                await self.handle_pre_script_error("写入 BAAH 托管配置失败", e)
                return
        else:
            ## 用户关闭了配置托管：模拟器地址等运行期取值也不再注入，
            ## BAAH 完全按它自己的配置文件运行
            logger.info("未开启「托管 BAAH 运行配置」, 跳过配置托管")

        try:
            await self._run_launched()
        finally:
            ## 本次运行的进程此时已经结束、日志不再增长，正是收尾采集的时机。
            ## 先于配置恢复执行，是因为恢复失败会向上抛出，采集不能因此漏掉；
            ## 放在 finally 里则是因为 BAAH 每次运行各有自己的日志文件，采集
            ## 会话必须随着本次运行一起收尾（close 幂等）
            self._close_log_collect()
            await self._restore_managed_config()

    async def _restore_managed_config(self) -> None:
        """恢复托管配置，并把恢复失败明确告知用户。

        恢复失败不能让整个任务失败（此时任务往往已经跑完），但也绝不能静默：
        用户的配置文件会一直带着本次运行写入的托管值，界面却显示一切正常。
        """

        failures = restore_managed_config(self.managed_backup)
        self.managed_backup = None

        if not failures:
            return

        message = "恢复 BAAH 配置失败, 请检查配置文件是否可写: " + "; ".join(failures)
        logger.error(message)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=message),
        )

    async def _run_launched(self) -> None:
        """启动 BAAH 进程并等待日志给出结果"""

        if self.process_manager is None:
            raise RuntimeError("自动代理任务尚未完成初始化")

        config_name = self.user_config_path.name
        logger.info(f"运行 BAAH 任务: {self.baah_path}, 配置: {config_name}")

        ## 记录启动时刻：BAAH 每次运行都会新建日志文件，据此锁定本次日志
        launch_at = time.time()

        try:
            await self.process_manager.open_process(self.baah_path, config_name)
        except Exception as e:
            logger.opt(exception=True).warning(f"启动 BAAH 进程失败: {e}")
            await self.handle_pre_script_error("启动 BAAH 进程失败", e)
            return

        self.script_info.log = "正在等待 BAAH 日志文件生成"
        log_path: Path | None = None
        wait_started_at = time.monotonic()
        deadline = wait_started_at + _LOG_FILE_WAIT_SECONDS
        while time.monotonic() < deadline:
            log_path = latest_log_file(self.log_dir, launch_at)
            if log_path is not None:
                break
            ## 状态带上已等待秒数：否则界面在整个等待窗口里都是一句静止的
            ## 文案，用户无法区分「正在等」与「已经卡死」
            self.script_info.log = (
                f"正在等待 BAAH 日志文件生成（已等待 "
                f"{int(time.monotonic() - wait_started_at)} 秒）"
            )
            await asyncio.sleep(1)

        if log_path is None:
            await self.handle_pre_script_error("未找到 BAAH 日志文件")
            return

        self.script_log_path = log_path
        logger.success(f"成功定位到日志文件: {self.script_log_path}")
        ## 采集会话必须建在文件定位之后：日志源从当前文件末尾起只取新增内容，
        ## 这里记录下的起点正好是 BAAH 写出任务节点之前的位置
        self._start_log_collect()
        ## 定位成功后立刻改写状态：日志监控要等 BAAH 写出首批日志行才会回调，
        ## 不改写的话界面会继续停在「正在等待日志文件生成」，看起来像没进展
        self.script_info.log = f"已定位 BAAH 日志文件 {log_path.name}, 正在读取日志"

        ## 时间戳区间按首行实际排版推算；监控器也在这里才构造，让它补齐 %M:%S
        ## 缺失小时所用的基准落在日志真正出现之后，跨整点时不会把首行算成上个小时
        time_range = resolve_log_time_range(log_path, BAAH_LOG_TIME_FORMAT)
        if time_range is None:
            await self.handle_pre_script_error("无法从 BAAH 日志首行识别时间戳位置")
            return

        self.log_monitor = LogMonitor(
            time_range,
            BAAH_LOG_TIME_FORMAT,
            self.check_log,
        )

        await self.log_monitor.start_monitor_file(
            self._resolve_log_file_path, self.log_start_time
        )
        await self.wait_event.wait()
        await self.log_monitor.stop()

        ## 命中成功标记只说明任务跑完了，BAAH 还要执行收尾（自动退出与用户的
        ## POST_COMMAND）：先给它时间自己走完，超时才强制结束
        if self.cur_user_log.status == "Success!":
            await self._wait_process_exit()

        await self.kill_managed_process()
        await asyncio.sleep(_PROCESS_EXIT_WAIT_SECONDS)

    async def _wait_process_exit(self) -> None:
        """等待 BAAH 自行退出，给它执行收尾命令的机会。"""

        if self.process_manager is None:
            return

        deadline = time.monotonic() + _PROCESS_GRACE_SECONDS
        while time.monotonic() < deadline:
            if not await self.process_manager.is_running():
                return
            await asyncio.sleep(1)

        logger.warning(
            f"BAAH 进程在 {_PROCESS_GRACE_SECONDS} 秒内未自行退出, 将强制结束"
        )

    def _resolve_log_file_path(self) -> Path:
        """返回当前会话的日志文件路径"""

        if self.script_log_path is None:
            raise RuntimeError("尚未定位到 BAAH 日志文件")
        return self.script_log_path

    def _start_log_collect(self) -> None:
        """按本次运行的日志文件开始采集 BAAH 的任务节点。

        BAAH 每次运行都新建一个日志文件，因此采集会话只能建在文件定位之后，
        且每次运行各建一个：日志源从文件末尾起采集（``start_from_end=True``），
        只取会话内新增的行，运行前已有的启动信息不会混进结果。

        上一次运行采集到的节点在这里丢弃：``RunTimesLimit`` 重试会让同名任务
        在报告里重复出现，而报告要呈现的是最终一次运行的流程。
        """

        self.cur_user_item.push_log.clear()
        if not self.push_log_enabled or self.script_log_path is None:
            return

        self.log_collect = log_box.get_collect(
            paths=[self.script_log_path],
            sink=self._append_push_log,
            start_from_end=True,
        )
        self.log_collect.open()
        for rule in BAAH_PUSH_RULES:
            self.log_collect.collect(*rule)

    def _append_push_log(self, log_type: str, text: str, ts: float) -> None:
        """sink：把 log_box 采集结果写入当前用户的推送日志（供调度器聚合到报告）"""

        append_push_log(self.cur_user_item, log_type, text, ts)

    def _close_log_collect(self) -> None:
        """结束采集会话：冲刷本次运行剩余日志、解析任务节点并写入推送日志。

        采集失败时既记日志也写入报告，避免节点详情缺失却仍呈现为正常结果；
        ``close`` 幂等，收尾与异常路径都可以重复调用，未创建会话时直接返回。
        """

        if self.log_collect is None:
            return

        try:
            self.log_collect.close(baah_resolve)
        except Exception:
            logger.opt(exception=True).warning("BAAH log_box 收尾推送失败（baah_resolve）")
            self.cur_user_item.push_log.append(
                (LogType.NORMAL, "⚠️ 节点采集失败", time.time())
            )

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调：判定本次运行的结果"""

        log = "".join(log_content)
        ## 日志内容始终写入任务记录：结果判定与任务记录都是基础能力，
        ## 与「是否推送任务节点详情」无关，开关只决定要不要采集节点
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if self.success_log.search(log) is not None:
            self.cur_user_log.status = "Success!"
        elif self.is_log_stalled(
            latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "脚本进程超时"
        elif self.error_log.search(log) is not None:
            self.cur_user_log.status = "BAAH 运行出错"
        elif self.process_manager is not None and await self.process_manager.is_running():
            self.cur_user_log.status = "BAAH 正常运行中"
        else:
            ## 进程已退出但未命中成功标记：不能确认任务完成
            self.cur_user_log.status = "BAAH 在完成任务前退出"

        logger.debug(f"BAAH 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "BAAH 正常运行中":
            logger.info(f"BAAH 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def kill_managed_process(self) -> None:
        """中止本次运行托管的进程"""

        if self.process_manager is None:
            return

        try:
            logger.info(f"中止 BAAH 进程: {self.baah_path}")
            await self.process_manager.kill()
            await System.kill_process(self.baah_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 BAAH 进程失败: {e}")

    async def handle_pre_script_error(
        self, error_message: str, e: Exception | None = None
    ) -> None:
        """处理运行前的准备阶段错误"""

        if e is None:
            logger.warning(f"用户: {self.cur_user_uid} - {error_message}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=error_message),
            )
        else:
            logger.opt(exception=True).warning(
                f"用户: {self.cur_user_uid} - {error_message}: {e}"
            )
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"{error_message}: {e}"),
            )

        self.cur_user_log.content = [f"{error_message}, 无日志记录"]
        self.cur_user_log.status = error_message

        await self.kill_managed_process()

        await Notify.push_plyer(
            "用户自动代理出现异常！",
            f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
            f"{self.cur_user_item.name}的自动代理出现异常",
            3,
        )

    async def final_task(self):
        """运行结束后的收尾工作"""

        if self.check_result != "Pass":
            self.cur_user_item.status = "异常"
            return

        if self.log_monitor is not None:
            await self.log_monitor.stop()

        await self.kill_managed_process()

        await self._restore_managed_config()

        for t, log_item in self.cur_user_item.log_record.items():
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=t.astimezone(UTC4),
            )

            if log_item.status == "BAAH 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        if self.run_book:
            ## 与通用脚本同一套口径：当天首次成功才递减剩余天数，代理次数始终累加。
            ## 不更新的话用户标签会一直停在「任务：未代理」、剩余天数也不减
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )

        await self._push_statistic()

    async def _push_statistic(self) -> None:
        """推送本用户的统计信息通知。

        渠道由该用户的 ``Notify`` 配置决定（邮件 / Server 酱 / 自定义 Webhook），
        未开启通知时整条链路直接返回，不发任何内容。
        """

        statistics = {
            "user_info": self.cur_user_item.name,
            "start_time": self.user_start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_result": (
                "代理任务全部完成" if self.run_book else self.cur_user_item.status
            ),
        }
        success_symbol = "√" if self.run_book else "X"
        title = (
            f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
            f"{self.cur_user_item.name} 的自动代理统计报告"
        )

        try:
            await push_notification(
                "统计信息", title, statistics, self.cur_user_config
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"推送统计信息时出现异常: {e}")

    async def on_crash(self, e: Exception):
        """任务异常时的清理"""

        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"BAAH 任务出现异常: {e}")

        try:
            if self.log_monitor is not None:
                await self.log_monitor.stop()
        except Exception as stop_error:
            logger.opt(exception=True).warning(f"停止日志监控失败: {stop_error}")

        try:
            await self.kill_managed_process()
        except Exception as kill_error:
            logger.opt(exception=True).warning(f"清理 BAAH 进程失败: {kill_error}")

        try:
            await self._restore_managed_config()
        except Exception as restore_error:
            logger.opt(exception=True).warning(
                f"恢复 BAAH 托管配置失败: {restore_error}"
            )

        ## 异常可能发生在 run_once 的 finally 之前，这里兜底收尾采集（close 幂等）
        self._close_log_collect()

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"BAAH 任务出现异常: {e}"),
        )
