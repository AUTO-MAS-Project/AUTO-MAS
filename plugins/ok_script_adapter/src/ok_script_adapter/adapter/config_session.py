#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 运行期配置注入、写回与原目录恢复。"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.utils import get_logger

from ..common.provider import OkScriptRuntimeConfigOverride
from ..shell.runtime import OkConfigStore


logger = get_logger("ok-script 配置会话")


def _replace_tree(source: Path, target: Path) -> None:
    """通过同级临时目录替换一棵配置目录。"""

    if not source.is_dir():
        raise FileNotFoundError(source)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_target = target.with_name(target.name + ".tmp")
    shutil.rmtree(temporary_target, ignore_errors=True)
    shutil.copytree(source, temporary_target, dirs_exist_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    temporary_target.rename(target)


def _apply_runtime_overrides(
    config_dir: Path,
    overrides: tuple[OkScriptRuntimeConfigOverride, ...],
) -> dict[tuple[str, str], tuple[bool, object]]:
    """应用仅在 MAS 托管期间生效的配置，并记录字段原值。"""

    store = OkConfigStore(config_dir)
    available = set(store.list())
    pending: dict[str, dict[str, object]] = {}
    originals: dict[tuple[str, str], tuple[bool, object]] = {}

    for override in overrides:
        if override.file_name not in available:
            logger.warning(
                f"运行期配置覆盖目标不存在，保留兼容兜底: {override.file_name}"
            )
            continue
        if override.file_name not in pending:
            pending[override.file_name] = store.read(override.file_name)

        data = pending[override.file_name]
        state_key = (override.file_name, override.key)
        originals[state_key] = (override.key in data, data.get(override.key))
        data[override.key] = override.value

    for file_name, data in pending.items():
        store.write(file_name, data, merge=False)
    return originals


def _restore_runtime_overrides(
    config_dir: Path,
    originals: dict[tuple[str, str], tuple[bool, object]],
) -> None:
    """写回前恢复运行期字段，同时保留脚本对其它字段的修改。"""

    store = OkConfigStore(config_dir)
    pending: dict[str, dict[str, object]] = {}
    for (file_name, key), (existed, value) in originals.items():
        if file_name not in pending:
            pending[file_name] = store.read(file_name)
        if existed:
            pending[file_name][key] = value
        else:
            pending[file_name].pop(key, None)

    for file_name, data in pending.items():
        store.write(file_name, data, merge=False)


class OkScriptConfigSession:
    """管理一次用户运行中的配置目录交换状态。"""

    def __init__(
        self,
        *,
        mas_config_dir: Path,
        project_config_dir: Path,
        backup_dir: Path,
        runtime_overrides: tuple[OkScriptRuntimeConfigOverride, ...] = (),
    ) -> None:
        self.mas_config_dir = mas_config_dir
        self.project_config_dir = project_config_dir
        self.backup_dir = backup_dir
        self.runtime_overrides = runtime_overrides
        self.had_original_config = False
        self.swap_started = False
        self.injected = False
        self.runtime_originals: dict[
            tuple[str, str], tuple[bool, object]
        ] = {}

    async def inject(self) -> None:
        """备份项目原配置，并注入当前 MAS 用户配置。"""

        if self.injected:
            return
        if not self.mas_config_dir.is_dir():
            raise FileNotFoundError(self.mas_config_dir)

        await self._backup_original()
        await asyncio.to_thread(
            _replace_tree,
            self.mas_config_dir,
            self.project_config_dir,
        )
        self.runtime_originals = await asyncio.to_thread(
            _apply_runtime_overrides,
            self.project_config_dir,
            self.runtime_overrides,
        )
        self.injected = True

    async def write_back(self) -> None:
        """移除运行期字段覆盖，并把项目配置写回 MAS 用户目录。"""

        if not self.injected:
            return
        await asyncio.to_thread(
            _restore_runtime_overrides,
            self.project_config_dir,
            self.runtime_originals,
        )
        await asyncio.to_thread(
            _replace_tree,
            self.project_config_dir,
            self.mas_config_dir,
        )
        self.runtime_originals = {}

    async def restore(self) -> None:
        """恢复任务前项目配置；重复调用保持幂等。"""

        if not self.swap_started:
            return

        try:
            if self.had_original_config:
                await asyncio.to_thread(
                    _replace_tree,
                    self.backup_dir,
                    self.project_config_dir,
                )
            else:
                await asyncio.to_thread(
                    shutil.rmtree,
                    self.project_config_dir,
                    ignore_errors=True,
                )
        finally:
            try:
                await asyncio.to_thread(
                    shutil.rmtree,
                    self.backup_dir,
                    ignore_errors=True,
                )
            finally:
                self.had_original_config = False
                self.swap_started = False
                self.injected = False
                self.runtime_originals = {}

    async def _backup_original(self) -> None:
        await asyncio.to_thread(
            shutil.rmtree,
            self.backup_dir,
            ignore_errors=True,
        )
        self.had_original_config = self.project_config_dir.is_dir()
        if self.had_original_config:
            await asyncio.to_thread(
                shutil.copytree,
                self.project_config_dir,
                self.backup_dir,
            )
        self.swap_started = True
