# TaskManager Native Candidate — CALLGRAPH

> **基线**: `all-plugins-integration` @ `b5e87281`
> **标注**: observed / inferred / unverified

---

## 1. 完整调用链

```
main.py lifespan
├── Config.init_config()                          [observed]
│   ├── ScriptConfig.connect(JSON)                [observed]
│   ├── QueueConfig.connect(JSON)                 [observed]
│   └── _migrate_general_scripts_to_plugin_storage() [observed]
│
├── PluginManager.start(fast_startup=False)       [observed]
│   └── validate_script_type_registry(Config)     [observed]
│
├── background: MainTimer.start()                 [observed]
│
├── (yield) ── 服务运行
│   │
│   ├── POST /api/dispatch/start
│   │   └── TaskManager.add_task(mode, id, resume_from_script_id)
│   │       ├── [1] 解析 ID → queue_id | script_id | user_id
│   │       │   ├── Config.QueueConfig[uid]                   [observed]
│   │       │   ├── Config.ScriptConfig[uid]                  [observed]
│   │       │   └── Config.ScriptConfig[uid].UserData         [observed]
│   │       │
│   │       ├── [2] _queue_script_ids(queue_id)
│   │       │   └── Config.QueueConfig[uid].QueueItem.values() [observed]
│   │       │       └── filter(script_id != "-")              [observed]
│   │       │
│   │       ├── [3] _validate_task_capabilities(mode, script_ids)
│   │       │   ├── Config.ScriptConfig[uid]                  [observed]
│   │       │   └── Config.get_script_record_capability(uid)  [observed]
│   │       │       ├── _resolve_record_provider(script_config) [observed]
│   │       │       └── provider.resolve_record_capability()  [observed]
│   │       │
│   │       ├── [4] 锁检查: Config.ScriptConfig[uid].is_locked [observed]
│   │       │
│   │       ├── [5] 创建 TaskInfo → Task → Task.execute()
│   │       │   ├── Task.prepare()
│   │       │   │   ├── Config.QueueConfig[uid].QueueItem.values() [observed]
│   │       │   │   └── Config.ScriptConfig[uid].get("Info", "Name") [observed]
│   │       │   │
│   │       │   ├── Task.main_task()
│   │       │   │   ├── resume 逻辑 → 查找 resume_from_script_id [observed]
│   │       │   │   │
│   │       │   │   ├── for each script:
│   │       │   │   │   ├── Config.ScriptConfig[uid] in check [observed]
│   │       │   │   │   ├── _resolve_script_provider(uid)     [observed]
│   │       │   │   │   │   ├── Config.ScriptConfig[uid]      [observed]
│   │       │   │   │   │   ├── PluginScriptConfig type check [observed]
│   │       │   │   │   │   ├── script_type_registry.get()    [observed]
│   │       │   │   │   │   └── build_legacy_fallback_provider() [observed]
│   │       │   │   │   │
│   │       │   │   │   ├── Config.get_script_record_capability() [observed]
│   │       │   │   │   ├── mode check                       [observed]
│   │       │   │   │   ├── Config.ScriptConfig[uid].is_locked [observed]
│   │       │   │   │   ├── PluginEventFactory.emit_script_event_async() [observed]
│   │       │   │   │   ├── provider.create_manager(script_item) [observed]
│   │       │   │   │   └── self.spawn(task_item)            [observed]
│   │       │   │   │
│   │       │   │   └── 异常处理 (CancelledError/Exception)   [observed]
│   │       │   │
│   │       │   ├── Task.final_task()
│   │       │   │   ├── Publisher.send(TASK_COMPLETED)       [observed]
│   │       │   │   ├── PluginEventFactory.emit_event_async() [observed]
│   │       │   │   ├── AfterAccomplish → Config.power_sign  [observed]
│   │       │   │   │   └── Publisher.send(POWER_SIGN_UPDATED) [observed]
│   │       │   │   └── MainTimer.try_game_sign_for_task()   [observed]
│   │       │   │
│   │       │   └── Task.on_crash(e)                         [observed]
│   │       │       └── Publisher.send(TASK_NOTICE)          [observed]
│   │       │
│   │       └── [6] clean_task(task_uid)
│   │           ├── task_handler[uid].accomplish.wait()      [observed]
│   │           ├── 清理 dict                                [observed]
│   │           └── System.start_power_task()                [observed]
│   │
│   ├── POST /api/dispatch/stop
│   │   └── TaskManager.stop_task(task_id)
│   │       ├── task_handler[uid].cancel()                   [observed]
│   │       └── task_handler[uid].accomplish.wait()          [observed]
│   │
│   ├── POST /api/dispatch/get/power
│   │   └── Config.power_sign                                [observed]
│   │
│   ├── POST /api/dispatch/set/power
│   │   └── Config.power_sign = signal                       [observed]
│   │
│   └── POST /api/dispatch/cancel/power
│       └── System.cancel_power_task()                       [observed]
│
├── 关闭: TaskManager.stop_task("ALL")                       [observed]
├── 关闭: MainTimer.stop()                                   [observed]
├── 关闭: System.cancel_power_task()                         [observed]
└── 关闭: config_service.shutdown()                          [observed]
```

## 2. 启动队列调用链

```
TaskManager.start_startup_queue()
├── asyncio.sleep(10)                                        [observed]
├── Config.websocket is None → 跳过                          [observed]
├── for uid, queue in Config.QueueConfig.items():            [observed]
│   ├── queue.get("Info", "StartUpEnabled")                  [observed]
│   └── TaskManager.add_task("AutoProxy", str(uid), ...)     [observed]
└── _startup_queue_started = True                            [observed]
```

## 3. TaskInfo.on_change 调用链

```
TaskInfo.on_change()
├── Publisher.send(id=task_id, type=TASK_INFO_UPDATED)       [observed]
├── Publisher.send(id=task_id, type=TASK_LOG_UPDATED)        [observed]
├── _emit_task_progress()                                    [observed]
│   ├── PluginEventFactory.build_task_progress_data()        [observed]
│   │   └── _resolve_queue_name(queue_id)                    [observed]
│   │       └── Config.QueueConfig[queue_id].get("Info", "Name") [observed]
│   └── PluginEventFactory.emit_event_async(TASK_PROGRESS)   [observed]
└── _emit_task_log()                                         [observed]
    └── PluginEventFactory.emit_event_async(TASK_LOG)        [observed]
```

## 4. Config v2 与 ConfigBase 交汇点

```
apply_script_type_registry_to_global_config(Config)
├── script_type_registry.bootstrap()                         [observed]
├── Config.ScriptConfig.sub_config_type[...] = PluginScriptConfig [observed]
└── for provider in script_type_registry.list():
    └── Config.ScriptConfig.sub_config_type[...] = provider.script_config_class [observed]

Config.init_config()
├── Config.ScriptConfig.connect(JSON)  ← 仍然是 ConfigBase  [observed]
├── Config.QueueConfig.connect(JSON)   ← 仍然是 ConfigBase  [observed]
└── Config.ToolsConfig.connect(JSON)   ← 仍然是 ConfigBase  [observed]
```

**关键发现**: 当前 `Config.ScriptConfig` 和 `Config.QueueConfig` 仍然是 `MultipleConfig` (ConfigBase 子类)，连接到 JSON 文件。Config v2 的 authoritative 模式是在上层叠加 TOML 数据源，而非替换这些 ConfigBase 实例。这意味着 TaskManager 的迁移必须通过端口抽象来隔离，而非直接让 ConfigBase 退出运行链。

## 5. 端口隔离后的调用链

```
TaskManager (native)
├── TaskConfigPort (protocol)
│   ├── build_queue_snapshot(queue_id) → QueueExecutionSnapshot (frozen)
│   ├── build_script_descriptor(script_id) → ScriptDescriptor (frozen)
│   ├── build_script_execution_snapshot(script_id) → ScriptExecutionSnapshot (frozen)
│   ├── acquire_lock(script_id, task_id) → ScriptLockLease
│   ├── release_lock(script_id, task_id)
│   ├── get_power_policy() → PowerPolicyPort
│   ├── get_event_sink() → TaskEventSink
│   └── is_websocket_connected() → bool
│
├── TaskRunPlan (frozen, immutable)
│   ├── DispatchTarget
│   ├── Tuple[ScriptExecutionSnapshot, ...]
│   └── Optional[QueueExecutionSnapshot]
│
├── ScriptRunner (protocol)
│   └── execute(snapshot, task_id, mode, event_sink) → ScriptStatus
│
└── TaskEventSink (protocol)
    ├── emit_script_start/exit
    ├── emit_task_start/exit
    ├── send_notice/completed
    └── send_power_sign
```