# TaskInfo 使用示例

## 概述

TaskInfo 是一个基于 dataclass 的任务信息追踪系统,通过传递可变对象引用的方式,让任务能够实时上报状态到 TaskManager。

## 架构图

```
┌────────────────────────────────────┐
│      TaskManager                   │
│  ┌──────────────────────────────┐ │
│  │ task_info_dict = {           │ │
│  │   task_id: TaskInfo(...)     │ │
│  │ }                            │ │
│  └──────────────────────────────┘ │
└────────────┬───────────────────────┘
             │ 传入引用
             ▼
┌────────────────────────────────────┐
│  MaaManager(                       │
│      ...,                          │
│      TaskInfo=task_info  ← 引用    │
│  )                                 │
└────────────────────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│  self.task_info = TaskInfo         │
│                                    │
│  # 直接修改属性                     │
│  self.task_info.status = "运行"    │
│  self.task_info.update(            │
│      progress={"current": 1}       │
│  )                                 │
└────────────────────────────────────┘
```

## 在 MaaManager 中使用

### 1. 初始化时已接收引用

```python
class MaaManager:
    def __init__(self, mode, script_id, user_id, ws_id, TaskInfo=None):
        self.task_info = TaskInfo  # 已保存引用
```

### 2. 更新任务状态

```python
async def prepare(self):
    """运行前准备"""
    # 方式1: 使用 update 方法(推荐,自动更新时间戳)
    if self.task_info:
        self.task_info.update(
            status="准备完成",
            progress={"total": len(self.user_list), "current": 0}
        )
    
    # 方式2: 直接修改属性
    if self.task_info:
        self.task_info.status = "准备完成"
        self.task_info.progress = {"total": len(self.user_list), "current": 0}
        self.task_info.update_time = datetime.now()
```

### 3. 更新当前处理用户

```python
async def execute(self):
    if self.task_info:
        self.task_info.update(status="运行中")
    
    for self.index, user in enumerate(self.user_list):
        # 更新进度和当前用户
        if self.task_info:
            self.task_info.update(
                current_user={
                    "user_id": user["user_id"],
                    "name": user["name"]
                },
                progress={
                    "current": self.index + 1,
                    "total": len(self.user_list),
                    "percent": int((self.index + 1) / len(self.user_list) * 100)
                }
            )
        
        # ... 业务逻辑
```

### 4. 更新日志

```python
async def _on_log_received(self, log_content):
    """日志回调"""
    self.maa_logs = log_content
    
    # 上报最近的日志
    if self.task_info:
        self.task_info.logs = self.maa_logs[-50:]  # 保留最近50条
        self.task_info.update_time = datetime.now()
```

### 5. 完成任务

```python
async def finalize(self, task):
    """任务结束"""
    if self.task_info:
        self.task_info.update(
            status="已完成",
            progress={"current": len(self.user_list), "total": len(self.user_list)}
        )
    
    # ... 其他清理工作
```

## 在 API 中获取任务信息

### 获取单个任务信息

```python
from app.core.task_manager import TaskManager

# 获取任务信息
task_id = uuid.UUID("...")
task_info = TaskManager.get_task_info(task_id)

if task_info:
    print(f"任务状态: {task_info['status']}")
    print(f"进度: {task_info['progress']}")
    print(f"当前用户: {task_info['current_user']}")
    print(f"最近日志: {task_info['logs']}")
```

### 获取所有任务信息

```python
all_tasks = TaskManager.get_all_task_info()

for task_id, info in all_tasks.items():
    print(f"任务 {task_id}: {info['status']} - {info['progress']}")
```

### WebSocket 实时推送

```python
# 在 API 路由中
@app.get("/api/task/{task_id}/info")
async def get_task_info(task_id: str):
    task_uuid = uuid.UUID(task_id)
    info = TaskManager.get_task_info(task_uuid)
    
    if not info:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return info

@app.websocket("/ws/task/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str):
    await websocket.accept()
    task_uuid = uuid.UUID(task_id)
    
    while True:
        # 每秒推送一次任务信息
        info = TaskManager.get_task_info(task_uuid)
        if info:
            await websocket.send_json(info)
        await asyncio.sleep(1)
```

## TaskInfo 数据结构

```python
{
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "script_id": "123e4567-e89b-12d3-a456-426614174001",
    "mode": "自动代理",
    "status": "运行中",  # 初始化/准备完成/运行中/已完成/异常
    "progress": {
        "current": 5,
        "total": 10,
        "percent": 50
    },
    "current_user": {
        "user_id": "user-uuid",
        "name": "用户名"
    },
    "logs": [
        "2025-10-08 10:00:00 - 开始执行任务",
        "2025-10-08 10:00:05 - 连接模拟器",
        "..."
    ],
    "start_time": "2025-10-08T10:00:00",
    "update_time": "2025-10-08T10:05:30"
}
```

## 注意事项

### 1. 避免重新赋值

```python
# ❌ 错误: 会断开引用
self.task_info = TaskInfo(...)  

# ✅ 正确: 修改属性
self.task_info.status = "新状态"
self.task_info.update(status="新状态")
```

### 2. 空值检查

```python
# 总是检查 task_info 是否存在(兼容旧代码/测试)
if self.task_info:
    self.task_info.update(status="运行中")
```

### 3. 并发安全

```python
# TaskInfo 的修改是原子的,单个属性赋值是安全的
# 如果需要严格的事务性,可以添加锁:

async def _safe_update(self, **kwargs):
    if self.task_info:
        # 简单场景:直接更新即可
        self.task_info.update(**kwargs)
```

### 4. 日志大小控制

```python
# 避免日志列表过大占用内存
self.task_info.logs = self.maa_logs[-50:]  # 只保留最近50条
```

## 高级用法

### 自定义状态

```python
# 可以使用自定义的状态值
self.task_info.update(
    status="等待用户确认",
    extra_data={
        "waiting_for": "user_input",
        "timeout_at": (datetime.now() + timedelta(minutes=5)).isoformat()
    }
)
```

### 性能监控

```python
# 记录性能指标
self.task_info.update(
    extra_data={
        "memory_usage": psutil.virtual_memory().percent,
        "cpu_usage": psutil.cpu_percent(),
        "execution_time": (datetime.now() - start_time).total_seconds()
    }
)
```

## 常见问题

**Q: 任务信息什么时候会被清理?**

A: 任务结束时会标记为"已完成",但不会立即删除。可以通过 `_cleanup_task_info` 方法延迟清理(默认5分钟)。

**Q: 如何在前端实时显示任务进度?**

A: 通过 WebSocket 订阅任务信息,每秒获取一次更新。

**Q: 性能开销如何?**

A: 非常低,只是直接内存访问,无额外的函数调用或队列开销。
