# TaskManager Native Candidate — CANDIDATE_PATCH

> **基线**: `all-plugins-integration` @ `b5e87281`
> **标注**: observed / inferred / unverified

---

## 1. 候选代码结构

```
_alpha_build\a1\taskmanager-native-candidate-20260723\
├── task_config_port.py      # DTO/Protocol 定义 (489 行)
├── fake_native_port.py      # FakeTaskConfigPort + FakeTaskEventSink (380 行)
└── fake_runner.py           # FakeTaskManager + FakeScriptRunner (380 行)

tests\taskmanager_native_candidate\
├── conftest.py              # pytest 配置
└── test_fake_harness.py     # 13 个测试类，40+ 测试用例 (600+ 行)

scripts\taskmanager_native_candidate\
└── run_tests.py             # 测试运行器

docs\v6-taskmanager-native-candidate\
├── IMPORT_MATRIX.md         # 依赖矩阵
├── CALLGRAPH.md             # 调用链
├── SNAPSHOT_SCHEMA.md       # 快照模式
├── LOCK_LEASE_SPEC.md       # 锁租赁规范
├── CANDIDATE_PATCH.md       # 本文件
├── MIGRATION_PLAN.md        # 迁移计划
├── KNOWN_GAPS.md            # 已知差距
├── FAKE_HOST_TEST_LOG.md    # 测试日志
└── FINAL_REPORT.md          # 最终报告
```

## 2. 核心设计决策

### 2.1 端口抽象而非直接替换

**决策**: 引入 `TaskConfigPort` Protocol 而非直接修改 TaskManager 移除 ConfigBase 导入。

**原因**:
- ConfigBase 当前在 8 个宿主根配置中仍然是 `ConfigBase` 子类 (observed: project_memory.md)
- 直接移除 ConfigBase 需要重写整个配置层，超出本任务范围
- 端口抽象允许渐进迁移：先验证语义，再替换实现

### 2.2 不可变快照

**决策**: 所有配置数据通过 `frozen=True` dataclass 传递，执行中不读取 live 配置。

**原因**:
- 消除 TOCTOU 问题（执行中配置被修改）
- 使执行行为确定可测
- 为未来 Config v2 authoritative 的 ConfigEntry 版本化做准备

### 2.3 原子锁 Lease

**决策**: 使用 `ScriptLockLease` 替代 `ConfigBase.is_locked` 布尔标志。

**原因**:
- 支持持有者追踪（task_id）
- 支持过期机制（expires_at）
- 状态机模型比布尔标志更健壮

### 2.4 事件 Sink 协议

**决策**: 引入 `TaskEventSink` Protocol 替代直接调用 `Publisher.send` 和 `PluginEventFactory`。

**原因**:
- 解耦 WS 和插件事件总线
- 使测试可独立验证事件序列
- 为未来事件系统重构提供接口

## 3. 最小对正式源码的修改

### Phase 1: 零侵入（当前候选）

**不需要修改正式源码**。候选代码完全独立，通过 fake harness 验证语义。

### Phase 2: 注入点

仅需在 `main.py` lifespan 中添加端口注入：

```python
# main.py lifespan 中，Config.init_config() 之后:
from app.core.task_config_port_impl import ConfigV2TaskConfigPort
from app.core.task_manager_native import NativeTaskManager

# 创建 Config v2 的 TaskConfigPort 实现
task_config_port = ConfigV2TaskConfigPort(Config)

# 替换 TaskManager 实例
TaskManager = NativeTaskManager(task_config_port)
```

### Phase 3: 完整替换

`app/core/task_manager.py` 中移除 `from .config import Config` 依赖，改为接收 `TaskConfigPort` 参数。

## 4. 不修改的内容

- ❌ **不修改** `app/core/config.py`（ConfigBase 退出需要 v7 周期）
- ❌ **不修改** `app/models/config.py`（QueueConfig 等配置类）
- ❌ **不修改** `app/models/ConfigBase.py`（锁机制通过端口抽象）
- ❌ **不修改** `app/api/dispatch.py`（API 接口不变）
- ❌ **不修改** `app/core/ws/`（WS 通过 TaskEventSink 间接访问）
- ❌ **不修改** `app/plugins/`（插件事件通过 TaskEventSink 间接访问）

## 5. 关键测试覆盖

| 测试类 | 覆盖场景 | 状态 |
|--------|---------|------|
| TestDispatchResolution | 队列/脚本/用户解析，snapshot 隔离 | PASS |
| TestQueueOrdering | 队列顺序，'-' 过滤 | PASS |
| TestResume | resume 功能，不存在的脚本 | PASS |
| TestLockCompetition | 锁获取/释放，重复锁，持有者检查 | PASS |
| TestCancellation | 停止所有/单个任务，锁释放 | PASS |
| TestFailClosed | 不可用脚本，不支持模式，已删除脚本 | PASS |
| TestAfterAccomplish | AfterAccomplish 电源，NoAction，ScriptConfig 豁免 | PASS |
| TestStartupQueue | 启动队列，幂等，WS 断开 | PASS |
| TestWSEventSequence | 事件序列，完成通知 | PASS |
| TestFailureMessages | 所有失败文案 | PASS |
| TestEdgeCases | 空队列，数据完整性，冻结时间戳 | PASS |
| TestEventSinkIsolation | 事件 sink 独立性 | PASS |
| TestActiveTaskTracking | 活跃任务追踪 | PASS |