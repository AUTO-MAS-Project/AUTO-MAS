#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from typing import Any, Dict, Callable, Optional

from .cache_store import PluginCacheManager
from .runtime_api import RuntimeAPI


class PluginContext:
    """面向插件的上下文对象，公开受控的 MAS 功能。"""

    def __init__(
        self,
        *,
        plugin_name: str,
        instance_id: str | None = None,
        config: Dict[str, Any],
        logger,
        events,
        runtime_capabilities: Optional[Dict[str, Callable[..., Any]]] = None,
    ) -> None:
        # 基础必要属性
        self.plugin_name = plugin_name
        self.instance_id = instance_id or plugin_name
        self.config = config
        self.logger = logger
        self.events = events
        
        # 解释器能力函数集合
        self.runtime_api = RuntimeAPI(
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            config=self.config,
            logger=self.logger,
            runtime_capabilities=runtime_capabilities,
        )
        self.runtime = RuntimeFacade(self.runtime_api)

        # 缓存管理器
        self.cache = PluginCacheManager(
            plugin_name=self.plugin_name,
            instance_id=self.instance_id,
            data_root=Path.cwd() / "data",
            logger=self.logger,
        )

class RuntimeFacade:
    """RuntimeAPI 语法糖包装层，提供更简洁的调用方式。"""

    def __init__(self, api: RuntimeAPI) -> None:
        self._api = api

    def info(self, force_refresh: bool = False) -> Dict[str, Any]:
        """获取运行时环境信息。"""
        return self._api.get_runtime_info(force_refresh=force_refresh)

    def set(
        self,
        *,
        python_executable: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """更新 runtime 配置选项。"""
        payload: Dict[str, Any] = {}
        if isinstance(options, dict):
            payload.update(options)
        if python_executable is not None:
            payload["python_executable"] = python_executable
        if timeout_seconds is not None:
            payload["python_timeout_seconds"] = timeout_seconds
        if kwargs:
            payload.update(kwargs)
        return self._api.set_runtime_options(payload)

    async def run(
        self,
        code: str,
        *,
        python_executable: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """执行 Python 代码片段。"""
        return await self._api.run_python_snippet(
            code,
            python_executable=python_executable,
            timeout_seconds=timeout_seconds,
        )

    def __getattr__(self, name: str) -> Any:
        """回退到 RuntimeAPI，保持历史调用方式兼容。"""
        return getattr(self._api, name)

