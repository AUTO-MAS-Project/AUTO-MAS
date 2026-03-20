# MAS 插件事件契约（M1）

> 版本：v1  
> 生效日期：2026-03-20

## 1. 设计目标

统一插件事件命名、触发时机与 payload 结构，保证：

- 插件开发可预测
- 前后端调试可追踪
- 未来版本演进可兼容

## 2. 通用字段（所有事件）

所有插件事件 payload 均包含以下字段：

- `event: str` 事件名
- `event_version: str` 契约版本（当前 `1`）
- `source: str` 事件来源（如 `core.task_manager`）
- `timestamp: str` UTC+8 ISO8601 时间
- `data: object` 业务数据（通用事件推荐放在该字段）

来源规范：

- 建议使用点分命名：`{layer}.{module}`（示例：`core.task_manager`、`core.main`）
- 禁止空字符串来源

脚本领域事件常见字段（按需出现）：

- `task_id: str` 任务 ID
- `script_id: str` 脚本 ID
- `script_name: str` 脚本名
- `mode: str` 任务模式
- `status: str` 当前脚本状态

可选字段：

- `error: str` 错误信息（异常/失败路径）
- `result: str` 结果事件名（用于 `script.exit` 收口）

## 3. 事件列表与触发时机

### 通用事件示例：`backend.start`

用于后端启动成功场景，可只带版本等业务数据，不需要脚本字段。

```json
{
  "event": "backend.start",
  "source": "core.main",
  "timestamp": "2026-03-20T03:21:15.123456+00:00",
  "data": {
    "version": "1.0.0"
  }
}
```

### `task.start`

任务完成初始化并开始进入调度流程时触发。

### `task.progress`

任务状态发生变化时触发（脚本状态、用户状态、当前索引等变更）。

### `task.log`

当前执行脚本日志发生变化时触发。

### `task.exit`

任务执行流程退出时触发（成功 / 失败 / 取消统一收口）。

### `script.start`

脚本被调度并标记为运行时触发。

### `script.success`

脚本执行完成（`status == 完成`）时触发。

### `script.error`

脚本执行异常，或执行结束但状态非完成时触发。

### `script.cancelled`

脚本执行被取消（`CancelledError`）时触发。

### `script.exit`

统一收口事件。无论成功、失败、取消，脚本离开执行流程时都触发。

脚本生命周期标准事件集合：

- `script.start`
- `script.success`
- `script.error`
- `script.cancelled`
- `script.exit`

任务生命周期标准事件集合：

- `task.start`
- `task.progress`
- `task.log`
- `task.exit`

## 4. 典型 payload 示例

### 4.1 task.start

```json
{
  "event": "task.start",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:21:15.123456+00:00",
  "data": {
    "task_id": "xxxx",
    "mode": "AutoProxy",
    "queue_id": "xxxx",
    "script_id": null,
    "user_id": null,
    "script_total": 3,
    "scripts": [
      {
        "script_id": "xxxx",
        "script_name": "日常任务",
        "status": "等待"
      }
    ],
    "actions": {
      "stop_task": {
        "api": "/api/dispatch/stop",
        "method": "POST",
        "body": {
          "taskId": "xxxx"
        }
      },
      "stop_all_tasks": {
        "api": "/api/dispatch/stop",
        "method": "POST",
        "body": {
          "taskId": "ALL"
        }
      }
    }
  }
}
```

### 4.2 task.progress

```json
{
  "event": "task.progress",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:21:20.123456+00:00",
  "data": {
    "task_id": "xxxx",
    "mode": "AutoProxy",
    "queue_id": "xxxx",
    "script_id": null,
    "user_id": null,
    "current_script_index": 0,
    "script_total": 3,
    "script_completed": 1,
    "user_total": 12,
    "user_completed": 4,
    "task_info": [],
    "current_script": {
      "script_id": "xxxx",
      "script_name": "日常任务",
      "status": "运行",
      "current_user_index": 1,
      "user_count": 4
    }
  }
}
```

### 4.3 task.log

```json
{
  "event": "task.log",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:21:21.123456+00:00",
  "data": {
    "task_id": "xxxx",
    "mode": "AutoProxy",
    "script_id": "xxxx",
    "script_name": "日常任务",
    "script_status": "运行",
    "current_script_index": 0,
    "log": "...完整日志...",
    "log_tail": "...末尾日志...",
    "log_length": 12345,
    "truncated_for_tail": true
  }
}
```

### 4.4 task.exit

```json
{
  "event": "task.exit",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:22:00.123456+00:00",
  "data": {
    "task_id": "xxxx",
    "mode": "AutoProxy",
    "queue_id": "xxxx",
    "script_id": null,
    "user_id": null,
    "result": "success",
    "error": null,
    "summary": "任务摘要..."
  }
}
```

### 4.5 script.start

```json
{
  "event": "script.start",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:21:15.123456+00:00",
  "task_id": "xxxx",
  "script_id": "xxxx",
  "script_name": "日常任务",
  "mode": "AutoProxy",
  "status": "运行"
}
```

### 4.6 script.error

```json
{
  "event": "script.error",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:21:25.123456+00:00",
  "task_id": "xxxx",
  "script_id": "xxxx",
  "script_name": "日常任务",
  "mode": "AutoProxy",
  "status": "异常",
  "error": "RuntimeError: failed",
  "result": "script.error"
}
```

### 4.7 script.exit（收口）

```json
{
  "event": "script.exit",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-20T03:21:25.125000+00:00",
  "task_id": "xxxx",
  "script_id": "xxxx",
  "script_name": "日常任务",
  "mode": "AutoProxy",
  "status": "异常",
  "error": "RuntimeError: failed",
  "result": "script.error" 
}
```

## 5. 插件侧建议

- 推荐以 `task.start` 建立任务上下文，以 `task_id` 作为主键贯穿全流程。
- 推荐监听 `task.progress` 获取任务级进度，监听 `task.log` 获取实时日志。
- 推荐使用 `task.exit` 作为任务级统一收口事件。
- 推荐优先监听 `script.exit` 作为统一处理入口。
- 若需细分逻辑，可同时监听 `script.success` / `script.error` / `script.cancelled`。
- 处理函数应容错，不应抛出未捕获异常。

事件发送建议：

- 脚本生命周期：使用 `PluginEventFactory.emit_script_event(...)`
- 其他系统事件（如后端启动）：使用 `PluginEventFactory.emit_event(...)`
- 事件名常量建议使用 `PluginEventNames`，避免字符串拼写错误

## 6. 兼容性说明

- 后续新增字段仅追加，不会移除现有字段。
- 事件名若扩展，将保持已存在事件语义不变。
