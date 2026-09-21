#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MSS 自动代理模式（单用户运行编排）。

运行方式 = **改外壳实例配置 + 启动外壳 exe**（与 M9A / MaaEnd 同一模式）：

1. 以「本轮动手前」的实例配置为模板，只替换 `CurrentTasks` 与 `AdbDevice`
   里由 MAS 调度的模拟器决定的字段，其余键值原样写回
   （见 ``.tools.instance_config``）；
2. 启动 ``MFAAvalonia.exe --autostart -i <实例> -q``；
3. 读 ``<根>/logs/log-YYYYMMDD.log`` 判定本轮结果。

成败判定取自上游结果面（外壳写的日志），MAS 侧不自造标记：成功文案
``任务已全部完成！`` 与中止文案 ``已放弃本次任务`` 都在实测日志里出现过；
``任务运行失败`` 是同框架壳（M9A）的顶层失败文案，MSS 样本里尚未出现，
按宽松匹配保留。**失败文案待实测校准**：当前口径是「进程退出 + 日志里找不到
失败标记 = 成功」，命中失败标记一律按异常处理。
"""

import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.notify import NotifyPayload, dispatch, statistic_targets
from app.core.ws import Publisher, protocol
from app.models.config import MSSConfig, MSSUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify
from app.task.general.tools.ExecuteScript import execute_script_task
from app.utils import (
    LogMonitor,
    ProcessInfo,
    ProcessManager,
    compile_log_signs,
    get_logger,
)
from app.utils.platform import IS_ELEVATED
from app.utils.constants import UTC4

from .tools import (
    EXE_NAME,
    LOG_DIR_NAME,
    MssTaskCatalog,
    apply_adb_device,
    apply_queue_to_config,
    latest_log_file,
    mark_instance_config_injected,
    normalize_user_queue,
    read_instance_template,
    resolve_instance_id,
    resolve_instance_path,
    write_instance_config,
)

logger = get_logger("MSS 自动代理")

## MSS 的日志行形如：
##   [2026-07-28 00:08:41.110][INF] [cfg=Default][inst=配置 1/default][src=Worker][op=StopTask] 停止前状态：NOT_STARTED
## 时间戳区间是 LogMonitor 对**整行**做的字符切片（line[start:end]），不是按分隔符
## 分词后的字段下标：行首 `[` 占 1 个字符，其后 "YYYY-MM-DD HH:MM:SS.fff" 共 23 个。
## 该取值与 M9A 相同（两者同为 MFAAvalonia 外壳，日志行排版一致）。
MSS_LOG_TIME_RANGE = (1, 24)
MSS_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

## 成功标记：外壳 MonitorLog 在任务队列跑完时输出（实测 log-20260727 / log-20260915）
MSS_SUCCESS_LOG = "任务已全部完成！|All tasks completed"
## 未跑完就收场：用户中止或外壳放弃本次任务（实测同一批日志）
MSS_ABANDON_LOG = "已放弃本次任务"
## 顶层失败文案：同框架壳（M9A）用它作为运行失败的标志，MSS 样本里未出现，待实测校准
MSS_ERROR_LOG = "任务运行失败"

## 等待日志文件出现的超时（秒）。外壳要先拉起 Agent 与 MaaFramework，
## 冷启模拟器时的启动窗口明显长于通用脚本，给足等待时间。
_LOG_FILE_WAIT_SECONDS = 120

## 进程退出后留给外壳冲刷尾部日志的时间（秒）
_LOG_DRAIN_SECONDS = 5

## 一轮结束后等待相关进程退出的时间（秒）
_PROCESS_EXIT_WAIT_SECONDS = 10

## 命中成功标记后留给外壳自行收尾的宽限时间（秒）。
## 外壳带 `-q`，跑完会自己退出；立即强杀会把收尾动作截断。
_PROCESS_GRACE_SECONDS = 60


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MSSConfig,
        user_config: MultipleConfig[MSSUserConfig],
        emulator_manager: DeviceBase | None,
        task_catalog: MssTaskCatalog | None,
    ):
        """初始化单用户运行上下文。

        Args:
            script_info: 本次任务的脚本信息。
            script_config: MSS 脚本配置。
            user_config: 该脚本的全部用户配置（运行时副本）。
            emulator_manager: 本软件接管的模拟器实例；无模拟器时为 None。
            task_catalog: MSS 的 PI V2 任务清单，用于补齐模板里没有的任务项。
        """

        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.task_catalog = task_catalog
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"
        self.run_book = False
        self.process_manager: ProcessManager | None = None
        self.log_monitor: LogMonitor | None = None
        self.script_log_path: Path | None = None
        self.emulator_adb_address: str = ""
        ## 本用户的开始时刻，用于统计信息通知
        self.user_start_time = datetime.now()
        ## 进程退出看门狗
        self._exit_watch_task: asyncio.Task | None = None
        ## check 阶段解析出的队列，供 prepare / 写入配置复用
        self.user_queue: list[dict] = []
        self.success_log = compile_log_signs(MSS_SUCCESS_LOG, "Split")
        self.abandon_log = compile_log_signs(MSS_ABANDON_LOG, "Split")
        self.error_log = compile_log_signs(MSS_ERROR_LOG, "Split")

        self._resolve_paths()

    def _resolve_paths(self) -> None:
        """解析 MSS 根目录、外壳程序、日志目录与实例配置文件路径。

        这些位置都由脚本配置里的 ``Info.Path`` 派生，不再单独提供输入项：
        MSS 的外壳、清单、实例配置与日志都固定在同一个根目录下。
        """

        self.root_path = Path(self.script_config.get("Info", "Path"))
        self.exe_path = self.root_path / EXE_NAME
        self.log_dir = self.root_path / LOG_DIR_NAME
        self.snapshot_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        self.instance_id = resolve_instance_id(self.root_path)
        self.instance_path = resolve_instance_path(self.root_path, self.instance_id)
        ## 提权启动走 ShellExecute，拿不到子进程句柄，只能靠这份进程信息追踪外壳
        self.shell_target_process_info = ProcessInfo(
            name=EXE_NAME,
            exe=str(self.exe_path),
            cmdline=None,
        )

    def _resolve_log_file_path(self) -> Path:
        """按当前本地日期解析外壳日志路径。

        外壳每天写一个 ``logs/log-YYYYMMDD.log``。路径必须在监控循环里按需重算，
        否则任务跨过本地午夜后外壳写进新文件，监控仍盯着旧文件，读不到新行并
        最终误判为超时。

        Returns:
            Path: 当天日志文件路径。
        """

        return self.log_dir / f"log-{datetime.now().strftime('%Y%m%d')}.log"

    async def check(self) -> str:
        """校验本次运行所需的路径与用户队列。

        Returns:
            str: ``"Pass"`` 表示通过，其余文本是可直接展示给用户的失败原因。
        """

        if not self.exe_path.is_file():
            self.cur_user_item.status = "异常"
            return "未找到 MFAAvalonia.exe, 请检查脚本配置中的 MSS 根目录设置！"

        if not self.instance_path.is_file() and not (
            self.snapshot_path / self.instance_path.name
        ).is_file():
            self.cur_user_item.status = "异常"
            return (
                f"未找到 MSS 实例配置 config/instances/{self.instance_path.name}, "
                "请先在 MSS 界面中保存一次实例配置！"
            )

        try:
            self.user_queue = normalize_user_queue(
                self.cur_user_config.get("Task", "Queue")
            )
        except Exception as e:
            self.cur_user_item.status = "异常"
            return f"MSS 任务队列解析失败: {e}"

        if not self.user_queue:
            self.cur_user_item.status = "异常"
            return "未配置任务队列或队列为空, 请先在用户配置中选择要运行的任务！"

        return "Pass"

    async def prepare(self) -> None:
        """运行前准备：进程管理器、日志监控与判定标记。

        日志监控器**不在这里构造**：它把构造时刻当作补齐时间戳缺失部分的基准，
        而冷启模拟器与等待日志文件可能跨过整点，提前构造会把日志首行算成上一个
        小时而整段丢弃。等定位到日志文件之后再构造（见 ``_run_launched``）。
        """

        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.log_start_time = datetime.now()
        self.log_start_at = time.monotonic()
        self.log_monitor = None
        self._exit_watch_task = None

    async def main_task(self):
        """自动代理模式主逻辑"""

        self.user_start_time = datetime.now()

        ## 每日重置：跨天后代理次数归零，用户标签里的「任务」状态才会重新变成
        ## 「未代理」（与通用脚本同一套口径）
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

            ## 执行任务前脚本
            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            await self.run_once()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.cur_user_item.status = "完成"
                logger.success(f"用户: {self.cur_user_uid} - MSS 完成代理任务")
                break

            self.cur_user_item.status = "异常"
            logger.warning(
                f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
            )
            await asyncio.sleep(3)

    async def _ensure_emulator_online(self) -> bool:
        """由本软件拉起模拟器并等待其在线。

        模拟器的启动与关闭统一由 MAS 调度，MSS 只负责连接；冷启动耗时较长，
        在这里等它就绪，避免占用外壳自身的等待窗口。

        Returns:
            bool: 模拟器是否可用（未接管模拟器时恒为 True）。
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

    def _resolve_emulator_ref(self) -> tuple[str, str, Path]:
        """解析本次运行使用的模拟器类型、原生实例序号与主管理器程序路径。

        优先问模拟器管理器（一条配置可以纳管多个安装，那种情况下持久化的类型
        未必等于设备的真实类型），拿不到时退回脚本配置里的模拟器配置项。

        Returns:
            tuple[str, str, Path]: ``(类型, 原生实例序号, 管理器程序路径)``。
        """

        emulator_id = self.script_config.get("Emulator", "Id")
        emulator_index = self.script_config.get("Emulator", "Index")

        resolve_device = getattr(self.emulator_manager, "resolve_device", None)
        device_ref = resolve_device(emulator_index) if resolve_device else None
        if device_ref is not None:
            return (
                str(device_ref.emulator_type),
                str(device_ref.native_index),
                Path(device_ref.manager_path),
            )

        try:
            emulator_config = Config.EmulatorConfig[uuid.UUID(str(emulator_id))]
            return (
                str(emulator_config.get("Info", "Type") or ""),
                str(emulator_index),
                Path(str(emulator_config.get("Info", "Path") or "")),
            )
        except Exception as e:
            logger.warning(f"解析模拟器信息失败, 只更新 ADB 地址: {e}")
            return "", str(emulator_index), Path("")

    def _resolve_emulator_paths(
        self, manager_path: Path
    ) -> tuple[str | None, str | None]:
        """由主管理器程序路径推出 ``adb.exe`` 路径与模拟器安装根目录。

        MuMu 与雷电的布局一致：管理器程序在 ``<根>/<外壳目录>/`` 下，``adb.exe``
        与它同级，安装根目录是再上一层。实测 MuMu：管理器
        ``D:/mumu/MuMuPlayer/nx_main/MuMuManager.exe`` → adb
        ``D:/mumu/MuMuPlayer/nx_main/adb.exe`` → 根目录 ``D:/mumu/MuMuPlayer``。

        Args:
            manager_path: 模拟器主管理器程序路径。

        Returns:
            tuple[str | None, str | None]: ``(adb.exe 路径, 安装根目录)``；
            路径不可用时为 ``(None, None)``。
        """

        if not str(manager_path).strip() or not manager_path.name:
            return None, None

        shell_dir = manager_path.parent
        adb_path = shell_dir / "adb.exe"
        if not adb_path.is_file():
            ## 找不到 adb.exe 就保留用户原有的 AdbPath：写一条不存在的路径
            ## 只会让外壳起不来，而用户那份至少是他自己验证过的
            logger.warning(f"未找到模拟器 adb.exe: {adb_path}, 保留实例配置里的原始值")
            return None, str(shell_dir.parent)

        return str(adb_path).replace("\\", "/"), str(shell_dir.parent)

    def _write_instance_config(self) -> None:
        """按用户队列与本次模拟器调度结果改写外壳实例配置。

        模板取自「本轮动手前」的快照（多用户连续运行时现场文件已被上一个用户
        改写），只替换队列、任务项与 AdbDevice 里的 adb 字段。
        """

        template = read_instance_template(
            self.root_path, self.snapshot_path, instance_id=self.instance_id
        )
        if not template:
            raise FileNotFoundError(f"未找到可用的 MSS 实例配置: {self.instance_path}")

        catalog = self.task_catalog
        config = apply_queue_to_config(
            template,
            self.user_queue,
            task_definitions=catalog.task_definitions() if catalog else None,
            option_definitions=catalog.options if catalog else None,
        )

        emulator_type, native_index, manager_path = self._resolve_emulator_ref()
        adb_path, emulator_root = self._resolve_emulator_paths(manager_path)
        ## Name 不传：那是用户在 MSS 里自己起的名字，MAS 不参与命名
        changed = apply_adb_device(
            config,
            adb_path=adb_path,
            adb_serial=self.emulator_adb_address or None,
            emulator_type=emulator_type,
            emulator_index=native_index,
            emulator_root=emulator_root,
        )

        write_instance_config(self.instance_path, config)
        mark_instance_config_injected(
            self.root_path, self.snapshot_path, script_id=self.script_info.script_id
        )
        logger.info(
            f"MSS 实例配置已就绪: 实例 {self.instance_id}, 任务 "
            f"{len(self.user_queue)} 个, AdbDevice 改动: {changed or '无'}"
        )

    async def run_once(self) -> None:
        """执行一次 MSS 运行。

        启动模拟器、写入实例配置、启动外壳进程并等日志判定结果。
        """

        self.wait_event.clear()

        if not await self._ensure_emulator_online():
            return

        try:
            self._write_instance_config()
        except Exception as e:
            logger.opt(exception=True).warning(f"写入 MSS 实例配置失败: {e}")
            await self.handle_pre_script_error("写入 MSS 实例配置失败", e)
            return

        try:
            await self._run_launched()
        finally:
            await self._stop_exit_watch()

    async def _run_launched(self) -> None:
        """启动外壳进程并等待日志给出结果。"""

        if self.process_manager is None:
            raise RuntimeError("自动代理任务尚未完成初始化")

        launch_at = time.time()
        logger.info(
            f"运行 MSS: {self.exe_path} - 实例 {self.instance_id} "
            f"(--autostart -i {self.instance_id} -q)"
        )

        try:
            await self.process_manager.open_process(
                self.exe_path,
                "--autostart",
                "-i",
                self.instance_id,
                "-q",
                target_process=self.shell_target_process_info,
                # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承。
                # MSS 的桌面端 controller 在 interface 里声明了 permission_required，
                # 外壳没有管理员权限就操作不了游戏窗口。
                elevated=self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED,
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"启动 MFAAvalonia 进程失败: {e}")
            await self.handle_pre_script_error("启动 MFAAvalonia 进程失败", e)
            return

        ## 外壳带 -q，任务跑完会自己退出；退出后日志不再增长，日志回调也就
        ## 不会再触发，必须由看门狗兜底唤醒主流程
        self._start_exit_watch()

        self.script_info.log = "正在等待 MSS 日志文件生成"
        log_path = await self._wait_log_file(launch_at)
        if log_path is None:
            await self.handle_pre_script_error("未找到 MSS 日志文件")
            return

        self.script_log_path = log_path
        logger.success(f"成功定位到日志文件: {self.script_log_path}")
        ## 定位成功后立刻改写状态：日志监控要等外壳写出首批日志行才会回调，
        ## 不改写的话界面会继续停在「正在等待日志文件生成」，看起来像没进展
        self.script_info.log = f"已定位 MSS 日志文件 {log_path.name}, 正在读取日志"

        ## 监控器在这里才构造：让它补齐时间戳所用的基准落在日志真正出现之后，
        ## 跨整点时不会把首行算成上个小时
        self.log_monitor = LogMonitor(
            MSS_LOG_TIME_RANGE,
            MSS_LOG_TIME_FORMAT,
            self.check_log,
        )
        await self.log_monitor.start_monitor_file(
            self._resolve_log_file_path, self.log_start_time
        )
        await self.wait_event.wait()
        await self.log_monitor.stop()

        ## 命中成功标记只说明任务跑完了，外壳还要走自己的收尾（`-q` 退出）：
        ## 先给它时间自己走完，超时才强制结束
        if self.cur_user_log.status == "Success!":
            await self._wait_process_exit()

        await self.kill_managed_process()
        await asyncio.sleep(_PROCESS_EXIT_WAIT_SECONDS)

    async def _wait_log_file(self, launch_at: float) -> Path | None:
        """等本轮的日志文件出现。

        Args:
            launch_at: 启动外壳的时间戳，用于兜底定位刚刚被写过的日志文件。

        Returns:
            Path | None: 日志文件路径；超时未出现时返回 None。
        """

        wait_started_at = time.monotonic()
        deadline = wait_started_at + _LOG_FILE_WAIT_SECONDS

        while time.monotonic() < deadline:
            log_path = self._resolve_log_file_path()
            if log_path.is_file():
                return log_path
            fallback = latest_log_file(self.log_dir, launch_at)
            if fallback is not None:
                return fallback
            ## 状态带上已等待秒数：否则界面在整个等待窗口里都是一句静止的文案，
            ## 用户无法区分「正在等」与「已经卡死」
            self.script_info.log = (
                f"正在等待 MSS 日志文件生成（已等待 "
                f"{int(time.monotonic() - wait_started_at)} 秒）"
            )
            await asyncio.sleep(1)

        return None

    async def _wait_process_exit(self) -> None:
        """等外壳自行退出，给它走完收尾动作的机会。"""

        if self.process_manager is None:
            return

        deadline = time.monotonic() + _PROCESS_GRACE_SECONDS
        while time.monotonic() < deadline:
            if not await self.process_manager.is_running():
                return
            await asyncio.sleep(1)

        logger.warning(
            f"MSS 外壳在 {_PROCESS_GRACE_SECONDS} 秒内未自行退出, 将强制结束"
        )

    def _start_exit_watch(self) -> None:
        """启动进程退出看门狗。"""

        if self._exit_watch_task is None or self._exit_watch_task.done():
            self._exit_watch_task = asyncio.create_task(self._watch_process_exit())

    async def _stop_exit_watch(self) -> None:
        """停止进程退出看门狗。"""

        if self._exit_watch_task is None:
            return

        if not self._exit_watch_task.done():
            self._exit_watch_task.cancel()
            try:
                await self._exit_watch_task
            except asyncio.CancelledError:
                pass
        self._exit_watch_task = None

    async def _watch_process_exit(self) -> None:
        """进程退出看门狗。

        外壳带 ``-q``，任务跑完会自行退出；退出后日志不再增长，日志回调也就不会
        再触发，界面会一直停在「正在读取日志」。这里轮询进程状态，退出并留出日志
        冲刷窗口后按已采集到的日志做一次判定，再唤醒主流程。
        """

        while not self.wait_event.is_set():
            if self.process_manager is None or not await self.process_manager.is_running():
                await asyncio.sleep(_LOG_DRAIN_SECONDS)
                if self.wait_event.is_set():
                    return
                self.cur_user_log.status = self._judge_from_log(
                    "".join(self.cur_user_log.content)
                )
                logger.info(
                    f"MSS 外壳进程已退出, 结果判定: {self.cur_user_log.status}"
                )
                self.wait_event.set()
                return

            await asyncio.sleep(1)

    def _judge_from_log(self, log: str) -> str:
        """按已采集的日志内容判定本轮结果（进程已退出时的兜底口径）。

        Args:
            log: 本轮采集到的日志全文。

        Returns:
            str: 判定结果，成功时固定为 ``"Success!"``。
        """

        if self.success_log.search(log) is not None:
            return "Success!"
        if self.error_log.search(log) is not None:
            return "MSS 运行出错"
        if self.abandon_log.search(log) is not None:
            return "MSS 已放弃本次任务"
        return "MSS 在完成任务前退出"

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调：判定本轮运行的结果。

        判定取自上游结果面（外壳写的日志），MAS 侧不自造标记：命中成功 / 中止 /
        失败文案即收口，没有新日志超过 ``Run.RunTimeLimit`` 判超时，进程还在跑
        则继续等待。

        Args:
            log_content: 本轮累积的日志内容。
            latest_time: 最近一条日志的时间戳。
        """

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if self.success_log.search(log) is not None:
            self.cur_user_log.status = "Success!"
        elif self.error_log.search(log) is not None:
            self.cur_user_log.status = "MSS 运行出错"
        elif self.abandon_log.search(log) is not None:
            self.cur_user_log.status = "MSS 已放弃本次任务"
        elif self.is_log_stalled(
            latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "MSS 进程超时"
        elif (
            self.process_manager is not None and await self.process_manager.is_running()
        ):
            self.cur_user_log.status = "MSS 正常运行中"
        else:
            self.cur_user_log.status = "MSS 在完成任务前退出"

        logger.debug(f"MSS 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MSS 正常运行中":
            logger.info(f"MSS 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def kill_managed_process(self) -> None:
        """中止本次运行托管的外壳进程。

        外壳会再拉起 Agent 子进程，因此除了进程管理器持有的句柄，还要按可执行
        文件路径做一次整树清理。
        """

        if self.process_manager is None:
            return

        try:
            logger.info(f"中止 MSS 外壳进程: {self.exe_path}")
            await self.process_manager.kill()
            await System.kill_process(self.exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 MSS 外壳进程失败: {e}")
            ## 外壳由 MAS 提权启动、而 MAS 自身未提权时，MAS 无权结束它。
            ## 不说清楚的话，用户只会看到一个残留的 MFAAvalonia 挡着下一次运行。
            if self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED:
                logger.warning(
                    "MSS 外壳可能以管理员权限运行，而本软件自身未提权，无法结束它："
                    "请手动关闭 MFAAvalonia，或以管理员身份运行 AUTO-MAS 后重试"
                )

    async def handle_pre_script_error(
        self, error_message: str, e: Exception | None = None
    ) -> None:
        """处理运行前的准备阶段错误。

        Args:
            error_message: 面向用户的错误描述。
            e: 触发错误的具体异常，可为 None。
        """

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

    async def final_task(self) -> None:
        """运行结束后的收尾工作。"""

        await self._stop_exit_watch()

        if self.log_monitor is not None:
            await self.log_monitor.stop()

        await self.kill_managed_process()

        if self.check_result != "Pass":
            self.cur_user_item.status = "异常"
            return

        for t, log_item in sorted(
            self.cur_user_item.log_record.items(), key=lambda item: item[0]
        ):
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=t.astimezone(UTC4),
            )

            if log_item.status == "MSS 正常运行中":
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

        message_text = (
            f"开始时间: {statistics['start_time']}\n"
            f"结束时间: {statistics['end_time']}\n"
            f"MSS 执行结果: {statistics['user_result']}\n\n"
        )
        template = Config.notify_env.get_template("general_statistics.html")

        try:
            await dispatch(
                NotifyPayload(
                    title=title,
                    text=message_text,
                    html=template.render(statistics),
                ),
                statistic_targets(self.cur_user_config),
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"推送统计信息时出现异常: {e}")

    async def on_crash(self, e: Exception) -> None:
        """任务异常时的清理。

        Args:
            e: 触发收尾的异常。
        """

        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"MSS 任务出现异常: {e}")

        try:
            await self._stop_exit_watch()
        except Exception as stop_error:
            logger.opt(exception=True).warning(f"停止进程看门狗失败: {stop_error}")

        try:
            if self.log_monitor is not None:
                await self.log_monitor.stop()
        except Exception as stop_error:
            logger.opt(exception=True).warning(f"停止日志监控失败: {stop_error}")

        try:
            await self.kill_managed_process()
        except Exception as kill_error:
            logger.opt(exception=True).warning(f"清理 MSS 进程失败: {kill_error}")

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MSS 任务出现异常: {e}"),
        )
