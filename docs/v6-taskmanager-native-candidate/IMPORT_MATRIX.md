# TaskManager Native Candidate — IMPORT_MATRIX

> **基线**: `all-plugins-integration` @ `b5e87281` (integration/dev-v2-dev-all-plugins)
> **冻结 r6**: `D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\release-nexus-a1-r6`
> **标注**: observed / inferred / unverified

---

## 1. TaskManager → 外部依赖矩阵

| 依赖模块 | 导入路径 | 使用方式 | 类型 | 迁移策略 |
|---------|---------|---------|------|---------|
| **Config.QueueConfig** | `app.core.config` | `Config.QueueConfig[uid].get("Info", "Name")` | ConfigBase MultipleConfig | → TaskConfigPort.build_queue_snapshot() |
| **Config.QueueConfig.QueueItem** | `app.core.config` | `queue.QueueItem.values()` 遍历 | ConfigBase MultipleConfig | → QueueExecutionSnapshot.script_ids |
| **Config.ScriptConfig** | `app.core.config` | `Config.ScriptConfig[uid].get("Info", "Name")` | ConfigBase MultipleConfig | → TaskConfigPort.build_script_descriptor() |
| **Config.ScriptConfig.is_locked** | `app.core.config` | `Config.ScriptConfig[uid].is_locked` | ConfigBase 属性 | → TaskConfigPort.is_script_locked() |
| **Config.ScriptConfig.UserData** | `app.core.config` | `script.UserData` 遍历 | ConfigBase MultipleConfig | → TaskConfigPort.get_script_user_ids() |
| **Config.power_sign** | `app.core.config` | 读写 `Config.power_sign` | 实例属性 | → PowerPolicyPort |
| **Config.get_script_record_capability()** | `app.core.config` | `await Config.get_script_record_capability(uid)` | async 方法 | → ScriptDescriptor.available/supported_modes |
| **Config.websocket** | `app.core.config` | `Config.websocket is None` 检查 | 实例属性 | → TaskConfigPort.is_websocket_connected() |
| **Publisher.send()** | `app.core.ws` | `await Publisher.send(id=..., type=..., data=...)` | WS 发布器 | → TaskEventSink.send_notice/send_completed/send_power_sign |
| **protocol.TASK_*** | `app.core.ws.protocol` | `protocol.TASK_INFO_UPDATED` 等常量 | 协议常量 | → TaskEventSink 内部封装 |
| **PluginEventFactory** | `app.plugins` | `emit_event_async`, `emit_script_event_async` | 插件事件 | → TaskEventSink.emit_script_start/emit_script_exit |
| **PluginEventNames** | `app.plugins` | `SCRIPT_START`, `SCRIPT_EXIT` 等 | 事件枚举 | → TaskEvent.event_type 内部封装 |
| **script_type_registry** | `app.core.script_types` | `.get()`, `.get_by_script_config()` | 脚本类型注册表 | → TaskConfigPort.build_script_descriptor() |
| **provider.create_manager()** | `app.core.script_types` | `provider.create_manager(script_item)` | 管理器工厂 | → ScriptRunner.execute() |
| **System.start_power_task()** | `app.services` | `await System.start_power_task()` | 系统服务 | → PowerPolicyPort.start_power_task() |
| **MainTimer.try_game_sign_for_task()** | `app.core.timer` | `asyncio.create_task(MainTimer.try_game_sign_for_task())` | 定时器 | → **Phase 2 迁移**（游戏签到独立端口） |
| **TaskItem/ScriptItem/UserItem** | `app.models.task` | 数据模型 | dataclass | → **保留**（数据模型层，非 ConfigBase） |
| **WSTaskNoticeData 等** | `app.models.schema` | WS 数据 DTO | Pydantic | → **保留**（序列化层） |
| **PluginScriptConfig** | `app.models.plugin_script_config` | 插件脚本配置类型判断 | ConfigBase | → ScriptDescriptor.is_plugin_script |

## 2. Dispatch API → TaskManager 依赖

| 端点 | 依赖 | 迁移策略 |
|------|------|---------|
| `POST /api/dispatch/start` | `TaskManager.add_task(mode, id, resume_from_script_id)` | → 参数不变，内部使用 TaskConfigPort |
| `POST /api/dispatch/stop` | `TaskManager.stop_task(task_id)` | → 参数不变，内部使用 native lease |
| `POST /api/dispatch/get/power` | `Config.power_sign` | → PowerPolicyPort.get_power_sign() |
| `POST /api/dispatch/set/power` | `Config.power_sign = value` | → PowerPolicyPort.set_power_sign() |
| `POST /api/dispatch/cancel/power` | `System.cancel_power_task()` | → PowerPolicyPort.cancel_power_task() |

## 3. Main Lifespan → TaskManager 依赖

| 阶段 | 依赖 | 迁移策略 |
|------|------|---------|
| 启动 | `Config.init_config()` | → **Phase 1** 不变，Config v2 初始化后注入 TaskConfigPort |
| 启动 | `TaskManager.start_startup_queue()` | → 内部使用 TaskConfigPort.get_startup_queue_snapshots() |
| 关闭 | `TaskManager.stop_task("ALL")` | → 不变 |
| 关闭 | `System.cancel_power_task()` | → PowerPolicyPort.cancel_power_task() |

## 4. 关键路径标注

### observed
- [x] `Config.QueueConfig[uid]` 返回 `MultipleConfig[QueueConfig]` 实例 (observed: config.py L210)
- [x] `Config.ScriptConfig[uid]` 返回 `ConfigBase` 子类实例 (observed: config.py L209)
- [x] `is_locked` 是 `ConfigBase` 的属性 (observed: ConfigBase.py L877, L1036)
- [x] `get_script_record_capability` 是 async 方法，内部调用 `storage_to_form` (observed: config.py L1622-1644)
- [x] `Publisher.send` 通过 `ws_publisher` 发送 WS 消息 (observed: ws/__init__.py L14)
- [x] `PluginEventFactory` 通过 lazy import 加载 (observed: plugins/__init__.py L58)

### inferred
- [x] `Config.QueueConfig.QueueItem.values()` 返回的每个 item 是 `QueueItem` 实例 (inferred: QueueConfig.__init__)
- [x] `Config.ScriptConfig.items()` 返回 `(uuid, ConfigBase)` 对 (inferred: MultipleConfig 实现)
- [x] `provider.create_manager(script_item)` 返回的 manager 需要实现 `TaskExecuteBase` 接口 (inferred: ScriptTypeProvider.create_manager)

### unverified
- [ ] `Config.power_sign` 在 `ConfigBase` 和 `Config v2` 中的同步机制 (unverified: 需要 Config v2 源码确认)
- [ ] `MainTimer.try_game_sign_for_task()` 是否依赖 `Config.ToolsConfig` (unverified: 游戏签到独立审计)
- [ ] `PluginScriptConfig` 的 `get("Meta", "PluginTypeKey")` 在 Config v2 中的等价路径 (unverified: 需要 PluginScriptConfig 到 Config v2 的映射)