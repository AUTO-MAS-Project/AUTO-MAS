# MAS 插件事件契约

> 版本：v1.1  
> 生效日期：2026-03-22  
> 适用范围：AUTO-MAS 插件事件总线（EventBus）与任务编排事件

## 1. 目标与原则

本契约用于统一插件事件的命名、结构和触发语义，确保：

- 插件可以稳定消费事件，不依赖内核实现细节；
- 任务生命周期（task / script）可观测、可追踪；
- 新增字段时保持向后兼容。

核心原则：

- 字段追加优先，不做破坏式移除；
- 任务级事件放在 `data` 中，脚本级事件保持扁平兼容；
- 插件处理必须容错，不能因插件异常阻塞主流程。

## 2. 通用 Envelope

所有事件均包含以下顶层字段：

- `event: string`：事件名；
- `event_version: string`：契约版本，当前固定为 `1`；
- `source: string`：来源模块（建议：`core.task_manager`）；
- `timestamp: string`：ISO8601 时间字符串。

任务级事件（`task.*`）业务字段统一放在：

- `data: object`

脚本级事件（`script.*`）维持既有兼容结构，字段可在顶层直接读取。

## 3. 标准事件清单

### 3.1 任务生命周期事件

- `task.start`：任务初始化完成并开始执行时触发。
- `task.progress`：任务关键状态发生变化时触发（例如脚本状态、索引、完成数变化）。
- `task.log`：当前脚本日志发生有效变化时触发。
- `task.exit`：任务退出统一收口事件（成功 / 失败 / 取消）。

### 3.2 脚本生命周期事件

- `script.start`
- `script.success`
- `script.error`
- `script.cancelled`
- `script.exit`

说明：`script.exit` 为收口事件，建议插件优先监听它做统一处理。

## 4. 触发语义（实现对齐）

### 4.1 `task.progress` 可能多次触发

`task.progress` 是“状态快照事件”，不是“一次性事件”。任务执行过程中每次状态变化都可能触发。

### 4.2 `task.log` 与 `task.progress` 的日志过滤

当前实现对“无意义日志”做过滤：当当前日志为空或仅空白（如换行）时，不发送对应日志变化事件，减少噪声。

### 4.3 `task.start` 操作入口

`task.start` 包含可操作入口（如停止当前任务、停止全部任务），插件可直接据此触发 API 调用。

## 5. Payload 示例

### 5.1 task.start

```json
{
  "event": "task.start",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:45+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "script_total": 3,
    "scripts": [
      {
        "script_id": "script-001",
        "script_name": "日常任务",
        "status": "等待"
      }
    ],
    "actions": {
      "stop_task": {
        "api": "/api/dispatch/stop",
        "method": "POST",
        "body": {
          "taskId": "task-001"
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

### 5.2 task.progress

```json
{
  "event": "task.progress",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:50+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "current_script_index": 0,
    "script_total": 3,
    "script_completed": 1,
    "user_total": 12,
    "user_completed": 4,
    "current_script": {
      "script_id": "script-001",
      "script_name": "日常任务",
      "status": "运行",
      "current_user_index": 1,
      "user_count": 4
    }
  }
}
```

### 5.3 task.log

```json
{
  "event": "task.log",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:51+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "script_id": "script-001",
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

### 5.4 task.exit

```json
{
  "event": "task.exit",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:24:20+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "result": "success",
    "error": null,
    "summary": "任务摘要..."
  }
}
```

### 5.5 script.exit

```json
{
  "event": "script.exit",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:59+08:00",
  "task_id": "task-001",
  "script_id": "script-001",
  "script_name": "日常任务",
  "mode": "AutoProxy",
  "status": "完成",
  "error": null,
  "result": "script.success"
}
```

## 6. 插件侧实践建议

- 任务维度追踪：用 `task_id` 作为主键，监听 `task.start` / `task.progress` / `task.log` / `task.exit`。
- 脚本维度收口：优先监听 `script.exit`，按 `result` 做分支处理。
- 事件处理容错：处理函数内部应捕获异常，避免传播到总线。
- 缓存配合事件：建议使用 `ctx.cache` 对事件计数、去重签名、短期状态做本地持久化。

示例（推荐）：

- `counter:task.progress`：记录触发次数；
- `last:task.progress`：保存最后一条快照；
- `task:<task_id>:summary`：在 `task.exit` 收口写入摘要。

## 7. 兼容性与升级策略

- 新增字段只追加，不删除既有字段；
- 既有事件语义保持不变；
- 插件应对未知字段容忍（忽略即可），避免硬编码严格字段全集。
