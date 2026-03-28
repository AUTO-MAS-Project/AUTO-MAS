#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
import asyncio
import subprocess
import sys
from typing import Any, Dict
import uuid

from app.utils import get_logger

from .event_bus import EventBus
from .config_store import PluginConfigStore
from .loader import PluginLoader


logger = get_logger("插件管理器")


class _PluginManager:
    """协调插件的生命周期并为 MAS 核心提供事件 API。"""

    def __init__(self) -> None:
        self.started = False
        self.events = EventBus()
        self.config_store = PluginConfigStore()
        self.plugins_dir = Path.cwd() / "plugins"
        self.runtime: Dict[str, Any] = {
            "list_scripts": self._list_scripts,
            "get_script_log": self._get_script_log,
        }
        self.loader = PluginLoader(
            events=self.events,
            runtime=self.runtime,
            plugins_dir=self.plugins_dir,
        )

    def _discover_plugins(self) -> Dict[str, Any]:
        """发现插件（兼容本地目录与 PyPI Entry Point）。"""
        return self.loader.discover()

    async def _run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        """在线程池中执行子进程命令，避免阻塞事件循环。"""
        return await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    async def _update_pypi_plugin(
        self,
        plugin_name: str,
        discovered: Dict[str, Any],
        update_source: str = "directory",
    ) -> None:
        """重载前更新 PyPI 插件包。

        当前策略：
        - 当插件来源为 pypi 时，优先从 plugins/<plugin_name> 本地目录执行安装更新。
        - 若本地目录不存在，则跳过并保留现有包版本。

        预留策略：
        - update_source="pip-index" 为未来在线源更新入口（当前仅记录日志）。
        """
        plugin_source = discovered.get(plugin_name)
        if plugin_source is None or getattr(plugin_source, "source", "") != "pypi":
            return

        if update_source == "pip-index":
            logger.info(f"预留更新策略（待实现）: plugin={plugin_name}, source=pip-index")
            return

        package_dir = self.plugins_dir / plugin_name
        pyproject_path = package_dir / "pyproject.toml"
        if not package_dir.exists() or not pyproject_path.exists():
            logger.info(
                f"PyPI 插件未找到本地包目录，跳过目录更新: plugin={plugin_name}, path={package_dir}"
            )
            return

        target_dir = self.plugins_dir / "pypi" / "site-packages"
        target_dir.mkdir(parents=True, exist_ok=True)

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            str(package_dir),
            "--target",
            str(target_dir),
            "--upgrade",
        ]
        completed = await self._run_subprocess(command)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or "未知错误"
            raise RuntimeError(f"更新 PyPI 插件失败: plugin={plugin_name}, detail={detail}")

        logger.info(f"PyPI 插件目录更新完成: plugin={plugin_name}, path={package_dir}")

    async def _update_all_pypi_plugins(self, discovered: Dict[str, Any]) -> None:
        """批量更新已发现的 PyPI 插件。"""
        for plugin_name, plugin_source in discovered.items():
            if getattr(plugin_source, "source", "") != "pypi":
                continue
            await self._update_pypi_plugin(plugin_name, discovered)

    def _list_scripts(self) -> list[Dict[str, Any]]:
        try:
            from app.core import Config
            scripts = []
            for script_id, script in Config.ScriptConfig.items():
                scripts.append(
                    {
                        "id": str(script_id),
                        "name": script.get("Info", "Name"),
                        "type": type(script).__name__,
                    }
                )
            return scripts
        except Exception as e:
            logger.warning(f"获取脚本列表失败: {e}")
            return []

    def _get_script_log(self, script_id: str, limit: int = 200) -> str:
        try:
            from app.core import Config

            uid = uuid.UUID(script_id)
            script = Config.ScriptConfig.get(uid)
            if script is None:
                return ""

            log_value = getattr(script, "log", None)
            if isinstance(log_value, str):
                if limit <= 0:
                    return log_value
                lines = log_value.splitlines()
                return "\n".join(lines[-limit:])
            return ""
        except Exception as e:
            logger.warning(f"获取脚本日志失败: script_id={script_id}, error={e}")
            return ""

    async def start(self) -> None:
        """
        启动插件系统并按配置加载实例。

        Returns:
            None: 无返回值。
        """
        if self.started:
            logger.warning("插件系统已启动，忽略重复启动")
            return

        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        await self.loader.load_instances(instances)
        await self._repair_invalid_instances_after_start(discovered)
        self.started = True
        logger.info("插件系统启动完成")

    async def _repair_invalid_instances_after_start(self, discovered: Dict[str, Any]) -> None:
        """启动后修复失效插件实例配置。"""
        failed = dict(getattr(self.loader, "startup_failed_instances", {}) or {})
        if not failed:
            return

        missing_ids = set(getattr(self.loader, "startup_missing_instances", set()) or set())

        try:
            root = await self.config_store.get_root(
                self.plugins_dir,
                discovered,
                auto_create_missing=False,
            )
        except Exception as e:
            logger.error(f"读取插件配置失败，跳过失效实例修复: {type(e).__name__}: {e}")
            return

        instances = root.get("instances", [])
        if not isinstance(instances, list):
            return

        changed = False
        removed_ids: list[str] = []
        disabled_ids: list[str] = []
        new_instances = []

        for item in instances:
            if not isinstance(item, dict):
                new_instances.append(item)
                continue

            instance_id = str(item.get("id") or "")
            if not instance_id:
                new_instances.append(item)
                continue

            if instance_id in missing_ids:
                removed_ids.append(instance_id)
                changed = True
                continue

            if instance_id in failed and bool(item.get("enabled", False)):
                item["enabled"] = False
                disabled_ids.append(instance_id)
                changed = True

            new_instances.append(item)

        if not changed:
            return

        root["instances"] = new_instances
        try:
            await self.config_store.save_root(self.plugins_dir, root)
        except Exception as e:
            logger.error(f"保存插件配置失败，失效实例修复未落盘: {type(e).__name__}: {e}")
            return

        if removed_ids:
            logger.warning(f"已删除未发现插件的实例配置: {', '.join(removed_ids)}")
        if disabled_ids:
            logger.warning(f"已自动禁用启动失败的插件实例: {', '.join(disabled_ids)}")

    async def stop(self) -> None:
        """
        停止插件系统并卸载全部实例。

        Returns:
            None: 无返回值。
        """
        if not self.started:
            return

        await self.loader.unload_all()
        self.events.clear()
        self.started = False
        logger.info("插件系统已关闭")

    def on(self, event: str, handler, **kwargs: Any) -> str:
        """
        注册插件系统事件监听器。

        Args:
            event (str): 事件名。
            handler: 事件处理函数。
            **kwargs (Any): 附加注册参数（priority、scope、once、error_policy 等）。

        Returns:
            str: 注册后的监听器 ID。
        """
        return self.events.on(event, handler, **kwargs)

    def off(self, event: str, handler=None, *, listener_id: str | None = None) -> None:
        """
        移除插件系统事件监听器。

        Args:
            event (str): 事件名。
            handler: 需要移除的事件处理函数。
            listener_id (str | None): 监听器 ID。

        Returns:
            None: 无返回值。
        """
        self.events.off(event, handler, listener_id=listener_id)

    async def emit_async(self, event: str, payload: Any = None, **kwargs: Any) -> None:
        """
        以异步方式向插件系统广播事件。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷，默认为 None。
            **kwargs (Any): 透传给事件总线的附加参数。

        Returns:
            None: 无返回值。
        """
        await self.events.emit(event, payload, **kwargs)

    def emit(self, event: str, payload: Any = None, **kwargs: Any) -> None:
        """
        同步桥接方式广播事件。

        该方法用于过渡期兼容：
        - 若存在运行中的事件循环，则创建后台任务异步发送。
        - 若不存在运行中的事件循环，则直接 `asyncio.run` 完成发送。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷，默认为 None。
            **kwargs (Any): 透传给事件总线的附加参数。

        Returns:
            None: 无返回值。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.emit_async(event, payload, **kwargs))
            return

        loop.create_task(self.emit_async(event, payload, **kwargs))

    def list_plugins(self) -> Dict[str, str]:
        """
        列出当前已加载插件实例及其状态。

        Returns:
            Dict[str, str]: 键为实例 ID，值为实例状态。
        """
        return {
            instance_id: record.status
            for instance_id, record in self.loader.records.items()
        }

    async def reload(self) -> None:
        """
        重载插件系统并重新加载所有可用实例。

        Returns:
            None: 无返回值。

        Raises:
            RuntimeError: 更新某个 PyPI 插件包失败时抛出（pip 安装命令返回非 0）。
            ValueError: 重启过程中读取或校验插件实例配置失败时抛出。
        """
        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        await self._update_all_pypi_plugins(discovered)
        if self.started:
            await self.stop()
        await self.start()

    async def reload_instance(self, instance_id: str) -> None:
        """
        重载指定插件实例。

        Args:
            instance_id (str): 目标实例 ID。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 在以下场景抛出：
                1) 未找到目标实例；
                2) 实例配置读取后校验失败。
            RuntimeError: 目标实例对应 PyPI 插件更新失败时抛出。
        """
        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        target = next((item for item in instances if item.id == instance_id), None)
        if target is None:
            raise ValueError(f"未找到插件实例: {instance_id}")

        await self._update_pypi_plugin(target.plugin, discovered)

        if target.enabled:
            await self.loader.reload_instance(
                instance_id=target.id,
                plugin_name=target.plugin,
                instance_name=target.name,
                config=target.config,
                reason="manager.reload_instance",
            )
            return

        await self.loader.unload_instance(instance_id)

    async def reload_plugin(self, plugin_name: str) -> None:
        """
        重载指定插件的全部实例。

        Args:
            plugin_name (str): 插件名。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 在以下场景抛出：
                1) 未找到该插件对应实例；
                2) 插件实例配置读取后校验失败。
            RuntimeError: 目标 PyPI 插件更新失败时抛出。
        """
        discovered = self._discover_plugins()
        self.loader.discovered_plugins = discovered
        await self._update_pypi_plugin(plugin_name, discovered)
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        matched = [item for item in instances if item.plugin == plugin_name]
        if not matched:
            raise ValueError(f"未找到插件实例: {plugin_name}")

        for item in matched:
            if not item.enabled:
                await self.loader.unload_instance(item.id)
                continue
            await self.loader.reload_instance(
                instance_id=item.id,
                plugin_name=item.plugin,
                instance_name=item.name,
                config=item.config,
                reason="manager.reload_plugin",
            )


PluginManager = _PluginManager()
