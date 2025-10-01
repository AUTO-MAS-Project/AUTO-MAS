## 核心架构设计

### 1. 全局持久化存储

```typescript
const WS_STORAGE_KEY = Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')
```

- 使用 `Symbol.for()` 确保全局唯一性
- 存储在 `window` 对象上，实现跨组件共享
- 避免多次实例化，确保连接唯一性

### 2. 状态管理结构

```typescript
interface GlobalWSStorage {
  wsRef: WebSocket | null              // WebSocket 实例
  status: Ref<WebSocketStatus>         // 连接状态
  subscriptions: Ref<Map<string, WebSocketSubscription>>  // 订阅管理
  cacheMarkers: Ref<Map<string, CacheMarker>>            // 缓存标记
  cachedMessages: Ref<Array<CachedMessage>>              // 消息缓存
  // ... 其他状态
}
```

## 核心功能模块

### 1. 配置管理

```typescript
const BASE_WS_URL = 'ws://localhost:36163/api/core/ws'
const HEARTBEAT_INTERVAL = 15000      // 心跳间隔
const HEARTBEAT_TIMEOUT = 5000        // 心跳超时
const BACKEND_CHECK_INTERVAL = 3000   // 后端检查间隔
const MAX_RESTART_ATTEMPTS = 3        // 最大重启尝试次数
const RESTART_DELAY = 2000           // 重启延迟
const MAX_QUEUE_SIZE = 50            // 最大队列大小
const MESSAGE_TTL = 60000            // 消息过期时间
```

**要点**:
- 所有时间配置使用毫秒为单位
- 可根据网络环境调整超时时间
- 队列大小限制防止内存泄漏

### 2. 消息订阅系统

#### 订阅过滤器
```typescript
interface SubscriptionFilter {
  type?: string      // 消息类型过滤
  id?: string        // 消息ID过滤
  needCache?: boolean // 是否需要缓存
}
```

#### 订阅机制
```typescript
export const subscribe = (
  filter: SubscriptionFilter,
  handler: (message: WebSocketBaseMessage) => void
): string => {
  // 1. 生成唯一订阅ID
  // 2. 创建订阅记录
  // 3. 添加缓存标记
  // 4. 回放匹配的缓存消息
}
```

**要点**:
- 支持按 `type` 和 `id` 的组合过滤
- 自动回放缓存消息，确保不丢失历史数据
- 返回订阅ID用于后续取消订阅

### 3. 智能缓存系统

#### 缓存标记机制
```typescript
interface CacheMarker {
  type?: string
  id?: string
  refCount: number  // 引用计数
}
```

#### 缓存策略
- **引用计数**: 订阅时 +1，取消订阅时 -1
- **自动清理**: 引用计数为 0 时删除标记
- **TTL机制**: 消息超过 60 秒自动过期
- **大小限制**: 每个队列最多保留 50 条消息


### 4. 心跳检测机制

```typescript
const startGlobalHeartbeat = (ws: WebSocket) => {
  global.heartbeatTimer = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      const pingTime = Date.now()
      global.lastPingTime = pingTime
      ws.send(JSON.stringify({
        type: 'Signal',
        data: { Ping: pingTime, connectionId: global.connectionId }
      }))
    }
  }, HEARTBEAT_INTERVAL)
}
```


### 5. 后端服务监控

#### 状态检测
```typescript
type BackendStatus = 'unknown' | 'starting' | 'running' | 'stopped' | 'error'
```

#### 自动重启逻辑
```typescript
const restartBackend = async (): Promise<boolean> => {
  // 1. 防重入检查
  // 2. 递增重启计数
  // 3. 调用 Electron API 启动后端
  // 4. 更新状态
}
```


### 6. 连接控制机制

#### 连接权限控制
```typescript
const allowedConnectionReasons = ['后端启动后连接', '后端重启后重连']
const checkConnectionPermission = () => getGlobalStorage().allowNewConnection
```

#### 连接锁机制
```typescript
let isGlobalConnectingLock = false
const acquireConnectionLock = () => {
  if (isGlobalConnectingLock) return false
  isGlobalConnectingLock = true
  return true
}
```

**AI 开发要点**:
- 防止并发连接导致的竞态条件
- 只允许特定原因的连接请求
- 确保全局唯一连接

## 消息流处理

### 1. 消息匹配算法

```typescript
const messageMatchesFilter = (message: WebSocketBaseMessage, filter: SubscriptionFilter): boolean => {
  // 如果都不指定，匹配所有消息
  if (!filter.type && !filter.id) return true
  
  // 如果只指定type
  if (filter.type && !filter.id) return message.type === filter.type
  
  // 如果只指定id
  if (!filter.type && filter.id) return message.id === filter.id
  
  // 如果同时指定type和id，必须都匹配
  return message.type === filter.type && message.id === filter.id
}
```

### 2. 消息分发流程

```
WebSocket 接收消息
    ↓
JSON 解析
    ↓
遍历所有订阅者
    ↓
匹配过滤条件
    ↓
调用处理器函数
    ↓
检查是否需要缓存
    ↓
添加到缓存队列
```

## 外部接口设计

### 1. 主要导出函数

```typescript
export function useWebSocket() {
  return {
    subscribe,           // 订阅消息
    unsubscribe,         // 取消订阅
    sendRaw,            // 发送消息
    getConnectionInfo,   // 获取连接信息
    status,             // 连接状态
    backendStatus,      // 后端状态
    restartBackend,     // 重启后端
    getBackendStatus,   // 获取后端状态
  }
}
```

### 2. 特殊接口

```typescript
export const connectAfterBackendStart = async (): Promise<boolean>
```
- 后端启动后的连接入口
- 启动后端监控
- 设置连接权限

## 错误处理策略

### 1. 连接错误处理
- WebSocket 连接失败时设置状态为 '连接错误'
- 通过后端监控检测服务状态
- 自动重启后端服务

### 2. 消息处理错误
- 订阅处理器异常时记录警告但不中断其他订阅者
- JSON 解析失败时静默忽略
- 发送消息失败时静默处理

### 3. 后端故障处理
```typescript
const handleBackendFailure = async () => {
  if (global.backendRestartAttempts >= MAX_RESTART_ATTEMPTS) {
    // 显示错误对话框，提示重启应用
    Modal.error({
      title: '后端服务异常',
      content: '后端服务多次重启失败，请重启整个应用程序。'
    })
    return
  }
  // 自动重启逻辑
}
```

## 调试和监控

### 1. 调试模式
```typescript
const DEBUG = process.env.NODE_ENV === 'development'
const log = (...args: any[]) => {
  if (DEBUG) console.log('[WebSocket]', ...args)
}
```

### 2. 连接信息监控
```typescript
const getConnectionInfo = () => ({
  connectionId: global.connectionId,
  status: global.status.value,
  subscriberCount: global.subscriptions.value.size,
  moduleLoadCount: global.moduleLoadCount,
  wsReadyState: global.wsRef ? global.wsRef.readyState : null,
  isConnecting: global.isConnecting,
  hasHeartbeat: !!global.heartbeatTimer,
  hasEverConnected: global.hasEverConnected,
  reconnectAttempts: global.reconnectAttempts,
  isPersistentMode: true,
})
```

## AI 开发建议

### 1. 使用模式
```typescript
// 在 Vue 组件中使用
const { subscribe, unsubscribe, sendRaw, status } = useWebSocket()

// 订阅特定类型消息
const subId = subscribe(
  { type: 'TaskUpdate', needCache: true },
  (message) => {
    console.log('收到任务更新:', message.data)
  }
)

// 组件卸载时取消订阅
onUnmounted(() => {
  unsubscribe(subId)
})
```

### 2. 扩展建议
- 添加消息重试机制
- 实现消息优先级队列
- 支持消息压缩
- 添加连接质量监控

### 3. 性能优化点
- 使用 `Object.freeze()` 冻结配置对象
- 考虑使用 Web Worker 处理大量消息
- 实现消息批处理机制
- 添加消息去重功能

### 4. 安全考虑
- 验证消息来源
- 实现消息签名机制
- 添加连接认证
- 防止消息注入攻击

## 依赖关系

### 1. 外部依赖
- `vue`: 响应式系统和组合式API
- `ant-design-vue`: UI组件库（Modal）
- `schedulerHandlers`: 默认消息处理器

### 2. 运行时依赖
- `window.electronAPI`: Electron主进程通信
- WebSocket API: 浏览器原生支持

## 总结

这个 WebSocket 组合式函数是一个功能完整、设计精良的实时通信解决方案。它不仅解决了基本的 WebSocket 连接问题，还提供了高级功能如智能缓存、自动重连、后端监控等。

**核心优势**:
1. 全局持久化连接，避免重复建立
2. 智能订阅系统，支持精确过滤
3. 自动缓存回放，确保数据完整性
4. 完善的错误处理和自动恢复
5. 详细的调试和监控信息

**适用场景**:
- 实时数据展示
- 任务状态监控
- 系统通知推送
- 双向通信应用