---
name: mas-api-contract
description: Define FastAPI HTTP/WebSocket contracts in app/api and shared app/models/schema.py, including config-derived payloads, partial updates, stable envelopes, errors, and client compatibility.
---

# MAS API Contract

适用于 `app/api/*` HTTP 路由、端点模型、`app/models/schema.py` 与后端 WebSocket 契约。涉及任务创建/运行树/快照时联动 `mas-task-scheduler`；涉及配置端点时必读 `../mas-data-model/references/config-framework.md`。

## 路由与模型归属

- **路径规范**：资源前缀 `/api/<resource>`，非 CRUD 动作显式后缀（`/start`、`/stop`、`/reorder`）。`POST` 查询类接口（如下拉选项）优先单一路径 + 请求体 discriminator，不按配置表拆平行路径。
- **模型放置**：端点专用 `*In` / `*Out` 与私有子模型放在**所属 `app/api/` 模块顶部**（路由函数之前）；跨模块/业务层契约统一放在单文件 `app/models/schema.py`。Router 之间禁止互相导入共享模型。
- **薄路由**：路由函数仅做传输层适配与异常转换，显式声明 `response_model`，对齐 `OutBase` 信封，不返回无类型裸字典，不泄露内部堆栈。

## MCP 对外契约（高危）

`main.py` 通过 `fastapi_mcp.FastApiMCP(...).mount_http()` 将实时 OpenAPI 挂载为 `/mcp`（**streamable HTTP，非 SSE**），受 `AUTO_MAS_ENABLE_MCP`（默认 `"1"`）控制且在 `lifespan` yield 后后台挂载（早期请求 404 属正常）：

- 所有路由增改重命名都会自动反映为 MCP 工具签名；**路由路径、`operation_id` 与 tag 变更均属破坏性变更**。
- 破坏性接口必须带 **`tags=["Delete"]`** 才能被 `exclude_tags=["Delete"]` 排除出 MCP（仅靠路径名或 HTTP 方法不会排除）。

## 配置接口契约

1. 从真实配置类派生：`app/config/wire.py` 的 `ConfigInput[T]` / `StrictConfigInput[T]` / `ConfigPayload[T]` / `config_contract()`，禁止手写重复配置模型。
2. 局部更新必须用 **`model_dump(exclude_unset=True)`** 区分「省略」与「显式 `null`」；**禁止使用全量默认 dump 或 `exclude_none=True`**。
3. 保留隐藏/禁用/虚拟字段规则、脱敏占位值与业务锁；`update()` 不改嵌套集合，多步原子变更须显式事务。
4. `commit()` 成功不等于已落盘；`flush()` 与导出在事务外执行，导出读取运行中稳定配置而非磁盘旧文件。

## WebSocket 与兼容性

- **WS 信封**：统一 `id` / `type` / `data`，命令负载与对应 HTTP 保持一致，心跳与关闭语义收口在 core WS。
- **演进与生成物**：优先增量兼容；**避免把已被前端消费的稳定扁平 `Literal[...]` 改成 `Union[...]`**，除非确认生成的 TS 运行时导出不变。
- **客户端重生成**：后端 schema 变更后在 `frontend/` 运行 `yarn openapi`（针对开发端口，需先起本地后端），**禁止手改 `frontend/src/api/**`**。
