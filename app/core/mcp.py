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


"""MCP 可选服务：独立加载、状态发布、路由及资源所有权。"""

from __future__ import annotations

import asyncio
import importlib
import os
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal, TypeVar
from uuid import uuid4

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.models.schema import McpStatusData
from app.utils import get_logger

if TYPE_CHECKING:
    import httpx
    from fastapi_mcp import FastApiMCP

logger = get_logger("MCP 服务")
T = TypeVar("T")

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
    # 只读历史记录与编号详情，用于核对已结束的运行。
    "search_history_api_history_search_post",
    "get_history_detail_api_history_detail_post",
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


def _build_mcp(
    factory: Callable[..., FastApiMCP], schema_app: FastAPI, client: httpx.AsyncClient
) -> FastApiMCP:
    """只在线程里生成工具；HTTP 调用仍使用原应用。"""
    mcp = factory(
        schema_app,
        name="AUTO-MAS MCP",
        description=(
            "配置 AUTO-MAS 托管：创建托管并设置外部脚本安装路径，"
            "查询专项动态选项后创建并配置账号，按专项支持情况创建计划，"
            "建立队列、队列项和定时项，最后按需试运行。"
            "创建接口返回新 ID 和默认配置；修改时只提交需要变更的字段，"
            "并使用查询接口返回的真实 ID 与可选值。"
            "MFW/M9A/MSS 的安装目录通过 embedded/reimport 导入，"
            "用 preview 查询项目 controller/resource/task 后再配置账号。"
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
        # 生成说明使用路由视图，实际调用仍走原应用的中间件、依赖与状态。
        http_client=client,
        # 仅暴露通用配置与试运行能力；新增 HTTP 接口不会自动成为工具。
        # fastapi-mcp 的操作与标签过滤取并集，白名单不能再搭配标签过滤。
        include_operations=list(MCP_INCLUDED_OPERATIONS),
    )
    # fastapi-mcp 0.4.0 给联合类型补入单一 type，使可空字段拒绝 null。
    # 仅移除转换器新增的约束，保留 OpenAPI 自己声明的 type。
    body_routes = set()
    for tool in mcp.tools:
        operation = mcp.operation_map[tool.name]
        properties = tool.inputSchema["properties"]
        fields = {
            parameter["name"]: parameter.get("schema", {})
            for parameter in operation["parameters"]
        }
        request_body = operation["request_body"]
        body_schema = (
            request_body.get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        fields.update(body_schema.get("properties", {}))
        for name, schema in fields.items():
            if "type" not in schema and any(
                key in schema for key in ("anyOf", "oneOf", "allOf", "$ref")
            ):
                properties[name].pop("type", None)
        if request_body.get("required") and body_schema.get("type") == "object":
            body_routes.add((operation["method"], operation["path"]))

    # 同版本还会把空参数转成无请求体。按原路由契约保留必需的 JSON 对象。
    # 上游同时修复这两项转换行为后可移除此处适配。
    original_request = mcp._request

    async def request_with_body(client, method, path, query, headers, body):
        if body is None and (method, path) in body_routes:
            body = {}
        return await original_request(
            client=client,
            method=method,
            path=path,
            query=query,
            headers=headers,
            body=body,
        )

    mcp._request = request_with_body
    return mcp


def _validate_mcp(mcp: FastApiMCP) -> None:
    # 0.4.0 在工具清单为空时不会清空调用映射，仍需按实际清单收敛。
    tool_names = {tool.name for tool in mcp.tools}
    missing_operations = set(MCP_INCLUDED_OPERATIONS) - tool_names
    if missing_operations:
        raise RuntimeError(
            f"MCP 白名单包含不存在的 operation: {sorted(missing_operations)}"
        )
    if tool_names - set(MCP_INCLUDED_OPERATIONS):
        raise RuntimeError("MCP 工具包含未授权的 operation")
    mcp.operation_map = {
        name: operation
        for name, operation in mcp.operation_map.items()
        if name in tool_names
    }
    for tool in mcp.tools:
        if tool.name == "get_maaend_options_api_scripts_maaend_options_post":
            tool.description += (
                "\n\n先创建 MaaEnd 托管并设置 Info.Path 为已安装的 MaaEnd 目录，"
                "再用该托管的 scriptId 查询动态选项。"
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
                "按账号、托管名称、记录编号及带偏移的时间核对 index 中的 status 与 message。"
                "success 表示成功，error 表示执行失败，skipped/cancelled 分别表示跳过/取消；存储错误不改变执行结论。可用 recordId 获取详情；该接口不按 taskId 精确检索，按 taskId 取终态请用任务状态查询；"
                "记录缺失或无法唯一对应时，结果仍未知，"
                "不能把任务从运行快照消失视为成功。"
            )


class McpService:
    """事件循环持有状态和资源；线程只执行串行的导入、构建与校验。"""

    def __init__(self) -> None:
        enabled = os.getenv("AUTO_MAS_ENABLE_MCP", "1") == "1"
        self._status = McpStatusData(
            enabled=enabled,
            state="pending" if enabled else "skipped",
            instanceId=uuid4().hex,
            runId=uuid4().hex,
            stage=None,
            startedAt=None,
            finishedAt=None,
            elapsedMs=0,
            toolCount=0,
            error=None,
            revision=0,
        )
        self._app: FastAPI | None = None
        self._wait_for_home = os.getenv("AUTO_MAS_MCP_WAIT_FOR_HOME", "0") == "1"
        self._home_painted = False
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._shutdown_lock = asyncio.Lock()
        self._started_counter: float | None = None
        self._instance: FastApiMCP | None = None
        self._client: httpx.AsyncClient | None = None
        self._routes: list[Any] = []

    def status(self) -> McpStatusData:
        snapshot = self._status.model_copy()
        if self._started_counter is not None and snapshot.finishedAt is None:
            snapshot.elapsedMs = int((perf_counter() - self._started_counter) * 1000)
        return snapshot

    def start(self, app: FastAPI) -> bool:
        """主业务 ready 后登记应用；桌面端再等首页首帧，不等待实际加载。"""
        if self._closing or self._status.state != "pending" or self._task is not None:
            return False
        self._app = app
        if self._wait_for_home and not self._home_painted:
            return False
        return self._spawn()

    def notify_home_painted(self) -> None:
        """记住首页首帧信号；主业务与首帧都就绪后才加载，重复通知不重复启动。"""
        if self._closing:
            return
        self._home_painted = True
        if self._app is not None:
            self.start(self._app)

    def retry(self) -> bool:
        """仅允许已完成清理的失败尝试重试；受理与 ready 是两个结果。"""
        if (
            self._closing
            or self._status.state != "failed"
            or self._task is None
            or not self._task.done()
        ):
            return False
        self._status.runId = uuid4().hex
        return self._spawn()

    def _spawn(self) -> bool:
        self._started_counter = perf_counter()
        self._status.startedAt = datetime.now(timezone.utc)
        self._status.finishedAt = None
        self._status.elapsedMs = 0
        self._status.error = None
        self._status.toolCount = 0
        self._status.state = "running"
        self._status.stage = "importing"
        self._status.revision += 1
        self._task = asyncio.create_task(self._load(), name="mcp-load")
        if self._task is None:
            self._closing = True
            self._finish("cancelled")
            return False
        return True

    def _check_open(self) -> None:
        if self._closing:
            raise asyncio.CancelledError

    async def _in_thread(self, function: Callable[..., T], *args: Any) -> T:
        # 取消 to_thread 的等待者不会停止线程。保留并等待它，接回构建结果以便清理；
        # 关闭标记使结果只能回收，不能挂载，也不能与重试并发。
        worker = asyncio.create_task(asyncio.to_thread(function, *args))
        while True:
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                self._closing = True
                if worker.cancelled():
                    raise

    async def _publish(self) -> None:
        from app.core import Publisher
        from app.core.ws import protocol

        try:
            async with asyncio.timeout(1):
                await Publisher.send(
                    id=protocol.ID_MCP,
                    type=protocol.MCP_STATUS_UPDATED,
                    data=self.status(),
                )
        except Exception:
            logger.opt(exception=True).debug("MCP 状态推送失败，客户端可重新读取快照")

    async def _stage(
        self, stage: Literal["building", "validating", "mounting"]
    ) -> None:
        self._check_open()
        self._status.stage = stage
        self._status.revision += 1
        logger.info(f"MCP 加载阶段: {stage}，已耗时 {self.status().elapsedMs} ms")
        await self._publish()
        self._check_open()

    def _finish(self, state: Literal["ready", "failed", "cancelled"]) -> None:
        self._status.elapsedMs = self.status().elapsedMs
        self._status.finishedAt = datetime.now(timezone.utc)
        self._status.state = state
        self._status.revision += 1

    async def _load(self) -> None:
        try:
            await self._publish()
            self._check_open()
            # 唯一加载流程串行导入，禁用时不会到达这里。
            package = await self._in_thread(importlib.import_module, "fastapi_mcp")
            self._check_open()
            await self._stage("building")
            import httpx

            app = self._app
            assert app is not None
            schema_app = FastAPI(
                title=app.title,
                version=app.version,
                description=app.description,
                openapi_url=None,
                routes=[
                    route
                    for route in app.routes
                    if isinstance(route, APIRoute)
                    and (route.operation_id or route.unique_id)
                    in MCP_INCLUDED_OPERATIONS
                ],
            )
            schema_app.openapi_version = app.openapi_version
            self._client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://apiserver",
                timeout=10.0,
            )
            _patch_fastapi_mcp_ref_recursion()
            self._instance = await self._in_thread(
                _build_mcp, package.FastApiMCP, schema_app, self._client
            )
            self._check_open()
            await self._stage("validating")
            await self._in_thread(_validate_mcp, self._instance)
            self._check_open()
            await self._stage("mounting")
            # mount_http 是同步操作；记录本次新增路由，即使部分挂载失败也能精确撤回。
            # 挂载与提交之间不 await，其他请求不会看见半完成的路由。
            previous = {id(route) for route in app.routes}
            try:
                self._instance.mount_http(router=app)
            finally:
                self._routes = [
                    route for route in app.routes if id(route) not in previous
                ]
            from starlette.responses import JSONResponse

            # 已匹配但尚未进入端点的请求也要检查关闭标记，防止收尾后重建会话管理器。
            for route in self._routes:
                original = route.app

                async def available(scope, receive, send, endpoint=original):
                    if self._closing:
                        await JSONResponse(
                            {"detail": "MCP service is closing"}, status_code=503
                        )(scope, receive, send)
                    else:
                        await endpoint(scope, receive, send)

                route.app = available
            self._status.toolCount = len(self._instance.tools)
            self._finish("ready")
            logger.info(
                f"MCP 服务已挂载，共 {self._status.toolCount} 个工具，耗时 {self._status.elapsedMs} ms"
            )
        except asyncio.CancelledError:
            self._finish("cancelled")
        except Exception:
            logger.exception(f"MCP 加载失败: {self._status.stage}")
            self._status.error = {
                "importing": "import_failed",
                "building": "build_failed",
                "validating": "validation_failed",
                "mounting": "mount_failed",
            }[self._status.stage]
            self._finish("cancelled" if self._closing else "failed")
        finally:
            if self._status.state != "ready":
                try:
                    await self._release()
                except Exception:
                    # 资源所有权不确定时禁用重试，不能再创建一份有冲突的实例。
                    self._closing = True
                    self._status.error = "cleanup_failed"
                    self._status.revision += 1
                    logger.exception("MCP 资源清理失败，已禁止再次加载")
            await self._publish()

    async def _release(self) -> None:
        if self._app is not None and self._routes:
            owned = {id(route) for route in self._routes}
            self._app.router.routes[:] = [
                route for route in self._app.routes if id(route) not in owned
            ]
            self._routes.clear()
        try:
            if self._instance is not None:
                transport = self._instance._http_transport
                if transport is not None:
                    # 与首个请求的惰性启动串行，避免 shutdown 后又启动会话管理器。
                    async with transport._startup_lock:
                        await transport.shutdown()
                self._instance = None
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    def shutdown(self) -> Coroutine[Any, Any, None]:
        """调用时立即封禁新加载；返回等待线程和资源回收的协程。"""
        self._closing = True
        return self._shutdown()

    async def _shutdown(self) -> None:
        async with self._shutdown_lock:
            if self._task is not None:
                try:
                    await asyncio.shield(self._task)
                except asyncio.CancelledError:
                    if not self._task.cancelled():
                        raise
            await self._release()
            if self._status.state not in {"skipped", "cancelled"}:
                self._finish("cancelled")
                await self._publish()


MCP = McpService()
