# TaskManager Native Candidate — KNOWN_GAPS

> **基线**: `all-plugins-integration` @ `b5e87281`
> **标注**: observed / inferred / unverified

---

## 1. P0 差距（阻断迁移）

### GAP-001: Config v2 TOML 读取路径未确认
- **状态**: unverified
- **描述**: `ConfigV2TaskConfigPort` 需要从 Config v2 的 TOML 数据源读取队列和脚本配置。当前 Config v2 authoritative 模式的确切数据结构和读取 API 尚未确认。
- **影响**: Phase 1 无法开始
- **建议**: 审计 `app/core/config_service.py` 中 Config v2 的数据模型

### GAP-002: PluginScriptConfig 到 Config v2 映射未确认
- **状态**: unverified
- **描述**: 插件脚本配置 (`PluginScriptConfig`) 在 Config v2 中的存储路径和访问方式未确认。
- **影响**: 插件脚本的 `type_key` 解析可能失败
- **建议**: 确认 `PluginScriptConfig` 到 Config v2 ConfigEntry 的映射

## 2. P1 差距（影响迁移质量）

### GAP-003: 游戏签到无独立端口
- **状态**: inferred
- **描述**: `MainTimer.try_game_sign_for_task()` 直接依赖 `Config.ToolsConfig`，没有通过端口抽象。Phase 2 迁移时需要创建独立的 `GameSignPort` 或将其移到 `TaskEventSink` 回调中。
- **影响**: Task.final_task 中的游戏签到触发需要额外处理
- **建议**: Phase 2 中创建 `GameSignPort`

### GAP-004: ScriptRunner 生产者未定义
- **状态**: inferred
- **描述**: 当前 `FakeScriptRunner` 是确定性测试实现。生产级 `ScriptRunner` 需要桥接 `script_type_registry` 和 `provider.create_manager()`，但 `create_manager` 返回的 manager 类型不统一。
- **影响**: Phase 2 的 NativeTaskManager 无法执行真实脚本
- **建议**: 定义统一的 `ScriptRunner` 生产实现，包装 `provider.create_manager()` → `spawn()` 调用

### GAP-005: WS 连接检查路径不完整
- **状态**: inferred
- **描述**: `Config.websocket` 在 `start_startup_queue` 中用于检查 WS 连接状态。`TaskConfigPort.is_websocket_connected()` 需要确认 Config v2 中的等价路径。
- **影响**: 启动队列在 WS 断连时的行为可能不一致
- **建议**: 确认 Config v2 中 WS 连接状态的访问方式

### GAP-006: TaskInfo.on_change 未迁移
- **状态**: observed
- **描述**: `TaskInfo.on_change()` 在每次 `ScriptItem`/`UserItem` 状态变更时触发 `Publisher.send` 和 `PluginEventFactory`。当前候选代码未实现此机制，需要在 `TaskEventSink` 中添加 `send_task_info_updated` 等方法。
- **影响**: 前端任务进度 UI 不会实时更新
- **建议**: 在 `TaskEventSink` 中添加 `send_task_info` 和 `send_task_log` 方法

## 3. P2 差距（远期改进）

### GAP-007: 锁自动过期未实现
- **状态**: observed
- **描述**: `ScriptLockLease` 定义了 `expires_at` 和 `renew_callback`，但当前未实现自动过期机制。如果进程崩溃，锁不会自动释放。
- **影响**: 进程崩溃后需要手动清理锁
- **建议**: Phase 3 实现后台清理任务

### GAP-008: 多工作树/多实例场景未考虑
- **状态**: unverified
- **描述**: 当前锁机制是进程内内存锁，不支持多工作树或多实例场景。
- **影响**: 多实例场景下锁不生效
- **建议**: 远期考虑文件锁或 Redis 锁

### GAP-009: TaskRunPlan 的配置版本追踪未实现
- **状态**: observed
- **描述**: `QueueExecutionSnapshot.source_version` 固定为 "r6"，未实现自动版本追踪。
- **影响**: 审计时无法确定 snapshot 的确切配置版本
- **建议**: Phase 2 中从 Config v2 的 revision 读取

## 4. 已验证通过的能力

| 能力 | 状态 | 证据 |
|------|------|------|
| 脚本/用户/队列解析 | PASS | TestDispatchResolution |
| 队列顺序和 '-' 过滤 | PASS | TestQueueOrdering |
| Resume | PASS | TestResume |
| 锁获取/释放/竞争 | PASS | TestLockCompetition |
| 取消/异常释放 | PASS | TestCancellation |
| Fail-closed | PASS | TestFailClosed |
| AfterAccomplish/power | PASS | TestAfterAccomplish |
| Startup queue | PASS | TestStartupQueue |
| WS 事件序列 | PASS | TestWSEventSequence |
| 失败文案 | PASS | TestFailureMessages |
| 边界情况 | PASS | TestEdgeCases |
| 事件 Sink 隔离 | PASS | TestEventSinkIsolation |
| Snapshot 隔离 | PASS | test_queue_snapshot_isolation |