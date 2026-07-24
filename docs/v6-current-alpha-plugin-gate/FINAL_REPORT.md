# AUTO-MAS v6 Experimental Alpha：当前全插件自动门禁复核

状态：**P1 BLOCKED（插件重载失败被错误报告为成功）**。

此结论基于 [快照](START_FINAL_SNAPSHOT.md) 中固定的源码、wheelhouse 和 runtime-lock 哈希。报告只覆盖自动化、合成插件和 import-only 验证；不把真实 GUI、真实 Agent、游戏或模拟器当作已通过。

## 已自动验证通过（observed）

| 门禁 | 实测结果 |
| --- | --- |
| 严格 wheelhouse 快照 | PASS：127 wheels、23 plugin distributions、21 entry points、`auto-mas-core 6.0.0a1`，manifest/runtime-lock 哈希均匹配 snapshot。 |
| 宿主插件回归 | `py -3.12 -m pytest tests/plugins -q -p no:cacheprovider --basetemp <evidence>`：**156 passed**。 |
| 插件黑盒回归 | `tests/plugin_blackbox`：**145 passed, 2 skipped**。两个 skip 都是 `MaaKes-win-x86_64-v1.1.11: no agent block`，符合“不得启动真实 Agent”的边界。 |
| 离线候选环境 | 在专属新 venv 中以 `pip install --no-index --no-deps` 安装当前 127 个 wheel；`pip check` 返回 `No broken requirements found.` |
| 21 个正式入口点 | 从 runtime lock 读取 21 项；隔离 venv 中 metadata discovery、`module:Plugin` 只导入和 class 解析 **21/21 PASS**，无额外 entry point、无触发的进程/网络/浏览器/桌面启动拦截事件。未实例化 Plugin，也未调用生命周期。 |
| 合成生命周期 | FakeHost（真实 loader/event bus/service registry，合成插件）15 场景：**14 PASS、1 PARTIAL、0 FAIL**；覆盖启动失败隔离、批量部分失败、重载、卸载、重复/同名入口点、缺依赖、版本覆盖、配置迁移及重启恢复。 |

## P1：重载失败会造成插件不可用且 API 假报成功（observed）

### 最小复现

`direct_reload_closed_repro.json` 只 mock config store、loader 和 snapshot publish，不实例化任何插件：

1. Loader 返回当前失败清理后的 `status="closed", error=None`。
2. `PluginManager._reload_instance()` 没有调用 `_set_instance_enabled()`，却安排 snapshot。
3. `POST /plugins/reload_instance` 的函数层调用返回 `OutBase(code=200, status="success")` 与“插件实例重载成功”。

结果是 `VULNERABILITY_REPRODUCED`。这不是推断：可复现数据和日志在证据目录。

### 精确调用链

- `app/plugins/loader.py:1477-1499`：旧实例先执行 `on_reload_prepare`，随后在 **1484** 被 unload；新实例加载失败后，**1492-1498** 再 unload 新记录并标记 `closed`，没有恢复旧实例，也没有保留 failure error。
- `app/plugins/manager.py:2086-2108`（单实例）和 `2157-2180`（按插件批量）仅以 `record.status == "error"` 识别失败；`closed` 漏检。
- `app/api/plugins.py:583-592`：manager 无异常时固定返回 HTTP/function code 200 成功。
- 现有 `tests/chaos/test_plugin_lifecycle.py:440-471` 允许失败后为 `error` **或** `closed`；现有 FakeHost `case_runner.py:367-430` 也明确将此情况标为 `PARTIAL`，并承认旧实例已被移除。

该问题由用户可操作的单实例重载路由和按插件批量重载路径触发，故按 Alpha **P1** 处理。

### 推荐最小修复（candidate，未在本任务内改动）

1. Loader 的失败清理后必须保留明确失败信息，不能返回 `closed/error=None`；例如保持 `error` 状态或提供清晰的失败结果对象。
2. `PluginManager` 的单实例及批量重载路径必须按“**不是 active 即失败**”处理，不能只匹配 `error`；必须停止成功 snapshot/API 响应。
3. 对更新/配置重载，复用 `app/plugins/manager.py:1451-1525` 已有的配置与运行态回退 helper，回退失败必须向 API 返回明确的“回滚不完整”。现有 `update_instance_transaction()` 已有相关覆盖（`tests/plugins/test_plugin_lifecycle_fixes.py:855-920`），但直接重载路径没有复用它。
4. 新增真实 `PluginLoader` 合成插件回归：失败重载后旧配置/旧运行态恢复，或至少返回失败且绝不宣称成功；同时断言无 listener/service/page registry 残留。再新增 API/WS 路由测试，确保失败为非成功码。

完全的“新旧插件双实例 staged swap”可作为正式版增强；它不是修复 Alpha 假成功与无错误态的最小前置条件。

## 未验证或仅部分覆盖（unverified / partial）

- FakeHost case 05 为 `PARTIAL`：已确认失败后无 listener 泄漏，但旧实例未恢复，正是上述 P1。
- MaaKes 参考项目的两项 agent block 因安全边界跳过；它们不能据此标为兼容通过。
- 未启动真实 GUI、Electron、真实 Agent、真实游戏或模拟器；安装后首次启动、脚本实跑、设备/模拟器控制仍需要人工门禁。
- 当前共享工作树在审计期间有并行改动；若 P1 修复、wheelhouse、runtime lock、snapshot 或插件入口点变更，相关测试必须重跑。

## P0/P1 裁决

- **P0：未在本门禁范围内观察到。** 这不是全系统无 P0 声明。
- **P1：1 个已复现阻断项。** 在修复并通过上述回归前，不建议把当前源码标为 Alpha 全插件门禁通过或产出 A 测包。

完整日志、JSON 结果与哈希见 [EVIDENCE_INDEX.md](EVIDENCE_INDEX.md)。
