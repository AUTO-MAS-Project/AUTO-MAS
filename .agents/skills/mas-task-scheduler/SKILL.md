---
name: mas-task-scheduler
description: >-
  Design, implement, or review AUTO-MAS task creation, runtime information trees,
  L1-L4 execution, configuration lock ownership, cancellation, task updates, and
  startup/timed/cycle queue triggers. Use for scheduler migration and legacy
  manager integration; plan-type registration alone uses mas-plan-schedule.
---

# MAS 任务调度

保存已确认的调度框架目标设计（不以历史兼容代码反推规范）。跨层或细则修改前读取 [references/scheduler-framework.md](references/scheduler-framework.md)。仅新增计划表类型用 `mas-plan-schedule`。

## 核心不变量

1. **运行树结构**：`TaskItem → TaskScriptItem → TaskUserItem → LogRecord`，**无 `TaskQueueItem`**；调度器用映射保存多个独立任务根，不建总根。
2. **要求树与运行树分离**：公开模式仅 `TaskMode.AUTO_PROXY` / `SCRIPT_CONFIG` / `SCRIPT_VIEW`，输入为 `(mode, requirements, trigger)`；运行树仅存 `info.trigger`。要求树顶层有且仅有索引 `0` 一个入口（自动代理为队列或 `-`，会话为单个托管），节点统一 `uid`/`params`/`children`，运行节点 UUID 独立生成。
3. **L1 受理与计时**：短事务内校验、展开并建完整运行树；仅成功受理时按触发原因更新对应启动/定时/循环时间（手动触发不更新；失败不发布部分树、不记时；timer 不提交这些字段）。
4. **上层持下层锁（先查存在再取锁）**：L2 持托管非级联 X 锁交 L3，L3 持用户级联 X 锁交 L4，L4 不重复取锁或解上层锁。每次等待重试前先查对象存在性（失效即记异常跳过，禁止永久等待），取锁后再核对身份与准入。异常/取消由所属层 `final_task` 兜底释放，先收尾下层再解上层锁。共享 `default` 仅由 L2 托管锁保护。
5. **清单固定、字段热读**：L1 保留禁用/天数不足节点，L3 在用户锁内判准入；建树后改队列不改本轮清单。
6. **`TaskBase` 与提交归属**：下层经 `await self.spawn(child)` 同 Task 执行，停止经 `await task.stop()` 等待唯一收尾。主流程在自身 Task 提交暂存，不指望 `final_task` 代交；只提交改动字段，不整份回写旧快照；提交失败也必须释放锁。
7. **运行树是唯一状态源**：复用 Config 字段/集合/信号/虚拟结果，不登记持久化根；配置类订阅紧跟任务模型声明并直接调用 WS 发送（WS 信息树省略日志正文，日志走独立增量协议）。卫星等配置视图查 Config 与持久化历史，不建影子状态。
8. **Timer 与兼容分叉**：启动/定时/循环由 timer 独立提交，到期不判空闲、不等旧任务结束。旧专项在 L2 分叉给原 manager，必须明确唯一锁所有者，禁止上层锁与旧 manager 锁相互阻塞；兼容方法/别名须标注 `[兼容旧专项]` / `[兼容旧调用方]`，新代码禁止新增对其依赖。
