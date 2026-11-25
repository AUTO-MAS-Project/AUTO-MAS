---
name: mas-function-design
description: Define backend function design standards for Python services. Use when implementing or refactoring functions in app/, choosing function boundaries, designing signatures and return contracts, controlling side effects, and reviewing correctness/readability in core/task/services/api modules.
---

# MAS Function Design

仅约束 AUTO-MAS 后端（`app/`）中容易踩坑的签名、异步、任务生命周期与配置变更规范；模块归属见 `mas-module-boundary`。禁止 `except Exception: pass` 静默吞错或把失败洗成成功（记日志不算吞异常理由）。

## 签名、职责与命名

- **关键字参数红线**：**布尔参数**以及 **超过 2 个参数**的调用必须使用关键字参数；仅 ≤2 个显而易见的简单参数可用位置参数。
- **不造空壳抽象**：不要为只用一次或内联更清晰的逻辑抽 `builder`/`loader` 辅助函数；任务流中的配置导入/导出、日志监控与终态判定必须保持显式可读，禁止藏进含糊包装层。
- **返回值与错误**：领域函数返回领域值（不返回 HTTP 响应模型）；省略合法时不传冲突类型的占位符；领域层抛带上下文（`script_id`/`user_id`/步骤）的领域异常，仅在 `app/api/` 边界转为安全响应。
- **命名**：动词开头（`load_*`/`build_*`/`merge_*`/`send_*`/`check_*`/`prepare_*`/`finalize_*`），避免无范围词的 `handle`/`process`。

## 异步、线程与任务生命周期（高危）

1. **禁止线程池内延迟 import**：严禁将含模块延迟 `import` 的函数体丢进 `asyncio.to_thread` / `run_in_executor`——多线程并发冷导入同一包会触发 CPython 模块导入锁死锁或读到半初始化模块。必须在事件循环或启动期先完成导入，再传入已解析的可调用对象。
2. **异步边界**：仅在需要 `await` IO 或异步协调原语时使用 `async`；长流程清理放 `finally`；避免在 async 热路径直接跑同步阻塞调用；任务派生留在编排层，不放进叶子工具函数。
3. **`TaskBase` 生命周期**（联动 `mas-task-scheduler`）：
   - 遵循 `main_task` / `final_task` / `on_crash` 契约；`main_task` 与 `final_task` 可正常抛错，**`on_crash` 必须保护自身不抛出未捕获异常**。
   - 执行树子任务通过 `await self.spawn(...)` 同 Task 运行；应用级独立后台任务归 `BackgroundTaskManager`。
   - 停止已启动的 `TaskBase` 使用 `await task.stop()` 并等待清理（不要假定存在 `.cancel()`）；等待超时不代表已停止。

## 配置变更流（必读 `../mas-data-model/references/config-framework.md`）

- 拷贝嵌套可变对象后做**整字段赋值**或调公开集合方法，再在**同一 Task** 中 `await commit()`（原地 `append`/下标修改会绕过框架）。
- 关联写操作放进短显式事务；独立子 Task 不继承事务，持有全局闸门时禁止 `await` 需要提交配置的子任务。
- 写受保护实时配置时持有 X-lock 票据并在 `finally` 释放；`flush()` 与导出在事务外执行，不往同步原子落盘路径硬加并发写线程。
- `activate(fast_init=True)` 失败整批回滚并重跑逐字段路径，禁止复用失败值或将外部 IO 当事务处理。
