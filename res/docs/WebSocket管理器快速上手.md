# WebSocket 子系统快速上手

本文档描述 AUTO-MAS 重构后的 WebSocket 架构（issue #295）。

## 总体结构

前后端之间只保留**一条主 WebSocket 连接**（`/api/core/ws`），任务、调度器、更新、电源操作等全部业务消息统一走该连接。后端另有独立的**出站客户端**用于连接外部第三方进程（如 Koishi），与主连接分层管理，互不混用状态。

```
前端 (Electron/Vue)                       后端 (FastAPI)
┌─────────────────────────┐              ┌──────────────────────────────┐
│ services/websocket      │   唯一主连接  │ app/core/ws                  │
│  ├ connection.ts 连接层  │◄───────────►│  ├ manager.py MainConnection │
│  └ subscriptions.ts 订阅 │              │  ├ dispatcher.py Dispatcher  │
│ composables/            │              │  ├ publisher.py Publisher    │
│  ├ useWebSocket.ts 门面  │              │  └ protocol.py 消息类别常量   │
│  └ useAppLifecycle.ts    │              │ app/utils/websocket.py       │
│    生命周期协调器          │              │   出站客户端 (Koishi)  ───────┼──► 第三方进程
└─────────────────────────┘              └──────────────────────────────┘
```

## 统一消息信封

所有主连接消息使用统一信封，前后端均按 `id + type` 路由：

```json
{
  "id": "task-or-request-id",
  "type": "task.info.updated",
  "data": {}
}
```

- `id` 标识任务、请求或业务会话（如 `Main`、`TaskManager`、任务 UUID）
- `type` 标识消息类别，点分小写命名
- 请求与响应（如有）使用相同 `id`，通过 `data.requestId` 关联
- Python 模型见 `app/models/schema.py`（`WSEnvelope` 与 `WS*Data`），TypeScript 类型见 `frontend/src/services/websocket/types.ts`，两侧保持一致

## 消息类别总览

| id | 后端 → 前端 | 前端 → 后端 |
|---|---|---|
| `<taskId>` | `task.info.updated` / `task.log.updated` / `task.notice` / `task.completed` | — |
| `TaskManager` | `task.created` | — |
| `Main` | `backend.shutdown.ready` / `frontend.close.requested` / `power.countdown.updated` / `power.countdown.cancelled` / `power.sign.updated` | — |
| `Update` | `update.progress` / `update.completed` / `update.failed` / `update.cancelled` | — |
| `GameSign` | `gamesign.result.updated` | — |
| `EmulatorManager` | `emulator.notice` | — |
| `ArknightsPCToolkit` | `toolkit.notice` | — |

完整常量定义：`app/core/ws/protocol.py`。

## 后端用法

### 发送消息（业务模块统一入口）

```python
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData

await Publisher.send(
    id=task_id,
    type=protocol.TASK_NOTICE,
    data=WSTaskNoticeData(level="error", message="任务出现异常"),
)
```

主连接未就绪时消息**直接丢弃**（记录低级别日志），不缓存、不重放。关键消息请使用 `WS*Data` 模型构造，避免无边界字典。

### 处理前端消息

```python
from app.core.ws import Dispatcher, protocol

def handle(envelope):  # 同步或异步均可
    ...

unregister = Dispatcher.register(protocol.ID_MAIN, "some.type", handle)
```

未找到处理器的消息记录 debug 日志后丢弃。当前版本前端业务操作均走 HTTP API，主连接入站分发保留为架构入口。

### 心跳

主连接心跳依赖 WebSocket **协议层** ping/pong，由 uvicorn 配置（`main.py` 中 `ws_ping_interval=20, ws_ping_timeout=20`）。不存在应用层业务心跳消息。

### 出站客户端（第三方进程）

`app/utils/websocket.py` 的 `ws_client_manager` 管理后端作为客户端的出站连接（Koishi 通知）。心跳同样使用协议层 ping/pong；`type=="command"` 的入站消息经显式注册的强类型命令表（`app/api/ws_command.py`）执行，命令执行器在 `main.py` 启动时注入。

## 前端用法

### 订阅与发送

```ts
import { subscribe, unsubscribe, send } from '@/composables/useWebSocket'
import { WS_TASK_NOTICE, type WSTaskNoticeData } from '@/services/websocket/types'

const subscriptionId = subscribe({ id: taskId, type: WS_TASK_NOTICE }, message => {
  const data = message.data as unknown as WSTaskNoticeData
  // ...
})
unsubscribe(subscriptionId) // 幂等
```

- 同一 `id + type` 可多次订阅，按订阅顺序调用；单个 handler 异常不影响其他订阅者
- 找不到订阅者的消息直接丢弃，无缓存、无重放；后订阅者不会收到订阅前的消息
- 页面初始数据通过 HTTP API 获取快照，WS 只用于后续增量更新

### 生命周期协调器

`@/composables/useAppLifecycle` 持有应用级常驻订阅与后端进程恢复决策：

- 常驻订阅：`backend.shutdown.ready`、`frontend.close.requested`、`power.countdown.updated/cancelled`，在建立连接前注册，重连不重复注册，页面切换不取消
- `closeApp()`：退出并关闭后端 —— POST `/api/core/close` → 等待 `backend.shutdown.ready`（30 秒超时）→ 等待后端进程退出 → 超时才 taskkill → 关闭前端；关闭流程期间禁止自动重连与自动重启
- 异常断开：连接层一轮重连（5 次退避）失败后，由协调器查询后端进程状态 —— 进程已死则自动重启后端（上限 3 次，超限弹窗提示重启应用），进程存活则延迟继续重连
- 有意重启后端：标题栏「更新后端」在关闭后端前调用 `beginIntentionalBackendRestart()`，窗口期内的断开按计划内处理（不提示、不自动重启后端、一轮重连失败也不升级弹窗），由后端重新连上、进入关闭流程或 10 分钟兜底超时结束。两条更新链路都走这个窗口：旧链路由初始化流程重新拉起后端，Runtime 链路（`useBackendRuntimeUpdate` 的 `start` / `retry`，收口在 `settle`）由 Runtime 停机后 `workspace sync` 再重新监督。协调器都不得插手——旧链路会与初始化流程抢同一个进程，Runtime 链路会让 `workspace sync` 撞上「后端仍在跑」而失败

## 连接状态

前端连接层状态机：`idle` → `connecting` → `open` ⇄ `reconnecting`，`closed` 为退出流程终态，`superseded` 为"被另一个前端接管"终态（不再自动重连，显式 `connect` / `reconnectNow` 仍可重新接管）。同时最多存在一个连接尝试和一个重连计时器，连接成功后退避状态清零。

后端第二条主连接接入时，**新连接替换旧连接**（旧连接被关闭），避免休眠恢复后残留死连接阻塞重连。旧连接以应用级关闭码 **`4001`**、reason `replaced-by-new-connection` 关闭（常量 `CLOSE_CODE_REPLACED` / `WS_CLOSE_CODE_REPLACED`，见 `app/core/ws/protocol.py` 与 `services/websocket/types.ts`）；前端收到该码即进入 `superseded`，只提示一次、不重连，避免两个窗口互相踢下线。后端关闭流程中拒绝新连接仍使用 `1001`。
