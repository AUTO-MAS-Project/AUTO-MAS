# 配置重构 API 迁移说明

本文档记录 2026-04 配置重构相关 API 的破坏性变更，供前端组统一适配。

## 总体规则

1. 旧的 `/get`、`/add`、`/update`、`/delete`、`/time/*`、`/item/*` 兼容路由已移除，只保留新的 REST 风格路径。
2. 创建接口的返回字段统一为 `id`，不再返回 `emulatorId`、`queueId`、`timeSetId`、`queueItemId`、`webhookId` 这类资源专属字段。
3. 单资源查询统一返回：

```json
{
  "code": 200,
  "status": "success",
  "message": "操作成功",
  "data": {}
}
```

4. 集合查询统一返回：

```json
{
  "code": 200,
  "status": "success",
  "message": "操作成功",
  "index": [],
  "data": {}
}
```

5. 创建接口统一返回：

```json
{
  "code": 200,
  "status": "success",
  "message": "操作成功",
  "id": "资源ID",
  "data": {}
}
```

6. 更新接口的请求体直接传 `Patch` 数据，不再包一层 `{ "data": ... }`。
7. 排序接口统一为 `PATCH .../order`，请求体统一为：

```json
{
  "indexList": ["id1", "id2"]
}
```

## 模拟器 API

旧接口：
`POST /api/emulator/get`
`POST /api/emulator/add`
`POST /api/emulator/update`
`POST /api/emulator/delete`
`POST /api/emulator/order`
`POST /api/emulator/operate`
`POST /api/emulator/status`
`POST /api/emulator/emulator/search`

新接口：
`GET /api/emulator`
`POST /api/emulator`
`PATCH /api/emulator/order`
`GET /api/emulator/detected`
`GET /api/emulator/status`
`GET /api/emulator/{emulator_id}`
`PATCH /api/emulator/{emulator_id}`
`DELETE /api/emulator/{emulator_id}`
`GET /api/emulator/{emulator_id}/status`
`POST /api/emulator/{emulator_id}/actions/{action}`

动作接口说明：
`action` 取值为 `open`、`close`、`show`
请求体只保留：

```json
{
  "index": "0"
}
```

## 调度队列 API

旧接口：
`POST /api/queue/add`
`POST /api/queue/get`
`POST /api/queue/update`
`POST /api/queue/delete`
`POST /api/queue/order`
`POST /api/queue/time/get`
`POST /api/queue/time/add`
`POST /api/queue/time/update`
`POST /api/queue/time/delete`
`POST /api/queue/time/order`
`POST /api/queue/item/get`
`POST /api/queue/item/add`
`POST /api/queue/item/update`
`POST /api/queue/item/delete`
`POST /api/queue/item/order`

新接口：
`GET /api/queue`
`POST /api/queue`
`PATCH /api/queue/order`
`GET /api/queue/{queue_id}`
`PATCH /api/queue/{queue_id}`
`DELETE /api/queue/{queue_id}`
`GET /api/queue/{queue_id}/times`
`POST /api/queue/{queue_id}/times`
`PATCH /api/queue/{queue_id}/times/order`
`GET /api/queue/{queue_id}/times/{time_set_id}`
`PATCH /api/queue/{queue_id}/times/{time_set_id}`
`DELETE /api/queue/{queue_id}/times/{time_set_id}`
`GET /api/queue/{queue_id}/items`
`POST /api/queue/{queue_id}/items`
`PATCH /api/queue/{queue_id}/items/order`
`GET /api/queue/{queue_id}/items/{queue_item_id}`
`PATCH /api/queue/{queue_id}/items/{queue_item_id}`
`DELETE /api/queue/{queue_id}/items/{queue_item_id}`

关键变化：
单个队列、单个定时项、单个队列项不再返回 `index + data map`，只返回单个 `data`。
嵌套资源更新和删除不再在 body 中重复传 `queueId`、`timeSetId`、`queueItemId`。
WebSocket 命令 `queue.get` 现在只对应“查询单个队列”，如果需要拉取全部队列，请改走 `GET /api/queue`。

## 全局设置 API

旧接口：
`POST /api/setting/get`
`POST /api/setting/update`
`POST /api/setting/test_notify`
`POST /api/setting/webhook/get`
`POST /api/setting/webhook/add`
`POST /api/setting/webhook/update`
`POST /api/setting/webhook/delete`
`POST /api/setting/webhook/order`
`POST /api/setting/webhook/test`

新接口：
`GET /api/setting`
`PATCH /api/setting`
`POST /api/setting/actions/test-notify`
`GET /api/setting/webhooks`
`POST /api/setting/webhooks`
`PATCH /api/setting/webhooks/order`
`POST /api/setting/webhooks/test`
`GET /api/setting/webhooks/{webhook_id}`
`PATCH /api/setting/webhooks/{webhook_id}`
`DELETE /api/setting/webhooks/{webhook_id}`

关键变化：
`PATCH /api/setting` 请求体直接传 `GlobalConfigPatch`。
Webhook 单项查询返回单个 `data`，不再返回 `index + data map`。
Webhook 测试接口请求体直接传 `WebhookPatch`。

## 工具设置 API

旧接口：
`POST /api/tools/get`
`POST /api/tools/update`

新接口：
`GET /api/tools`
`PATCH /api/tools`

关键变化：
`PATCH /api/tools` 请求体直接传 `ToolsConfigPatch`。

## 脚本管理 API

旧接口：
`POST /api/scripts/add`
`POST /api/scripts/get`
`POST /api/scripts/update`
`POST /api/scripts/delete`
`POST /api/scripts/order`
`POST /api/scripts/import/file`
`POST /api/scripts/export/file`
`POST /api/scripts/import/web`
`POST /api/scripts/Upload/web`
`POST /api/scripts/user/get`
`POST /api/scripts/user/add`
`POST /api/scripts/user/update`
`POST /api/scripts/user/delete`
`POST /api/scripts/user/order`
`POST /api/scripts/user/infrastructure`
`POST /api/scripts/user/combox/infrastructure`
`POST /api/scripts/webhook/get`
`POST /api/scripts/webhook/add`
`POST /api/scripts/webhook/update`
`POST /api/scripts/webhook/delete`
`POST /api/scripts/webhook/order`

新接口：
`GET /api/scripts`
`POST /api/scripts`
`PATCH /api/scripts/order`
`GET /api/scripts/{script_id}`
`PATCH /api/scripts/{script_id}`
`DELETE /api/scripts/{script_id}`
`POST /api/scripts/{script_id}/actions/import-file`
`POST /api/scripts/{script_id}/actions/export-file`
`POST /api/scripts/{script_id}/actions/import-web`
`POST /api/scripts/{script_id}/actions/upload-web`
`GET /api/scripts/{script_id}/users`
`POST /api/scripts/{script_id}/users`
`PATCH /api/scripts/{script_id}/users/order`
`GET /api/scripts/{script_id}/users/{user_id}`
`PATCH /api/scripts/{script_id}/users/{user_id}`
`DELETE /api/scripts/{script_id}/users/{user_id}`
`POST /api/scripts/{script_id}/users/{user_id}/actions/import-infrastructure`
`GET /api/scripts/{script_id}/users/{user_id}/infrastructure-options`
`GET /api/scripts/{script_id}/users/{user_id}/webhooks`
`POST /api/scripts/{script_id}/users/{user_id}/webhooks`
`PATCH /api/scripts/{script_id}/users/{user_id}/webhooks/order`
`GET /api/scripts/{script_id}/users/{user_id}/webhooks/{webhook_id}`
`PATCH /api/scripts/{script_id}/users/{user_id}/webhooks/{webhook_id}`
`DELETE /api/scripts/{script_id}/users/{user_id}/webhooks/{webhook_id}`

关键变化：
脚本创建请求中的复制来源字段从 `scriptId` 改为 `copyFromId`。
脚本、用户、脚本用户下的 Webhook 都已经切到单资源 REST 返回，不再混用旧的 body 包装。
脚本级和用户级 patch 校验不再手写维护，而是基于运行期配置模型直接派生。

## 共享 Contract 变更

新增通用响应模型：
`ResourceCollectionOut[Index, Data]`
`ResourceItemOut[Data]`
`ResourceCreateOut[Data]`
`IndexOrderPatch`

这意味着后续新增配置资源时，应优先复用通用响应模型，不要再重复定义新的 `XXXGetOut`、`XXXCreateOut`、`XXXReorderIn` 壳子。

## Contract 生成规则

配置相关 `Read/Patch` contract 现在优先通过运行期 `PydanticConfigBase` 模型派生生成。

当前已经接入：
`EmulatorConfig`
`QueueConfig`
`TimeSet`
`QueueItem`
`Webhook`
`GlobalConfig`
`ToolsConfig`
`GeneralConfig`
`GeneralUserConfig`
`MaaConfig`
`MaaUserConfig`
`MaaPlanConfig`
`SrcConfig`
`SrcUserConfig`
`MaaEndConfig`
`MaaEndUserConfig`

规则说明：
读模型保留运行期模型字段和虚拟字段。
补丁模型自动把字段转为可选，并跳过虚拟字段。
脚本类读模型额外保留静态 `type` 字段，用于前端按 discriminator 分发。

## 额外说明

脚本相关创建接口和 Webhook 创建接口的返回字段都已统一为 `id`。
如果前端依赖旧的 `scriptId`、`userId`、`webhookId` 返回字段，需要同步调整读取逻辑。
