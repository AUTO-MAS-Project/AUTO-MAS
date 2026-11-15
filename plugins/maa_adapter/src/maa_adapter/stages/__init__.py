"""MAA 插件内的关卡服务消费入口，所有消费者使用启用实例的同一份缓存。"""

import httpx
from auto_mas_core import Config, Plugin


async def fetch_stage(headers: dict[str, str]) -> httpx.Response:
    """按配置代理与条件请求头获取 MAA 官方关卡资源。"""
    async with httpx.AsyncClient(proxy=Config.proxy, follow_redirects=True) as client:
        return await client.get(
            "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json",
            headers=headers,
            timeout=15,
        )


async def get_stage(*, refresh=False):
    """等待当前启用实例的资源检查，返回原始缓存供本插件既有活动判断使用。"""
    return await Plugin.services.require("arknights.stage_data")(refresh=refresh)


async def get_stage_info(kind, *, server="Official"):
    """按区服查询关卡选项或活动视图，复用插件实例已发布的服务。"""
    return await Plugin.services.require("arknights.stage_info")(kind, server=server)
