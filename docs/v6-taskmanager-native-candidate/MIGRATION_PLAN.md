# TaskManager Native Candidate — MIGRATION_PLAN

> **基线**: `all-plugins-integration` @ `b5e87281`
> **标注**: observed / inferred / unverified

---

## 1. 分阶段落地顺序

### Phase 0: 候选验证（当前已完成）

**产出**:
- [x] `task_config_port.py` — 8 个 DTO/Protocol 定义
- [x] `fake_native_port.py` — FakeTaskConfigPort 实现
- [x] `fake_runner.py` — FakeTaskManager 实现
- [x] `test_fake_harness.py` — 13 个测试类，40+ 测试用例
- [x] 文档交付物 (IMPORT_MATRIX, CALLGRAPH, SNAPSHOT_SCHEMA, LOCK_LEASE_SPEC, CANDIDATE_PATCH, MIGRATION_PLAN, KNOWN_GAPS, FINAL_REPORT)

**门禁**: 所有测试通过

### Phase 1: ConfigV2TaskConfigPort 实现（下一阶段）

**目标**: 创建生产级 `TaskConfigPort` 实现，桥接 Config v2 authoritative。

**任务**:
1. 创建 `app/core/task_config_port_impl.py`:
   - `ConfigV2TaskConfigPort` 实现 `TaskConfigPort` Protocol
   - `build_queue_snapshot()` → 从 Config v2 TOML 读取队列
   - `build_script_descriptor()` → 从 Config v2 TOML 读取脚本元数据
   - `acquire_lock()` / `release_lock()` → 使用 ScriptLockLease
   - `get_power_policy()` → 返回 ConfigPowerPolicyPort
   - `get_event_sink()` → 返回 WSEventSink (桥接 Publisher + PluginEventFactory)

2. 创建 `app/core/power_policy_port_impl.py`:
   - `ConfigPowerPolicyPort` 实现 `PowerPolicyPort` Protocol
   - 桥接 `Config.power_sign` 和 `System`

3. 创建 `app/core/event_sink_impl.py`:
   - `WSEventSink` 实现 `TaskEventSink` Protocol
   - 桥接 `Publisher.send()` 和 `PluginEventFactory`

**门禁**: 集成测试通过（使用真实 Config v2 但 fake runner）

**风险**:
- Config v2 的 TOML 读取路径需要确认 (unverified)
- `PluginScriptConfig` 到 Config v2 的映射路径需要确认 (unverified)

### Phase 2: FakeTaskManager → NativeTaskManager 迁移

**目标**: 将 `FakeTaskManager` 的核心逻辑迁移到生产级 `NativeTaskManager`。

**任务**:
1. 创建 `app/core/task_manager_native.py`:
   - `NativeTaskManager` 类，构造函数接收 `TaskConfigPort` + `ScriptRunner`
   - 复用 `FakeTaskManager` 的核心逻辑
   - 集成真实的 `ScriptRunner`（通过 `script_type_registry`）

2. 修改 `app/core/__init__.py`:
   - 根据配置选择 `NativeTaskManager` 或 `LegacyTaskManager`

3. 修改 `main.py` lifespan:
   - 注入 `TaskConfigPort` 到 `TaskManager`

**门禁**: 全量集成测试 + 回归测试

**风险**:
- `MainTimer.try_game_sign_for_task()` 需要独立端口 (inferred)
- 真实 `ScriptRunner` 需要处理所有脚本类型 (MAA, SRC, M9A, MaaFW, General, PluginScript)

### Phase 3: Legacy 代码移除

**目标**: 确认 NativeTaskManager 稳定后，移除旧 TaskManager 中 ConfigBase 直接依赖。

**任务**:
1. 移除 `app/core/task_manager.py` 中 `from .config import Config` 导入
2. 移除 `_resolve_queue_name` 中的 `Config.QueueConfig` 调用
3. 移除 `Task.prepare` 中的 `Config.QueueConfig` / `Config.ScriptConfig` 调用
4. 移除 `_TaskManager._queue_script_ids` 中的 `Config.QueueConfig` 调用
5. 移除 `_TaskManager.start_startup_queue` 中的 `Config.QueueConfig.items()` 调用
6. 移除 `Task.final_task` 中的 `Config.power_sign` 直接访问

**门禁**: 所有旧测试通过 + 新测试通过

### Phase 4: ConfigBase 退出运行链（v7 周期）

**目标**: 宿主配置层重写为 Config v2 原生类（非本任务范围）。

**注意**: 根据 project_memory.md 记录，当前 8 个宿主根配置仍是 ConfigBase 子类，authoritative 是在上层叠加 v2 TOML 数据源而非替换。ConfigBase 完全退出需要 v7 周期。

## 2. 不能回退的约束

| 约束 | 说明 |
|------|------|
| **不把 legacy ConfigBase 回退写进 authoritative 运行链** | 端口抽象是单向的：TaskManager → TaskConfigPort → (Config v2 OR ConfigBase) |
| **不通过延迟 import 伪造通过** | 所有依赖通过构造函数注入，不用 lazy import 绕过 |
| **不通过 selector 包装伪造通过** | 不使用 `if use_native: ... else: ...` 分支 |
| **不通过 mock 掉核心模块伪造通过** | 候选代码可直接替换为生产实现 |

## 3. 时间线

```
Phase 0: [COMPLETED] 候选验证
Phase 1: [NEXT] ConfigV2TaskConfigPort 实现
Phase 2: NativeTaskManager 迁移
Phase 3: Legacy 代码移除
Phase 4: [v7] ConfigBase 退出运行链
```

## 4. 回滚策略

每个 Phase 都保留旧代码：
- Phase 1-2: `NativeTaskManager` 与 `LegacyTaskManager` 共存，通过配置开关切换
- Phase 3: 旧 `task_manager.py` 保留为 `task_manager_legacy.py`
- Phase 4: ConfigBase 保留为只读兼容层
