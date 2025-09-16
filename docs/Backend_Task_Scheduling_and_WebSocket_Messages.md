# AUTO-MAS 后端任务调度逻辑与WebSocket消息格式说明

## 1. 任务调度架构概览

AUTO-MAS 后端采用基于 AsyncIO 的异步任务调度系统，主要由以下核心组件构成：

### 1.1 核心组件

- **TaskManager**: 任务调度器，负责任务的创建、运行、停止和清理
- **Broadcast**: 消息广播系统，负责在不同组件间传递消息
- **WebSocket**: 与前端的实时通信通道
- **Config**: 配置管理系统，包含脚本配置、队列配置等

### 1.2 任务类型

系统支持三种主要任务模式：

1. **设置脚本** - 直接执行单个脚本配置
2. **自动代理** - 按队列顺序自动执行多个脚本
3. **人工排查** - 手动排查和执行任务

## 2. 任务调度流程

### 2.1 任务创建流程

```
前端请求 → API接口 → TaskManager.add_task() → 任务验证 → 创建异步任务 → 返回任务ID
```

**具体步骤：**

1. **任务验证**: 根据模式和UID验证任务配置是否存在
2. **重复检查**: 确保相同任务未在运行中
3. **任务创建**: 使用`asyncio.create_task()`创建异步任务
4. **回调设置**: 添加任务完成回调用于清理工作

### 2.2 任务执行流程

#### 设置脚本模式
```
获取脚本配置 → 确定脚本类型(MAA/General) → 创建对应Manager → 执行任务
```

#### 自动代理模式
```
获取队列配置 → 构建任务列表 → 逐个执行脚本 → 更新状态 → 发送完成信号
```

### 2.3 任务状态管理

- **等待**: 任务已加入队列但未开始执行
- **运行**: 任务正在执行中
- **跳过**: 任务因重复或其他原因被跳过
- **完成**: 任务执行完毕

## 3. WebSocket 消息系统

### 3.1 消息基础结构

所有WebSocket消息都遵循统一的JSON格式：

```json
{
  "id": "消息ID或任务ID",
  "type": "消息类型",
  "data": {
    "具体数据": "根据类型而定"
  }
}
```

### 3.2 消息类型详解

#### 3.2.1 Update 类型 - 数据更新

**用途**: 通知前端更新界面数据，"user_list"仅给出当前处于`运行`状态的脚本的用户列表值

**常见数据格式:**

```json
{
  "id": "task-uuid",
  "type": "Update",
  "data": {
    "user_list": [
      {
        "name": "用户名",
        "status": "运行状态",
        "config": "配置信息"
      }
    ]
  }
}
```

```json
{
  "id": "task-uuid", 
  "type": "Update",
  "data": {
    "task_dict": [
      {
        "script_id": "脚本ID",
        "status": "等待/运行/完成/跳过",
        "name": "脚本名称",
        "user_list": [
          {
            "name": "用户名",
            "status": "运行状态",
            "config": "配置信息"
          }
        ]
      }
    ]
  }
}
```

```json
{
  "id": "task-uuid", 
  "type": "Update",
  "data": {
    "task_list": [
      {
        "script_id": "脚本ID",
        "status": "等待/运行/完成/跳过",
        "name": "脚本名称"
      }
    ]
  }
}
```

```json
{
  "id": "task-uuid",
  "type": "Update", 
  "data": {
    "log": "任务执行日志内容"
  }
}
```

#### 3.2.2 Info 类型 - 信息显示

**用途**: 向前端发送需要显示的信息，包括普通信息、警告和错误

**数据格式:**

```json
{
  "id": "task-uuid",
  "type": "Info",
  "data": {
    "Error": "错误信息内容"
  }
}
```

```json
{
  "id": "task-uuid",
  "type": "Info",
  "data": {
    "Warning": "警告信息内容"
  }
}
```

```json
{
  "id": "task-uuid",
  "type": "Info",
  "data": {
    "Info": "普通信息内容"
  }
}
```

#### 3.2.3 Message 类型 - 对话框请求

**用途**: 请求前端弹出对话框显示重要信息

**数据格式:**

```json
{
  "id": "task-uuid",
  "type": "Message",
  "data": {
    "title": "对话框标题",
    "content": "对话框内容",
    "type": "info/warning/error"
  }
}
```

#### 3.2.4 Signal 类型 - 程序信号

**用途**: 发送程序控制信号和状态通知

**常见信号:**

**任务完成信号:**
```json
{
  "id": "task-uuid",
  "type": "Signal", 
  "data": {
    "Accomplish": "任务完成后调度台显示的日志内容"
  }
}
```

**电源操作信号:**
```json
{
  "id": "task-uuid",
  "type": "Signal",
  "data": {
    "power": "NoAction/KillSelf/Sleep/Hibernate/Shutdown/ShutdownForce",
  }
}
```

**心跳信号:**
```json
{
  "id": "Main",
  "type": "Signal",
  "data": {
    "Ping": "无描述"
  }
}
```

```json
{
  "id": "Main", 
  "type": "Signal",
  "data": {
    "Pong": "无描述"
  }
}
```

## 4. 任务管理器详细说明

### 4.1 TaskManager 核心方法

#### add_task(mode: str, uid: str)
- **功能**: 添加新任务到调度队列
- **参数**: 
  - `mode`: 任务模式 ("设置脚本", "自动代理", "人工排查")
  - `uid`: 任务唯一标识符
- **返回**: 任务UUID

#### stop_task(task_id: str)
- **功能**: 停止指定任务
- **参数**: 
  - `task_id`: 任务ID，支持 "ALL" 停止所有任务

#### run_task(mode: str, task_id: UUID, actual_id: Optional[UUID])
- **功能**: 执行具体任务逻辑
- **流程**: 根据模式选择相应的执行策略

### 4.2 任务执行器

#### GeneralManager
- **用途**: 处理通用脚本任务
- **特点**: 支持自定义脚本路径和参数
- **配置**: 基于 GeneralConfig 和 GeneralUserConfig

#### MaaManager  
- **用途**: 处理MAA (明日方舟助手) 专用任务
- **特点**: 支持模拟器控制、ADB连接、游戏自动化
- **配置**: 基于 MaaConfig 和 MaaUserConfig

## 5. 消息广播系统

### 5.1 Broadcast 机制

- **设计模式**: 发布-订阅模式
- **功能**: 实现组件间解耦的消息传递
- **特点**: 支持多个订阅者同时接收消息

### 5.2 消息流向

```
任务执行器 → Broadcast → WebSocket → 前端界面
                    ↓
                 其他订阅者
```

## 6. 配置管理系统

### 6.1 配置类型

- **ScriptConfig**: 脚本配置，包含MAA和General两种类型
- **QueueConfig**: 队列配置，定义自动代理任务的执行顺序
- **GlobalConfig**: 全局系统配置

### 6.2 配置操作

- **锁机制**: 防止配置在使用时被修改
- **实时更新**: 支持动态加载配置变更
- **类型验证**: 确保配置数据的正确性

## 7. API 接口说明

### 7.1 任务控制接口

**创建任务**
- **端点**: `POST /api/dispatch/start`
- **请求体**: 
  ```json
  {
    "mode": "自动代理|人工排查|设置脚本",
    "taskId": "目标任务ID"
  }
  ```
- **响应**: 
  ```json
  {
    "code": 200,
    "status": "success", 
    "message": "操作成功",
    "websocketId": "新任务ID"
  }
  ```

**停止任务**
- **端点**: `POST /api/dispatch/stop`
- **请求体**:
  ```json
  {
    "taskId": "要停止的任务ID"
  }
  ```

**电源操作**
- **端点**: `POST /api/dispatch/power`
- **请求体**:
  ```json
  {
    "signal": "NoAction|Shutdown|ShutdownForce|Hibernate|Sleep|KillSelf"
  }
  ```

### 7.2 WebSocket 连接

**端点**: `WS /api/core/ws`

**连接特性**:
- 同时只允许一个WebSocket连接
- 自动心跳检测 (15秒超时)
- 连接断开时自动清理资源

## 8. 错误处理机制

### 8.1 异常类型

- **ValueError**: 配置验证失败
- **RuntimeError**: 任务状态冲突
- **TimeoutError**: 操作超时
- **ConnectionError**: 连接相关错误

### 8.2 错误响应格式

```json
{
  "id": "相关任务ID",
  "type": "Info",
  "data": {
    "Error": "具体错误描述"
  }
}
```

## 9. 性能和监控

### 9.1 日志系统

- **分层日志**: 按模块划分日志记录器
- **实时监控**: 支持日志实时推送到前端
- **文件轮转**: 自动管理日志文件大小

### 9.2 资源管理

- **进程管理**: 自动清理子进程
- **内存监控**: 防止内存泄漏
- **连接池**: 复用数据库和网络连接

## 10. 安全考虑

### 10.1 输入验证

- **参数校验**: 使用 Pydantic 模型验证
- **路径安全**: 防止路径遍历攻击
- **命令注入**: 严格控制执行的命令参数

### 10.2 权限控制

- **单一连接**: 限制WebSocket连接数量
- **操作限制**: 防止重复或冲突操作
- **资源保护**: 防止资源滥用

---

*此文档基于 AUTO-MAS v5.0.0 版本编写，详细的API文档和配置说明请参考相关配置文件和源代码注释。*
