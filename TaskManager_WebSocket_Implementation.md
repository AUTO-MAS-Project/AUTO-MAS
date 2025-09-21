# TaskManager WebSocket消息处理功能实现

## 功能概述

根据后端TaskManager的WebSocket消息机制，实现了前端对ID为"TaskManager"的WebSocket消息的完整处理逻辑。

## 后端TaskManager消息分析

### 消息格式
```json
{
  "id": "TaskManager",
  "type": "Signal", 
  "data": {
    "newTask": "任务UUID"
  }
}
```

### 触发时机
当后端启动时运行的队列开始执行时，TaskManager会发送此消息通知前端有新任务被自动创建。

## 前端实现

### 1. WebSocket订阅机制
在`useSchedulerLogic.ts`中添加了以下功能：

- **subscribeToTaskManager()**: 订阅ID为"TaskManager"的WebSocket消息
- **handleTaskManagerMessage()**: 处理TaskManager发送的消息
- **createSchedulerTabForTask()**: 根据任务ID自动创建调度台

### 2. 自动调度台创建逻辑

当收到`newTask`信号时，系统会：

1. **检查重复**: 验证是否已存在相同websocketId的调度台
2. **创建调度台**: 自动创建新的调度台标签页
3. **设置状态**: 直接将调度台状态设置为"运行"
4. **建立连接**: 立即订阅该任务的WebSocket消息
5. **用户提示**: 显示成功创建的消息提示

### 3. 调度台特性

自动创建的调度台具有以下特性：
- 标题格式：`自动调度台{编号}`
- 初始状态：`运行`
- 可关闭：`true`（但运行时不可删除）
- 自动订阅：立即开始接收任务消息

### 4. 生命周期管理

- **初始化**: 在组件挂载时调用`initialize()`订阅TaskManager消息
- **清理**: 在组件卸载时取消TaskManager订阅
- **任务结束**: 复用现有的任务结束处理逻辑

## 代码修改点

### 1. useSchedulerLogic.ts
```typescript
// 新增TaskManager消息订阅
const subscribeToTaskManager = () => {
  ws.subscribe('TaskManager', {
    onMessage: (message) => handleTaskManagerMessage(message)
  })
}

// 新增TaskManager消息处理
const handleTaskManagerMessage = (wsMessage: any) => {
  if (type === 'Signal' && data && data.newTask) {
    createSchedulerTabForTask(data.newTask)
  }
}

// 新增自动调度台创建
const createSchedulerTabForTask = (taskId: string) => {
  // 创建运行状态的调度台并立即订阅
}
```

### 2. index.vue
```typescript
// 生命周期中添加初始化调用
onMounted(() => {
  initialize() // 订阅TaskManager消息
  loadTaskOptions()
})
```

## 功能特点

### 1. 无缝集成
- 完全复用现有的调度台逻辑和UI组件
- 与手动创建的调度台行为一致
- 支持所有现有功能（日志显示、任务总览、消息处理等）

### 2. 状态同步
- 调度台状态与后端任务状态严格同步
- 支持任务完成后的自动状态更新
- 正确处理WebSocket连接的建立和清理

### 3. 用户体验
- 自动切换到新创建的调度台
- 提供清晰的成功提示
- 防止重复创建相同任务的调度台

### 4. 错误处理
- 检查消息格式的有效性
- 防止重复订阅和创建
- 优雅处理异常情况

## 测试验证

功能实现后需要验证以下场景：

1. **启动时队列**: 后端启动时运行的队列应自动创建调度台
2. **消息接收**: 调度台应正确接收和显示任务消息
3. **状态更新**: 任务状态变化应正确反映在UI上
4. **任务结束**: 任务完成后应正确清理资源
5. **重复处理**: 相同任务不应创建多个调度台

## 兼容性

- 完全向后兼容现有功能
- 不影响手动创建的调度台
- 保持现有的WebSocket消息处理机制
- 复用所有现有的UI组件和样式