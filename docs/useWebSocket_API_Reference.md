# useWebSocket API 参考文档

## 概述

`useWebSocket()` 组合式函数提供了完整的 WebSocket 通信接口，包含消息订阅、连接管理、状态监控等核心功能。

## 导出函数详解

### 1. subscribe() - 订阅消息

```typescript
const subscribe = (
  filter: SubscriptionFilter,
  handler: (message: WebSocketBaseMessage) => void
): string
```

#### 参数说明

**filter: SubscriptionFilter**
```typescript
interface SubscriptionFilter {
  type?: string      // 消息类型过滤器（可选）
  id?: string        // 消息ID过滤器（可选）
  needCache?: boolean // 是否启用缓存回放（可选）
}
```

**handler: Function**
- 消息处理回调函数
- 参数: `message: WebSocketBaseMessage`
- 无返回值

#### 返回值
- `string`: 唯一的订阅ID，用于后续取消订阅

#### 使用示例

```typescript
// 订阅所有消息
const allMsgSub = subscribe({}, (msg) => {
  console.log('收到消息:', msg)
})

// 订阅特定类型消息
const taskSub = subscribe(
  { type: 'TaskUpdate', needCache: true },
  (msg) => {
    console.log('任务更新:', msg.data)
  }
)

// 订阅特定ID消息
const specificSub = subscribe(
  { id: 'TaskManager' },
  (msg) => {
    console.log('任务管理器消息:', msg)
  }
)

// 精确订阅（同时匹配type和id）
const preciseSub = subscribe(
  { type: 'Progress', id: 'task_001', needCache: true },
  (msg) => {
    console.log('特定任务进度:', msg.data)
  }
)
```

#### 特殊功能
- **自动回放**: 如果 `needCache: true`，会立即回放匹配的历史消息
- **过滤优先级**: type + id > type > id > 全部
- **引用计数**: 多个订阅共享缓存，自动管理内存

---

### 2. unsubscribe() - 取消订阅

```typescript
const unsubscribe = (subscriptionId: string): void
```

#### 参数说明

**subscriptionId: string**
- 由 `subscribe()` 返回的订阅ID
- 必须是有效的订阅ID

#### 使用示例

```typescript
const subId = subscribe({ type: 'TaskUpdate' }, handleTaskUpdate)

// 取消订阅
unsubscribe(subId)

// Vue 组件中的最佳实践
import { onUnmounted } from 'vue'

const setupSubscription = () => {
  const subId = subscribe({ type: 'TaskUpdate' }, handleTaskUpdate)
  
  onUnmounted(() => {
    unsubscribe(subId)
  })
}
```

#### 自动清理
- 自动减少缓存引用计数
- 引用计数为0时清理相关缓存
- 不会影响其他订阅者

---

### 3. sendRaw() - 发送消息

```typescript
const sendRaw = (type: string, data?: any, id?: string): void
```

#### 参数说明

**type: string** (必需)
- 消息类型标识
- 后端用于路由消息

**data: any** (可选)
- 消息负载数据
- 可以是任何可序列化的对象

**id: string** (可选)
- 消息标识符
- 用于消息跟踪和响应匹配

#### 使用示例

```typescript
// 发送简单消息
sendRaw('Hello')

// 发送带数据的消息
sendRaw('TaskStart', {
  taskId: '12345',
  config: { timeout: 30000 }
})

// 发送带ID的消息（便于追踪响应）
sendRaw('GetTaskStatus', { taskId: '12345' }, 'query_001')

// 发送控制信号
sendRaw('Signal', { 
  command: 'pause',
  reason: '用户手动暂停'
}, 'TaskManager')
```

#### 发送条件
- 仅在 WebSocket 连接为 `OPEN` 状态时发送
- 连接异常时静默失败（不抛出异常）
- 自动JSON序列化

---

### 4. getConnectionInfo() - 获取连接信息

```typescript
const getConnectionInfo = (): ConnectionInfo
```

#### 返回值类型

```typescript
interface ConnectionInfo {
  connectionId: string           // 连接唯一标识
  status: WebSocketStatus        // 当前连接状态
  subscriberCount: number        // 当前订阅者数量
  moduleLoadCount: number        // 模块加载计数
  wsReadyState: number | null    // WebSocket原生状态
  isConnecting: boolean          // 是否正在连接
  hasHeartbeat: boolean          // 是否启用心跳
  hasEverConnected: boolean      // 是否曾经连接成功
  reconnectAttempts: number      // 重连尝试次数
  isPersistentMode: boolean      // 是否持久化模式
}
```

#### 使用示例

```typescript
const info = getConnectionInfo()

console.log('连接ID:', info.connectionId)
console.log('连接状态:', info.status)
console.log('订阅者数量:', info.subscriberCount)

// 检查连接是否健康
const isHealthy = info.status === '已连接' && 
                  info.hasHeartbeat && 
                  info.wsReadyState === WebSocket.OPEN

// 监控重连情况
if (info.reconnectAttempts > 0) {
  console.log(`已重连 ${info.reconnectAttempts} 次`)
}
```

#### 调试用途
- 诊断连接问题
- 监控连接质量
- 统计使用情况

---

### 5. status - 连接状态

```typescript
const status: Ref<WebSocketStatus>
```

#### 状态类型

```typescript
type WebSocketStatus = '连接中' | '已连接' | '已断开' | '连接错误'
```

#### 状态说明

| 状态 | 描述 | 触发条件 |
|------|------|----------|
| `'连接中'` | 正在建立连接 | WebSocket.CONNECTING |
| `'已连接'` | 连接成功 | WebSocket.OPEN |
| `'已断开'` | 连接断开 | WebSocket.CLOSED |
| `'连接错误'` | 连接异常 | WebSocket.onerror |

#### 使用示例

```typescript
import { watch } from 'vue'

const { status } = useWebSocket()

// 监听状态变化
watch(status, (newStatus) => {
  console.log('连接状态变化:', newStatus)
  
  switch (newStatus) {
    case '已连接':
      console.log('✅ WebSocket 连接成功')
      break
    case '已断开':
      console.log('❌ WebSocket 连接断开')
      break
    case '连接错误':
      console.log('⚠️ WebSocket 连接错误')
      break
    case '连接中':
      console.log('🔄 WebSocket 连接中...')
      break
  }
})

// 在模板中显示状态
// <div>连接状态: {{ status }}</div>
```

#### 响应式特性
- Vue 响应式 Ref 对象
- 自动更新 UI
- 可用于计算属性和监听器

---

### 6. backendStatus - 后端状态

```typescript
const backendStatus: Ref<BackendStatus>
```

#### 状态类型

```typescript
type BackendStatus = 'unknown' | 'starting' | 'running' | 'stopped' | 'error'
```

#### 状态说明

| 状态 | 描述 | 含义 |
|------|------|------|
| `'unknown'` | 未知状态 | 初始状态，尚未检测 |
| `'starting'` | 启动中 | 后端服务正在启动 |
| `'running'` | 运行中 | 后端服务正常运行 |
| `'stopped'` | 已停止 | 后端服务已停止 |
| `'error'` | 错误状态 | 后端服务异常 |

#### 使用示例

```typescript
const { backendStatus, restartBackend } = useWebSocket()

// 监听后端状态
watch(backendStatus, (newStatus) => {
  console.log('后端状态:', newStatus)
  
  switch (newStatus) {
    case 'running':
      console.log('✅ 后端服务运行正常')
      break
    case 'stopped':
      console.log('⏹️ 后端服务已停止')
      break
    case 'error':
      console.log('❌ 后端服务异常')
      // 可以提示用户或自动重启
      break
    case 'starting':
      console.log('🚀 后端服务启动中...')
      break
  }
})

// 根据状态显示不同UI
const statusColor = computed(() => {
  switch (backendStatus.value) {
    case 'running': return 'green'
    case 'error': return 'red'
    case 'starting': return 'orange'
    default: return 'gray'
  }
})
```

#### 自动管理
- 每3秒自动检测一次
- 异常时自动尝试重启（最多3次）
- 集成 Electron 进程管理

---

## 完整使用示例

```typescript
import { onMounted, onUnmounted, watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'

export default {
  setup() {
    const { 
      subscribe, 
      unsubscribe, 
      sendRaw, 
      getConnectionInfo, 
      status, 
      backendStatus 
    } = useWebSocket()
    
    let taskSubscription: string
    let systemSubscription: string
    
    onMounted(() => {
      // 订阅任务消息
      taskSubscription = subscribe(
        { type: 'TaskUpdate', needCache: true },
        (message) => {
          console.log('任务更新:', message.data)
        }
      )
      
      // 订阅系统消息
      systemSubscription = subscribe(
        { id: 'System' },
        (message) => {
          console.log('系统消息:', message)
        }
      )
      
      // 发送初始化消息
      sendRaw('ClientReady', { 
        timestamp: Date.now() 
      }, 'System')
    })
    
    onUnmounted(() => {
      // 清理订阅
      if (taskSubscription) unsubscribe(taskSubscription)
      if (systemSubscription) unsubscribe(systemSubscription)
    })
    
    // 监听连接状态
    watch([status, backendStatus], ([wsStatus, beStatus]) => {
      console.log(`WS: ${wsStatus}, Backend: ${beStatus}`)
    })
    
    // 获取连接信息
    const connectionInfo = getConnectionInfo()
    
    return {
      status,
      backendStatus,
      connectionInfo,
      sendMessage: (type: string, data: any) => sendRaw(type, data)
    }
  }
}
```

## 最佳实践

### 1. 订阅管理
- 总是在组件卸载时取消订阅
- 使用 `needCache: true` 确保不丢失消息
- 避免重复订阅相同的消息类型

### 2. 错误处理
- 监听连接状态变化
- 根据后端状态调整UI显示
- 实现重连提示和手动重启

### 3. 性能优化
- 精确的过滤条件减少不必要的处理
- 合理使用缓存避免消息丢失
- 及时取消不需要的订阅

### 4. 调试技巧
- 使用 `getConnectionInfo()` 诊断问题
- 开发环境下查看控制台日志
- 监控订阅者数量避免内存泄漏