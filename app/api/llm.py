#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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
LLM 配置 API 模块

本模块提供 LLM 配置管理和 Token 使用统计的 API 接口。
"""

from datetime import datetime
from fastapi import APIRouter, Body

from app.core.llm_config import get_llm_config_manager
from app.services.llm import get_llm_service
from app.services.token_tracker import get_token_tracker
from app.models.schema import (
    OutBase,
    LLMConfigGetOut,
    LLMConfigUpdateIn,
    LLMProviderIndexItem,
    LLMProviderConfig,
    LLMProviderConfig_Info,
    LLMProviderConfig_Data,
    LLMGlobalSettings,
    LLMProviderCreateIn,
    LLMProviderCreateOut,
    LLMProviderUpdateIn,
    LLMProviderDeleteIn,
    LLMProviderTestIn,
    LLMProviderTestOut,
    LLMUsageQueryIn,
    LLMUsageStatisticsOut,
    LLMUsageHistoryOut,
    TokenUsageRecord,
)

router = APIRouter(prefix="/api/llm", tags=["LLM 设置"])


# ==================== 配置管理接口 ====================


@router.post(
    "/config/get",
    tags=["Get"],
    summary="获取 LLM 配置",
    response_model=LLMConfigGetOut,
    status_code=200,
)
async def get_llm_config() -> LLMConfigGetOut:
    """获取 LLM 配置"""
    try:
        config_manager = await get_llm_config_manager()
        
        # 获取所有提供商
        providers = await config_manager.get_all_providers()
        
        # 构建索引和数据
        index = []
        data = {}
        for provider in providers:
            uid = provider.get("uid", "")
            index.append(LLMProviderIndexItem(uid=uid, type="LLMProviderConfig"))
            
            # 转换为 Pydantic 模型
            info_data = provider.get("Info", {})
            data_section = provider.get("Data", {})
            
            data[uid] = LLMProviderConfig(
                Info=LLMProviderConfig_Info(
                    Name=info_data.get("Name"),
                    Type=info_data.get("Type"),
                    Active=provider.get("is_active", False)
                ),
                Data=LLMProviderConfig_Data(
                    ApiKey=data_section.get("ApiKey"),
                    BaseUrl=data_section.get("BaseUrl"),
                    Model=data_section.get("Model"),
                    MaxTokens=data_section.get("MaxTokens"),
                    Temperature=data_section.get("Temperature")
                )
            )
        
        # 获取全局设置
        global_settings = await config_manager.get_global_settings()
        settings = LLMGlobalSettings(
            Enabled=global_settings.get("enabled"),
            ActiveProviderId=global_settings.get("active_provider_id"),
            Timeout=global_settings.get("timeout"),
            MaxRetries=global_settings.get("max_retries"),
            RateLimit=global_settings.get("rate_limit")
        )
        
        # 获取预设提供商
        preset_providers = config_manager.get_preset_providers()
        
        return LLMConfigGetOut(
            index=index,
            data=data,
            settings=settings,
            preset_providers=preset_providers
        )
        
    except Exception as e:
        return LLMConfigGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
            settings=LLMGlobalSettings(),
            preset_providers={}
        )


@router.post(
    "/config/update",
    tags=["Update"],
    summary="更新 LLM 全局配置",
    response_model=OutBase,
    status_code=200,
)
async def update_llm_config(config: LLMConfigUpdateIn = Body(...)) -> OutBase:
    """更新 LLM 全局配置"""
    try:
        config_manager = await get_llm_config_manager()
        
        # 转换为字典格式
        settings_data = config.settings.model_dump(exclude_unset=True)
        
        # 转换字段名（从 PascalCase 到 snake_case）
        update_data = {}
        if "Enabled" in settings_data:
            update_data["enabled"] = settings_data["Enabled"]
        if "ActiveProviderId" in settings_data:
            update_data["active_provider_id"] = settings_data["ActiveProviderId"]
        if "Timeout" in settings_data:
            update_data["timeout"] = settings_data["Timeout"]
        if "MaxRetries" in settings_data:
            update_data["max_retries"] = settings_data["MaxRetries"]
        if "RateLimit" in settings_data:
            update_data["rate_limit"] = settings_data["RateLimit"]
        
        success = await config_manager.update_global_settings(update_data)
        
        if not success:
            return OutBase(code=500, status="error", message="更新配置失败")
        
        return OutBase()
        
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


# ==================== 提供商管理接口 ====================


@router.post(
    "/provider/add",
    tags=["Add"],
    summary="添加 LLM 提供商",
    response_model=LLMProviderCreateOut,
    status_code=200,
)
async def add_provider(provider: LLMProviderCreateIn = Body(...)) -> LLMProviderCreateOut:
    """添加 LLM 提供商"""
    try:
        config_manager = await get_llm_config_manager()
        
        uid, config = await config_manager.add_provider(
            provider_type=provider.provider_type,
            api_key=provider.api_key
        )
        
        # 获取配置数据
        config_data = await config.toDict()
        info_data = config_data.get("Info", {})
        data_section = config_data.get("Data", {})
        
        return LLMProviderCreateOut(
            providerId=uid,
            data=LLMProviderConfig(
                Info=LLMProviderConfig_Info(
                    Name=info_data.get("Name"),
                    Type=info_data.get("Type"),
                    Active=info_data.get("Active", False)
                ),
                Data=LLMProviderConfig_Data(
                    ApiKey=data_section.get("ApiKey"),
                    BaseUrl=data_section.get("BaseUrl"),
                    Model=data_section.get("Model"),
                    MaxTokens=data_section.get("MaxTokens"),
                    Temperature=data_section.get("Temperature")
                )
            )
        )
        
    except Exception as e:
        return LLMProviderCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            providerId="",
            data=LLMProviderConfig()
        )


@router.post(
    "/provider/update",
    tags=["Update"],
    summary="更新 LLM 提供商配置",
    response_model=OutBase,
    status_code=200,
)
async def update_provider(provider: LLMProviderUpdateIn = Body(...)) -> OutBase:
    """更新 LLM 提供商配置"""
    try:
        config_manager = await get_llm_config_manager()
        
        # 转换 Pydantic 模型为字典
        update_data = {}
        
        if provider.data.Info is not None:
            info_dict = provider.data.Info.model_dump(exclude_unset=True)
            if info_dict:
                update_data["Info"] = info_dict
        
        if provider.data.Data is not None:
            data_dict = provider.data.Data.model_dump(exclude_unset=True)
            if data_dict:
                update_data["Data"] = data_dict
        
        success = await config_manager.update_provider(provider.providerId, update_data)
        
        if not success:
            return OutBase(code=404, status="error", message="提供商不存在或更新失败")
        
        return OutBase()
        
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/provider/delete",
    tags=["Delete"],
    summary="删除 LLM 提供商",
    response_model=OutBase,
    status_code=200,
)
async def delete_provider(provider: LLMProviderDeleteIn = Body(...)) -> OutBase:
    """删除 LLM 提供商"""
    try:
        config_manager = await get_llm_config_manager()
        
        success = await config_manager.delete_provider(provider.providerId)
        
        if not success:
            return OutBase(code=404, status="error", message="提供商不存在或删除失败")
        
        return OutBase()
        
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )


@router.post(
    "/provider/test",
    tags=["Action"],
    summary="测试 LLM 提供商连接",
    response_model=LLMProviderTestOut,
    status_code=200,
)
async def test_provider(provider: LLMProviderTestIn = Body(...)) -> LLMProviderTestOut:
    """测试 LLM 提供商连接"""
    try:
        config_manager = await get_llm_config_manager()
        llm_service = await get_llm_service()
        
        # 获取提供商配置
        provider_config = await config_manager.get_provider(provider.providerId)
        
        if provider_config is None:
            return LLMProviderTestOut(
                code=404,
                status="error",
                message="提供商不存在",
                success=False,
                response_time=0.0,
                model=""
            )
        
        # 测试连接
        result = await llm_service.test_connection(provider_config)
        
        return LLMProviderTestOut(
            success=result.get("success", False),
            message=result.get("message", ""),
            response_time=result.get("response_time", 0.0),
            model=result.get("model", "")
        )
        
    except Exception as e:
        return LLMProviderTestOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            success=False,
            response_time=0.0,
            model=""
        )


# ==================== Token 使用统计接口 ====================


@router.post(
    "/usage/statistics",
    tags=["Get"],
    summary="获取 Token 使用统计",
    response_model=LLMUsageStatisticsOut,
    status_code=200,
)
async def get_usage_statistics(query: LLMUsageQueryIn = Body(...)) -> LLMUsageStatisticsOut:
    """获取 Token 使用统计"""
    try:
        token_tracker = await get_token_tracker()
        
        # 获取当天、本周、本月统计
        daily_stats = await token_tracker.get_daily_usage()
        weekly_stats = await token_tracker.get_weekly_usage()
        monthly_stats = await token_tracker.get_monthly_usage()
        
        # 如果指定了日期范围，获取该范围的统计
        if query.start_date and query.end_date:
            try:
                start = datetime.strptime(query.start_date, "%Y-%m-%d")
                end = datetime.strptime(query.end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                range_stats = await token_tracker.get_usage_statistics(start, end)
                
                return LLMUsageStatisticsOut(
                    total_tokens=range_stats.total_tokens,
                    total_requests=range_stats.total_requests,
                    average_tokens_per_request=round(range_stats.average_tokens_per_request, 2),
                    input_tokens=range_stats.input_tokens,
                    output_tokens=range_stats.output_tokens,
                    daily=daily_stats.to_dict(),
                    weekly=weekly_stats.to_dict(),
                    monthly=monthly_stats.to_dict()
                )
            except ValueError:
                pass
        
        # 根据周期类型返回对应统计
        if query.period == "daily":
            stats = daily_stats
        elif query.period == "weekly":
            stats = weekly_stats
        elif query.period == "monthly":
            stats = monthly_stats
        else:
            # 默认返回月度统计作为主要数据
            stats = monthly_stats
        
        return LLMUsageStatisticsOut(
            total_tokens=stats.total_tokens,
            total_requests=stats.total_requests,
            average_tokens_per_request=round(stats.average_tokens_per_request, 2),
            input_tokens=stats.input_tokens,
            output_tokens=stats.output_tokens,
            daily=daily_stats.to_dict(),
            weekly=weekly_stats.to_dict(),
            monthly=monthly_stats.to_dict()
        )
        
    except Exception as e:
        return LLMUsageStatisticsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            total_tokens=0,
            total_requests=0,
            average_tokens_per_request=0.0,
            input_tokens=0,
            output_tokens=0
        )


@router.post(
    "/usage/history",
    tags=["Get"],
    summary="获取 Token 使用历史",
    response_model=LLMUsageHistoryOut,
    status_code=200,
)
async def get_usage_history(query: LLMUsageQueryIn = Body(...)) -> LLMUsageHistoryOut:
    """获取 Token 使用历史"""
    try:
        token_tracker = await get_token_tracker()
        
        # 如果指定了日期范围
        if query.start_date and query.end_date:
            try:
                start = datetime.strptime(query.start_date, "%Y-%m-%d")
                end = datetime.strptime(query.end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                stats = await token_tracker.get_usage_statistics(start, end)
                records = stats.records
            except ValueError:
                records = await token_tracker.get_all_records()
        else:
            # 默认获取所有记录
            records = await token_tracker.get_all_records()
        
        # 转换为 Pydantic 模型
        record_models = [
            TokenUsageRecord(
                id=r.id,
                timestamp=r.timestamp,
                provider_name=r.provider_name,
                model_name=r.model_name,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                total_tokens=r.total_tokens,
                task_id=r.task_id
            )
            for r in records
        ]
        
        # 按时间倒序排列
        record_models.sort(key=lambda x: x.timestamp, reverse=True)
        
        return LLMUsageHistoryOut(
            records=record_models,
            total_count=len(record_models)
        )
        
    except Exception as e:
        return LLMUsageHistoryOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            records=[],
            total_count=0
        )
