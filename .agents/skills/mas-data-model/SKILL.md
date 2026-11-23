---
name: mas-data-model
description: Define AUTO-MAS backend models and configuration framework usage. Use for app/models, app/config, config field declarations, stage/commit callers, transactions, signals, locks, persistence, and config contract evolution.
---

# MAS Data Model

适用于 `app/models/schema.py`、`app/api/` 端点模型、`app/models/config/` 配置模型、`app/config/` 框架调用及 `task` 运行态模型。涉及调度任务树/锁时联动 `mas-task-scheduler`。

## 配置框架红线

涉及配置定义、读写、事务、锁、信号、持久化、API 投影或历史升级前，**必读 [references/config-framework.md](references/config-framework.md)**。

- **单点声明**：配置字段只在 `ConfigEntry` / `ConfigGroup`（带类型与中文 `description`）声明一次，集合用 `ConfigCollection[T]` + `collection(...)`；API 投影一律经 `app/config/wire.py` 派生。
- **禁止绕过框架**：禁止原地修改容器、直接改 `order`/`data` 或整组替换；热写必须通过整字段赋值或公开集合操作暂存，再在同一 Task 中 `await commit()`。
- **运行态与常量**：运行态放 `PrivateAttr`，类常量放 `ClassVar`；计算字段用 `Virtual[T]` + `@virtual_field(...)`。
- **启动快速初始化**：`activate(fast_init=True)` 共享单次局部事务，任一字段或 Init 信号失败必须整体回滚并退回逐字段路径，禁止复用失败尝试的值或假设外部副作用可回滚。
- **框架变更需授权**：未经用户确认不得修改配置基类框架设计。

## 分层归属与类型约束

1. **三层隔离**：`schema.py` / `app/api/`（对外契约）、`config`（持久化与校验）、`task`（运行态）职责分离。任务运行状态/日志的 Config 类订阅直接声明在任务模型定义之后，导入时不得触发宿主初始化。
2. **明确类型**：优先具体类型、`Literal` 或枚举，避免 `Any`、无边界 `Dict[str, Any]` 与字符串化布尔/数字；可变默认值用 `default_factory`。
3. **日期时间**：配置时间字段一律使用完整 `datetime`（UTC 存储，naive 输入按 UTC 解释，`tz(...)` 控制读取，序列化输出 UTC）。
4. **可选与校验**：用类型系统或字段省略表达可选，禁止塞入非法占位哨兵值；校验器只补下层容器/`ref(...)` 未覆盖的缺失不变量，**禁止在校验器中执行网络/文件/进程副作用**。区分 Pydantic 拒绝约束与 `Annotated` 归一化语义。
5. **敏感数据**：隔离 `password`/`token`/`key` 等敏感字段，禁止误暴露至响应模型，加解密逻辑不写进 schema 层。

## 演进与迁移

- **内部改动彻底迁移**：MAS 内部模型变更须把历史数据与全部内部调用方迁至新契约，**不保留旧业务分支或平行字段**。
- **迁移入口**：字段迁移用 `legacy(group=..., name=..., convert=...)`（仅作输入转换，非第二套运行契约）；结构与数据库升级归启动升级编排。
- **禁止重复或无消费者字段**：新增字段前先核对已有字段（含特殊值如 `=0`）是否已表达同一语义，不为一个用户选择建两个重叠字段；未具备持久化、UI 与运行消费前，不提前加未来占位字段。

## 审查清单

- 归属层正确（`schema`/`config`/`task`），命名对齐 `mas-schema-naming`，API 对齐 `mas-api-contract`。
- 集合声明了具体成员类型，引用目标先于依赖项激活，局部更新区分省略 / `null` / 脱敏占位值。
- 事务、整字段赋值、信号、锁与持久化满足 `config-framework.md`，测试使用隔离文件与外部替身。
