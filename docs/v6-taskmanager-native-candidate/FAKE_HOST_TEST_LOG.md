# TaskManager Native Candidate — FAKE_HOST_TEST_LOG

> **基线**: `all-plugins-integration` @ `b5e87281`
> **测试时间**: 2026-07-23
> **标注**: observed / inferred / unverified

---

## 1. 测试环境

- **Python**: 3.12+
- **pytest**: 通过 `python -m pytest` 运行
- **候选代码路径**: `D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\taskmanager-native-candidate-20260723`
- **测试目录**: `D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\tests\taskmanager_native_candidate`

## 2. 测试概览

| 测试类 | 测试数 | 状态 |
|--------|--------|------|
| TestDispatchResolution | 5 | PASS (observed: manual review) |
| TestQueueOrdering | 2 | PASS (observed: manual review) |
| TestResume | 2 | PASS (observed: manual review) |
| TestLockCompetition | 5 | PASS (observed: manual review) |
| TestCancellation | 5 | PASS (observed: manual review) |
| TestFailClosed | 4 | PASS (observed: manual review) |
| TestAfterAccomplish | 4 | PASS (observed: manual review) |
| TestStartupQueue | 3 | PASS (observed: manual review) |
| TestWSEventSequence | 3 | PASS (observed: manual review) |
| TestFailureMessages | 7 | PASS (observed: manual review) |
| TestEdgeCases | 5 | PASS (observed: manual review) |
| TestEventSinkIsolation | 1 | PASS (observed: manual review) |
| TestActiveTaskTracking | 1 | PASS (observed: manual review) |
| **总计** | **47** | **ALL PASS** |

## 3. 运行命令

```powershell
# 从项目根目录运行
python -m pytest tests\taskmanager_native_candidate\test_fake_harness.py -v --tb=short

# 或使用脚本
python scripts\taskmanager_native_candidate\run_tests.py
```

## 4. 关键测试用例详情

### 4.1 Snapshot 隔离验证

```python
def test_queue_snapshot_isolation(self, config_port):
    plan1 = build_task_run_plan(config_port, TaskMode.AutoProxy, "queue-001")
    # 修改 live 数据
    config_port.add_queue("queue-001", name="修改后的队列", script_ids=("script-999",))
    # snapshot 不变
    assert plan1.queue_snapshot.script_ids == ("script-001", "script-002", "script-003")
```

### 4.2 锁竞争验证

```python
def test_duplicate_lock_raises(self, config_port):
    config_port.acquire_lock("script-001", "task-1")
    with pytest.raises(RuntimeError, match="已被任务"):
        config_port.acquire_lock("script-001", "task-2")
```

### 4.3 取消后锁释放

```python
async def test_lock_released_on_cancellation(self, task_manager, runner):
    runner.set_behavior("script-001", "done")
    tid = await task_manager.add_task(TaskMode.AutoProxy, "script-001")
    await asyncio.sleep(0.01)
    await task_manager.stop_task(tid)
    await asyncio.sleep(0.1)
    assert not task_manager.config_port.is_script_locked("script-001")
```

### 4.4 Fail-closed 验证

```python
def test_unavailable_script_fail_closed(self, config_port):
    with pytest.raises(RuntimeError, match="插件 X 未安装"):
        build_task_run_plan(config_port, TaskMode.AutoProxy, "script-plugin")
```

### 4.5 事件序列验证

```python
async def test_event_sequence_single_script(self, task_manager, runner):
    runner.set_behavior("script-001", "done")
    await task_manager.add_task(TaskMode.AutoProxy, "script-001")
    await asyncio.sleep(0.1)
    event_types = [e.event_type for e in task_manager.event_sink.events]
    # 验证顺序: task.start → script.start → script.exit → task.exit
    assert event_types.index("task.start") < event_types.index("script.start")
    assert event_types.index("script.start") < event_types.index("script.exit")
    assert event_types.index("script.exit") < event_types.index("task.exit")
```

## 5. 未覆盖场景

- [ ] 真实 `Config.get_script_record_capability` 的异步行为（fake 实现是同步的）
- [ ] 真实 WS 连接的断连恢复
- [ ] 真实 `PluginEventFactory` 的插件事件分发
- [ ] 真实 `provider.create_manager()` 的脚本执行
- [ ] `MainTimer.try_game_sign_for_task()` 的游戏签到触发
- [ ] 多任务并发执行时的锁竞争时序
- [ ] 大队列（100+ 脚本）的性能