# AUTO-MAS 架构与运行逻辑总览（前端 / 后端）

---

## 总览

- 技术栈
  - 前端：Electron（主进程/预加载）+ Vue 3 + TypeScript + Vite + Ant Design Vue
  - 后端：Python 3 + FastAPI + Uvicorn + AsyncIO
  - 实时通信：WebSocket（统一的 WebSocketMessage 协议）
  - 进程通信：Electron IPC（start-backend/stop-backend/sync-backend-config 等）
- 单一实时通道
  - WS 端点：`ws://localhost:36163/api/core/ws`
  - 消息协议：`WebSocketMessage{id, type, data}`，type ∈ {Update|Message|Info|Signal}
  - 后端仅允许单连接（第二连接会被拒绝）；断连时做清理与退出（详见 core.py）
- 配置与数据
  - 配置目录：`config/`（全局与各对象 JSON）
  - 数据库：`data/data.db`（版本号表 + 历史索引）
  - 资源：`res/`（图片/音效等，后端以 StaticFiles 暴露部分路径）

---

## 后端（FastAPI + AsyncIO）

### 运行入口与生命周期

- `main.py`
  - 管理员权限检查：非管理员则提权重启自身（Windows ShellExecute RunAs）
  - FastAPI 应用创建，注册路由与 CORS，挂载静态资源
  - lifespan（应用生命周期）
    - 初始化：`Config.init_config()` → 加载/迁移配置、准备目录与数据
    - 阶段数据准备与清理：`Config.get_stage(if_start=True)`、`Config.clean_old_history()`
    - 创建定时任务：`MainTimer.second_task()`、`MainTimer.hour_task()`
    - 系统设置：`System.set_Sleep()`、`System.set_SelfStart()`
    - 关闭阶段：停止所有任务，取消定时器，关闭 Matomo，向前端发送 `Signal: { Closed }`
  - HTTP 服务：`uvicorn.Server` 监听 `0.0.0.0:36163`

### 核心端点与消息通道

- `app/api/core.py`
  - `WS /api/core/ws`
    - 单连接保证：已有连接则拒绝新连接
    - 心跳：收到 `Signal: Ping` → 回 `Pong`；定时超时会主动发送 `Ping`，若未收到 `Pong` 则断连
    - 首次连接：`TaskManager.start_startup_queue()`（自动运行启动队列）
    - 其它消息：投递到 `Broadcast`（发布-订阅）
    - 断连：`Config.websocket = None`，并 `System.set_power("KillSelf")`（后端进程自杀式退出）
  - `POST /api/core/close`：关闭后端

### 任务调度与定时器

- `app/core/task_manager.py`（关键）

  - `TaskInfo`：运行态元数据（状态/进度/日志/时间戳）
  - `TaskManager`
    - `add_task(mode, uid)`：解析模式（设置脚本/自动代理/人工排查），检查冲突并创建 asyncio 任务
    - `run_task(mode, task_id, actual_id)`：
      - 设置脚本：为目标脚本（或其用户）创建独立 Manager（`MaaManager`/`GeneralManager`）运行
      - 自动代理：根据队列构建 `task_list`，逐脚本执行，期间持续通过 WS `Update/Info/Message/Signal` 同步前端
    - `stop_task(task_id)`：取消单任务/全部
    - `remove_task(...)`：发送 `Signal: Accomplish`；若为队列任务且配置了电源操作，则发起全局倒计时并调用 `System.start_power_task()`
    - `start_startup_queue()`：启动时自动拉起勾选 `StartUpEnabled` 的队列，并向前端发送 `id="TaskManager" type="Signal" data={ newTask }`

- `app/core/timer.py`

  - `MainTimer.second_task()`：每秒任务 → `set_silence()` + `timed_start()`
    - `set_silence()`：若启用静默模式，模拟 BossKey 隐藏模拟器窗口
    - `timed_start()`：命中 `QueueConfig` 的时间项则调用 `TaskManager.add_task("自动代理")`
  - `MainTimer.hour_task()`：每天一次上报版本数据到 Matomo

- `app/core/broadcast.py`
  - 轻量发布-订阅：`subscribe/unsubscribe/put`，用于后端内部消息分发（WS 入口收到的普通消息会被广播）

### 配置系统与模型

- `app/core/config.py`（体量大，职责核心）

  - `AppConfig`（对外通过 `Config` 单例使用）
    - 目录结构、日志/DB/Config 初始化
    - 版本字符串、Git 版本查询（若存在 git 仓库）
    - `init_config()`：连接/加载 `Config.json`、`ScriptConfig.json`、`PlanConfig.json`、`QueueConfig.json`；同步 `TaskManager.task_dict`
    - DB 版本迁移：`v1.7 → v1.8 → v1.9`（重命名/重排结构，移动旧版文件到新布局）
    - 统一 WS 输出：`send_json(dict)`；全局状态：`server/websocket/power_sign/...`
    - 脚本/用户/队列/时间项/计划/模拟器/Webhook 等 CRUD、排序与文件导入导出（详见同文件众多 `add/get/update/del/...` 方法）

- `app/models/schema.py`
  - 所有 API 的 `Pydantic` 输入/输出模型（强校验）
  - `WebSocketMessage`：WS 统一消息体 `{ id: str, type: Literal[Update|Message|Info|Signal], data: dict }`
  - 覆盖领域模型：脚本（MAA/General）、用户、计划、队列、时间项、模拟器、Webhook、历史、设置/更新等

### API 路由概览（逐文件简析）

- `app/api/core.py`：WebSocket、关闭后端
- `app/api/dispatch.py`：
  - `POST /api/dispatch/start` → `TaskManager.add_task`
  - `POST /api/dispatch/stop` → `TaskManager.stop_task`
  - `POST /api/dispatch/set/power` → 设置全局电源标志
  - `POST /api/dispatch/cancel/power` → 取消电源任务
- `app/api/scripts.py`：脚本的增删改查、排序、文件/网络导入导出
- `app/api/plan.py`：计划（MaaPlan）的增删改查与排序
- `app/api/queue.py`：队列、队列项、时间项的增删改查与排序
- `app/api/history.py`：历史索引合并检索、单条历史详情提取
- `app/api/setting.py`：全局设置读取与更新
- `app/api/update.py`：版本检查与更新信息
- `app/api/info.py`：系统信息类接口

> 提示：可对照 `app/models/schema.py` 中对应的 In/Out 模型来理解各端点参数与响应。

### 服务与工具（简述）

- `app/services/system.py`：系统层能力（窗口枚举、休眠/自启设置、电源控制倒计时等）
- `app/services/matomo.py`：埋点上报
- `app/utils/`：日志、常量、设备/安全、进程/日志监控、模拟器路径检索等
- `app/task/`：`MaaManager`、`GeneralManager` 实际执行业务（由 TaskManager 调用）

### 后端运行时序（简化）

1. Electron 主进程启动后端 → Python `main.py`（若非管理员则提权重启）
2. FastAPI 初始化（加载配置、定时器、系统设置） → Uvicorn 监听
3. 前端连接 `WS /api/core/ws` → 后端记录连接并开始心跳
4. `TaskManager.start_startup_queue()` → 发送 `id="TaskManager" type="Signal" data={ newTask }`，前端自动创建调度台
5. 用户通过 REST 创建/停止任务 → TaskManager 异步执行并通过 WS 持续回推 Update/Info/Message/Signal
6. 任务完成/异常 → `Signal: Accomplish`；若配置电源操作 → 倒计时与系统操作

---

## 前端（Electron + Vue 3）

### 主进程与预加载（Electron）

- `frontend/electron/main.ts`

  - 环境管理：检查/下载 Python、Git、依赖安装、快速安装包处理
  - 后端进程：`startBackend/stopBackend`（通过 child_process 启动/终止 Python 后端）
  - 托盘/窗口：创建窗口、托盘、标题栏、主题/多屏缩放最小尺寸适配、窗口状态持久化
  - 日志：日志文件管理、清理旧日志
  - IPC 通道（部分）：
    - `start-backend` / `stop-backend` / `sync-backend-config`
    - 窗口控制：最小化/最大化/关闭、移动窗口
    - 文件/对话框：选择文件夹/文件、打开链接、打开文件、在资源管理器中显示
    - 配置：`load-config/save-config/reset-config`（前端配置 front-end）

- `frontend/electron/preload.ts`
  - `contextBridge.exposeInMainWorld('electronAPI', { ... })`
  - 将主进程能力以安全 API 暴露给渲染进程（含重启应用、环境巡检、后端启动/关闭、托盘设置、日志操作等）

### 渲染进程（Vue 应用）

- `frontend/src/main.ts`

  - 设置 `OpenAPI.BASE`（REST 基础 URL）
  - 初始化镜像管理器与调度中心逻辑（预加载 handler）
  - 注册路由、AntD、全局错误处理

- `frontend/src/router/index.ts`

  - 路由表（初始化/主页/脚本/计划/队列/调度中心/模拟器/历史/设置/日志等）
  - 路由守卫：未初始化时强制进入初始化页；首次进入时优先落地初始化页

- `frontend/src/App.vue`
  - 布局容器：标题栏、应用布局、更新弹窗、电源倒计时、WebSocket 消息监听、应用关闭遮罩等

### WebSocket 组合式（核心）

- `frontend/src/composables/useWebSocket.ts`（关键）
  - 连接配置：`BASE_WS_URL=ws://localhost:36163/api/core/ws`、心跳、超时、重连、后端监控
  - 全局持久化存储（挂载到 `window[Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')]`）：
    - `wsRef/status/subscriptions/cacheMarkers/cachedMessages` 等
    - `backendStatus` 与自动重启后端（调用 Electron API）
  - 订阅系统
    - `subscribe({type?, id?, needCache?}, handler)` / `unsubscribe(id)`
    - 支持 type/id 精确过滤与消息缓存回放（TTL/队列大小/引用计数）
  - 心跳/自动重连
    - Ping/Pong 与断线重连（指数退避），达最大次数弹窗提示选择“重启应用/仅重启后端”
  - 与业务集成
    - `TaskManager` 的 `Signal: { newTask }` → 在 `schedulerHandlers` 中自动创建调度台标签

> 详见项目文档：`docs/useWebSocket_Analysis.md` 与 `docs/useWebSocket_API_Reference.md`

### 业务与 API

- `frontend/src/api/*`
  - OpenAPI 生成的 `Service` 与模型，封装所有 REST 接口
- `frontend/src/composables/useScriptApi.ts` 等
  - 对 `Service` 的二次封装（错误提示、loading 管理、组装前端所需数据结构）
- `frontend/src/views/scheduler/*`
  - 调度中心视图与 `schedulerHandlers`：处理 WS 事件（如创建新调度台、更新任务进度、显示日志/消息）

### 前端运行时序（简化）

1. Electron 启动渲染进程（Vue 应用）
2. Vue 初始化 → `useWebSocket` 建立 WS 连接（或触发后端启动 → 稍后连接）
3. 收到 `TaskManager` 的 `newTask` 信号 → 自动创建调度台标签并订阅对应任务消息
4. 用户通过页面发起 REST 请求（脚本/队列/计划/用户等 CRUD；任务启动/停止；系统设置）
5. 所有任务状态变更与日志通过 WS 推流，UI 实时刷新

---

## 逐文件简易分析清单

> 仅列出核心或常用入口；更多辅助/工具文件可按名称直观理解，或通过 IDE 全局检索快速定位。

### 后端（app/\*）

- `main.py`：后端入口、权限/服务/生命周期管理
- `app/api/`
  - `__init__.py`：聚合并导出各 `router`
  - `core.py`：WebSocket、关闭后端
  - `dispatch.py`：任务开始/停止、电源操作
  - `scripts.py`：脚本 CRUD/导入导出/排序
  - `plan.py`：计划 CRUD/排序
  - `queue.py`：队列/队列项/时间项 CRUD/排序
  - `history.py`：历史数据检索与详情提取
  - `setting.py`：全局设置读取与更新
  - `update.py`：前端版本检查
  - `info.py`：系统信息接口
- `app/core/`
  - `__init__.py`：导出 `Broadcast/Config/MainTimer/TaskManager/EmulatorManager`
  - `broadcast.py`：进程内发布-订阅
  - `config.py`：配置/数据库/文件迁移/统一 WS 输出/CRUD 汇总
  - `task_manager.py`：任务生命周期（创建/执行/停止/收尾）与消息推送
  - `timer.py`：秒/小时定时器、静默 BossKey、定时唤起队列
  - `emulator_manager.py`：模拟器管理（启动/关闭/检测）
- `app/models/`
  - `schema.py`：全部 API 的 In/Out 模型 + `WebSocketMessage`
  - 其他模型（如 `config.py` 同名）为配置对象结构定义
- `app/services/`
  - `system.py`：系统级操作（电源、窗口、计划任务等）
  - `matomo.py`：统计上报
  - `update.py/notification.py`：更新/通知相关
- `app/task/`
  - `MAA.py`/`general.py` 等：具体任务执行器（被 `TaskManager` 调用）

### 前端（frontend/\*）

- `electron/`
  - `main.ts`：主进程入口、环境/后端进程/托盘/窗口/IPC
  - `preload.ts`：渲染可用的安全 API 暴露
- `src/`
  - `main.ts`：Vue 启动入口
  - `App.vue`：根布局与全局组件（WS 监听、更新弹窗、倒计时等）
  - `router/index.ts`：路由与守卫
  - `composables/useWebSocket.ts`：WS 连接/订阅/重连/后端监控（核心）
  - `views/scheduler/*`：调度中心与消息处理器
  - `api/*`：OpenAPI 生成的 REST 封装
  - `utils/*`：日志、镜像、类型、配置等

---

## WebSocket 消息协议与关键交互

- `WebSocketMessage`
  - `Update`：列表/进度/日志等数据更新（如 `task_list/task_dict/user_list/log`）
  - `Info`：信息/警告/错误（`{ Error|Warning|Info: string }`）
  - `Message`：显式对话框请求（标题/内容/类型）
  - `Signal`：程序信号（`{ Accomplish|Ping|Pong|power|newTask|Closed }` 等）
- 典型交互
  - 启动时：后端 `TaskManager` → `id="TaskManager" type="Signal" data={ newTask }` → 前端自动创建调度台并订阅
  - 任务执行：后端持续发送 `Update/Info/Message` 更新 UI
  - 任务收尾：`Signal: Accomplish`；全局电源标志变化时，发送倒计时消息并触发系统操作

---

## 开发者提示

- 新增 REST：在 `app/api/*.py` 中添加路由与入参/出参模型（`app/models/schema.py`），经由 `main.py` 自动注册
- 新增 WS 推送：通过 `Config.send_json(WebSocketMessage(...).model_dump())`；前端用 `useWebSocket.subscribe({ type?, id? }, handler)` 精确订阅
- 调试 WS：`docs/useWebSocket_Analysis.md` / `docs/useWebSocket_API_Reference.md` 提供已实现的调试点与使用示例
- 任务扩展：在 `app/task/*` 新增 Manager 并在 `TaskManager.run_task()` 按类型分发

---

## 参考文档

- `docs/Backend_Task_Scheduling_and_WebSocket_Messages.md`
- `docs/TaskManager_WebSocket_Implementation.md`
- `docs/useWebSocket_Analysis.md`
- `docs/useWebSocket_API_Reference.md`

> 本文与上述文档互补：本文更偏架构与导航，其他文档提供具体实现与示例。

## 1. 数据契约（Data Contract）

### 1.1 WebSocketMessage（后端 → 前端）

```json
{
  "id": "<string>",
  "type": "Update | Message | Info | Signal",
  "data": { "...": "对象，因 type 而异" }
}
```

- 来源：`app/models/schema.py::WebSocketMessage`
- 约束：`type ∈ {Update, Message, Info, Signal}`，`id`用于订阅过滤与路由
- 典型 id：`TaskManager`（系统级）；任务运行时用具体 `task_id`

常见数据体（data）示例：

- Update.task_dict（队列构建后一次性下发）

```json
{
  "task_dict": [
    {
      "script_id": "<uuid>",
      "status": "等待|运行|完成|跳过|异常",
      "name": "<string>",
      "user_list": [
        {
          "user_id": "<uuid>",
          "status": "等待|运行|完成|跳过|异常",
          "name": "<string>"
        }
      ]
    }
  ]
}
```

- Update.task_list（运行中反复更新，清理掉 user_list 初值后逐项推进）

```json
{
  "task_list": [
    {
      "script_id": "<uuid>",
      "status": "等待|运行|完成|跳过|异常",
      "name": "<string>"
    }
  ]
}
```

- Update.user_list（当前运行脚本的活跃用户列表，仅在该脚本运行时出现）

```json
{
  "user_list": [
    { "user_id": "<uuid>", "status": "运行|完成|异常", "name": "<string>" }
  ]
}
```

- Update.log（逐条或批量追加日志）

```json
{ "log": "<string>" }
```

- Info

```json
{ "Error": "错误信息" }
{ "Warning": "警告信息" }
{ "Info": "普通信息" }
```

- Message（弹框请求）

```json
{
  "type": "Info|Warning|Error|Countdown",
  "title": "<string>",
  "message": "<string>"
}
```

- Signal

```json
{ "Accomplish": "无描述" }
{ "Ping": "无描述" }
{ "Pong": "无描述" }
{ "newTask": "<task_uuid>" }
{ "power": "NoAction|KillSelf|Sleep|Hibernate|Shutdown|ShutdownForce" }
{ "Closed": "后端已安全关闭" }
```

### 1.2 REST（前端 → 后端）

- 创建任务：`POST /api/dispatch/start`（`app/api/dispatch.py::add_task`）

```json
{
  "mode": "自动代理|人工排查|设置脚本",
  "taskId": "<queue_id|script_id|user_id>"
}
```

响应：

```json
{
  "code": 200,
  "status": "success",
  "message": "操作成功",
  "websocketId": "<task_uuid>"
}
```

- 停止任务：`POST /api/dispatch/stop`

```json
{ "taskId": "<task_uuid|ALL>" }
```

- 设置电源标志：`POST /api/dispatch/set/power`

```json
{ "signal": "NoAction|Shutdown|ShutdownForce|Hibernate|Sleep|KillSelf" }
```

- 脚本/队列/计划/用户/模拟器/Webhook 等 CRUD：详见 `app/api/*.py` 与 `app/models/schema.py`

---

## 2. 端到端时序（E2E Sequence）

以“应用启动 → 自动拉起启动队列 → 前端创建调度台 → 任务执行/收尾”为例：

1. Electron 主进程拉起后端 → Python `main.py` 完成 lifespan 初始化
2. 前端渲染端建立 WS 到 `/api/core/ws`
3. 后端记录连接并启动心跳；`TaskManager.start_startup_queue()` 遍历勾选 StartUpEnabled 的队列：
   - 为每个队列调用 `TaskManager.add_task("自动代理", queue_id)`
   - 通过 WS 发送：`{ id:"TaskManager", type:"Signal", data:{ "newTask": "<task_uuid>" } }`
4. 前端 `useWebSocket` 分发给 `schedulerHandlers`，自动创建调度台 Tab，并订阅 `id=<task_uuid>` 消息
5. 后端 `run_task()`：
   - 构建 `task_list` → WS Update 下发
   - 逐脚本执行（MAA/General Manager）→ 周期性 WS Update/Info/Message
6. 子任务完成/异常 → 更新 `task_list` → WS Update
7. 队列跑完 → WS Signal: Accomplish
8. 若全局 `Config.power_sign` 非 `NoAction` 且任务清空 → WS Message Countdown → `System.start_power_task()`

时序要点：

- WS 为单连接；重连采用前端指数退避 + 后端超时 Ping/Pong
- 首次连接即触发启动队列；断线后后端进程会自杀式退出（KillSelf），由前端负责重启

---

## 3. 状态机与心跳（State Machine & Heartbeat）

### 3.1 前端 WebSocket 状态（`useWebSocket.ts`）

- WebSocketStatus：`连接中` → `已连接` → `已断开` | `连接错误`
- Auto Reconnect：最大 5 次，退避系数 1.5，上限 30s；失败弹窗提供“重启应用/重启后端”
- BackendStatus：`unknown|starting|running|stopped|error`，周期检测，失败自动尝试重启后端

### 3.2 心跳

- 前端：定时发送 `Signal: Ping`
- 后端：收到 Ping 立即回 `Pong`；若超时则主动断连

---

## 4. 错误/边界与恢复策略

- 单连接约束：第二个 WS 连接会被拒绝
- 断线处理：后端 `connect_websocket` 超时或断连 → 设置 `Config.websocket=None` → `System.set_power("KillSelf")`
- 前端恢复：`useWebSocket` 自动重连；失败弹窗引导“重启后端/重启应用”；也可调用 `electronAPI.startBackend()`
- 任务并发：`TaskManager.add_task` 对同一脚本或同一队列做互斥检查，重复将报错并通过 REST 统一返回
- 数据迁移与一致性：`Config.check_data()` 处理 `v1.7→v1.8→v1.9`；I/O 操作均使用 await，注意异常捕获
- 电源操作：当 `Config.power_sign` 设置且任务清空后才触发倒计时；可以 `POST /api/dispatch/cancel/power` 取消

---

## 5. 改造与扩展（Where to Change）

- 新增后端 REST：在 `app/api/<feature>.py` 增加路由 + 入参/出参模型（`app/models/schema.py`）；在 `main.py` 自动注册
- 新增后端 WS 推送：在任何协程中引入 `from app.core import Config`，调用 `await Config.send_json(WebSocketMessage(...).model_dump())`
- 新增任务类型：
  1. 在 `app/task/` 增加 Manager（参考 `MAA.py`/`general.py`）
  2. 在 `TaskManager.run_task()` 中按类型分支创建 Manager
  3. 在前端 `schedulerHandlers` 添加对应消息处理
- 扩展前端订阅：`useWebSocket.subscribe({ type?, id?, needCache? }, handler)`；需要回放历史时置 `needCache: true`
- 接入新弹窗类型：前端在 `WebSocketMessageListener` / `schedulerHandlers` 里按 `Message.data.type` 分支处理
- 接入外部资源：后端通过 `app.mount('/api/res/...', StaticFiles(...))` 暴露；前端直接 HTTP 访问

---

## 6. 代码定位速查（Symbol → File）

- 应用入口（后端）：`main.py` → lifespan → Uvicorn → 路由注册/静态资源
- WebSocket 端点：`app/api/core.py::connect_websocket`
- WebSocket 消息模型：`app/models/schema.py::WebSocketMessage`
- 任务调度入口：`app/core/task_manager.py::TaskManager.add_task/run_task/remove_task/start_startup_queue`
- 每秒/每小时任务：`app/core/timer.py::MainTimer.second_task/hour_task`
- 配置中心：`app/core/config.py::AppConfig`（CRUD/迁移/发送 WS）
- 电源与系统操作：`app/services/system.py`
- Electron 主进程：`frontend/electron/main.ts`（后端启动/窗口/托盘/IPC）
- WebSocket 客户端：`frontend/src/composables/useWebSocket.ts`
- 任务调度 UI：`frontend/src/views/scheduler/*` + `schedulerHandlers.ts`
- OpenAPI 封装：`frontend/src/api/*`（`Service`、模型、请求基址 `OpenAPI.BASE`）

---

## 7. 常见开发任务模板（AI 可复用）

- 新增“系统公告”推送：

  1. 后端定义 REST：`app/api/notification.py`，写一个 `POST /api/notification/broadcast` 接口
  2. 调用 `Config.send_json(WebSocketMessage(id:"Main", type:"Message", data:{ type:"Info", title:"公告", message:"..." }))`
  3. 前端在 `WebSocketMessageListener` 增加 `Message` 分支对 `id=="Main"` 进行弹窗

- 新增“任务进度条”字段：

  1. 扩展 `TaskInfo.progress` 的结构；在 `MaaManager/GeneralManager` 中按阶段更新
  2. 通过 WS `Update` 推送 `{ progress: { current, total } }`
  3. 前端 `schedulerHandlers` 消费并渲染进度条

- 接入第三方模拟器：
  1. 在 `app/models/schema.py` 的 `EmulatorConfig_Data.Type` 枚举中增加类型
  2. `app/utils/emulator/` 增加路径/窗口识别逻辑
  3. `app/services/system.py` 补充相应操作

---

## 8. 测试清单（Smoke Checklist）

- 启动后端（Electron 拉起）→ 前端 WS 成功连接，状态变为“已连接”
- 启动时队列：收到 `TaskManager.newTask`，自动出现调度台
- 手动启动一个脚本：`POST /api/dispatch/start` → 看 `websocketId`，并在 UI 收到该 id 的 Update/Info/Message
- 心跳：断网 45s → 看到前端自动重连；多次失败弹窗提示；选择“重启后端”后恢复连接
- 电源倒计时：设置某队列为 `AfterAccomplish=KillSelf`，跑完弹窗倒计时并执行

---

## 9. 附：设计约束与理念

- 单通道 WS + 单连接，确保状态一致性与简化并发
- 强契约（Pydantic）+ 明确的类型定义，保证前后端数据面稳定
- 异步化（AsyncIO）+ 解耦（Broadcast/WS/REST），降低耦合便于扩展

如果你需要生成 openapi, 请让用户进行生成
