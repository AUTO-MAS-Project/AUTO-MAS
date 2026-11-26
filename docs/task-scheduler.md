# 任务调度架构概览

本文说明 AUTO-MAS 调度系统的核心分层、运行模式与源码归属。完整的代理与开发约束见 [scheduler-framework.md](../.agents/skills/mas-task-scheduler/references/scheduler-framework.md)。

## 公开任务模式

调度入口当前只开放三种创建模式（`TaskMode`）：

- `AUTO_PROXY`：自动代理执行
- `SCRIPT_CONFIG`：打开脚本原生配置界面
- `SCRIPT_VIEW`：只读查看历史配置备份

> 定时/循环属于队列触发器（`app/core/timer.py`）；专项独立维护操作走 `app/api/scripts/operations.py`，均不属于公开 `TaskMode`。

## 四级执行骨架（L1–L4）

```text
L1  TaskManager.start(mode, tasks, trigger=...)
    校验要求树 → 构建唯一运行树 → 登记并广播 task.created
    └─ L2 ScriptExpander
       按托管快照顺序派发；插件分支持有托管配置锁
       ├─ 内建专项：factory → 旧 manager._execute_task()
       │  └─ 由专项 manager 自行校验、持锁、展开账号并收尾
       └─ 插件专项：plugin_expander → UserExpander
          └─ L3 UserExpander：准备运行环境、逐账号持锁派发
             └─ L4 ModeWorker：执行具体模式并完成单账号收尾
```

- `TaskBase`（`app/task/lifecycle.py`）是 L2 / L3 / L4 共用的生命周期基类，提供统一的执行、中止与收尾契约；L1（`TaskManager`）负责管理任务树，不继承 `TaskBase`。
- 内建专项随插件化迁移逐步从左侧 manager 路径过渡到右侧 L3 / L4 路径。

## 关键模块归属

| 模块 | 职责 |
| --- | --- |
| `app/api/dispatch.py` | 创建、停止、查询任务与重连快照的 HTTP 入口 |
| `app/api/queue.py` | 队列、定时与循环触发配置的读写入口 |
| `app/core/task_manager.py` | L1 调度中心、要求树建树、运行索引与全局 `TaskManager` |
| `app/core/timer.py` | 启动、定时、循环队列的到期判定与任务提交 |
| `app/core/power.py` | 任务结束后的电源动作意图与倒计时管理 |
| `app/core/background_tasks.py` | 后台任务组、并发限额与应用退出收尾 |
| `app/models/task.py` | 任务模式、运行节点、订阅与日志游标模型 |
| `app/models/schema.py` | 要求节点、任务树投影及 HTTP / WebSocket 公共契约 |
| `app/task/script_expander.py` | L2 托管展开与内建 / 插件分叉 |
| `app/task/user_expander.py` | L3 插件托管执行骨架 |
| `app/task/mode_worker.py` | L4 三种模式的抽象执行骨架 |
| `app/task/manager_base.py` | 旧内建专项共用的账号筛选、跳过与报告逻辑 |
| `frontend/src/composables/useTaskApi.ts` | 前端任务提交、停止与错误转译 |
| `frontend/src/composables/useTaskRuntimeState.ts` | HTTP 快照与 WebSocket 增量运行态缓存 |
| `frontend/src/views/scheduler/` | 调度台界面、实时日志与恢复入口 |
