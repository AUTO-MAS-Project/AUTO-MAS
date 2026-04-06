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
import logging
from pathlib import Path

from app.utils import get_logger

logger = get_logger("M9A 任务加载器")


class M9ATaskLoader:
    """M9A 任务加载器"""

    def __init__(self, m9a_root_path: Path):
        self.root_path = m9a_root_path
        self.tasks_dir = m9a_root_path / "resource/tasks"
        self._task_cache: dict[str, dict] = {}
        self._load_all_tasks()

    def _load_all_tasks(self):
        """加载所有任务定义（排除 standalone 任务）"""
        if not self.tasks_dir.exists():
            logger.error(f"任务目录不存在: {self.tasks_dir}")
            return

        skipped_count = 0
        for json_file in self.tasks_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                for task in data.get("task", []):
                    name = task.get("name")
                    if not name:
                        continue
                    
                    # 过滤掉 standalone 任务（需要单独运行的任务）
                    task_group = task.get("group", [])
                    if "standalone" in task_group:
                        skipped_count += 1
                        logger.debug(f"跳过 standalone 任务: {name}")
                        continue
                    
                    self._task_cache[name] = task
                    logger.debug(f"加载任务: {name}")
            except Exception as e:
                logger.warning(f"读取 {json_file.name} 失败: {e}")

        logger.success(
            f"M9A 任务加载完成，共 {len(self._task_cache)} 个任务"
            + (f"，已跳过 {skipped_count 个 standalone 任务" if skipped_count > 0 else "")
        )

    def get_available_tasks(self) -> list[dict]:
        """
        获取所有可用任务列表
        
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
        ]

    def get_task_definition(self, task_name: str) -> dict | None:
        """
        获取单个任务的完整定义
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务完整定义字典，如果不存在返回 None
        """
        return self._task_cache.get(task_name)

    def get_task_names(self) -> list[str]:
        """
        获取所有任务名称列表
        
        Returns:
            任务名称列表
        """
        return list(self._task_cache.keys())

    def reload(self):
        """重新加载所有任务（用于热更新）"""
        self._task_cache.clear()
        self._load_all_tasks()