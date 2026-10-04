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


"""MCP 挂载、配置工具白名单与 Agent 使用提示。

复用已有 HTTP 接口，不注册新的配置路由或专项业务逻辑。
"""

import asyncio
import importlib
import os

from fastapi import FastAPI

from app.utils.logger import get_logger

logger = get_logger("MCP 服务")

# 操作与标签过滤在 fastapi-mcp 0.4.0 中取并集，因此只用操作白名单。
# 保留既有工具名；删除、清理、发布、登录和应用更新接口不自动暴露。
MCP_INCLUDED_OPERATIONS = (
    # 通用配置、MaaEnd 动态选项与试运行
    "add_script_api_scripts_add_post",
    "get_script_api_scripts_get_post",
    "update_script_api_scripts_update_post",
    "add_user_api_scripts_user_add_post",
    "get_user_api_scripts_user_get_post",
    "update_user_api_scripts_user_update_post",
    "import_script_config_file_api_scripts_config_import_post",
    "get_maafw_embedded_status_api_scripts_maafw_embedded_status_post",
    "reimport_maafw_embedded_api_scripts_maafw_embedded_reimport_post",
    "get_maaend_options_api_scripts_maaend_options_post",
    "get_stage_combox_api_info_combox_stage_post",
    "get_plan_combox_api_info_combox_plan_post",
    "get_emulator_combox_api_info_combox_emulator_post",
    "get_emulator_devices_combox_api_info_combox_emulator_devices_post",
    "add_plan_api_plan_add_post",
    "get_plan_api_plan_get_post",
    "update_plan_api_plan_update_post",
    "add_queue_api_queue_add_post",
    "get_queues_api_queue_get_post",
    "update_queue_api_queue_update_post",
    "add_item_api_queue_item_add_post",
    "get_item_api_queue_item_get_post",
    "update_item_api_queue_item_update_post",
    "reorder_item_api_queue_item_order_post",
    "add_time_set_api_queue_time_add_post",
    "get_time_set_api_queue_time_get_post",
    "update_time_set_api_queue_time_update_post",
    "reorder_time_set_api_queue_time_order_post",
    "get_task_runtime_snapshot_api_dispatch_runtime_snapshot_get",
    "get_task_status_api_dispatch_task__task_id__get",
    "add_task_api_dispatch_start_post",
    "stop_task_api_dispatch_stop_post",
    # 只读历史索引，用于核对已结束的运行；不开放接受文件路径的历史详情。
    "search_history_api_history_search_post",
    # MAA 基建选项
    "get_user_combox_infrastructure_api_scripts_user_combox_infrastructure_post",
    "get_infrast_plan_select_api_scripts_user_infrastructure_plan_select_get_post",
    "set_infrast_plan_select_api_scripts_user_infrastructure_plan_select_post",
    # MFW / M9A / MSS 项目与外壳配置
    "preview_maafw_interface_api_scripts_maafw_preview_post",
    "list_maafw_shell_instances_api_scripts_maafw_shell_instances_post",
    "import_maafw_shell_instances_api_scripts_maafw_shell_instances_import_post",
    "resolve_maafw_game_package_api_scripts_maafw_game_package_post",
    # HSR 引擎能力、托管配置和动态选项
    "get_hsr_capabilities_api_api_scripts_hsr_capabilities_get",
    "get_hsr_managed_config_api_api_scripts_hsr_managed_config_get",
    "get_hsr_stage_options_api_api_scripts_hsr_stage_options_get",
    "get_hsr_sra_profiles_api_api_scripts_hsr_sra_profiles_get",
    # BetterGI 任务来源、配置组与设置
    "get_bettergi_game_info_api_api_scripts_bettergi_game_info_get",
    "get_bettergi_strategies_api_api_scripts_bettergi_strategies_get",
    "get_bettergi_custom_groups_api_api_scripts_bettergi_one_dragon_custom_groups_get",
    "get_bettergi_one_dragon_configs_api_api_scripts_bettergi_one_dragon_configs_get",
    "get_bettergi_js_scripts_api_api_scripts_bettergi_js_scripts_get",
    "get_bettergi_key_mouse_scripts_api_api_scripts_bettergi_key_mouse_scripts_get",
    "get_bettergi_script_groups_api_api_scripts_bettergi_script_groups_get",
    "get_bettergi_script_group_detail_api_api_scripts_bettergi_script_group_detail_get",
    "get_bettergi_script_settings_ui_api_api_scripts_bettergi_script_settings_ui_get",
    "get_bettergi_script_readme_api_api_scripts_bettergi_script_readme_get",
    "get_bettergi_auto_pathing_tree_api_api_scripts_bettergi_auto_pathing_tree_get",
    "get_bettergi_one_dragon_settings_api_api_scripts_bettergi_one_dragon_settings_get",
    "save_bettergi_one_dragon_settings_api_api_scripts_bettergi_one_dragon_settings_post",
    "save_bettergi_script_group_api_api_scripts_bettergi_script_group_save_post",
    "set_one_dragon_plan_step_enabled_api_scripts_bettergi_one_dragon_plan_step_enabled_post",
    # ZZZ-OD 实例、任务和原生配置
    "get_zzzod_instances_api_api_scripts_zzzod_instances_get",
    "add_zzzod_instance_api_api_scripts_zzzod_instances_add_post",
    "rename_zzzod_instance_api_api_scripts_zzzod_instances_rename_post",
    "set_zzzod_instance_active_in_od_api_api_scripts_zzzod_instances_active_in_od_post",
    "set_zzzod_active_instance_api_api_scripts_zzzod_instances_set_active_post",
    "set_zzzod_instance_force_login_api_api_scripts_zzzod_instances_force_login_post",
    "set_zzzod_instance_run_mode_api_api_scripts_zzzod_instances_run_mode_post",
    "get_zzzod_teams_api_api_scripts_zzzod_teams_get",
    "save_zzzod_teams_api_api_scripts_zzzod_teams_save_post",
    "get_zzzod_catalog_api_api_scripts_zzzod_catalog_get",
    "get_zzzod_app_config_api_api_scripts_zzzod_app_config_get",
    "get_zzzod_task_options_api_api_scripts_zzzod_options_get",
    "save_zzzod_app_config_api_api_scripts_zzzod_app_config_save_post",
    "get_zzzod_native_config_api_api_scripts_zzzod_native_config_get",
    "save_zzzod_native_config_api_api_scripts_zzzod_native_config_save_post",
    "get_zzzod_launchers_api_api_scripts_zzzod_launchers_get",
    "import_zzzod_config_api_api_scripts_zzzod_import_post",
    # BAAH 原生配置名称
    "get_baah_config_names_api_api_scripts_baah_config_names_get",
    # 奇想盒任务目录
    "get_whimbox_task_catalog_api_api_scripts_whimbox_task_catalog_get",
    # OK-NTE 配置字段与批量编辑
    "get_oknte_configs_list_api_scripts_oknte_configs_list_post",
    "batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post",
)


def _patch_fastapi_mcp_ref_recursion(max_depth: int = 96) -> None:
    """给 fastapi_mcp 的 $ref 解析加递归深度上限。

    库实现（openapi.utils.resolve_schema_references）在模型互相
    $ref 引用时会无限展开（A→B→A…），递归 ~1000 层即 RecursionError，
    导致 MCP 挂载失败。
    这里以相同逻辑但带深度上限的实现替换；超限的 $ref 原样保留，
    仅影响 MCP 工具 schema 的展示完整度，不再炸初始化。
    需同时替换 utils 与 convert 两处按名绑定的引用。
    """
    import fastapi_mcp.openapi.convert as _fm_convert
    from fastapi_mcp.openapi import utils as _fm_utils

    def resolve_with_depth_limit(schema_part, reference_schema, _depth=0):
        schema_part = schema_part.copy()
        if "$ref" in schema_part and _depth < max_depth:
            ref_path = schema_part["$ref"]
            # 标准 OpenAPI 引用格式："#/components/schemas/ModelName"
            if ref_path.startswith("#/components/schemas/"):
                model_name = ref_path.split("/")[-1]
                components = reference_schema.get("components") or {}
                schemas = components.get("schemas") or {}
                if model_name in schemas:
                    ref_schema = schemas[model_name].copy()
                    schema_part.pop("$ref")
                    schema_part.update(ref_schema)
        for key, value in schema_part.items():
            if isinstance(value, dict):
                schema_part[key] = resolve_with_depth_limit(
                    value, reference_schema, _depth + 1
                )
            elif isinstance(value, list):
                schema_part[key] = [
                    resolve_with_depth_limit(item, reference_schema, _depth + 1)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
        return schema_part

    _fm_utils.resolve_schema_references = resolve_with_depth_limit
    _fm_convert.resolve_schema_references = resolve_with_depth_limit


async def mount_mcp(app: FastAPI) -> None:
    """后台挂载配置工具，保持 /mcp 与 AUTO_MAS_ENABLE_MCP 开关兼容。"""

    # MCP 构建需要遍历完整 OpenAPI schema (约 1s)，后移到后台
    # 导入与构建均为重 CPU 操作，放入线程避免阻塞事件循环推迟 API 响应
    # Starlette 支持运行期追加路由，首个 /mcp 请求前挂载完成即可
    if os.getenv("AUTO_MAS_ENABLE_MCP", "1") == "1":
        fastapi_mcp = await asyncio.to_thread(importlib.import_module, "fastapi_mcp")
        _patch_fastapi_mcp_ref_recursion()

        mcp = await asyncio.to_thread(
            fastapi_mcp.FastApiMCP,
            app,
            name="AUTO-MAS MCP",
            description=(
                "配置已安装的 AUTO-MAS 脚本：创建脚本并设置安装路径，"
                "查询专项动态选项后创建并配置用户，按专项支持情况创建计划，"
                "建立队列、队列项和定时项，最后按需试运行。"
                "创建接口返回新 ID 和默认配置；修改时只提交需要变更的字段，"
                "并使用查询接口返回的真实 ID 与可选值。"
                "MFW/M9A/MSS 的安装目录通过 embedded/reimport 导入，"
                "用 preview 查询项目 controller/resource/task 后再配置用户。"
                "HSR 先查询 capabilities 和 managed-config；"
                "BetterGI、ZZZ-OD、奇想盒先查询任务目录与选项；"
                "OK-NTE 先查询配置 schema，BAAH 先查询已有配置文件名。"
                "保存后回读核对；检查业务 code，失败时不要猜测 ID、字段或选项。"
                "任务创建成功仅表示已受理，不代表脚本运行成功。"
                "运行快照只包含当前任务；任务结束后按 taskId 查任务状态取终态，"
                "更早的结果查历史索引中的 DONE/ERROR，没有匹配记录时不能判定成功。"
            ),
            describe_full_response_schema=False,
            describe_all_responses=False,
            # 仅暴露通用配置与试运行能力；新增 HTTP 接口不会自动成为工具。
            # fastapi-mcp 的操作与标签过滤取并集，白名单不能再搭配标签过滤。
            include_operations=list(MCP_INCLUDED_OPERATIONS),
        )
        # 0.4.0 在工具清单为空时不会清空调用映射，仍需按实际清单收敛。
        tool_names = {tool.name for tool in mcp.tools}
        missing_operations = set(MCP_INCLUDED_OPERATIONS) - tool_names
        if missing_operations:
            raise RuntimeError(
                f"MCP 白名单包含不存在的 operation: {sorted(missing_operations)}"
            )
        mcp.operation_map = {
            name: operation
            for name, operation in mcp.operation_map.items()
            if name in tool_names
        }
        for tool in mcp.tools:
            if tool.name == "get_maaend_options_api_scripts_maaend_options_post":
                tool.description += (
                    "\n\n先创建 MaaEnd 脚本并设置 Info.Path 为已安装的 MaaEnd 目录，"
                    "再用该脚本的 scriptId 查询动态选项。"
                    "根据 controllerTypes 判断控制器协议：Adb 需配置模拟器与实例，"
                    "Win32 需配置游戏路径。控制器、基质与采集选项使用返回的真实值；"
                    "检查返回的 code，查询失败时先处理错误，不要猜测选项。"
                )
            elif tool.name == "get_task_status_api_dispatch_task__task_id__get":
                tool.description += (
                    "\n\n按 taskId 单点查询一个任务：运行中返回 running，已结束返回"
                    "success/error/cancelled 及结果文本与错误信息，不返回日志。"
                    "code=404 表示该 id 既不在运行中，也不在最近完成的记录里，"
                    "结果未知，不要判成功。"
                )
            elif tool.name == "search_history_api_history_search_post":
                tool.description += (
                    "\n\n用于查询已结束运行的结果，建议按运行日期使用 DAILY 模式。"
                    "按用户和记录时间核对 index 中的 status（DONE/ERROR）与 result。"
                    "该接口不按 taskId 精确检索，按 taskId 取终态请用任务状态查询；"
                    "记录缺失或无法唯一对应时，结果仍未知，"
                    "不能把任务从运行快照消失视为成功。"
                )
        mcp.mount_http()
        logger.info(f"MCP 服务已挂载，共 {len(mcp.tools)} 个工具")
    else:
        logger.info("MCP 服务未启用，跳过路由挂载")
