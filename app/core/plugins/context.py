#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
from copy import deepcopy
from typing import Any, Dict, Callable, Optional, Iterator

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
        self.config = PluginConfigProxy(config)
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

class PluginConfigProxy(dict):
    """插件配置代理，兼容字典访问并提供 set/update/reset 语义。"""

    def __init__(self, initial: Dict[str, Any] | None = None) -> None:
        data = deepcopy(initial) if isinstance(initial, dict) else {}
        super().__init__(data)
        self._source_config: Dict[str, Any] = deepcopy(data)

    def set(self, key: str, value: Any) -> None:
        """
        设置单个配置项。

        Args:
            key (str): 配置键。
            value (Any): 配置值。

        Returns:
            None: 无返回值。

        Raises:
            TypeError: `key` 不是字符串时抛出。
            ValueError: `key` 为空字符串时抛出。
        """
        if not isinstance(key, str):
            raise TypeError("配置键必须是字符串")
        if not key.strip():
            raise ValueError("配置键不能为空字符串")
        self[key] = value

    def update(self, values: Dict[str, Any] | None = None, **kwargs: Any) -> None:
        """
        批量更新配置项。

        Args:
            values (Dict[str, Any] | None): 待合并配置字典，可为 None。
            **kwargs (Any): 额外键值对参数。

        Returns:
            None: 无返回值。

        Raises:
            TypeError: `values` 非字典时抛出。
        """
        if values is not None and not isinstance(values, dict):
            raise TypeError("update(values) 的 values 必须是字典或 None")

        payload: Dict[str, Any] = {}
        if isinstance(values, dict):
            payload.update(values)
        if kwargs:
            payload.update(kwargs)

        for key, value in payload.items():
            self.set(key, value)

    def reset(self, values: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        删除源配置并以新配置重建当前配置。

        Args:
            values (Dict[str, Any] | None): 新配置对象；为 None 时重置为空字典。

        Returns:
            Dict[str, Any]: 重置后的配置快照。

        Raises:
            TypeError: `values` 非字典且非 None 时抛出。
        """
        if values is not None and not isinstance(values, dict):
            raise TypeError("reset(values) 的 values 必须是字典或 None")

        next_source = deepcopy(values) if isinstance(values, dict) else {}
        self._source_config = deepcopy(next_source)
        super().clear()
        super().update(deepcopy(next_source))
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        """返回当前配置的深拷贝字典。"""
        return deepcopy(dict(self))

    def source_dict(self) -> Dict[str, Any]:
        """返回源配置的深拷贝字典。"""
        return deepcopy(self._source_config)

    def __iter__(self) -> Iterator[Any]:
        """返回配置键的迭代器。"""
        return super().__iter__()




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

