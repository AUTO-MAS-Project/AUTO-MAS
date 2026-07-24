#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""WebSocket 远程命令的显式契约注册表。

第三方 WS 连接（例如 Koishi）只能调用这里明确注册的端点。每个有参命令
必须声明 Pydantic 参数模型；执行期不再反射 FastAPI 包装器或函数签名。
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

from app.utils.logger import get_logger

logger = get_logger("WS命令")

WSCommandHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class WSCommandRegistration:
    endpoint: str
    params_model: Optional[Type[BaseModel]]
    func: WSCommandHandler


_ws_command_registry: Dict[str, WSCommandRegistration] = {}


def ws_command(endpoint: str, params: Optional[Type[BaseModel]] = None):
    """注册一个远程命令及其显式参数模型。

    ``params=None`` 表示命令不接收参数；有参命令必须写成
    ``@ws_command("queue.get", params=QueueGetIn)``。
    """

    normalized_endpoint = str(endpoint or "").strip()
    if not normalized_endpoint:
        raise ValueError("WebSocket 命令 endpoint 不能为空")
    if params is not None and not (
        isinstance(params, type) and issubclass(params, BaseModel)
    ):
        raise TypeError("WebSocket 命令 params 必须是 Pydantic BaseModel 类型")

    def decorator(func: WSCommandHandler) -> WSCommandHandler:
        _ws_command_registry[normalized_endpoint] = WSCommandRegistration(
            endpoint=normalized_endpoint,
            params_model=params,
            func=func,
        )
        logger.debug(f"已注册 WebSocket 命令: {normalized_endpoint}")
        # 保留 FastAPI 端点的原始函数与签名，不再叠加反射依赖。
        return func

    return decorator


def _normalize_result(result: Any) -> Dict[str, Any]:
    if isinstance(result, BaseModel):
        result_dict = result.model_dump()
    elif isinstance(result, dict):
        result_dict = result
    else:
        return {"success": True, "data": result, "code": 200}

    code = result_dict.get("code", 200)
    return {
        "success": code == 200,
        "data": result_dict,
        "code": code,
        "message": result_dict.get("message"),
    }


async def execute_ws_command(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按显式参数模型校验并执行命令，返回稳定的结果字典。"""

    command = _ws_command_registry.get(endpoint)
    if command is None:
        logger.warning(f"未找到命令: {endpoint}")
        return {"success": False, "message": f"未找到命令: {endpoint}", "code": 404}

    if params is not None and not isinstance(params, dict):
        return {"success": False, "message": "参数错误: params 必须是对象", "code": 400}

    try:
        if command.params_model is None:
            if params:
                return {
                    "success": False,
                    "message": f"参数错误: 命令 {endpoint} 不接受参数",
                    "code": 400,
                }
            result = await command.func()
        else:
            try:
                param_instance = command.params_model.model_validate(params or {})
            except ValidationError as exc:
                logger.warning(f"命令 {endpoint} 参数校验失败: {exc}")
                return {
                    "success": False,
                    "message": f"参数错误: {exc}",
                    "code": 400,
                }
            result = await command.func(param_instance)

        return _normalize_result(result)
    except Exception as exc:
        logger.error(
            f"执行命令 {endpoint} 失败: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return {
            "success": False,
            "message": f"执行失败: {type(exc).__name__}: {exc}",
            "code": 500,
        }


def get_ws_command_registry() -> Dict[str, WSCommandHandler]:
    """返回端点到处理函数的兼容只读副本。"""

    return {endpoint: command.func for endpoint, command in _ws_command_registry.items()}


def get_ws_command_contracts() -> Dict[str, WSCommandRegistration]:
    """返回完整显式契约的只读副本，供诊断与测试使用。"""

    return _ws_command_registry.copy()


def list_ws_commands() -> list[str]:
    return list(_ws_command_registry.keys())


def unregister_ws_command(endpoint: str) -> bool:
    return _ws_command_registry.pop(endpoint, None) is not None
