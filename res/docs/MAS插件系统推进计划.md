# MAS 插件系统推进计划（详细版）

> 版本：v1.0  
> 日期：2026-03-20  
> 适用范围：AUTO-MAS 插件系统后端核心 + 前端配置闭环 + 开发者生态

---

## 1. 现状基线（已完成）

当前已经具备插件系统主干能力：

- `PluginContext`：插件侧受控能力入口（`logger / config / events / runtime`）
- `EventBus`：事件订阅/取消/广播（`on/off/emit`）
- `PluginLoader`：插件发现、模块导入、`setup(ctx)` 调用、`dispose` 卸载
- `PluginManager`：统一启动、停止、重载、实例管理
- `PluginSchemaManager` + `PluginConfigStore`：Schema 加载、配置默认值注入、类型校验
- `/api/plugins/*`：实例增删改查 + 重载接口
- `TaskManager`：已接入 `script.start / script.success / script.error / script.cancelled` 事件发射

---

## 2. 总体目标（未完成部分）

在现有基础上补齐以下闭环：

1. **事件契约标准化**（命名、载荷字段、触发时机）
2. **生命周期状态可观测**（状态、错误、时间线可查询）
3. **Schema 演进能力**（版本化与迁移）
4. **权限模型 MVP**（按能力授权 runtime 调用）
5. **热重载安全策略**（失败回滚、并发隔离）
6. **测试矩阵**（单测 + 集成回归）
7. **Schema -> UI 自动渲染闭环**
8. **开发者模板与文档**

---

## 3. 里程碑计划（4 周）

## M1（第 1 周）：事件契约 + 生命周期可观测（P0）

### 目标

让插件开发者可以“只看文档就正确接入”，让运维能快速定位某实例为什么不可用。

### 任务拆解

#### 3.1 事件契约标准化

- 建立统一事件清单（至少）：
  - `script.start`
  - `script.success`
  - `script.error`
  - `script.cancelled`
  - `script.exit`（新增统一收口事件）
- 为每个事件定义固定 payload 字段（建议）：
  - `event`
  - `timestamp`
  - `task_id`
  - `script_id`
  - `script_name`
  - `mode`
  - `status`
  - `error`（仅异常事件）
  - `result`（仅成功/结束事件）
- 在任务结束处统一补发 `script.exit`（无论成功/失败/取消）
- 编写事件契约文档（示例 payload + 字段含义）

#### 3.2 生命周期状态可观测

- 规范状态流转：
  - `discovered -> loaded -> active -> disposed -> unloaded`
  - 异常态：`error`
- 在 `PluginRecord` 中补充可观测字段：
  - `created_at`
  - `loaded_at`
  - `activated_at`
  - `disposed_at`
  - `last_error`
  - `last_trace`（可选，脱敏）
- 新增管理器查询接口（或扩展现有 `/api/plugins/get` 返回）：
  - 每实例当前状态
  - 最近一次错误
  - 最近状态变更时间

### 验收标准

- 任一插件实例出现失败时，可在 API 返回中直接看到失败原因
- 插件开发文档能明确说明监听哪个事件、能拿到哪些字段
- `script.exit` 在成功/失败/取消三种路径都能触发

### 涉及文件（建议）

- `app/core/task_manager.py`
- `app/core/plugins/loader.py`
- `app/core/plugins/manager.py`
- `app/api/plugins.py`
- `res/docs/`（新增契约文档）

---

## M2（第 2 周）：Schema 演进 + 权限模型 MVP（P1）

### 目标

保证配置可平滑升级，并限制插件调用高风险能力。

### 任务拆解

#### 3.3 Schema 版本化与迁移

- 在 Schema 增加版本信息（例如 `schema_version`）
- 在配置实例记录 `config_version`
- 增加迁移机制：
  - `migrations = {1: migrate_1_to_2, 2: migrate_2_to_3}`
- 扩展字段校验能力（按需）：
  - `enum`
  - `minimum` / `maximum`
  - `pattern`
  - `min_items` / `max_items`
- 错误提示定位到具体路径（如：`smtp_port`、`table_data[2].id`）

#### 3.4 权限模型 MVP

- 插件声明权限（示例）：
  - `runtime.list_scripts`
  - `runtime.get_script_log`
  - `runtime.run_python_snippet`
  - `events.subscribe.script.*`
- `RuntimeAPI` 在调用前统一鉴权
- 未授权访问返回标准错误并记录审计日志
- 预置默认策略：最小权限（默认只读）

### 验收标准

- 旧配置能自动迁移为新版本并通过校验
- 未授权 runtime 调用被稳定拦截，日志含插件名、实例ID、能力名

### 涉及文件（建议）

- `app/core/plugins/schema.py`
- `app/core/plugins/config_store.py`
- `app/core/plugins/runtime_api.py`
- `plugins/*/schema.py`（示例权限声明）

---

## M3（第 3 周）：热重载与隔离（P1）

### 目标

支持稳定迭代插件，不影响主系统可用性。

### 任务拆解

#### 3.5 热重载流程强化

- 统一实例重载流程：
  1. 标记 `reloading`
  2. 调用旧 `dispose`
  3. 加载新模块并 `setup`
  4. 成功后标记 `active`
- 失败回滚：
  - 新版本加载失败时，回到旧实例（或保持 `error` 且不污染其他实例）
- 并发控制：
  - 按实例加锁，避免同实例并发重载

#### 3.6 故障隔离

- 插件事件处理异常不影响主任务流（继续保持）
- 插件异常限流日志，避免日志风暴
- 单插件失败不影响其他插件实例

### 验收标准

- 连续重载同实例不出现状态错乱
- 重载失败后系统仍可继续运行，其他实例正常

### 涉及文件（建议）

- `app/core/plugins/loader.py`
- `app/core/plugins/manager.py`
- `app/core/plugins/event_bus.py`

---

## M4（第 4 周）：测试回归 + 前端闭环 + 开发者体验（P0/P1）

### 目标

形成可持续迭代体系：改动可验证、插件可快速开发。

### 任务拆解

#### 3.7 测试矩阵补全

- 单元测试：
  - `schema.py`：字段类型/默认值/约束/错误定位
  - `config_store.py`：实例增删改查、ID 唯一性、迁移
  - `event_bus.py`：on/off/emit、异常处理
  - `loader.py`：setup/dispose、异常路径、状态变更
- 集成测试：
  - 启动插件系统 -> 触发任务事件 -> 插件响应 -> 卸载
  - API 流程：新增实例/更新配置/重载/删除

#### 3.8 前端 Schema 自动渲染

- 根据 Schema 类型生成控件：
  - `boolean` -> Switch
  - `string` -> Input
  - `number` -> NumberInput
  - `list` -> ListEditor
  - `key_value` -> KVEditor
  - `table` -> TableEditor
- 渲染 `required/default/description/format=password`
- 配置提交前做前端基础校验，后端做最终校验

#### 3.9 开发者模板与文档

- 发布插件模板目录：
  - `plugin.py`
  - `schema.py`
  - `README.md`
- 文档内容：
  - 插件快速开始
  - 生命周期
  - 事件契约
  - Runtime 能力清单与权限说明
  - 常见错误排查

### 验收标准

- 关键链路有自动化测试覆盖，回归可复现
- 新插件只写 `plugin.py + schema.py` 即可在前端完成配置
- 新开发者可在 10~15 分钟内跑通最小插件

### 涉及文件（建议）

- `frontend/src/**`（插件配置页）
- `app/api/plugins.py`
- `app/core/plugins/**`
- `res/docs/**`
- `plugins/smoke_test`（扩展为回归样例）

---

## 4. 每周执行节奏（建议）

### 每周固定节奏

- 周一：设计与契约确认（字段/状态/接口）
- 周二~周三：核心开发
- 周四：联调与补充测试
- 周五：回归 + 文档更新 + 演示

### 每周交付物模板

- `功能变更清单`
- `API/Schema 变更说明`
- `回归测试结果`
- `已知问题与下周计划`

---

## 5. 风险清单与应对

1. **事件字段频繁变动导致插件不兼容**  
   - 应对：引入 `event_version` + 向后兼容策略

2. **Schema 迭代破坏现有实例配置**  
   - 应对：强制迁移函数 + 回滚备份

3. **热重载状态竞争导致实例异常**  
   - 应对：实例级锁 + 状态机保护

4. **插件执行高风险 runtime 行为**  
   - 应对：权限白名单 + 审计日志 + 默认最小权限

5. **前后端校验不一致**  
   - 应对：以后端 Schema 为唯一事实来源，前端仅做体验增强

---

## 6. 立即执行清单（下一个迭代）

> 建议先落地 P0：事件契约 + 生命周期可观测 + 核心测试。

1. 补充 `script.exit` 统一事件收口（任务成功/失败/取消均触发）
2. 在 `PluginRecord` 增加可观测字段并对外返回
3. 输出事件契约文档（事件名 + payload 示例）
4. 新增 3 类最小测试：
   - 事件触发路径
   - 插件加载失败路径
   - 配置校验失败路径

---

## 7. 完成定义（DoD）

满足以下条件视为插件系统一期完成：

- 插件事件契约稳定，文档完整
- 生命周期状态可观测，错误可定位
- Schema 支持版本与迁移
- Runtime 权限控制生效且可审计
- 热重载可靠，不影响主流程
- 有可运行的测试矩阵与回归流程
- 前端可基于 Schema 自动生成插件配置 UI
- 开发者可按模板快速创建新插件

---

## 8. 备注

- 设计原则保持不变：**插件只看到 `ctx`，不直接依赖 MAS 内核实现细节**。
- 实施优先级建议：**P0（稳定性与可观测） > P1（能力增强） > P2（生态体验）**。
