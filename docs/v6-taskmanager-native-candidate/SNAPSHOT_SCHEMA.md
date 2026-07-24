# TaskManager Native Candidate — SNAPSHOT_SCHEMA

> **基线**: `all-plugins-integration` @ `b5e87281`
> **标注**: observed / inferred / unverified

---

## 1. 快照隔离原则

**核心约束**: snapshot 与 live ConfigEntry 隔离；执行中不能再次读取整份 live 配置。

- snapshot 创建时冻结所有必要数据（`frozen=True, slots=True` dataclass）
- 执行期间只读取 snapshot 中的字段，不查询 ConfigBase 或 Config v2
- snapshot 包含 `frozen_at` 时间戳和 `source_version` 用于审计

## 2. QueueExecutionSnapshot

```python
@dataclass(frozen=True, slots=True)
class QueueExecutionSnapshot:
    queue_id: str                          # 队列 UUID
    queue_name: str                        # 队列名称
    script_ids: Tuple[str, ...]            # 已排序、已过滤 '-' 的脚本 ID 列表
    after_accomplish: PowerAction          # 完成后电源操作
    startup_enabled: bool                  # 是否启动时运行
    last_timed_start: str                  # 上次定时启动时间
    frozen_at: str                         # 冻结时间戳 (ISO 8601)
    source_version: str                    # 来源版本 (e.g. "r6")
```

**数据来源映射** (observed):

| Snapshot 字段 | ConfigBase 来源 | 访问方式 |
|-------------|----------------|---------|
| `queue_id` | `QueueConfig` key | `Config.QueueConfig.items()` |
| `queue_name` | `QueueConfig.Info_Name` | `.get("Info", "Name")` |
| `script_ids` | `QueueConfig.QueueItem` | `.QueueItem.values()` → `.get("Info", "ScriptId")` → filter `!= "-"` |
| `after_accomplish` | `QueueConfig.Info_AfterAccomplish` | `.get("Info", "AfterAccomplish")` |
| `startup_enabled` | `QueueConfig.Info_StartUpEnabled` | `.get("Info", "StartUpEnabled")` |
| `last_timed_start` | `QueueConfig.Data_LastTimedStart` | `.get("Data", "LastTimedStart")` |

## 3. ScriptDescriptor

```python
@dataclass(frozen=True, slots=True)
class ScriptDescriptor:
    script_id: str                         # 脚本 UUID
    script_name: str                       # 脚本名称
    type_key: str                          # 脚本类型键 (e.g. "MAA", "SRC")
    display_name: str                      # 显示名称
    supported_modes: FrozenSet[TaskMode]   # 支持的任务模式
    available: bool                        # 是否可用
    unavailable_reason: Optional[str]      # 不可用原因
    editor_kind: str                       # 编辑器类型
    is_builtin: bool                       # 是否内建
    has_native_descriptor: bool            # 是否有 native descriptor
```

**数据来源映射** (observed):

| Snapshot 字段 | 来源 | 访问方式 |
|-------------|------|---------|
| `script_id` | `ScriptConfig` key | `Config.ScriptConfig.items()` |
| `script_name` | `ScriptConfig.Info_Name` | `.get("Info", "Name")` |
| `type_key` | `ScriptTypeProvider.type_key` | `script_type_registry.get_by_script_config()` |
| `display_name` | `ScriptTypeProvider.display_name` | provider 属性 |
| `supported_modes` | `ScriptRecordCapability.supported_modes` | `Config.get_script_record_capability()` |
| `available` | `ScriptRecordCapability.available` | `Config.get_script_record_capability()` |
| `unavailable_reason` | `ScriptRecordCapability.unavailable_reason` | `Config.get_script_record_capability()` |
| `editor_kind` | `ScriptTypeProvider.editor_kind` | provider 属性 |
| `is_builtin` | `ScriptTypeProvider.is_builtin` | provider 属性 |
| `has_native_descriptor` | `provider.metadata["available"]` | provider 元数据是否为 False |

## 4. ScriptExecutionSnapshot

```python
@dataclass(frozen=True, slots=True)
class ScriptExecutionSnapshot:
    descriptor: ScriptDescriptor           # 脚本描述符
    is_locked: bool                        # 是否被锁定
    frozen_at: str                         # 冻结时间戳
```

## 5. DispatchTarget

```python
@dataclass(frozen=True, slots=True)
class DispatchTarget:
    mode: TaskMode                         # 任务模式
    task_uid: uuid.UUID                    # 任务实例 UUID
    queue_id: Optional[str]                # 队列 ID
    script_id: Optional[str]               # 脚本 ID
    user_id: Optional[str]                 # 用户 ID
    resume_from_script_id: Optional[str]   # resume 目标
    resolved_script_ids: Tuple[str, ...]   # 解析后的脚本 ID 列表
```

## 6. TaskRunPlan

```python
@dataclass(frozen=True, slots=True)
class TaskRunPlan:
    target: DispatchTarget                 # 调度目标
    script_snapshots: Tuple[ScriptExecutionSnapshot, ...]  # 所有脚本快照
    queue_snapshot: Optional[QueueExecutionSnapshot]       # 队列快照
    created_at: str                        # 创建时间戳
```

## 7. 隔离保证

### 7.1 时间隔离
- snapshot 创建时 `frozen_at` 记录时间戳
- 执行期间不重新读取 live 配置
- 新请求创建新 snapshot，旧 snapshot 不影响新请求

### 7.2 数据隔离
- 所有 DTO 使用 `frozen=True, slots=True` dataclass
- 使用 `Tuple` 而非 `List` 确保不可变性
- 使用 `FrozenSet` 而非 `Set` 确保集合不可变

### 7.3 锁隔离
- 锁通过 `ScriptLockLease` 管理，不依赖 `ConfigBase.is_locked`
- 锁获取/释放通过 `TaskConfigPort` 端口，实现可替换
- 任务取消/异常时锁在 finally 块中释放

### 7.4 验证
- `test_queue_snapshot_isolation` 测试证明了 live 数据修改不会影响已创建的 snapshot (observed: test_fake_harness.py)
- `FakeTaskConfigPort` 的内部数据与 snapshot 分离 (observed: fake_native_port.py)