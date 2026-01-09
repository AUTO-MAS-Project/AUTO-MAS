#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""
WebSocket 命令装饰器系统

提供 @ws_command 装饰器，用于将 POST API 适配到 WebSocket 环境
"""

import inspect
from typing import Callable, Dict, Any, Optional
from functools import wraps
from pydantic import BaseModel

from app.utils.logger import get_logger

logger = get_logger("WS命令")


# 全局命令注册表
_ws_command_registry: Dict[str, Callable] = {}


def ws_command(endpoint: str):
    """
    WebSocket 命令装饰器
    
    将一个函数注册为 WebSocket 命令，使其可以通过 WebSocket 调用
    
    用法:
        @ws_command("ws.clone")
        @router.post("/clone")
        async def clone_task(params: TaskCloneIn):
            # 你的逻辑
            return result
    
    WebSocket 调用:
        {
            "id": "server",
            "type": "command",
            "data": {
                "endpoint": "ws.clone",
                "params": {...}  # 可选，传递给函数的参数
            }
        }
    
    Args:
        endpoint: 命令的唯一标识符，如 "ws.clone", "core.shutdown"
    """
    def decorator(func: Callable):
        # 注册到全局命令表
        _ws_command_registry[endpoint] = func
        logger.debug(f"已注册 WebSocket 命令: {endpoint}")
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 保持原函数功能不变
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


async def execute_ws_command(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    执行 WebSocket 命令
    
    Args:
        endpoint: 命令标识符
        params: 命令参数（可选）
    
    Returns:
        执行结果字典，格式为:
        {
            "success": True/False,
            "data": {...} 或 None,
            "message": "..." 或 None,
            "code": 200/500/...
        }
    """
    # 检查命令是否存在
    if endpoint not in _ws_command_registry:
        logger.warning(f"未找到命令: {endpoint}")
        return {
            "success": False,
            "message": f"未找到命令: {endpoint}",
            "code": 404
        }
    
    func = _ws_command_registry[endpoint]
    
    try:
        # 获取函数签名
        sig = inspect.signature(func)
        parameters = sig.parameters
        
        # 准备函数参数
        if not parameters:
            # 无参数函数
            result = await func()
        else:
            # 检查第一个参数是否是 Pydantic Model
            first_param = list(parameters.values())[0]
            param_type = first_param.annotation
            
            if param_type != inspect.Parameter.empty and isinstance(param_type, type) and issubclass(param_type, BaseModel):
                # 参数是 Pydantic Model，使用 params 构建（params 为空时使用空字典）
                try:
                    param_instance = param_type(**(params or {}))
                    result = await func(param_instance)
                except Exception as e:
                    logger.error(f"构建参数模型失败: {type(e).__name__}: {e}")
                    return {
                        "success": False,
                        "message": f"参数错误: {str(e)}",
                        "code": 400
                    }
            elif params:
                # 普通参数，直接传递
                result = await func(**params)
            else:
                # 没有 params 且不是 Pydantic Model，尝试无参调用
                result = await func()
        
        # 处理返回结果
        if isinstance(result, BaseModel):
            result_dict = result.model_dump()
            return {
                "success": result_dict.get("code", 200) == 200,
                "data": result_dict,
                "code": result_dict.get("code", 200),
                "message": result_dict.get("message")
            }
        elif isinstance(result, dict):
            return {
                "success": result.get("code", 200) == 200,
                "data": result,
                "code": result.get("code", 200),
                "message": result.get("message")
            }
        else:
            return {
                "success": True,
                "data": result,
                "code": 200
            }
    
    except Exception as e:
        logger.error(f"执行命令 {endpoint} 失败: {type(e).__name__}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"执行失败: {type(e).__name__}: {str(e)}",
            "code": 500
        }


def get_ws_command_registry() -> Dict[str, Callable]:
    """获取所有已注册的 WebSocket 命令"""
    return _ws_command_registry.copy()


def list_ws_commands() -> list[str]:
    """列出所有已注册的命令名称"""
    return list(_ws_command_registry.keys())


def unregister_ws_command(endpoint: str) -> bool:
    """
    取消注册 WebSocket 命令
    
    Args:
        endpoint: 命令标识符
    
    Returns:
        是否成功取消注册
    """
    if endpoint in _ws_command_registry:
        del _ws_command_registry[endpoint]
        logger.info(f"已取消注册命令: {endpoint}")
        return True
    return False
