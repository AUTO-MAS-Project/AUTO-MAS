#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


"""WebSocket 远程命令注册表

供外部第三方 WS 连接（如 Koishi）远程调用后端能力。
命令以显式参数模型注册，不做函数签名反射。

调用消息格式:
    {
        "id": "Koishi",
        "type": "command",
        "data": {"endpoint": "queue.add", "params": {...}}
    }

响应格式（保持既有对外契约）:
    {"success": bool, "data": {...}, "message": str | None, "code": int}
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

from app.utils.logger import get_logger

logger = get_logger("WS命令")


@dataclass
class _WSCommand:
    """一条已注册命令：端点名、显式参数模型与处理函数。"""

    endpoint: str
    params_model: Optional[Type[BaseModel]]
    func: Callable[..., Any]


# 全局命令注册表
_ws_command_registry: Dict[str, _WSCommand] = {}


def ws_command(endpoint: str, params: Optional[Type[BaseModel]] = None):
    """注册 WebSocket 远程命令。

    用法:
        @ws_command("queue.get", params=QueueGetIn)
        @router.post("/get")
        async def get_queues(queue: QueueGetIn = Body(...)) -> QueueGetOut:
            ...

    Args:
        endpoint (str): 命令唯一标识，如 "queue.add"、"core.close"。
        params (Optional[Type[BaseModel]]): 命令参数模型；None 表示无参命令。
    """

    def decorator(func: Callable[..., Any]):
        _ws_command_registry[endpoint] = _WSCommand(
            endpoint=endpoint, params_model=params, func=func
        )
        logger.debug(f"已注册 WebSocket 命令: {endpoint}")
        return func

    return decorator


async def execute_ws_command(
    endpoint: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """执行 WebSocket 远程命令。

    Args:
        endpoint (str): 命令标识符。
        params (Optional[Dict[str, Any]]): 命令参数。

    Returns:
        Dict[str, Any]: 归一化结果 {"success", "data", "message", "code"}。
    """
    command = _ws_command_registry.get(endpoint)
    if command is None:
        logger.warning(f"未找到命令: {endpoint}")
        return {"success": False, "message": f"未找到命令: {endpoint}", "code": 404}

    try:
        if command.params_model is None:
            result = await command.func()
        else:
            try:
                param_instance = command.params_model(**(params or {}))
            except ValidationError as e:
                logger.error(f"命令 {endpoint} 参数校验失败: {e}")
                return {
                    "success": False,
                    "message": f"参数错误: {str(e)}",
                    "code": 400,
                }
            result = await command.func(param_instance)

        # 归一化返回结果，保持既有对外契约
        if isinstance(result, BaseModel):
            result_dict = result.model_dump()
        elif isinstance(result, dict):
            result_dict = result
        else:
            return {"success": True, "data": result, "code": 200}

        return {
            "success": result_dict.get("code", 200) == 200,
            "data": result_dict,
            "code": result_dict.get("code", 200),
            "message": result_dict.get("message"),
        }

    except Exception as e:
        logger.error(
            f"执行命令 {endpoint} 失败: {type(e).__name__}: {str(e)}", exc_info=True
        )
        return {
            "success": False,
            "message": f"执行失败: {type(e).__name__}: {str(e)}",
            "code": 500,
        }
