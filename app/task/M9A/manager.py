#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime

from app.core import Config, EmulatorManager
from app.models.task import TaskExecuteBase, ScriptItem, UserItem
from app.models.ConfigBase import MultipleConfig
from app.models.config import M9AConfig, M9AUserConfig
from app.services import Notify, System
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH
from .tools import push_notification
from .AutoProxy import AutoProxyTask


logger = get_logger("M9A 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask]] = {
    "AutoProxy": AutoProxyTask
}


class M9AManager(TaskExecuteBase):
    """M9A 调度器"""

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.has_new_version = False
        self.auto_update_fix_enabled = False
        self._virtual_user_old_version = None
        self._virtual_user_new_version = None

    async def check(self) -> str:
        """校验 M9A 配置是否可用"""
        script_id = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_id]

        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式，请检查任务配置！"
        if not isinstance(script_config, M9AConfig):
            return "脚本配置类型错误，不是 M9A 脚本类型"
        if script_config.get("Emulator", "Id") == "-" or script_config.get(
            "Emulator", "Index"
        ) in ("", "-"):
            return "未完成模拟器配置，请检查脚本配置中的模拟器设置！"

        m9a_exe_path = Path(script_config.get("Info", "Path")) / "M9A.exe"
        if not m9a_exe_path.exists():
            return "M9A.exe 文件不存在，请检查 M9A 路径设置！"

        m9a_root = Path(script_config.get("Info", "Path"))
        m9a_config_dir = m9a_root / "config"
        m9a_instances_dir = m9a_config_dir / "instances"

        root_name_lower = str(m9a_root).lower()
        looks_like_mux = "mux" in root_name_lower or any(
            "mux" in p.name.lower() for p in m9a_root.iterdir()
        )

        if not m9a_config_dir.exists():
            return "M9A/config 目录不存在，请检查 M9A 路径是否指向完整的 M9A 程序目录。"

        if not m9a_instances_dir.exists():
            if looks_like_mux:
                return (
                    "检测到当前 M9A 可能为 MuX 框架构建"
                    "（目录/配置结构与 AUTO-MAS 的 M9A 适配不兼容）。\n"
                    "请在脚本编辑设置中将 M9A 路径切换为 MFAA 构建版本的 M9A 根目录"
                    "（应包含 M9A.exe 与 config/instances/）。"
                )
            return (
                "M9A/config/instances 目录不存在，无法写入运行配置。\n"
                "请确认 M9A 路径正确，或使用 MFAA 构建版本的 M9A。"
            )

        if not any(m9a_config_dir.glob("*.json")):
            return "M9A 配置文件不存在或已损坏，请检查 M9A 路径或配置文件情况！"
        return "Pass"

    async def _set_m9a_auto_update(self, enabled: bool):
        """设置 M9A config.json 中 EnableAutoUpdateResource 的值"""
        if not self.m9a_config_path:
            return
        config_json = self.m9a_config_path / "config.json"
        if not config_json.exists():
            return
        try:
            config = json.loads(config_json.read_text(encoding="utf-8"))
            config["EnableAutoUpdateResource"] = enabled
            config_json.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            status = "开启" if enabled else "关闭"
            logger.info(f"已{status} M9A 自动更新开关")
        except Exception:
            logger.warning("读写 M9A config.json 失败，跳过自动更新控制")

    async def _set_m9a_silent_mode(self):
        if not self.m9a_config_path:
            return
        config_json = self.m9a_config_path / "config.json"
        if not config_json.exists():
            return
        try:
            config = json.loads(config_json.read_text(encoding="utf-8"))
            is_silent = Config.get("Function", "IfSilence")
            config["AutoMinimize"] = is_silent
            config["AutoHide"] = is_silent
            config["ShouldMinimizeToTray"] = is_silent
            config_json.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            status = "开启" if is_silent else "关闭"
            logger.info(f"已{status} M9A 静默模式（AutoMinimize={is_silent}, AutoHide={is_silent}, ShouldMinimizeToTray={is_silent}）")
        except Exception as e:
            logger.warning(f"读写 M9A config.json 失败，跳过静默模式配置: {e}")

    async def prepare(self):
        """运行前准备"""

        script_id = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_id].lock()
        self.script_config = Config.ScriptConfig[script_id]
        self.user_config = MultipleConfig([M9AUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id} 已锁定，M9A 配置提取完成")

        self.m9a_config_path = Path(self.script_config.get("Info", "Path")) / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        # 初始化模拟器管理器
        self.emulator_manager = await EmulatorManager.get_emulator_instance(
            self.script_config.get("Emulator", "Id")
        )

        # 备份原始配置并清空 instances 目录（仅保留 default.json）
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)
        if self.m9a_config_path.exists():
            shutil.copytree(self.m9a_config_path, self.temp_path, dirs_exist_ok=True)

            instances_dir = self.m9a_config_path / "instances"
            if instances_dir.exists():
                for json_file in instances_dir.glob("*.json"):
                    try:
                        json_file.unlink()
                        logger.info(f"已删除原始配置文件：{json_file}")
                    except Exception as e:
                        logger.warning(f"删除原始配置文件 {json_file} 失败：{e}")

        # 构建用户列表
        self.script_info.user_list = [
            UserItem(
                user_id=str(uid), name=config.get("Info", "Name"), status="等待"
            )
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
        ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        m9a_exe = Path(self.script_config.get("Info", "Path")) / "M9A.exe"
        await System.kill_process(m9a_exe)

        await self._set_m9a_auto_update(False)
        await self._set_m9a_silent_mode()

        self.auto_update_fix_enabled = self.script_config.get("Run", "IfAutoUpdateAfterQueue")
        if self.auto_update_fix_enabled:
            logger.success("已开启队列结束后自动更新，将在批量任务后统一处理")
        else:
            logger.info("队列结束后自动更新未开启，跳过自动更新处理")

    async def main_task(self):

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.error(f"未通过配置检查: {self.check_result}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if not isinstance(self.script_config, M9AConfig):
            raise RuntimeError("脚本配置类型错误, 不是 M9A 脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                self.emulator_manager,
            )
            if self.auto_update_fix_enabled and self.script_info.current_index == 0:
                task.is_first_user_for_version_check = True

            await self.spawn(task)

            if self.auto_update_fix_enabled and self.script_info.current_index == 0:
                self.has_new_version = getattr(self.script_info, '_m9a_has_new_version', False)
                if not self.has_new_version:
                    logger.info("首个用户未检测到 M9A 新版本，批量任务完成后将跳过自动更新")

        if self.auto_update_fix_enabled and self.has_new_version:
            logger.info("检测到 M9A 有新版本，将启动虚拟用户执行自动更新")

            self.script_info._m9a_restart_triggered = False
            await self._set_m9a_auto_update(True)

            virtual_uid_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, "m9a-update.mas.auto")
            virtual_uid = str(virtual_uid_uuid)

            virtual_user = UserItem(
                user_id=virtual_uid,
                name="M9A自动更新",
                status="等待"
            )
            self.script_info.user_list.append(virtual_user)

            virtual_user_config_data = M9AUserConfig()
            await virtual_user_config_data.set("Info", "Name", "M9A自动更新")
            await virtual_user_config_data.set("Info", "Status", True)
            await virtual_user_config_data.set("Info", "RemainedDay", 999)
            await virtual_user_config_data.set("Notify", "Enabled", False)
            virtual_user_config = {
                virtual_uid_uuid: virtual_user_config_data
            }

            self.script_info.current_index = len(self.script_info.user_list) - 1

            virtual_task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                virtual_user_config,
                self.emulator_manager,
            )
            virtual_task.is_virtual_update_user = True

            await self.spawn(virtual_task)

            self._virtual_user_old_version = getattr(self.script_info, '_m9a_current_version', '未知')
            self._virtual_user_new_version = getattr(self.script_info, '_m9a_latest_version', '未知')

            virtual_user_item = self.script_info.user_list[-1]
            if virtual_user_item.status == "完成":
                logger.success(f"M9A 自动更新完成: v{self._virtual_user_old_version} → v{self._virtual_user_new_version}")
            else:
                logger.warning(f"虚拟用户未正常完成，状态: {virtual_user_item.status}")

    async def final_task(self):
        """运行结束后的收尾工作"""

        if self.check_result != "Pass":
            self.script_info.status = "异常"
            return self.check_result

        logger.info("M9A 主任务已结束, 开始执行后续操作")
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].unlock()
        logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if self.task_info.mode in ["AutoProxy"]:

            await self.emulator_manager.close(
                self.script_config.get("Emulator", "Index")
            )
            await Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.load(await self.user_config.toDict())

            error_user = [
                u.name for u in self.script_info.user_list if u.status == "异常"
            ]
            over_user = [
                u.name for u in self.script_info.user_list if u.status == "完成"
            ]
            wait_user = [
                u.name for u in self.script_info.user_list if u.status == "等待"
            ]

            title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
            result = {
                "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
                "script_name": self.script_info.name or "空白",
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_user),
                "uncompleted_count": len(error_user) + len(wait_user),
                "result": self.script_info.result,
            }

            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
                f"已完成用户数: {len(over_user)}, 未完成用户数: {len(error_user) + len(wait_user)}",
                10,
            )
            try:
                await push_notification("代理结果", title, result, None)
            except Exception as e:
                logger.exception(f"推送代理结果时出现异常: {e}")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"推送代理结果时出现异常: {e}"},
                )

            await self._notify_version_update_result()

        if (self.temp_path).exists():
            shutil.rmtree(self.m9a_config_path, ignore_errors=True)
            shutil.copytree(self.temp_path, self.m9a_config_path, dirs_exist_ok=True)
        shutil.rmtree(self.temp_path, ignore_errors=True)

        self.script_info.status = "完成"

    async def _notify_version_update_result(self):

        if (
            getattr(self.script_info, '_m9a_update_success', False)
            and self._virtual_user_new_version
            and self._virtual_user_old_version
        ):
            update_title = "M9A 资源版本更新"
            update_message = (
                f"M9A 资源版本已从 v{self._virtual_user_old_version} "
                f"更新至 v{self._virtual_user_new_version}"
            )
            try:
                await Notify.push_plyer(update_title, update_message, update_message, 10)
            except Exception as e:
                logger.exception(f"版本更新桌面通知发送失败: {e}")

            update_result = {
                "start_time": datetime.now().strftime("%H:%M:%S"),
                "end_time": datetime.now().strftime("%H:%M:%S"),
                "completed_count": 1,
                "uncompleted_count": 0,
                "result": update_message,
            }
            try:
                await push_notification("代理结果", update_title, update_result, None)
                logger.info(f"已发送版本更新通知: {update_message}")
            except Exception as e:
                logger.exception(f"版本更新通知发送失败: {e}")

        elif not getattr(self.script_info, '_m9a_update_success', False) and self._virtual_user_old_version:
            err_log = getattr(self.script_info, '_m9a_err_log', [])
            virtual_status = "未知错误"
            full_reason = err_log[-1] if err_log else "无"
            if getattr(self.script_info, '_m9a_timeout', False):
                virtual_status = "更新超时"
            elif err_log:
                last_err = err_log[-1]
                if "网络连接中断" in last_err:
                    virtual_status = "网络连接中断"
                elif "HTTP 请求失败" in last_err:
                    virtual_status = "HTTP 请求失败"
                elif "获取资源包下载信息失败" in last_err:
                    virtual_status = "获取资源包下载信息失败"
                elif "进程异常结束" in last_err or "进程异常退出" in last_err:
                    virtual_status = "进程异常退出"
                else:
                    virtual_status = "未知错误"

            fail_title = "M9A 资源更新失败"
            fail_message = f"M9A 资源更新失败（{virtual_status}）\n当前版本: v{self._virtual_user_old_version}"
            try:
                await Notify.push_plyer(fail_title, fail_message, fail_message, 10)
            except Exception as e:
                logger.exception(f"版本更新失败桌面通知发送失败: {e}")

            fail_result = {
                "start_time": datetime.now().strftime("%H:%M:%S"),
                "end_time": datetime.now().strftime("%H:%M:%S"),
                "completed_count": 0,
                "uncompleted_count": 1,
                "result": f"更新失败（{virtual_status}），当前版本: v{self._virtual_user_old_version}",
            }
            try:
                await push_notification("代理结果", fail_title, fail_result, None)
            except Exception as e:
                logger.exception(f"版本更新失败通知发送失败: {e}")
            logger.warning(f"M9A 自动更新失败: {virtual_status}（完整原因: {full_reason}）")

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.exception(f"M9A任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"M9A任务出现异常: {e}"},
        )
