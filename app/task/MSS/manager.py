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

"""MSS（MaaStellaSora / 星塔旅人）控制器。

按用户逐个拉起 MSS 的外壳自动代理任务，结束时统一组装任务报告并推送。

**比通用 MaaFW 多控制了什么**：通用线（``ScriptType = "MaaFW"``）直接由 MAS 的
运行池加载 MaaFramework 运行项目，不碰项目自带的界面程序；MSS 专项走的是
**官方 MFAAvalonia 外壳**（``MFAAvalonia.exe --autostart -i <实例> -q``），因此
需要 MAS 负责任务级地改写并恢复外层的**实例配置**（``config/instances/*.json``，
上游私有格式，MAS 只在值层面经手）、按用户编排任务队列，并把外壳写的日志接进
MAS 的历史记录 / 通知 / 统计链路。选择外壳路线的原因：上游尚未提供 `preset`，
用户需要在 MAS 里按星塔语义组织任务队列并且不想自己打开 GUI。
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.emulator_manager import EmulatorManager
from app.core.ws import Publisher, protocol
from app.models.config import MSSConfig, MSSUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase, DeviceProvider
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services import System
from app.task.emulator_core import close_emulator
from app.task.notify_core import push_proxy_result
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .tools import (
    EXE_NAME,
    MssTaskCatalog,
    commit_instance_snapshot,
    discard_instance_snapshot,
    interface_exists,
    load_task_catalog_or_error,
    recover_previous_instance_snapshot,
    resolve_instance_dir,
    restore_instance_snapshot,
)

logger = get_logger("MSS 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask,
}


class MSSManager(TaskExecuteBase):
    """MSS 控制器"""

    def __init__(
        self,
        script_info: ScriptItem,
        mode: str = "AutoProxy",
        *,
        device_provider: DeviceProvider | None = None,
    ):
        """初始化 MSS 控制器。

        Args:
            script_info: 本次任务的脚本信息。
            mode: 任务模式；实际分派以 ``task_info.mode`` 为准，此参数仅用于
                显式覆盖与测试注入。
            device_provider: 模拟器实例提供者，缺省用全局 ``EmulatorManager``。
        """

        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.mode = mode
        self.check_result = "-"
        self.prepared = False
        self.snapshot_restored = False
        self.emulator_manager: DeviceBase | None = None
        self.task_catalog: MssTaskCatalog | None = None
        self.had_original_script_config = False
        self._device_provider = device_provider

    async def check(self) -> str:
        """校验 MSS 脚本配置是否可用。

        Returns:
            str: ``"Pass"`` 表示通过，其余文本是可直接展示给用户的失败原因。
        """

        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, MSSConfig):
            return "脚本配置类型错误, 不是 MSS 脚本类型"

        if script_config.get("Emulator", "Id") == "-" or script_config.get(
            "Emulator", "Index"
        ) in ["", "-"]:
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"

        ## 根目录、外壳程序与实例配置目录都由 Info.Path 派生，逐项给可读的原因
        root_path = Path(str(script_config.get("Info", "Path") or ""))
        if not (root_path / EXE_NAME).is_file():
            return "未找到 MFAAvalonia.exe, 请检查脚本配置中的 MSS 根目录设置！"

        if not interface_exists(root_path):
            return "未找到 MSS 的 interface.json, 请检查 MSS 根目录设置！"

        if not resolve_instance_dir(root_path).is_dir():
            return (
                "未找到 MSS 实例配置目录 config/instances, "
                "请先在 MSS 界面中保存一次实例配置！"
            )

        return "Pass"

    async def prepare(self) -> None:
        """运行前准备。

        顺序不能乱：先处置上次崩溃残留的快照，再备份本轮动手前的现场；实例配置
        的备份必须发生在任何注入之前。
        """

        script_id = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_id].lock()
        self.script_config = Config.ScriptConfig[script_id]
        self.user_config = MultipleConfig([MSSUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定, MSS 脚本配置提取完成")

        self.root_path = Path(str(self.script_config.get("Info", "Path") or ""))
        self.snapshot_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        ## 任务清单来自 MSS 自己的 interface.json（PI V2），读不出来只降级、不阻断：
        ## 模板里已有的任务项照常写入
        self.task_catalog, catalog_error = await asyncio.to_thread(
            load_task_catalog_or_error, self.root_path
        )
        if self.task_catalog is None:
            logger.warning(f"MSS 任务清单读取失败, 仅按实例配置模板写入任务: {catalog_error}")
        else:
            await self._sync_available_tasks(self.task_catalog)

        ## 初始化模拟器管理器：模拟器的启动与关闭统一由本软件调度，
        ## MSS 自身不再负责拉起模拟器
        device_provider = self._device_provider or EmulatorManager.get_emulator_instance
        self.emulator_manager = await device_provider(
            self.script_config.get("Emulator", "Id")
        )

        self._recover_previous_run()
        self.had_original_script_config = commit_instance_snapshot(
            self.root_path, self.snapshot_path, script_id=self.script_info.script_id
        )
        if not self.had_original_script_config:
            logger.warning(
                f"未找到可备份的 MSS 实例配置目录: {resolve_instance_dir(self.root_path)}"
            )

        ## 外壳常驻：同路径下已在运行的 MFAAvalonia 会接管新的命令行请求，那样
        ## `-q`（本次任务完成后退出）与本次的进程跟踪都会失效，所以先结束它
        try:
            await System.kill_process(self.root_path / EXE_NAME)
        except Exception as e:
            logger.warning(f"结束上次残留的 MSS 外壳进程失败: {e}")

        self.script_info.user_list = [
            UserItem(user_id=str(uid), name=config.get("Info", "Name"), status="等待")
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
            and self.task_info.is_target_user(str(uid))
        ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        self.prepared = True

    async def _sync_available_tasks(self, catalog: MssTaskCatalog) -> None:
        """把 MSS 的任务清单同步进用户的 ``Task.AvailableTasks``。

        前端任务勾选表直接读这个字段；MSS 的清单会随上游发版变化，每次运行前
        同步一次比在 MAS 里维护一份副本可靠。写入走 ``commit=False``，由收尾时
        的整表写回统一落盘；失败只告警，不阻断任务。

        Args:
            catalog: 本次读到的 MSS 任务清单。
        """

        payload = json.dumps(catalog.available_tasks(), ensure_ascii=False)
        for uid, config in self.user_config.items():
            if config.get("Task", "AvailableTasks") == payload:
                continue
            try:
                await config.set("Task", "AvailableTasks", payload, commit=False)
            except Exception as e:
                logger.warning(f"同步用户 {uid} 的 MSS 可用任务列表失败: {e}")

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的实例配置快照。"""

        result = recover_previous_instance_snapshot(
            self.root_path, self.snapshot_path, script_id=self.script_info.script_id
        )
        if result == "restored":
            logger.info("已恢复上次中断前的 MSS 实例配置")
        elif result == "skipped":
            logger.warning(
                "检测到 MSS 实例配置在中断后被改动, 已保留当前配置并丢弃旧快照"
            )

    async def _restore_instance_config(self) -> None:
        """原子恢复任务开始前的 MSS 实例配置。

        正常结束、异常与崩溃后的首次运行都会走到这里；恢复失败必须让用户知道——
        实例配置会一直带着本次运行写入的队列与 adb 地址，界面却显示一切正常。
        """

        if self.snapshot_restored or not self.prepared:
            return
        self.snapshot_restored = True

        try:
            restore_instance_snapshot(
                self.root_path,
                self.snapshot_path,
                had_original=self.had_original_script_config,
            )
            discard_instance_snapshot(self.snapshot_path)
        except Exception as e:
            ## 恢复失败时保留快照：下次任务开始时 recover_previous_run 还能再试一次
            logger.opt(exception=True).warning(f"恢复 MSS 实例配置失败: {e}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"恢复 MSS 实例配置失败: {e}"
                ),
            )

    async def main_task(self):
        """按用户逐个执行自动代理任务。"""

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.warning(f"未通过配置检查: {self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if not isinstance(self.script_config, MSSConfig):
            raise RuntimeError("脚本配置类型错误, 不是 MSS 脚本类型")

        ## 各用户共用同一份外壳实例配置，只能串行执行
        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                self.emulator_manager,
                self.task_catalog,
            )
            await self.spawn(task)

    async def final_task(self):
        """运行结束后的收尾工作。"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            await self._restore_instance_config()
            return self.check_result

        logger.info("MSS 任务已结束, 开始执行后续操作")

        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode == "AutoProxy":
            if self.script_config.get("Emulator", "CloseOnFinish"):
                await close_emulator(self)

            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())
            await Config.ScriptConfig.save()

            error_count = sum(
                1 for u in self.script_info.user_list if u.status == "异常"
            )
            over_count = sum(
                1 for u in self.script_info.user_list if u.status == "完成"
            )
            wait_count = sum(
                1 for u in self.script_info.user_list if u.status == "等待"
            )

            title = (
                f"{datetime.now().strftime('%m-%d')} | "
                f"{self.script_info.name or '空白'}的"
                f"{TASK_MODE_ZH[self.task_info.mode]}任务报告"
            )
            result = {
                "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
                "script_name": self.script_info.name or "空白",
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": over_count,
                "uncompleted_count": error_count + wait_count,
                "result": self.script_info.result,
            }

            try:
                await push_proxy_result(
                    title=title, message=result, task_info=self.task_info
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送代理结果时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送代理结果时出现异常: {e}"
                    ),
                )

        await self._restore_instance_config()

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):
        """任务异常时的清理。

        外壳进程与实例配置都在 ``app/task/MSS/AutoProxy.py`` 与 ``final_task``
        里收尾；这里只保证实例配置不会停在注入态，并把异常告知用户。

        Args:
            e: 触发收尾的异常。
        """

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"MSS 任务出现异常: {e}")

        await self._restore_instance_config()

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MSS 任务出现异常: {e}"),
        )
