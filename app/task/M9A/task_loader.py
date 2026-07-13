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


import json
from pathlib import Path

from app.utils import get_logger

logger = get_logger("M9A 任务加载器")


class M9ATaskLoader:
    """M9A 任务加载器"""

    def __init__(self, m9a_root_path: Path):
        self.root_path = m9a_root_path
        self.tasks_dir = self._resolve_tasks_dir()
        self._task_cache: dict[str, dict] = {}
        self._raw_data_cache: dict[str, dict] = {}
        self._load_all_tasks()

    def _resolve_tasks_dir(self) -> Path:
        """兼容新版和旧版 M9A 的任务目录结构。"""
        candidates = (
            self.root_path / "tasks",
            self.root_path / "resource/tasks",
        )

        for tasks_dir in candidates:
            if tasks_dir.is_dir() and any(tasks_dir.glob("*.json")):
                return tasks_dir

        # 保留确定的路径用于错误日志；新版路径优先。
        return next((path for path in candidates if path.is_dir()), candidates[0])

    def _load_all_tasks(self):
        """加载所有任务定义（包括 standalone 任务）"""
        # M9A 热更新可能会在进程运行期间迁移任务目录，因此每次加载都重新探测。
        self.tasks_dir = self._resolve_tasks_dir()
        json_files = list(self.tasks_dir.glob("*.json"))
        if not json_files:
            logger.error(
                "M9A 任务定义不存在，已检查："
                f"{self.root_path / 'tasks'}、{self.root_path / 'resource/tasks'}"
            )
            return

        for json_file in json_files:
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))

                # 缓存原始数据（包含 option 定义对象）
                if "option" in data:
                    for task in data.get("task", []):
                        name = task.get("name")
                        if name:
                            self._raw_data_cache[name] = data

                # 加载所有任务定义（包括 standalone）
                for task in data.get("task", []):
                    name = task.get("name")
                    if not name:
                        continue
                    
                    # ✅ 不再过滤 standalone 任务，加载所有任务
                    self._task_cache[name] = task
                    logger.debug(f"加载任务：{name}")
                    
            except Exception as e:
                logger.warning(f"读取 {json_file.name} 失败：{e}")

        logger.success(f"M9A 任务加载完成，共 {len(self._task_cache)} 个任务")

        self._add_missing_option_fallback()

    def _add_missing_option_fallback(self):
        """
        添加缺失选项的动态兜底逻辑：
        如果某个任务的 task.option 数组里列了某个选项，但该文件的 option 字典里没有定义，
        则从其他有该选项定义的任务中复制过来，包括递归处理子选项
        """
        global_option_defs = {}
        
        for json_file in self.tasks_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if "option" in data:
                    for opt_name, opt_def in data["option"].items():
                        if opt_name not in global_option_defs:
                            global_option_defs[opt_name] = opt_def
            except Exception:
                continue
        
        if not global_option_defs:
            logger.debug("未找到任何选项定义，跳过兜底逻辑")
            return
        
        def collect_required_options(opt_name: str, collected: set):
            if opt_name in collected:
                return
            if opt_name not in global_option_defs:
                return
            
            collected.add(opt_name)
            opt_def = global_option_defs[opt_name]
            
            if "cases" in opt_def:
                for case in opt_def["cases"]:
                    if "option" in case:
                        for sub_opt_name in case["option"]:
                            collect_required_options(sub_opt_name, collected)
        
        for task_name, raw_data in self._raw_data_cache.items():
            if "option" not in raw_data or "task" not in raw_data:
                continue
            
            task_def_list = raw_data["task"]
            referenced_options = set()
            
            for t in task_def_list:
                if "option" in t:
                    for opt_name in t["option"]:
                        collect_required_options(opt_name, referenced_options)
            
            missing_options = []
            for opt_name in referenced_options:
                if opt_name not in raw_data["option"] and opt_name in global_option_defs:
                    missing_options.append(opt_name)
            
            if missing_options:
                logger.info(f"为任务 '{task_name}' 添加缺失选项配置: {missing_options}")
                
                for opt_name in missing_options:
                    raw_data["option"][opt_name] = global_option_defs[opt_name].copy()

    def get_available_tasks(self) -> list[dict]:
        """
        获取可用任务列表（排除 standalone 任务）

        用于前端展示，standalone 任务不会出现在可选列表中
        
        Returns:
            任务列表，每个任务包含 name, entry, group, description
        """
        return [
            {
                "name": t.get("name"),
                "entry": t.get("entry"),
                "group": t.get("group", []),
                "description": t.get("description", ""),
            }
            for t in self._task_cache.values()
            if "standalone" not in t.get("group", [])
        ]

    def get_full_definition(self, task_name: str) -> dict | None:
        """
        获取任务的完整定义（包含原始 option 定义对象）

        Args:
            task_name: 任务名称
            
        Returns:
            任务定义字典，包含额外的 _option_definitions 字段
        """
        task_def = self._task_cache.get(task_name)
        if not task_def:
            return None

        result = dict(task_def)

        # 添加 option 定义对象（用于构建 TaskItems）
        if task_name in self._raw_data_cache:
            raw_data = self._raw_data_cache[task_name]
            if "option" in raw_data:
                result["_option_definitions"] = raw_data["option"]

        return result

    def get_task_definition(self, task_name: str) -> dict | None:
        """
        获取单个任务的定义（兼容旧接口）

        Args:
            task_name: 任务名称
            
        Returns:
            任务定义字典，如果不存在返回 None
        """
        return self._task_cache.get(task_name)

    def get_all_task_names(self) -> list[str]:
        """
        获取所有任务名称列表（包括 standalone）
        
        Returns:
            任务名称列表
        """
        return list(self._task_cache.keys())

    def get_all_tasks_with_entry(self) -> list[dict]:
        """
        获取所有任务及其 entry（用于构建 CurrentTasks）
        
        Returns:
            任务列表，每个任务包含 name 和 entry
        """
        return [
            {
                "name": name,
                "entry": task.get("entry", name)
            }
            for name, task in self._task_cache.items()
        ]

    def reload(self):
        """重新加载所有任务（用于热更新）"""
        self._task_cache.clear()
        self._raw_data_cache.clear()
        self._load_all_tasks()
