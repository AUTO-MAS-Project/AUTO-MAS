# TaskManager Native Candidate — LOCK_LEASE_SPEC

> **基线**: `all-plugins-integration` @ `b5e87281`
> **标注**: observed / inferred / unverified

---

## 1. 现有锁机制分析

### 1.1 ConfigBase.is_locked (observed)

```
ConfigBase.is_locked: bool = False          [ConfigBase.py L877]
├── lock(): is_locked = True                [ConfigBase.py L1036]
├── unlock(): is_locked = False             [ConfigBase.py L1042]
├── del(): is_locked = False               [ConfigBase.py L1060]
└── 检查: if self.is_locked → block write   [ConfigBase.py L919, L1092, ...]
```

**问题**:
- is_locked 是简单的布尔标志，不支持多任务持有者追踪
- 没有过期机制，如果任务崩溃锁不会自动释放
- 没有租约续约，长任务无法安全持有锁

### 1.2 TaskManager 中的锁使用 (observed)

```python
# task_manager.py L392
if Config.ScriptConfig[current_script_uid].is_locked:
    script_item.status = "跳过"
    # 发送 warning 通知

# task_manager.py L676
if script_uid is not None and Config.ScriptConfig[script_uid].is_locked:
    raise RuntimeError("任务已在运行")
```

## 2. ScriptLockLease 设计

### 2.1 数据结构

```python
@dataclass
class ScriptLockLease:
    script_id: str                           # 被锁定的脚本 ID
    task_id: str                             # 持有锁的任务 ID
    state: LockLeaseState                    # 锁状态
    acquired_at: Optional[str]               # 获取时间
    expires_at: Optional[str]                # 过期时间
    _renew_callback: Optional[Callable]      # 续约回调
```

### 2.2 状态机

```
Free ──acquire()──→ Acquired ──release()──→ Released
                       │
                       ├──expire()──→ Expired
                       │
                       └──renew()───→ Acquired (extends expires_at)
```

### 2.3 操作语义

| 操作 | 前置条件 | 后置条件 | 失败行为 |
|------|---------|---------|---------|
| `acquire(script_id, task_id)` | lock not held | lease Active | RuntimeError |
| `release(script_id, task_id)` | held by task_id | lease Released | 无操作 (幂等) |
| `is_active` | N/A | bool | N/A |
| `expire()` | acquired | Expired | N/A |

### 2.4 与 TaskConfigPort 的集成

```
TaskConfigPort.acquire_lock(script_id, task_id) → ScriptLockLease
    ├── 检查现有 lease
    │   ├── 无 lease → 创建新 lease
    │   └── 有 active lease → RuntimeError
    └── 返回 lease

TaskConfigPort.release_lock(script_id, task_id)
    ├── 检查 lease 持有者
    │   ├── 匹配 → release
    │   └── 不匹配 → 无操作
    └── 清理

TaskConfigPort.is_lock_held_by(script_id, task_id) → bool
```

## 3. 锁生命周期

### 3.1 任务执行中的锁流程

```
1. 任务开始前：
   - 单脚本任务：add_task 中检查锁 → raise RuntimeError if locked
   - 队列任务：每个脚本执行前检查 → skip + warning

2. 脚本执行前：
   - acquire_lock(script_id, task_id)
   - 成功 → 执行脚本
   - 失败 → skip + warning

3. 脚本执行后 (finally)：
   - release_lock(script_id, task_id)

4. 任务取消：
   - CancelledError → finally 释放锁

5. 任务异常：
   - Exception → finally 释放锁
```

### 3.2 锁竞争场景

| 场景 | 行为 | 验证 |
|------|------|------|
| 同一脚本两次 add_task | 第二次 raise RuntimeError | observed: test_duplicate_lock_raises |
| 队列中已锁定脚本 | 跳过并发送 warning | observed: test_locked_script_skipped_in_queue |
| 取消后锁释放 | 锁自动释放 | observed: test_lock_released_on_cancellation |
| 异常后锁释放 | 锁自动释放 | observed: test_lock_released_on_exception |
| 错误任务释放锁 | 无操作 | observed: test_lock_release_wrong_task_noop |

## 4. 与 ConfigBase 锁的对比

| 特性 | ConfigBase.is_locked | ScriptLockLease |
|------|---------------------|-----------------|
| 持有者追踪 | 无 | task_id |
| 过期机制 | 无 | expires_at + renew |
| 原子性 | 简单布尔 | 状态机 + 持有者检查 |
| 可测试性 | 需 ConfigBase 实例 | 独立 dataclass |
| 多任务支持 | 不支持 | 支持追踪 |
| 自动释放 | 依赖 del() | explicitly release |

## 5. Phase 2 增强

以下为 Phase 2 计划，当前候选代码未实现：

- [ ] 基于时间的自动过期（`expires_at` + 后台清理任务）
- [ ] 续约机制（`renew()` 延长 `expires_at`）
- [ ] 持久化锁状态（跨进程重启保持）
- [ ] 分布式锁（多实例场景，远期）

## 6. 风险

- **unverified**: `ConfigBase.is_locked` 在 Config v2 authoritative 模式下的行为可能与 v1 不同
- **inferred**: 当前没有其他模块在运行时设置 `is_locked`（只有 ConfigBase 内部操作和 TaskManager 检查）
- **observed**: 锁的释放依赖于 `finally` 块，在进程崩溃时不会自动释放——Phase 2 的过期机制可解决此问题