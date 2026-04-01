# WebSocket 双向通信实战教程（基于 MAS 现有结构）

本教程 **不** 是从零开始写连接管理器，而是**利用 MAS 现有的 `WSClientManager`，实现前后端双向通信**。

目标：让你明白为什么 MAS 这样设计，以及怎么扩展它来支持一个完整的前后端双向场景。

---

## 0. MAS 现有结构回顾

你项目里已有：

```
app/utils/websocket.py  -> WSClientManager（连接管理、历史、广播）
app/api/ws_debug.py     -> /api/ws_debug/live 端点
frontend/src/views/WSdev.vue  -> 前端调试页面
```

`WSClientManager` 已经提供的能力：

1. **连接管理**：`add_debug_connection / remove_debug_connection`
2. **消息历史**：`_message_history` 按客户端存储
3. **广播机制**：`_broadcast` 推送给所有连接
4. **任务调度**：`_tasks` 管理后台任务
5. **系统通道**：`KOISHI_CLIENT_NAME` 示例

你要做的：**复用这些能力，增加"系统级前端通道"和"双向业务消息处理"**。

---

## 1. 协议设计（扣在 MAS 现有结构上）

MAS 已经用 JSON 信封，格式建议统一为：

```json
{
  "type": "command",
  "request_id": "req-123",
  "timestamp": 1760000000.123,
  "data": {
    "action": "echo",
    "payload": { "text": "hello" }
  }
}
```

消息类型映射：

| type | 方向 | 含义 | 例子 |
|------|------|------|------|
| `init` | 后->前 | 初始化，包含历史、客户端列表 | `{"type": "init", "clients": [...], "history": {...}}` |
| `ping` | 前->后 | 心跳请求 | `{"type": "ping", "timestamp": 123}` |
| `pong` | 后->前 | 心跳响应 | `{"type": "pong", "timestamp": 123}` |
| `command` | 前->后 | 下发命令 | `{"type": "command", "request_id": "r1", "data": {...}}` |
| `ack` | 后->前 | 命令反馈 | `{"type": "ack", "request_id": "r1", "data": {"success": true}}` |
| `event` | 后->前 | 事件推送 | `{"type": "event", "data": {"event": "demo_tick", "value": 123}}` |

---

## 2. 后端：基于 WSClientManager 的扩展

### 2.1 第一步：在管理器里定义系统级前端通道（如果你要开发的是MAS系统级WS）

位置：`app/utils/websocket.py` 的 `WSClientManager.__init__`:

```python
class WSClientManager:
    KOISHI_CLIENT_NAME = "Koishi"
    FRONTEND_DEMO_CLIENT_NAME = "MAS-Frontend-System"  # ← 新增
    
    def __init__(self):
        self._clients: Dict[str, WebSocketClient] = {}
        self._system_clients: set[str] = set()
        self._message_history: Dict[str, List[Dict[str, Any]]] = {}
        self._debug_connections: List[Any] = []
        
        # ← 新增：初始化系统前端通道
        self._system_clients.add(self.FRONTEND_DEMO_CLIENT_NAME)
        self._message_history[self.FRONTEND_DEMO_CLIENT_NAME] = []
        self._frontend_demo_task: Optional[asyncio.Task] = None
```

作用：

- 定义虚拟客户端，不连外部服务
- 作为后端 -> 前端的消息通道
- 写入历史、可被调试前端订阅

### 2.2 第二步：增加记录&广播接口

位置：`WSClientManager` 增加新方法：

```python
async def record_frontend_demo_number(self, value: int):
    """
    记录前端系统级演示数字，并广播给调试前端。
    
    数据会自动进入消息历史，可供前端初始化恢复。
    同时立即广播给所有实时连接。
    """
    # 1. 写入历史
    await self._record_message(
        self.FRONTEND_DEMO_CLIENT_NAME,
        "received",
        {"type": "demo_number", "value": value},
    )
    
    # 2. 立即广播给调试前端（实时看板）
    await self._broadcast({
        "type": "demo_tick",
        "channel": self.FRONTEND_DEMO_CLIENT_NAME,
        "value": value,
        "timestamp": time.time(),
    })
```

为什么分两步：

- `_record_message`：进历史库，前端重连时 `init` 会包含
- `_broadcast`：实时推送给当前连接，看板立即更新

### 2.3 第三步：定时推送任务（后端主动）

位置：`WSClientManager` 增加新方法：

```python
async def _frontend_demo_loop(self):
    """
    后端主动推送循环：每3秒生成随机数。
    
    关键特性：
    - 根据"是否有前端连接"自动启停
    - 避免无人订阅时浪费资源
    - 避免多开页面导致消息翻倍
    """
    try:
        while self._debug_connections:  # 有连接就继续推送
            await self.record_frontend_demo_number(random.randint(0, 999))
            await asyncio.sleep(3.0)
    except asyncio.CancelledError:
        self._logger.info("前端系统级 WS 演示任务已停止")
        raise
```

### 2.4 第四步：连接生命周期管理（启停定时任务）

修改 `add_debug_connection` 和 `remove_debug_connection`：

```python
def add_debug_connection(self, ws: Any):
    """
    调试前端连接 -> 启动定时任务。
    
    当首个前端连接进入时，启动演示推送任务。
    """
    self._debug_connections.append(ws)
    # ← 新增：启动定时任务
    if not self._frontend_demo_task or self._frontend_demo_task.done():
        self._frontend_demo_task = asyncio.create_task(self._frontend_demo_loop())

def remove_debug_connection(self, ws: Any):
    """
    调试前端断开 -> 停止定时任务。
    
    当最后一个前端连接离线时，停止推送。
    """
    if ws in self._debug_connections:
        self._debug_connections.remove(ws)
    # ← 新增：无连接时停止任务
    if not self._debug_connections and self._frontend_demo_task:
        self._frontend_demo_task.cancel()
        self._frontend_demo_task = None
```

### 2.5 第五步：轻薄化 WS 端点

位置：`app/api/ws_debug.py` 的 `websocket_live`:

```python
@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """
    前端调试页的 WS 实时通道。
    
    责任边界清晰：
    - 生命周期管理 ✓ (accept/add/remove)
    - 初始化推送 ✓ (history/clients)
    - 心跳处理 ✓ (ping/pong)
    - 定时推送 ✗ (由管理器负责)
    - 消息分发 ✗ (由管理器负责)
    """
    await websocket.accept()
    ws_client_manager.add_debug_connection(websocket)

    logger.info(f"调试前端已连接: {websocket.client}")

    try:
        # 1. 初始化：推送当前客户端列表
        clients = ws_client_manager.list_clients()
        await websocket.send_json({
            "type": "init",
            "clients": list(clients.values()),
        })

        # 2. 初始化：推送系统通道信息
        await websocket.send_json({
            "type": "system_channel",
            "name": ws_client_manager.FRONTEND_DEMO_CLIENT_NAME,
            "status": "connected",
            "description": "后端每3秒推送随机数用于前端实时渲染示例",
        })

        # 3. 持续监听心跳
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    
    except WebSocketDisconnect:
        logger.info(f"调试前端已断开: {websocket.client}")
    finally:
        ws_client_manager.remove_debug_connection(websocket)
```

关键理解：

- 端点职责是"连接管理 + 初始化 + 心跳"
- 不自己生成业务消息，让管理器做
- 多个连接共用一个定时任务（管理器统一调度）

---

## 3. 前端：从零实现消费侧

### 3.1 建立连接（生命周期）

位置：`frontend/src/views/WSdev.vue`:

```ts
import { OpenAPI } from '@/api'  // 获取真实后端地址
import { ref, onMounted, onUnmounted } from 'vue'

let ws: WebSocket | null = null
const connected = ref(false)
const currentValue = ref(0)
const values = ref<number[]>([])

function buildWsUrl(): string {
  const base = (OpenAPI.BASE || '').trim()
  if (base.startsWith('http://')) {
    return base.replace('http://', 'ws://') + '/api/ws_debug/live'
  }
  if (base.startsWith('https://')) {
    return base.replace('https://', 'wss://') + '/api/ws_debug/live'
  }
  // 回退
  return `ws://${window.location.host}/api/ws_debug/live`
}

function connect() {
  const url = buildWsUrl()
  console.log('Connecting to:', url)
  
  ws = new WebSocket(url)
  
  ws.onopen = () => {
    console.log('WS connected')
    connected.value = true
  }
  
  ws.onmessage = (event) => {
    handleMessage(JSON.parse(event.data))
  }
  
  ws.onerror = (error) => {
    console.error('WS error:', error)
  }
  
  ws.onclose = () => {
    console.log('WS closed')
    connected.value = false
    // 5秒后重连
    setTimeout(connect, 5000)
  }
}

onMounted(() => {
  connect()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})
```

### 3.2 处理消息分发

```ts
function handleMessage(msg: any) {
  switch (msg.type) {
    case 'init':
      // 初始化，来自服务器的冷启动数据
      console.log('Init:', msg)
      break
    
    case 'system_channel':
      // 系统通道信息
      console.log('System channel:', msg)
      break
    
    case 'pong':
      // 心跳反馈（暂时不用做什么）
      break
    
    case 'demo_tick':
      // 实时随机数推送
      currentValue.value = msg.value
      values.value.push(msg.value)
      if (values.value.length > 20) {
        values.value.shift()  // 只保留最近20个
      }
      break
    
    case 'ack':
      // 命令反馈
      console.log('Ack:', msg)
      break
    
    default:
      console.log('Unknown message type:', msg.type)
  }
}
```

### 3.3 发送命令（前端 -> 后端）

```ts
function sendCommand(action: string, payload: Record<string, any>) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WS not open')
    return
  }
  
  const requestId = `req-${Date.now()}`
  const msg = {
    type: 'command',
    request_id: requestId,
    timestamp: Date.now() / 1000,
    data: { action, payload },
  }
  
  ws.send(JSON.stringify(msg))
  console.log('Sent:', msg)
}
```

### 3.4 心跳实现

```ts
let heartbeatInterval: NodeJS.Timeout | null = null

function startHeartbeat() {
  heartbeatInterval = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() / 1000 }))
    }
  }, 20000)  // 每20秒一次
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval)
    heartbeatInterval = null
  }
}

// 在 onopen 启动，onclose 停止
ws.onopen = () => {
  connected.value = true
  startHeartbeat()
}

ws.onclose = () => {
  connected.value = false
  stopHeartbeat()
  setTimeout(connect, 5000)
}
```

---

## 6. 验收清单（用于自检）

完成以下检查点，说明你理解了双向链路：

- [ ] 能解释为什么 WS 和 HTTP 要同源
- [ ] 能修改定时任务的推送周期（从 3s 改成 1s）
- [ ] 能添加一个新的 `event` 类型并在前端显示
- [ ] 能在 WSdev 页面改一个动作，让后端能收到并处理
- [ ] 能看懂管理器的 `_broadcast`, `_record_message` 做了什么
- [ ] 能解释"为什么要检查 `_debug_connections` 的长度"

---

## 7. 下一步扩展

### 扩展 1：从演示改成真实事件

```python
# 后端
async def push_queue_status():
    """推送队列状态而不是随机数"""
    status = get_queue_status()  # 真实业务
    await self.record_message(
        self.FRONTEND_DEMO_CLIENT_NAME,
        "received",
        {"type": "queue_status", "status": status},
    )
```

### 扩展 2：双向命令响应

```python
# 后端处理前端的 command，并回 ack
if msg.get("type") == "command":
    request_id = msg.get("request_id")
    action = msg.get("data", {}).get("action")
    result = handle_action(action)
    
    await websocket.send_json({
        "type": "ack",
        "request_id": request_id,
        "data": result,
    })
```

### 扩展 3：消息订阅过滤

```python
# 让前端只订阅某些事件
await websocket.send_json({
    "type": "subscribe",
    "channels": ["queue_status", "task_progress"],
})
```

这些扩展都是把管理器现有的逻辑复用和变化。
