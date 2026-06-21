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

import json5

from app.utils import get_logger

logger = get_logger("M9A 任务加载器")


class M9ATaskLoader:
    """M9A 任务加载器"""

    def __init__(self, m9a_root_path: Path):
        self.root_path = m9a_root_path
        self.tasks_dir = m9a_root_path / "resource/tasks"
        self._task_cache: dict[str, dict] = {}
        self._raw_data_cache: dict[str, dict] = {}
        self._load_all_tasks()

    def _load_all_tasks(self):
        """加载所有任务定义（包括 standalone 任务）"""
        if self._load_interface_tasks():
            return

        if not self.tasks_dir.exists():
            logger.error(f"任务目录不存在：{self.tasks_dir}")
            return

        for json_file in self.tasks_dir.glob("*.json"):
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

    def _load_interface_tasks(self) -> bool:
        """优先从新版 M9A interface.json 读取任务定义。"""
        interface_path = next(
            (
                base_dir / file_name
                for base_dir in (self.root_path, self.root_path / "resource")
                for file_name in ("interface.json", "interface.jsonc")
                if (base_dir / file_name).is_file()
            ),
            None,
        )
        if interface_path is None:
            return False

        def resolve_path(base_dir: Path, raw_path: str) -> Path:
            relative_path = raw_path.strip().replace("\\", "/")
            if not relative_path or Path(relative_path).is_absolute() or ".." in relative_path.split("/"):
                raise ValueError(f"路径不允许使用绝对路径或包含 ..：{raw_path}")
            return (base_dir / relative_path).resolve()

        def read_interface(path: Path, stack: list[Path]) -> tuple[list, dict]:
            resolved_path = path.resolve()
            if resolved_path in stack:
                raise ValueError(f"检测到 interface 循环导入：{resolved_path}")

            data = json5.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"interface 必须是 JSON 对象：{path}")

            tasks = data.get("task", [])
            options = data.get("option", {})
            tasks = tasks if isinstance(tasks, list) else []
            options = options if isinstance(options, dict) else {}

            for option_data in options.values():
                if not isinstance(option_data, dict) or option_data.get("type") != "scan_select":
                    continue

                scan_dir = option_data.get("scan_dir")
                scan_filter = option_data.get("scan_filter")
                if not isinstance(scan_dir, str) or not isinstance(scan_filter, str):
                    option_data["cases"] = []
                    continue

                scan_filter = scan_filter.strip().replace("\\", "/")
                if not scan_filter or Path(scan_filter).is_absolute() or ".." in scan_filter.split("/"):
                    raise ValueError(f"路径不允许使用绝对路径或包含 ..：{scan_filter}")
                scan_path = resolve_path(path.parent, scan_dir)
                option_data["cases"] = [
                    {"name": file.relative_to(scan_path).as_posix(), "label": file.name}
                    for file in sorted(scan_path.glob(scan_filter))
                    if file.is_file()
                ]

            for import_path in data.get("import", []) or []:
                if not isinstance(import_path, str) or not import_path.strip():
                    continue

                child_tasks, child_options = read_interface(resolve_path(path.parent, import_path), [*stack, resolved_path])
                tasks.extend(child_tasks)
                options.update(child_options)

            return tasks, options

        try:
            tasks, options = read_interface(interface_path, [])
        except Exception as e:
            logger.warning(f"读取 M9A interface 失败，回退旧任务目录：{e}")
            return False

        for task in tasks:
            if not isinstance(task, dict):
                continue
            name = task.get("name")
            if not isinstance(name, str) or not name or not task.get("entry"):
                continue

            self._task_cache[name] = task
            self._raw_data_cache[name] = {"option": options}
            logger.debug(f"加载 interface 任务：{name}")

        if not self._task_cache:
            return False

        logger.success(f"M9A interface 任务加载完成，共 {len(self._task_cache)} 个任务")
        return True

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
                "label": t.get("label"),
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
