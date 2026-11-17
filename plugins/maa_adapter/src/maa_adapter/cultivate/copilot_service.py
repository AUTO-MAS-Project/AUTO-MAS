import asyncio
from pathlib import Path
from typing import Any, Literal

from auto_mas_core.host.core import Config
from auto_mas_core.host.utils import get_logger

from maa_adapter.config.access import _maa_script_config
from maa_adapter.cultivate import source as _service_maa_copilot
from maa_adapter.cultivate.editor import (
    _cultivate_skland_ref,
    get_cultivate_skland_progression,
)

logger = get_logger("MAA")


_copilot_repository: _service_maa_copilot.CopilotRepository | None = None


def _get_copilot_repository() -> _service_maa_copilot.CopilotRepository:
    """惰性创建并复用作业缓存仓库，统一保存 MAA 作业来源数据。"""
    global _copilot_repository
    if _copilot_repository is None:
        _copilot_repository = _service_maa_copilot.CopilotRepository(
            Path.cwd() / "data/cache/maa-copilot"
        )
    return _copilot_repository


async def get_copilot_source(
    source: _service_maa_copilot.CopilotScope,
    query: str,
    *,
    action: Literal["load", "refresh", "status"],
) -> dict[str, Any]:
    """规范化作业来源参数，按加载、刷新或状态查询动作访问作业仓库并返回结果。"""
    from maa_adapter.cultivate import source as _service_maa_copilot

    query = _service_maa_copilot.normalize_source(source, query)
    repository = _get_copilot_repository()
    if action == "status":
        return repository.status(source, query)
    return await repository.load(
        source, query, refresh=action == "refresh", proxy=Config.proxy
    )


async def search_copilot_authors(keyword: str) -> list[dict[str, str]]:
    """通过宿主代理查询作业平台作者，将搜索结果转换为作者选择项。"""
    import httpx

    from maa_adapter.cultivate import source as _service_maa_copilot

    async with httpx.AsyncClient(proxy=Config.proxy or None, timeout=20) as client:
        users = await _service_maa_copilot.request_data(
            client, "/user/search", userName=keyword.strip(), page=1, size=20
        )
    return [
        {"value": str(user["id"]), "label": str(user["user_name"])} for user in users
    ]


async def analyze_copilot_training(
    script_id: str,
    user_id: str,
    *,
    source: _service_maa_copilot.CopilotScope,
    query: str,
    coverage: int,
    require_modules: bool,
    binding_key: str = "",
    ignore_level_gaps: bool = False,
) -> dict[str, Any]:
    """结合指定账号养成数据和作业需求执行练度分析，返回覆盖情况、缺口与缓存更新时间。"""
    from maa_adapter.cultivate import depot_cultivate_service
    from maa_adapter.cultivate import source as _service_maa_copilot
    from maa_adapter.cultivate.copilot import analyze_copilots

    script_config = _maa_script_config(script_id)
    binding = _cultivate_skland_ref(script_config, user_id)
    actual_binding_key = "|".join(binding) if binding else ""
    if binding_key and binding_key != actual_binding_key:
        raise ValueError("森空岛角色绑定尚未保存或已变更，请保存后重新分析")
    snapshot = _get_copilot_repository().cached(
        source, _service_maa_copilot.normalize_source(source, query)
    )
    if snapshot is None:
        raise ValueError("请先完成作业数据同步")
    skland = await get_cultivate_skland_progression(script_id, user_id, force=True)
    if skland is None:
        raise ValueError("未能读取森空岛练度，请先绑定角色或重新登录后重试")
    # 不用已过滤满练干员的编辑器选择器：分析需要完整目录与整表练度。
    catalog = await depot_cultivate_service.operator_catalog(
        config_path=Config.config_path, proxy=Config.proxy
    )
    result = await asyncio.to_thread(
        analyze_copilots,
        snapshot["assignments"],
        catalog,
        skland[0],
        coverage=coverage,
        require_modules=require_modules,
        ignore_level_gaps=ignore_level_gaps,
    )
    if binding != _cultivate_skland_ref(script_config, user_id):
        raise ValueError("分析期间森空岛角色已变更，请重新分析")
    return {
        **result,
        "bindingKey": actual_binding_key,
        "capturedAt": skland[1],
        "updatedAt": snapshot["updatedAt"],
    }
