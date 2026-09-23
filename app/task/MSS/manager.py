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

**比通用 MaaFW 多控制了什么**：通用线（``ScriptType = "MaaFW"``）由 MAS 的运行池
直接加载 MaaFramework，任务清单每次现读 ``interface.json``、在 MAS 里挑任务，从不
启动项目自带的界面程序；MSS 专项走的是**官方 MFAAvalonia 外壳**——用户在外壳里
配好实例与任务，MAS 只按实例把它拉起来（``MFAAvalonia.exe --autostart -i <实例>
-q``），再把外壳写的日志接进 MAS 的历史记录 / 通知 / 统计链路。

MAS 只在「计划表与活动编排」里读写外壳的实例配置（``config/instances/*.json`` 是上游私有
格式，只改 ``CurrentTasks`` 与三个选项、跑完还原，见 ``tools/orchestrate.py``）；游戏启停与
可选的 Unity 分辨率临时覆盖由 ``tools/game_launch.py`` 负责。

MSS 只适配**桌面端**：星塔旅人的模拟器端游戏起不来，未做适配——所以这里既不要模拟器配置，
也不参与模拟器的启停。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import MSSConfig, MSSUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.services import System
from app.task.notify_core import push_proxy_result
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH
from app.utils.io import (
    clear_native_config_snapshot,
    dir_fingerprint,
    recover_native_config,
    replace_dir,
    write_native_config_snapshot,
)

from .AutoProxy import AutoProxyTask
from .tools import (
    EXE_NAME,
    INTERFACE_NAME,
    resolve_instance_dir,
    resolve_temp_dir,
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
    ):
        """初始化 MSS 控制器。

        Args:
            script_info: 本次任务的脚本信息。
            mode: 任务模式；实际分派以 ``task_info.mode`` 为准，此参数仅用于
                显式覆盖与测试注入。
        """

        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.mode = mode
        self.check_result = "-"
        self.prepared = False
        ## 桌面端专用：MSS 不接管模拟器，这里恒为 None（AutoProxy 会跳过模拟器的启动与关闭）
        self.emulator_manager: DeviceBase | None = None

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

        ## 这里**不校验模拟器配置**：MSS 只做桌面端（星塔旅人的模拟器端游戏起不来，
        ## 不进行适配），没有模拟器也照常运行。缺模拟器要拦的话，拦在 App 自己的
        ## 桌面端准备里，而不是在这里要求用户去配一个用不上的模拟器。

        ## 根目录、外壳程序与实例配置目录都由 Info.Path 派生，逐项给可读的原因
        root_path = Path(str(script_config.get("Info", "Path") or ""))
        if not (root_path / EXE_NAME).is_file():
            return "未找到 MFAAvalonia.exe, 请检查脚本配置中的 MSS 根目录设置！"

        if not (root_path / INTERFACE_NAME).is_file():
            return "未找到 MSS 的 interface.json, 请检查 MSS 根目录设置！"

        if not resolve_instance_dir(root_path).is_dir():
            return (
                "未找到 MSS 实例配置目录 config/instances, "
                "请先在 MSS 界面中保存一次实例配置！"
            )

        return "Pass"

    async def prepare(self) -> None:
        """运行前准备：锁定脚本配置、加载用户列表、结束上次残留的外壳进程。"""

        script_id = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_id].lock()
        self.script_config = Config.ScriptConfig[script_id]
        self.user_config = MultipleConfig([MSSUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定, MSS 脚本配置提取完成")

        self.root_path = Path(str(self.script_config.get("Info", "Path") or ""))

        ## 实例配置的注入快照与恢复：编排会改写外壳的 config/instances，改之前把整目录
        ## 快照到 MAS 自己的数据目录。崩溃时下次运行自动恢复成原样；正常跑完清掉快照，
        ## 也就是「保留编排」——这套与 MAA / M9A 用的是同一套设施。
        self.instance_dir = resolve_instance_dir(self.root_path)
        self.temp_path = resolve_temp_dir(self.script_info.script_id)
        self._recover_previous_run()
        if self.instance_dir.is_dir():
            replace_dir(self.instance_dir, self.temp_path)
            write_native_config_snapshot(
                self.temp_path,
                script_id=self.script_info.script_id,
                original_exists=True,
                baseline=dir_fingerprint(self.temp_path),
            )

        ## 桌面端用不上模拟器：MSS 未适配模拟器端，这里不再按脚本配置去取实例，
        ## 免得老配置里残留的模拟器被莫名其妙拉起来
        self.emulator_manager = None

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

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的实例配置快照。"""

        result = recover_native_config(
            self.temp_path,
            self.instance_dir,
            expected_script_id=self.script_info.script_id,
        )
        if result == "restored":
            logger.info("已恢复上次中断前的外壳实例配置")
        elif result == "skipped":
            logger.warning(
                "检测到外壳实例配置在中断后被改动, 已保留当前配置并丢弃旧快照"
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
            )
            await self.spawn(task)

    async def final_task(self):
        """运行结束后的收尾工作。"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        logger.info("MSS 任务已结束, 开始执行后续操作")

        ## 跑完了就把注入快照清掉：编排结果留在外壳里，下次运行不再「恢复」它
        clear_native_config_snapshot(self.temp_path)

        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode == "AutoProxy":
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

        self.script_info.status = "完成"

    async def on_crash(self, e: Exception):
        """任务异常时的清理。

        外壳进程在 ``app/task/MSS/AutoProxy.py`` 里收尾；这里把异常告知用户。

        Args:
            e: 触发收尾的异常。
        """

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"MSS 任务出现异常: {e}")

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MSS 任务出现异常: {e}"),
        )
