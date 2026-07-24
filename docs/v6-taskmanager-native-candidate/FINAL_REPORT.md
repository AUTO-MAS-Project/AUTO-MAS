# TaskManager Native Candidate — FINAL_REPORT

> **基线**: `all-plugins-integration` @ `b5e87281` (integration/dev-v2-dev-all-plugins)
> **冻结 r6**: `D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\release-nexus-a1-r6`
> **任务**: TaskManager 原生 TaskConfigPort、执行快照与 LockLease 迁移
> **标注**: observed / inferred / unverified

---

## 1. 执行摘要

为 AUTO-MAS v6 Experimental Alpha 的 Config v2 authoritative 模式，构建了 TaskManager 的无旧 ConfigBase 运行端口候选方案。核心交付物包括：

- **8 个 DTO/Protocol 定义**: TaskConfigPort, DispatchTarget, QueueExecutionSnapshot, ScriptExecutionSnapshot, ScriptLockLease, TaskEventSink, PowerPolicyPort, TaskRunPlan
- **Fake 实现**: FakeTaskConfigPort, FakeTaskEventSink, FakePowerPolicyPort, FakeScriptRunner, FakeTaskManager
- **确定性 Test Harness**: 13 个测试类，47 个测试用例，覆盖所有核心场景
- **9 个文档交付物**: IMPORT_MATRIX, CALLGRAPH, SNAPSHOT_SCHEMA, LOCK_LEASE_SPEC, FAKE_HOST_TEST_LOG, CANDIDATE_PATCH, MIGRATION_PLAN, KNOWN_GAPS, FINAL_REPORT

**结论**: 候选方案通过端口抽象实现了 TaskManager 与 ConfigBase 的解耦，snapshot 隔离机制和原子锁 lease 语义可验证。但需要 Phase 1 的 ConfigV2TaskConfigPort 实现才能进入生产验证。

## 2. 交付清单

### 2.1 候选代码

| 文件 | 路径 | 行数 | 状态 |
|------|------|------|------|
| task_config_port.py | `_alpha_build\a1\taskmanager-native-candidate-20260723\` | 489 | DONE |
| fake_native_port.py | `_alpha_build\a1\taskmanager-native-candidate-20260723\` | 380 | DONE |
| fake_runner.py | `_alpha_build\a1\taskmanager-native-candidate-20260723\` | 380 | DONE |

### 2.2 测试

| 文件 | 路径 | 状态 |
|------|------|------|
| test_fake_harness.py | `tests\taskmanager_native_candidate\` | DONE |
| conftest.py | `tests\taskmanager_native_candidate\` | DONE |
| run_tests.py | `scripts\taskmanager_native_candidate\` | DONE |

### 2.3 文档

| 文件 | 路径 | 状态 |
|------|------|------|
| IMPORT_MATRIX.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| CALLGRAPH.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| SNAPSHOT_SCHEMA.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| LOCK_LEASE_SPEC.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| CANDIDATE_PATCH.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| MIGRATION_PLAN.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| KNOWN_GAPS.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| FAKE_HOST_TEST_LOG.md | `docs\v6-taskmanager-native-candidate\` | DONE |
| FINAL_REPORT.md | `docs\v6-taskmanager-native-candidate\` | DONE |

## 3. 核心发现

### 3.1 ConfigBase 依赖盘点 (observed)

TaskManager 对 `Config` 的直接依赖共 **15 处**：

| 类别 | 数量 | 依赖项 |
|------|------|--------|
| 队列配置读取 | 5 | `QueueConfig[uid]`, `QueueItem.values()`, `get("Info", "Name")`, `get("Info", "StartUpEnabled")`, `get("Info", "AfterAccomplish")` |
| 脚本配置读取 | 5 | `ScriptConfig[uid]`, `get("Info", "Name")`, `is_locked`, `UserData`, `items()` |
| 能力校验 | 1 | `get_script_record_capability(uid)` |
| 电源策略 | 1 | `power_sign` (读写) |
| WS 连接 | 1 | `websocket` |
| 脚本类型 | 2 | `script_type_registry.get()`, `get_by_script_config()` |

全部通过 `TaskConfigPort` + `PowerPolicyPort` + `TaskEventSink` 抽象。

### 3.2 Snapshot 隔离 (observed)

- `QueueExecutionSnapshot` 和 `ScriptExecutionSnapshot` 使用 `frozen=True, slots=True`
- 测试 `test_queue_snapshot_isolation` 证明 live 数据修改不影响已创建的 snapshot
- 所有 DTO 使用 `Tuple`/`FrozenSet` 确保不可变性

### 3.3 锁语义 (observed)

- `ScriptLockLease` 替代 `ConfigBase.is_locked` 布尔标志
- 支持持有者追踪（`task_id`）
- 测试覆盖：获取、释放、重复锁、取消释放、异常释放、错误持有者

### 3.4 失败文案 (observed)

6 种失败文案已定义：
- `build_no_descriptor_error_message` — 无 native descriptor
- `build_plugin_script_missing_provider_message` — 插件脚本 provider 缺失
- `build_maafw_no_descriptor_message` — MaaFW 无 descriptor
- `build_mode_not_supported_message` — 模式不支持
- `build_script_not_found_message` — 脚本未找到
- `build_script_locked_message` — 脚本被锁定

## 4. 门禁状态

| 门禁项 | 状态 | 说明 |
|--------|------|------|
| 不修改正式源码 | PASS | 所有候选代码在独立目录 |
| 不 commit/push/reset/stash | PASS | 未执行任何 Git 操作 |
| 不启动真实游戏/模拟器/Agent | PASS | 纯 fake 测试 |
| Snapshot 与 live 隔离 | PASS | 测试验证 |
| 执行中不读取 live 配置 | PASS | FakeTaskManager 仅在 add_task 时构建 snapshot |
| 不通过延迟 import 伪造 | PASS | 所有依赖通过构造函数注入 |
| 不通过 selector/mock 伪造 | PASS | FakeTaskConfigPort 是完整实现 |

## 5. 风险与建议

### 5.1 P0 风险

1. **Config v2 TOML 读取路径未确认** (GAP-001): 需要在 Phase 1 前审计 `config_service.py`
2. **PluginScriptConfig 映射未确认** (GAP-002): 需要确认插件脚本在 Config v2 中的存储方式

### 5.2 P1 风险

3. **游戏签到无独立端口** (GAP-003): 需要在 Phase 2 创建 `GameSignPort`
4. **ScriptRunner 生产者未定义** (GAP-004): 需要统一 `provider.create_manager()` 的包装
5. **WS 连接检查路径不完整** (GAP-005): 需要确认 Config v2 中的 WS 状态
6. **TaskInfo.on_change 未迁移** (GAP-006): 需要在 `TaskEventSink` 中添加进度更新方法

### 5.3 建议

- **立即**: 审计 `app/core/config_service.py` 确认 Config v2 数据模型
- **Phase 1**: 实现 `ConfigV2TaskConfigPort`，在真实 Config v2 环境中验证
- **Phase 2**: 实现 `NativeTaskManager`，逐步替换旧 TaskManager
- **v7**: ConfigBase 完全退出运行链

## 6. 结论

候选方案在架构层面证明了 TaskManager 可以通过端口抽象与 ConfigBase 解耦，snapshot 隔离和原子锁 lease 语义可验证。所有 47 个测试用例通过，覆盖了队列解析、锁竞争、取消/异常、fail-closed、电源策略、启动队列和事件序列等核心场景。

**下一步**: 进入 Phase 1 — 实现 `ConfigV2TaskConfigPort`，桥接 Config v2 authoritative 数据源。需要先解决 GAP-001 和 GAP-002 两个 P0 差距。