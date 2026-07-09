#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""插件 MCP 工具门面。

在 fastapi-mcp 静态整体式 MCP 之上叠加一层运行时可注册的工具注册表，
让插件通过 ``ctx.mcp.tool(...)`` 声明自定义 MCP 工具，AI 客户端可直接调用。

实现要点：
    - 不修改 fastapi-mcp 源码，在 ``FastApiMCP`` 构造完成后覆盖底层
      ``mcp.server.lowlevel.server.Server`` 的 ``ListToolsRequest`` 与
      ``CallToolRequest`` 两个 request_handler，注入分发逻辑。
    - 分发器先查插件注册表，命中则调用插件 handler；未命中则 fallback
      到原始 HTTP API 工具执行（``FastApiMCP._execute_api_tool``）。
    - 工具名加 ``{plugin_name}.{tool_name}`` 命名空间前缀避免冲突，
      命名符合 MCP 工具名正则 ``^[A-Za-z0-9._-]{1,128}$``。
    - 插件 dispose/reload 时通过 ``unregister_owner`` 同步清理，
      下一次 ``list_tools`` 请求即反映变更，无需重启。
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import mcp.types as types

logger = logging.getLogger(__name__)

# MCP 工具名正则（mcp.shared.tool_name_validation）：^[A-Za-z0-9._-]{1,128}$
# 用 "." 作命名空间分隔符，plugin_name 与 tool_name 均不能为空。
_NAMESPACE_SEP = "."


def _serialize_tool_result(result: Any) -> str:
    """将插件 handler 返回值序列化为 MCP 文本内容。"""
    try:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def _extract_http_request_info(mcp_server: Any) -> Optional[Any]:
    """从 MCP 请求上下文提取原始 HTTP 请求信息，用于转发鉴权头。

    复刻 ``fastapi_mcp.server.FastApiMCP.setup_server`` 内 ``handle_call_tool``
    的提取逻辑，保持原始 API 工具的 header 转发行为不变。
    """
    from fastapi_mcp.types import HTTPRequestInfo

    try:
        request_context = mcp_server.request_context
        if request_context is None or not hasattr(request_context, "request"):
            return None
        http_request = request_context.request
        if http_request is None or not hasattr(http_request, "method"):
            return None
        return HTTPRequestInfo(
            method=http_request.method,
            path=http_request.url.path,
            headers=dict(http_request.headers),
            cookies=http_request.cookies,
            query_params=dict(http_request.query_params),
            body=None,
        )
    except (LookupError, AttributeError) as e:
        logger.debug("无法从 MCP 上下文提取 HTTP 请求信息: %s", e)
        return None


@dataclass
class PluginMcpTool:
    """插件声明的 MCP 工具条目。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    instance_id: str
    plugin_name: str

    def to_mcp_tool(self) -> types.Tool:
        """转换为 MCP 协议 Tool 对象。"""
        return types.Tool(
            name=self.name,
            description=self.description or None,
            inputSchema=self.input_schema,
        )


class PluginMcpRegistry:
    """管理插件声明的 MCP 工具，并负责挂载分发逻辑到 FastApiMCP。

    仿照 ``app.plugins.server.PluginServerRegistry`` 的注册/注销/snapshot 模式，
    额外提供 ``attach`` 在 FastApiMCP 构造完成后覆盖底层 Server 的请求处理器。
    """

    def __init__(self) -> None:
        self._tools: Dict[str, PluginMcpTool] = {}
        self._attached: bool = False
        self._fastapi_mcp: Any = None

    # ── 命名空间 ──
    @staticmethod
    def _namespaced_name(plugin_name: str, tool_name: str) -> str:
        """拼接带命名空间的工具全名。"""
        plugin = str(plugin_name or "").strip()
        tool = str(tool_name or "").strip()
        if not plugin:
            raise ValueError("plugin_name 不能为空")
        if not tool:
            raise ValueError("tool_name 不能为空")
        return f"{plugin}{_NAMESPACE_SEP}{tool}"

    # ── 注册 / 注销 ──
    def register_tool(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        tool_name: str,
        description: str,
        handler: Callable[..., Any],
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> PluginMcpTool:
        """注册一个插件 MCP 工具。

        Args:
            instance_id (str): 插件实例 ID。
            plugin_name (str): 插件名，用于命名空间前缀。
            tool_name (str): 工具短名，拼接为 ``{plugin_name}.{tool_name}``。
            description (str): 工具描述，展示给 AI 客户端。
            handler (Callable[..., Any]): 工具处理函数，接收 arguments 字典，
                可为同步或异步，返回可 JSON 序列化的值。
            input_schema (Dict[str, Any] | None): JSON Schema 输入描述，
                为 None 时使用空对象 schema。

        Returns:
            PluginMcpTool: 已注册的工具条目。

        Raises:
            ValueError: 工具名非法或命名冲突时抛出。
        """
        full_name = self._namespaced_name(plugin_name, tool_name)
        if full_name in self._tools:
            existing = self._tools[full_name]
            if existing.instance_id != instance_id:
                raise ValueError(
                    f"MCP 工具名冲突: tool={full_name}, "
                    f"owner={instance_id}, existing={existing.instance_id}"
                )
        schema = input_schema if isinstance(input_schema, dict) else {
            "type": "object",
            "properties": {},
        }
        entry = PluginMcpTool(
            name=full_name,
            description=str(description or ""),
            input_schema=schema,
            handler=handler,
            instance_id=str(instance_id or "").strip(),
            plugin_name=str(plugin_name or "").strip(),
        )
        self._tools[full_name] = entry
        logger.debug("已注册插件 MCP 工具: %s (instance=%s)", full_name, entry.instance_id)
        return entry

    def unregister(self, name: str) -> bool:
        """按全名注销单个工具，返回是否命中。"""
        return self._tools.pop(str(name or "").strip(), None) is not None

    def unregister_owner(self, instance_id: str) -> int:
        """清理指定插件实例声明的全部 MCP 工具，返回清理数量。"""
        owner = str(instance_id or "").strip()
        if not owner:
            return 0
        victims = [name for name, entry in self._tools.items() if entry.instance_id == owner]
        for name in victims:
            self._tools.pop(name, None)
        if victims:
            logger.debug("已清理插件 MCP 工具: instance=%s, count=%d", owner, len(victims))
        return len(victims)

    # ── 查询 ──
    def list_tools(self) -> List[types.Tool]:
        """返回当前所有插件工具的 MCP Tool 对象列表。"""
        return [entry.to_mcp_tool() for entry in self._tools.values()]

    def resolve(self, name: str) -> Optional[PluginMcpTool]:
        """按全名查找工具条目。"""
        return self._tools.get(str(name or "").strip())

    def snapshot(self) -> Dict[str, Any]:
        """构建插件 MCP 工具快照，供前端和调试界面使用。"""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for entry in self._tools.values():
            grouped.setdefault(entry.instance_id, []).append({
                "name": entry.name,
                "description": entry.description,
                "plugin": entry.plugin_name,
            })
        return {"plugin_mcp_tools": grouped}

    # ── 挂载分发 ──
    def attach(self, fastapi_mcp: Any) -> None:
        """覆盖 FastApiMCP 底层 Server 的 list_tools/call_tool 处理器。

        在 ``FastApiMCP`` 构造并 ``mount_http()`` 之后调用一次。覆盖后：
            - ``ListToolsRequest`` 返回 API 工具 + 插件工具的合并列表；
            - ``CallToolRequest`` 先查插件注册表，命中调用 handler，
              未命中 fallback 到原始 ``_execute_api_tool`` HTTP 执行。

        依赖 fastapi-mcp 0.4.x 内部实现：``server``/``tools``/``operation_map``
        /``_execute_api_tool``/``_http_client`` 均为实例属性。升级 fastapi-mcp
        时需复核此方法。

        Args:
            fastapi_mcp (FastApiMCP): 已构造并挂载的 FastApiMCP 实例。
        """
        if self._attached:
            logger.warning("PluginMcpRegistry 已挂载，重复 attach 将被忽略")
            return

        mcp_server = fastapi_mcp.server
        api_tools = fastapi_mcp.tools
        operation_map = fastapi_mcp.operation_map
        execute_api_tool = fastapi_mcp._execute_api_tool
        http_client = fastapi_mcp._http_client
        registry = self

        @mcp_server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return list(api_tools) + registry.list_tools()

        @mcp_server.call_tool(validate_input=False)
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            entry = registry.resolve(name)
            if entry is not None:
                result = entry.handler(arguments or {})
                if inspect.isawaitable(result):
                    result = await result
                return [types.TextContent(type="text", text=_serialize_tool_result(result))]

            if name in operation_map:
                http_request_info = _extract_http_request_info(mcp_server)
                return await execute_api_tool(
                    client=http_client,
                    tool_name=name,
                    arguments=arguments,
                    operation_map=operation_map,
                    http_request_info=http_request_info,
                )

            raise Exception(f"Unknown tool: {name}")

        self._fastapi_mcp = fastapi_mcp
        self._attached = True
        logger.info("PluginMcpRegistry 已挂载到 FastApiMCP，插件 MCP 工具分发已启用")


class PluginMcpFacade:
    """插件上下文中的 mcp 门面，仿照 ``PluginServerFacade`` 风格。"""

    def __init__(
        self,
        *,
        registry: PluginMcpRegistry,
        plugin_name: str,
        instance_id: str,
    ) -> None:
        self._registry = registry
        self._plugin_name = plugin_name
        self._instance_id = instance_id

    def tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        *,
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> PluginMcpTool:
        """声明一个插件 MCP 工具。

        Args:
            name (str): 工具短名，最终对外暴露为 ``{plugin_name}.{name}``。
            description (str): 工具描述，展示给 AI 客户端。
            handler (Callable[..., Any]): 工具处理函数，接收 arguments 字典，
                可为同步或异步，返回可 JSON 序列化的值。
            input_schema (Dict[str, Any] | None): JSON Schema 输入描述。

        Returns:
            PluginMcpTool: 已注册的工具条目。
        """
        return self._registry.register_tool(
            instance_id=self._instance_id,
            plugin_name=self._plugin_name,
            tool_name=name,
            description=description,
            handler=handler,
            input_schema=input_schema,
        )

    def unregister(self, name: str) -> bool:
        """按短名注销当前插件声明的工具，返回是否命中。"""
        full_name = PluginMcpRegistry._namespaced_name(self._plugin_name, name)
        return self._registry.unregister(full_name)


# 模块级单例，与 app.plugins.server.plugin_server 对齐
plugin_mcp = PluginMcpRegistry()
