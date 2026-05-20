# 专项适配 · 代码规范（必遵守）

新增或维护 `ScriptType` 时按表实现，**不要**依赖事后排查叙事。Okww 专项增量见 [examples-okww.md](./examples-okww.md#实现规范okww-必遵守)。

## 1. 注册与 API

| 必做 | 位置 |
|------|------|
| `XxxConfig` / `XxxUserConfig` + `schema.py` | `app/models/` |
| `SCRIPT_BOOK`、`USER_BOOK`、`task_manager` 分支 | `app/core/`、`app/models/config.py` |
| `TYPE_BOOK["XxxConfig"]` → 展示文案 | `app/utils/constants.py`（否则调度 `combox/task` KeyError） |
| 后端改 schema 后 `yarn openapi` | `frontend/`；**禁止**手改 `src/api/models/*` |
| OpenAPI 生效 | 重启后端 → `openapi.json` **文本**含新类型名（勿只靠 PowerShell 对象键）→ 确认 36163 为当前 `main.py` |

## 2. 前端表面

| 必做 | 位置 |
|------|------|
| Hub 片段、`ScriptTable` 卡片图标与文案 | `Scripts.vue`、`ScriptTable.vue` |
| 脚本编辑三段 + 用户编辑三段 | `EditView/Script/`、`EditView/User/` |
| `useScriptApi`：**脚本类型**与 **UserConfig→users[]** 两处分支 | 漏后者则列表 NO DATA |
| 用户 **add**：先 `addUser` 再 `router.replace` 到带 `userId` 路由 | 参考 `GeneralUserEdit` |
| **ScriptConfig** 按钮在脚本卡片，不在脚本编辑页 | `Scripts.vue` 遮罩 + WebSocket |
| WebSocket | `@/composables/useWebSocket`（勿造 `@/utils/websocketClient`） |
| 展示文案 vs 技术标识分离 | 文案如 `ok-ww`；`ScriptType`/路由/OpenAPI 名保持 `Okww` 等 |

## 3. 任务模块（`app/task/Xxx/`）

| 必做 | 类 |
|------|-----|
| 实现 `final_task`、`on_crash` | `Manager`、`AutoProxy`、`ScriptConfig` |
| `final_task` 解锁配置、清进程、写 `history/`（或专项 `save_*_log`） | `AutoProxy` |
| `on_crash` 设异常 + WebSocket `Error` | 同上 |

### AutoProxy 日志与状态（通用）

| 规则 | 实现 |
|------|------|
| `LogMonitor` 构造 | 必须传 `time_stamp_range`、`time_format`、`check_log`（对齐 `general/AutoProxy.py`） |
| 任务结果 | 每轮 `log_record[start_time] = LogRecord()`，只写 **`log_record.status`** |
| 禁止 | 对 `UserItem.result` 赋值（只读 property） |
| 用户配置索引 | `cur_user_uid = uuid.UUID(user_id)`，再 `user_config[cur_user_uid]` |

### AutoProxy 进程（有 `IfTrackProcess` 时）

| 规则 | 实现 |
|------|------|
| `ProcessInfo` | 至少一项非空（ok-script 默认 `pythonw.exe` + `{RootPath}/data/apps/ok-ww/python/pythonw.exe`） |

## 4. 简洁 / 详细（除 M9A）

| Mode | 配置入口 | 落盘 |
|------|----------|------|
| 简洁 | 脚本卡片 ScriptConfig，`taskId=scriptId` | `data/{scriptId}/Default/ConfigFile` |
| 详细 | 用户页 ScriptConfig，`taskId=userId` | `data/{scriptId}/{userId}/ConfigFile` |

`AutoProxy.check()` 须按 `Mode` 校验对应目录存在；用户页仅 **详细** 显示配置按钮。

## 5. 架构线选型（实现前只读）

| 线 | 自启动 | 用户改设置 |
|----|--------|------------|
| ok-script（Okww） | CLI `-t`/`-e`，`AutoProxy` 拼 argv | ScriptConfig 无参启 exe |
| MFAA（M9A） | 写盘 + exe，无稳定 CLI | 写 JSON，勿套 ScriptConfig 壳 |
| MXU（MaaEnd） | 文档化参数 / `mxu-*.json` | ScriptConfig + `mxu-*.json` |

细节：[script-frontend-architectures.md](./script-frontend-architectures.md)、各 `examples-*.md`。
