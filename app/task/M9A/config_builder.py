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


import json
from pathlib import Path

from app.utils import get_logger
from app.models.emulator import DeviceInfo

logger = get_logger("M9A 配置构建器")


class M9AConfigBuilder:
    """M9A 配置构建器 - 后端兜底模式"""

    def __init__(self, m9a_root_path: Path):
        self.root_path = m9a_root_path
        self.template_path = m9a_root_path / "config/instances/default.json"

    def build_config(
        self,
        queue: list[str],
        task_loader: 'M9ATaskLoader',
        emulator_info: DeviceInfo = None
    ) -> dict:
        """
        根据任务队列构建完整配置
        
        关键改动：
        1. CurrentTasks 包含所有任务（格式：任务名<|||>entry）
        2. TaskItems 包含所有任务的完整定义
        3. option 字段正确转换（从 option 名称列表 → {name, index} 格式）
        
        Args:
            queue: 用户选择的任务名称列表 ["启动游戏", "常规作战", ...]
            task_loader: 任务加载器实例
            emulator_info: 模拟器设备信息（可选）

        Returns:
            完整的 default.json 配置字典
        """
        # 1. 读取模板配置（保留所有原有字段）
        try:
            config = json.loads(self.template_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"读取 M9A 配置模板失败：{e}")
            raise

        # 2. 构建 CurrentTasks - 所有任务，格式：任务名<|||>entry（保持原始顺序，不排序）
        all_tasks = task_loader.get_all_tasks_with_entry()
        config["CurrentTasks"] = [
            f"{task['name']}<|||>{task['entry']}"
            for task in all_tasks
        ]
        logger.info(f"M9A CurrentTasks：共 {len(config['CurrentTasks'])} 个任务")

        # 3. 构建 TaskItems - 所有任务的完整定义（排除 standalone 组任务）
        config["TaskItems"] = []
        all_task_names = task_loader.get_all_task_names()
        skipped_standalone = 0

        for task_name in all_task_names:
            task_def = task_loader.get_full_definition(task_name)
            if not task_def:
                logger.warning(f"未找到任务定义：{task_name}，跳过")
                continue

            # 关键修改：过滤掉 standalone 组的任务
            if "standalone" in task_def.get("group", []):
                logger.debug(f"跳过 standalone 任务：{task_name}")
                skipped_standalone += 1
                continue

            item = self._build_task_item(task_def)
            config["TaskItems"].append(item)

        logger.info(
            f"M9A TaskItems：共 {len(config['TaskItems'])} 个任务项"
            f"（已过滤 {skipped_standalone} 个 standalone 任务）"
        )

        # 4. 对 TaskItems 排序：启动游戏(StartUp)必须在第一个，关闭游戏(Close1999)必须在最后一个
        startup_item = None
        close_item = None
        normal_items = []

        for item in config["TaskItems"]:
            if item.get("entry") == "StartUp":
                startup_item = item
            elif item.get("entry") == "Close1999":
                close_item = item
            else:
                normal_items.append(item)

        # 按正确顺序组装：启动游戏 → 普通任务 → 关闭游戏
        ordered_task_items = []
        if startup_item:
            ordered_task_items.append(startup_item)
        ordered_task_items.extend(normal_items)
        if close_item:
            ordered_task_items.append(close_item)

        config["TaskItems"] = ordered_task_items
        logger.info("M9A TaskItems 已排序：启动游戏首位，关闭游戏末位")

        # 5. 设置 ADB 地址（如果提供）
        if emulator_info and emulator_info.adb_address != "Unknown":
            config["Connect.Address"] = emulator_info.adb_address

        # 6. 设置 BeforeTask 和 AfterTask（M9A 运行所需）
        if "BeforeTask" not in config:
            config["BeforeTask"] = "StartupSoftwareAndScript"
        if "AfterTask" not in config:
            config["AfterTask"] = "CloseMFA"

        logger.info(
            f"M9A 配置构建完成：CurrentTasks={len(config['CurrentTasks'])} 个任务, "
            f"TaskItems={len(config['TaskItems'])} 个任务项"
        )
        return config

    @staticmethod
    def _build_option_list(option_names: list[str], option_definitions: dict) -> list[dict]:
        """
        将 option 名称列表转换为 TaskItems 所需的格式
        
        Args:
            option_names: 任务定义中的 option 名称列表，如 ["好梦井", "魔精收菜"]
            option_definitions: tasks/*.json 中的完整 option 定义对象
        
        Returns:
            转换后的 option 列表，如 [{"name": "好梦井", "index": 0}, ...]
            
        示例：
            输入: ["领取任务奖励"]
                  option_definitions: {"领取任务奖励": {..., "option": ["领取每日活跃奖励", "领取每周活跃奖励"]}}
            
            输出: [{"name": "领取任务奖励", "index": 0, "sub_options": [
                    {"name": "领取每日活跃奖励", "index": 0},
                    {"name": "领取每周活跃奖励", "index": 0, "sub_options": [
                        {"name": "领取每周显影罐", "index": 0}
                    ]}
                ]}]
        """
        options = []
        for opt_name in option_names:
            opt_item = {"name": opt_name, "index": 0}
            
            # 检查是否有子选项（sub_options）
            opt_def = option_definitions.get(opt_name, {})
            if isinstance(opt_def, dict) and "cases" in opt_def:
                sub_options = []
                
                # 遍历 cases 查找嵌套的 option
                for case in opt_def.get("cases", []):
                    if "option" in case:
                        # 递归处理子选项
                        sub_opts = M9AConfigBuilder._build_option_list(
                            case["option"], option_definitions
                        )
                        sub_options.extend(sub_opts)
                
                if sub_options:
                    opt_item["sub_options"] = sub_options
            
            options.append(opt_item)
        
        return options

    def _build_task_item(self, task_def: dict) -> dict:
        """
        构建单个 TaskItem
        
        参考 default - 副本.json 的结构，包含所有必要字段
        
        Args:
            task_def: 任务完整定义（包含 _option_definitions 字段）
            
        Returns:
            TaskItem 字典
        """
        item = {
            "name": task_def["name"],
            "entry": task_def["entry"],
            "default_check": True,  # 所有任务默认为 true
        }
        
        # 保留 group 和 description（如果存在）
        if "group" in task_def:
            item["group"] = task_def["group"]
        
        if "description" in task_def:
            item["description"] = task_def["description"]
        
        # 添加 controller（如果存在）
        if "controller" in task_def:
            item["controller"] = task_def["controller"]
        
        # 构建 option 列表（关键步骤）
        if "option" in task_def and "_option_definitions" in task_def:
            item["option"] = self._build_option_list(
                task_def["option"],              # 选项名称列表
                task_def["_option_definitions"]  # 完整的 option 定义对象
            )
        
        # 添加 pipeline_override（如果存在）
        if "pipeline_override" in task_def:
            item["pipeline_override"] = task_def["pipeline_override"]
        
        return item
