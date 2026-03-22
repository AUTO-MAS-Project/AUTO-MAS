# MAS 插件系统推进计划

> 版本：v1.1  
> 日期：2026-03-22  
> 适用范围：AUTO-MAS 插件系统后端核心、插件运行时、前端配置闭环

---

## 1. 当前状态总览

### 1.1 已落地能力（可用）

- 插件上下文能力：`ctx.logger / ctx.config / ctx.events / ctx.runtime / ctx.cache`。
- 事件总线：支持 `on/off/emit`，插件异常不阻塞主流程。
- 任务事件：已实现 `task.start / task.progress / task.log / task.exit`。
- 脚本事件：支持 `script.start / script.success / script.error / script.cancelled / script.exit`。
- 插件配置：Schema 默认值注入 + 严格类型校验（插件端可直接强类型读取 `ctx.config`）。
- PyPI 插件：支持本地 site-packages 加载、重载前更新、模块缓存清理。
- 实例级缓存：`ctx.cache.register(...)` 支持 JSON 持久化、CRUD、超限自动清理。

### 1.2 关键工程修复（已完成）

- 修复 PyPI 插件 schema 回退加载（entrypoint 模块 `schema/get_schema`）。
- 修复重载偶发旧代码问题（加载前清理模块缓存）。
- 减少重复 discover 扫描，降低重载日志噪声。
- 增加 task 日志有效性过滤，空日志/纯空白日志不再发无意义事件。

---

## 2. 架构约束与职责边界

### 2.1 `TaskManager` 与 `EventFactory`

- `TaskManager` 负责“何时发”：触发时机、状态机、去重与收口。
- `PluginEventFactory` 负责“发什么”：payload 组装与 envelope 统一。

### 2.2 配置与插件职责

- 类型和默认值由 Schema 层保证，插件不重复做 config 类型兜底。
- 插件处理逻辑关注业务消费，避免在插件内重复实现平台校验。

### 2.3 缓存职责

- 缓存按实例隔离存储：`data/<instance>/plugin_cache/*.json`。
- 插件通过 `ctx.cache` 管理缓存，平台负责目录与生命周期。

---

## 3. 缓存能力路线图

### 3.1 已实现（v1）

- 注册接口：`ctx.cache.register(cache_name, backend, limit, limit_mode, limit_unit)`。
- 支持后端：`json`（`database` 作为未来扩展类型保留）。
- 限制模式：
  - `count`：按条目数淘汰；
  - `bytes`：按字节大小淘汰。
- 单位支持：`b / kb / mb / gb`，支持 `10mb`、`1.5gb` 形式。
- CRUD：`set/get/delete/exists/update/all/clear/stats`。

### 3.2 下一阶段（v2）

- 数据库后端抽象：
  - `database` 模式接入 MySQL / Mongo 驱动适配层；
  - 统一 TTL、索引、批量操作语义。
- 缓存可观测：
  - 暴露实例缓存指标（条目数、大小、清理次数）；
  - 对接管理 API 查询。
- 缓存策略：
  - 支持 LRU / FIFO 策略可选；
  - 支持按 key 前缀分区清理。

---

## 4. 事件能力路线图

### 4.1 已实现（v1）

- 任务级与脚本级生命周期事件齐全。
- `task.start` 提供动作入口（停止当前任务/全部任务）。
- `task.progress` 为状态快照事件，允许多次触发。
- `task.log` 提供完整日志与 tail，便于实时订阅和长日志展示。

### 4.2 下一阶段（v2）

- 增加事件字段演进指引（新增字段规范、保留字段策略）。
- 增加事件回放工具（按 task_id 回放关键事件序列）。
- 增加事件压力治理（按插件配置的节流/采样）。

---

## 5. 重载与发布路线图

### 5.1 已实现（v1）

- `reload/reload_plugin/reload_instance` 前执行 PyPI 目录更新。
- 预留 `pip-index` 更新分支（接口位保留，待实现）。
- 加载前清理 PyPI 模块缓存，确保读取磁盘最新代码。

### 5.2 下一阶段（v2）

- 完成 `pip-index` 更新链路（版本选择、失败回退）。
- 引入重载事务日志（开始/成功/失败/回滚）。
- 增加实例级重载锁，防止并发重载竞争。

---

## 6. 测试与质量门禁

### 6.1 当前测试资产

- PyPI 任务事件测试插件：覆盖 task 四事件观测。
- `smoke_test` 已改造为缓存测试插件：覆盖注册、CRUD、超限清理、事件计数写入。

### 6.2 下一阶段门禁

- 单元测试：
  - `cache_store.py`（单位换算、阈值清理、异常输入）；
  - `task_manager.py`（空日志过滤、progress 触发语义）；
  - `schema.py`（严格类型与默认值行为）。
- 集成测试：
  - 插件加载 -> 任务触发 -> 缓存写入 -> 重载 -> 继续写入；
  - PyPI 更新后重载生效验证（新版本代码签名变化）。

---

## 7. 近期迭代计划（建议两周）

### 第 1 周（P0）

1. 输出缓存能力开发文档（参数说明 + 示例 + 排障）。
2. 增加缓存相关 API 观测端点（只读统计）。
3. 补齐 `cache_store.py` 单元测试。

### 第 2 周（P1）

1. 实现 `database` 抽象基类与空实现适配。
2. 打通 `pip-index` 更新最小可用链路。
3. 增加重载事务日志与错误诊断字段。

---

## 8. 风险与对策

1. **事件量增大导致插件处理压力上升**  
   对策：插件侧使用 `ctx.cache` 做去重/聚合，平台侧增加节流选项。

2. **缓存无限增长**  
   对策：`limit` 设为必填，超限自动清理，后续增加监控告警。

3. **PyPI 更新后行为不一致**  
   对策：更新前后记录版本与模块签名，重载失败可回滚。

4. **插件自行兜底导致行为分裂**  
   对策：统一要求“类型由 Schema 保证”，插件不重复解析配置类型。

---

## 9. 完成定义（本阶段）

满足以下条件即视为 v1.1 阶段完成：

- 事件契约文档与实现一致；
- `ctx.cache` 文档化并可被示例插件验证；
- PyPI 重载更新链路稳定可复现；
- 核心改动通过静态检查且无新增错误。
