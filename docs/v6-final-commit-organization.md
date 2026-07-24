# v6 最终提交组织与 PR 草案

> 生成时间：2026-07-23
> 工作树：`AUTO-MAS-workspace\worktrees\all-plugins-integration`（分支 `integration/dev-v2-dev-all-plugins`）
> 基线 HEAD：`b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e`
> 变更规模：210 个有效变更（129 modified + 81 untracked），排除 node_modules/dist/构建产物
> 性质：proposed — 基于 observed 工作树状态，需人工 review 后执行

本文档将当前未提交工作树的全部变更组织为 10 个语义清晰、可独立审查的 PR 分组。每个分组标注：覆盖范围、文件清单、与现有 PR 的关系、验证命令、注意事项。

r6 冻结产物（`_backup/`、`reference/` 中的 r6 artifact）不在本工作树内，不受影响。

---

## PR 分组总览

| PR | 标题 | 类型 | 文件数 | 依赖 | 上游可行性 |
|---|---|---|---|---|---|
| #296 | WebSocket 子系统全栈重构 | refactor | ~28 | 无（基础） | 可上游 |
| #268 | 循环队列模式 | feat | ~5 | #296 | 可上游 |
| #289 | 游戏中心系统插件 | feat | ~12 | #296 | 可上游（需拆分） |
| NEW-1 | Config v2 配置框架 | feat | ~25 | 无 | 可上游 |
| NEW-2 | 插件系统硬化与兼容 | feat/fix | ~20 | #296, NEW-1 | 可上游 |
| NEW-3 | UI v6 重构与插件 UI 扩展 | refactor | ~45 | #296 | 可上游 |
| NEW-4 | CI 硬化与发布门禁 | chore | ~12 | 无 | 可上游 |
| NEW-5 | 发布工具与 wheelhouse 脚本 | chore | ~8 | 无 | 集成专属 |
| NEW-6 | 测试覆盖：WS/Config/Plugin/Emulator | test | ~16 | #296, NEW-1, NEW-2 | 可上游 |
| NEW-7 | 任务适配器兼容与 MaaFW 更新 | fix | ~18 | 无 | 可上游 |

---

## 1. PR #296 — WebSocket 子系统全栈重构（refactor）

### 1.1 覆盖范围

后端 WS 核心模块 + 前端连接层 + 协议迁移。这是 #268 和 #289 的合并前置依赖。

### 1.2 文件清单

**后端（新增）：**
- `app/core/ws/` （整个目录：manager.py, protocol.py, publisher.py, connection.py 等）
- `app/core/config_service.py` （ConfigService，WS 生命周期与配置初始化协调）
- `app/core/lifecycle.py` （ShutdownCoordinator，drain+inflight 关闭协调）
- `app/utils/ws_limits.py` （背压常量：4MiB/64条/5s）
- `app/utils/atomic_file.py` （原子写盘工具，WS 状态持久化用）

**后端（修改）：**
- `app/api/websocket.py` — WS 端点重写，主连接管理器接入
- `app/api/ws_command.py` — `@ws_command(name, params=Model)` 强类型注册表
- `app/api/core.py` — router 列表调整，移除旧 ws_router
- `app/plugins/realtime.py` — 迁移到 `Publisher.send(id=, type=, data=)`
- `app/models/schema.py` — WS 消息 typed payload 模型
- `app/utils/websocket.py` — 旧 `send_websocket_message` 委托适配层

**前端（新增）：**
- `frontend/src/services/websocket/` （整个目录：connection.ts, subscriptions.ts, types.ts）
- `frontend/src/composables/useAppLifecycle.ts` — 生命周期协调器（含启动打点）
- `frontend/src/utils/websocketAuth.ts` — subprotocol HMAC 鉴权
- `frontend/src/utils/httpSecurity.ts` — HTTP 安全头
- `frontend/src/composables/useAppBackground.ts` — 后台检测（修改+新增测试）

**前端（修改）：**
- `frontend/src/composables/useWebSocket.ts` — 迁移到新连接层
- `frontend/src/main.ts` — 初始化顺序调整
- `frontend/src/views/WSdev.vue` — WS 调试页适配
- `frontend/src/components/WebSocketMessageListener.vue` — 消息监听适配
- `frontend/src/types/electron.d.ts` — IPC 类型补充

### 1.3 验证

```powershell
# 后端
uv run python -m pytest tests/ws/ -v
uv run python -m unittest discover tests -v

# 前端
yarn typecheck
yarn vitest run src/services/websocket/ src/composables/useAppLifecycle.ts
yarn lint
```

### 1.4 注意

- 旧 `send_websocket_message` 保留为委托适配层，确保插件渐进迁移。
- `useAppLifecycle.ts` 包含本轮新增的 `performance.now()` 启动打点（P0-PERF-02 修复）。
- 30min/10k+ soak 验证未执行，需真实 Electron 环境补测。

---

## 2. PR #268 — 循环队列模式（feat）

### 2.1 覆盖范围

CycleRun 模式与 per-item 循环调度。

### 2.2 文件清单

- `app/core/task_manager.py` — `_run_cycle_loop`、`_ensure_queue_editable`、cycle 预览推送
- `app/api/queue.py` — 循环队列 API 端点
- `frontend/src/views/scheduler/useSchedulerLogic.ts` — cycleNext/cycleNextList 处理
- `frontend/src/views/scheduler/schedulerConstants.ts` — 循环队列常量
- `frontend/src/views/scheduler/schedulerHandlers.ts` — 调度处理器

### 2.3 依赖

- rebase 到 `dev_v2 + #296`，将 cycle 预览推送迁移到 `Publisher.send(id=protocol.ID_TASK_MANAGER, type=protocol.CYCLE_NEXT, data=...)`。
- 需在 `app/core/ws/protocol.py` 新增 `ID_TASK_MANAGER` / `CYCLE_NEXT` / `CYCLE_NEXT_LIST` 常量。

### 2.4 验证

```powershell
python -m compileall app/core/task_manager.py
uv run python -m pytest tests/ -k "cycle or queue" -v
```

---

## 3. PR #289 — 游戏中心系统插件（feat，需拆分）

### 3.1 覆盖范围

多 provider 游戏管理、ADB APK 安装、模拟器关联、游戏中心前端页面。

### 3.2 文件清单

**后端：**
- `app/core/emulator_manager.py` — 模拟器关联与启动
- `app/api/emulator.py` — 模拟器 API
- `app/api/info.py` — 游戏信息端点
- `app/MaaFW/ArknightWin32.py` — Win32 游戏适配

**前端：**
- `frontend/src/views/emulator/` （整个目录：模拟器管理中心）
- `frontend/src/views/tools/TabGameSign.vue` — 游戏签到页适配
- `frontend/src/router/pageDeclarations.ts` — 路由注册
- `frontend/src/views/setting/TabBasic.vue` — 设置页适配

### 3.3 建议拆分

- **289-A (API)**：`app/api/emulator.py` + `app/api/info.py` router 注册
- **289-B (plugin)**：游戏中心系统插件本体（如工作树中有独立 plugin 目录）
- **289-C (UI)**：`frontend/src/views/emulator/` + 路由
- **289-D (emulator-manager)**：`app/core/emulator_manager.py` 模拟器关联

### 3.4 依赖

- `app/api/__init__.py` 的 router 列表与 #296 协调，建议 #296 先合并。

---

## 4. NEW-PR-1 — Config v2 配置框架（feat）

### 4.1 覆盖范围

Config v2 完整实现：ConfigEntry/ConfigGroup/ConfigCollection/ConfigManager、事务、DPAPI 加密、TOML 持久化、shadow/canary 模式、旧配置兼容迁移。

### 4.2 文件清单

**新增（整个目录）：**
- `app/configuration/__init__.py` — 公共 API 导出，CONFIG_V2_MODE 环境变量
- `app/configuration/v2/` — 核心实现（manager.py, entry.py, group.py, collection.py, node.py, wire.py, encrypted.py, fields.py, signals.py, staging.py, errors.py, shortcuts.py, types.py, examples/, support/）
- `app/configuration/compat/` — 旧配置兼容迁移管道
- `app/configuration/persistence/` — 持久化适配
- `app/configuration/runtime/` — 运行时适配

**修改：**
- `app/core/config.py` — Config 单例接入 v2 shadow 模式
- `app/models/ConfigBase.py` — EncryptValidator 抛 `EncryptedConfigValueError`（P1-SEC-02 修复）
- `app/models/config.py` — 配置模型适配
- `app/models/plugin_script_config.py` — 插件脚本配置适配
- `app/utils/security.py` — DPAPI 应用 entropy + 版本化前缀（P1-SEC-01 修复）
- `app/models/schema.py` — 配置相关 schema（与 #296 有交叉，需协调）

### 4.3 与现有代码的关系

- `config_framework_v2`（群主设计基线）是 `app/configuration/v2` 的严格子集。生产加固实现已包含：per-task 事务队列、validator/observer 拆分、原子落盘、DPAPI 应用 entropy 迁移、shadow/canary 路由、compat 迁移管道。
- 本轮已完成 3 处命名空间清理：`v2/examples/reference_config.py`、`v2/support/logger.py`、`v2/manager.py` 中的 `config_framework_v2` → `app.configuration`。

### 4.4 验证

```powershell
uv run python -m pytest tests/configuration/ -v
uv run python -m unittest discover tests -v
```

### 4.5 注意

- 当前 `_authoritative_load()` / `_migrate_legacy_to_v2()` 仍建立在 legacy 运行时对象之上；启动仍先 `Config.init_config()`，保存仍先写 legacy JSON。它们只能归入过渡兼容实现，不能描述为“v2 TOML 已成为唯一权威源”。
- 默认仍为 `shadow`。在生产原生根、全根 generation/CURRENT 事务、r6 原始字节快照和旧类退出完成前，`AUTO_MAS_CONFIG_V2_MODE=authoritative` 必须 fail-closed。
- 需真实 Windows DPAPI 设备验证 round-trip 后方可默认启用。
- r6 用户配置（旧 JSON）升级路径已在 `_migrate_legacy_to_v2()` 实现，但未实测 round-trip。

---

## 5. NEW-PR-2 — 插件系统硬化与兼容（feat/fix）

### 5.1 覆盖范围

插件生命周期、缓存安全、市场渠道、emulator 兼容、pypi_site、script_adapter。

### 5.2 文件清单

- `app/plugins/cache_store.py` — 缓存安全修复
- `app/plugins/context.py` — 插件上下文
- `app/plugins/fields.py` — 插件字段定义
- `app/plugins/loader.py` — 插件加载器
- `app/plugins/manager.py` — 插件管理器
- `app/plugins/market.py` — 插件市场
- `app/plugins/pypi_site.py` — PyPI 源
- `app/plugins/schema.py` — 插件 schema
- `app/plugins/script_adapter.py` — 脚本适配器
- `app/plugins/system.py` — 系统插件
- `app/plugins/emulator_compat.py` （新增）— 模拟器兼容层
- `app/plugins/market_channel.py` （新增）— 市场渠道
- `app/api/plugins.py` — 插件 API
- `app/api/plugin_gateway.py` — 插件网关
- `app/core/page_registry.py` — 页面注册
- `app/core/script_types.py` — 脚本类型
- `app/services/system.py` — 系统服务
- `app/services/update.py` — 更新服务
- `plugins/auto_mas_core/src/auto_mas_core/__init__.py` — 核心插件
- `plugins/ok_script_adapter/src/ok_script_adapter/adapter/autoproxy.py` — 脚本适配
- `plugins/ok_script_adapter/src/ok_script_adapter/adapter/runtime.py`
- `plugins/ok_script_adapter/src/ok_script_adapter/providers/okef_report.py`
- `plugins/okww_adapter/src/okww_adapter/adapter/autoproxy.py`
- `plugins/okww_adapter/src/okww_adapter/adapter/runtime.py`
- `plugins/auto_mas_core/pyproject.toml`

### 5.3 依赖

- #296（realtime.py 迁移）、NEW-PR-1（配置接入）

### 5.4 验证

```powershell
uv run python -m pytest tests/plugins/ -v
```

---

## 6. NEW-PR-3 — UI v6 重构与插件 UI 扩展（refactor）

### 6.1 覆盖范围

前端 v6 设计系统、组件重构、插件 UI 扩展（iframe sandbox + Vue runtime）、脚本搜索、主题系统。

### 6.2 文件清单

**v6 设计系统（新增）：**
- `frontend/src/components/v6/` — v6 组件库
- `frontend/src/styles/v6-tokens.css` — 设计 token
- `frontend/src/theme/` — 主题系统

**插件 UI 扩展：**
- `frontend/src/plugin/pluginFrontendLoader.ts` — Vue 全局暴露修复（P0-SEC-03，`Object.defineProperty` 不可枚举/不可写/不可配置）
- `frontend/src/plugin/pluginAPI.ts` — 插件 API
- `frontend/src/views/PluginElementHost.vue` — 插件元素宿主
- `frontend/src/views/PluginPageHost.vue` — 插件页面宿主（iframe sandbox）
- `frontend/src/views/Plugin.vue` — 插件页
- `frontend/src/views/PluginMarket.vue` — 插件市场页

**视图重构：**
- `frontend/src/App.vue` — 根组件
- `frontend/src/components/AppLayout.vue` — 布局
- `frontend/src/components/GlobalPowerCountdown.vue`
- `frontend/src/components/NoticeModal.vue`
- `frontend/src/components/ScriptTable.vue`
- `frontend/src/components/TitleBar.vue`
- `frontend/src/components/UpdateModal.vue`
- `frontend/src/views/Home.vue`
- `frontend/src/views/Scripts.vue`
- `frontend/src/views/Initialization/index.vue`
- `frontend/src/views/setting/index.vue`
- `frontend/src/views/setting/TabBasic.vue`
- `frontend/src/views/EditView/Script/MaaEndScriptEdit.vue`
- `frontend/src/views/EditView/Script/SRCScriptEdit.vue`
- `frontend/src/views/EditView/shared/` （新增）

**脚本搜索（新增）：**
- `frontend/src/views/scripts/components/ScriptSearchBar.vue`
- `frontend/src/views/scripts/scriptPageSearch.ts`
- `frontend/src/views/scripts/components/scriptCreateFlow.ts`（修改）

**工具与 composables：**
- `frontend/src/composables/useTheme.ts` — 主题
- `frontend/src/composables/useUpdateDownload.ts` — 更新下载
- `frontend/src/utils/appEntry.ts`
- `frontend/src/utils/browserDevElectronAPI.ts`
- `frontend/src/utils/openExternal.ts`
- `frontend/src/utils/scheduler-debug.ts`
- `frontend/src/utils/skippedInitializationStartup.ts`
- `frontend/src/composables/useLowPerfMode.ts` （新增）
- `frontend/src/types/markdown-it.d.ts` （新增）
- `frontend/src/views/pluginActionTransport.ts` （新增）

**前端测试：**
- `frontend/src/composables/useAppBackground.test.ts`
- `frontend/src/composables/useTheme.test.ts`
- `frontend/src/composables/useWebSocket.test.ts`
- `frontend/src/utils/httpSecurity.test.ts`
- `frontend/src/utils/openExternal.test.ts`
- `frontend/src/utils/websocketAuth.test.ts`
- `frontend/src/views/pluginActionTransport.test.ts`
- `frontend/src/views/scripts/scriptPageSearch.test.ts`

### 6.3 依赖

- #296（WS 连接层是 UI 交互基础）

### 6.4 验证

```powershell
yarn typecheck
yarn vitest run
yarn lint
yarn build
```

### 6.5 注意

- `vite.config.ts` 的 manualChunks 分包（P0-PERF-01）已配置，但不在本工作树修改列表中（可能已提交或位于构建配置层）。
- 2 个预存 typecheck 错误（`emulatorApiContract.test.ts` possibly undefined、`vite.config.ts replaceAll` lib target），非本轮引入。

---

## 7. NEW-PR-4 — CI 硬化与发布门禁（chore）

### 7.1 覆盖范围

GitHub Actions 第三方 SHA pin、permissions 最小化、SignPath 配置、CNB 同步、MirrorChyan 发布。

### 7.2 文件清单

- `.github/workflows/build-app.yml` — SHA pin + permissions 拆分
- `.github/workflows/check-version-json.yml`
- `.github/workflows/cnb_release.py`
- `.github/workflows/cnb_trigger.py`
- `.github/workflows/github_download_and_cnb_upload.py`
- `.github/workflows/mirrorchyan-release-note.yml`
- `.github/workflows/mirrorchyan.yml` — permissions 声明
- `.github/workflows/requirements.txt`
- `.github/workflows/sync-cnb.yml`
- `.github/workflows/ACTION_PINS.md` （新增）— SHA pin 对照表
- `.github/workflows/RELEASE_HARDENING_REPORT.md` （新增）— 硬化报告
- `.github/workflows/scripts/` （新增）

### 7.3 验证

```powershell
# YAML 语法检查
yarn yaml-lint .github/workflows/*.yml
# SHA pin 完整性
Get-Content .github/workflows/ACTION_PINS.md
```

### 7.4 注意

- SignPath `project-slug: AUTO_MAA` 与仓库名 AUTO-MAS 不一致，需 SignPath 侧确认是否为历史命名。
- permissions 拆分后 release job 仍需 `actions: write`（触发 release 工作流）。

---

## 8. NEW-PR-5 — 发布工具与 wheelhouse 脚本（chore，集成专属）

### 8.1 覆盖范围

wheelhouse 构建/验证脚本、集成发布构建脚本。**部分内容集成专属，不可直接上游。**

### 8.2 文件清单

- `scripts/verify_wheelhouse_snapshot.py` （新增）— snapshot 验证
- `scripts/build_integration_wheelhouse.ps1` （新增）
- `scripts/build_complete_integration_wheelhouse.ps1` （新增）
- `scripts/complete_integration_wheelhouse.ps1` （新增）
- `scripts/plugin_compat/` （新增）— 插件兼容性检查
- `frontend/scripts/build-integration-release.mjs` （新增）
- `frontend/scripts/validate-wheelhouse.mjs` （新增）
- `frontend/scripts/integration-release.test.mjs` （新增）
- `res/version.json` （修改）— 版本信息
- `plugins/wheels/` （新增）— wheelhouse（二进制产物，可能需 .gitignore 排除）

### 8.3 注意

- **P0-REL-01 wheelhouse drift 仍存在，且先前版本记录已过期**：正式 wheelhouse 仍为 `automas-script-hsr` 0.1.2、SRA 0.1.2、M7A 0.1.3、meta 0.1.3；当前独立 HSR 源码已是 core/SRA 0.1.4、M7A/meta 0.1.5。r3 scratch 候选尚在安全复核，不能直接替换正式 wheelhouse；复核通过后还需重建 runtime-lock 和 `res/integration-snapshot.json` 并重跑严格契约。
- `plugins/wheels/` 可能是二进制 wheel 产物，需确认是否应纳入 Git 或加入 `.gitignore`。

---

## 9. NEW-PR-6 — 测试覆盖：WS/Config/Plugin/Emulator（test）

### 9.1 覆盖范围

WebSocket、Config v2、插件黑盒、模拟器、HTTP 安全、chaos 测试。

### 9.2 文件清单

- `tests/ws/` （新增）— WS 核心单元测试
- `tests/configuration/` （新增）— Config v2 测试
- `tests/chaos/` （新增）— 混沌测试
- `tests/emulator/` （新增）— 模拟器测试
- `tests/http/` （新增）— HTTP 安全测试
- `tests/plugin_blackbox/` （新增）— 插件黑盒认证测试
- `tests/plugins/test_bootstrap_discovery.py` （新增）
- `tests/plugins/test_browser_runtime.py` （新增）
- `tests/plugins/test_cache_store_security.py` （新增）
- `tests/plugins/test_manager_bundled_runtime_policy.py` （新增）
- `tests/plugins/test_official_script_adapter_compat.py` （新增）
- `tests/plugins/test_plugin_lifecycle_fixes.py` （新增）
- `tests/plugins/test_plugin_no_config_schema.py` （新增）
- `tests/plugins/test_verify_wheelhouse_snapshot.py` （新增）
- `tests/plugins/test_okww_plugin_schema.py` （修改）
- `tests/services/test_update_service.py` （修改）

### 9.3 验证

```powershell
uv run python -m pytest tests/ -v --tb=short
```

### 9.4 注意

- 真实设备手测卡（49 项验收 + 50 张手测卡）未回填，8 张关键手测卡（MC-001/002/018/028/031/039/043/050）必须后续补齐。

---

## 10. NEW-PR-7 — 任务适配器兼容与 MaaFW 更新（fix）

### 10.1 覆盖范围

M9A/MAA/MaaEnd/SRC/general 任务适配器与 MaaFW ArknightWin32 更新。

### 10.2 文件清单

- `app/task/general/adapter.py`
- `app/task/general/AutoProxy.py`
- `app/task/general/manager.py`
- `app/task/general/ScriptConfig.py`
- `app/task/M9A/AutoProxy.py`
- `app/task/M9A/manager.py`
- `app/task/MAA/AutoProxy.py`
- `app/task/MAA/manager.py`
- `app/task/MAA/ManualReview.py`
- `app/task/MAA/ScriptConfig.py`
- `app/task/MaaEnd/AutoProxy.py`
- `app/task/MaaEnd/manager.py`
- `app/task/MaaEnd/ManualReview.py`
- `app/task/MaaEnd/ScriptConfig.py`
- `app/task/SRC/AutoProxy.py`
- `app/task/SRC/manager.py`
- `app/task/SRC/ManualReview.py`
- `app/task/SRC/ScriptConfig.py`
- `app/MaaFW/ArknightWin32.py`

### 10.3 依赖

- 无直接依赖，可与 #296 并行。

---

## 根文件变更

以下根文件修改归属各 PR：

| 文件 | 归属 PR | 说明 |
|---|---|---|
| `.gitignore` | NEW-PR-5 | 排除 wheelhouse/dist 产物 |
| `main.py` | #296 | 启动入口 WS 初始化 |
| `pyproject.toml` | NEW-PR-1 | Config v2 依赖声明 |
| `requirements.txt` | NEW-PR-1 | Python 依赖 |
| `res/version.json` | NEW-PR-5 | 版本信息 |

---

## 合并顺序建议

```
1. NEW-PR-1 (Config v2)        ─── 无依赖，基础
2. #296 (WebSocket)            ─── 无依赖，基础
3. #268 (循环队列)              ─── 依赖 #296
4. NEW-PR-2 (插件硬化)          ─── 依赖 #296 + NEW-PR-1
5. #289 (游戏中心，拆分后)      ─── 依赖 #296
6. NEW-PR-3 (UI v6)            ─── 依赖 #296
7. NEW-PR-7 (任务适配器)        ─── 无依赖，可并行
8. NEW-PR-4 (CI 硬化)          ─── 无依赖，可并行
9. NEW-PR-5 (发布工具)          ─── 依赖全部功能 PR
10. NEW-PR-6 (测试覆盖)         ─── 依赖全部功能 PR
```

---

## r6 冻结产物保护

以下路径不在本工作树内，不受任何 PR 影响：

- `_backup/` — r6 迁移审计、配置、补丁
- `reference/` — 参考项目
- `_alpha_build/` — 历史审计输出（仅文档，不纳入提交）

`_alpha_build/a1/glm-game-emulator-management-20260723/` 出现在 untracked 列表中，属于本轮审计输出文档，应加入 `.gitignore` 或排除在提交之外。

---

## 本轮（2026-07-23）新增代码级修复

以下 6 项修复已包含在上述 PR 分组中：

| 修复 | 归属 PR | 文件 | 内容 |
|---|---|---|---|
| Config v2 命名空间 1 | NEW-PR-1 | `app/configuration/v2/examples/reference_config.py` | `from config_framework_v2` → `from app.configuration` |
| Config v2 命名空间 2 | NEW-PR-1 | `app/configuration/v2/support/logger.py` | logger 命名空间 → `app.configuration` |
| Config v2 命名空间 3 | NEW-PR-1 | `app/configuration/v2/manager.py:149-157` | ContextVar 名称 → `app_configuration_*` |
| P0-SEC-03 Vue 全局暴露 | NEW-PR-3 | `frontend/src/plugin/pluginFrontendLoader.ts:97-107` | `Object.defineProperty` 不可枚举/不可写/不可配置 |
| P0-PERF-02 启动打点 | #296 | `frontend/src/composables/useAppLifecycle.ts` | `performance.now()` 埋点 |
| P1-CFG-01 authoritative 模式 | NEW-PR-1 | `main.py`、`app/core/config_service.py`、`app/models/ConfigBase.py` | 当前仍是 legacy-first 投影链；需原生根、fail-closed、全根代际事务和启动顺序重构 |
| authoritative 模式测试 | NEW-PR-6 | `tests/configuration/test_config_v2_exp_alpha.py`、新增真实 r6 fixtures | 现有 116 tests 仅是过渡兼容回归；需补八根迁移、崩溃注入、完整回滚与旧类零运行引用门禁 |
| 8 张关键手测卡 | NEW-PR-6 | `docs/v6-final-manual-test-cards.md` | MC-001/002/018/028/031/039/043/050 完整步骤与证据清单 |
| 离线首次启动验证脚本 | NEW-PR-5 | `scripts/verify_offline_first_start.ps1` | 目录结构/wheelhouse/health/配置创建/日志检查 |
| r6 升级回滚验证脚本 | NEW-PR-5 | `scripts/verify_r6_upgrade_rollback.ps1` | r6 备份/v2 迁移/配置一致性/回滚/明文密钥检查 |

验证：
- `uv run python -m py_compile app/core/config_service.py`：0 错误
- `uv run pytest tests/configuration/ -v`：历史记录为 116 passed in 1.58s；不可据此宣称 native authoritative 已完成
- `yarn typecheck`：通过（仅剩 2 个预存错误，非本轮引入）

---

## 待办项（需人工/设备/CI 执行）

以下项无法在当前代码层完成，需后续推进：

| 项 | 阻断 | 所需环境 | 关联 PR | 就绪状态 |
|---|---|---|---|---|
| Config v2 native authoritative 实现与设备验证 | A 测配置门禁 | 先完成源码/fixture，再做 Windows DPAPI 设备验证 | NEW-PR-1 后续 | 源码门禁未就绪，不能直接切默认模式 |
| wheelhouse 重新构建（HSR 四包对齐） | P0-REL-01 drift（正式包落后当前 core/SRA 0.1.4、M7A/meta 0.1.5） | r3/r4 候选安全复核 + Python 构建 | NEW-PR-5 | scratch 候选存在，正式替换尚未执行 |
| SignPath 签名 | 无签名安装包 | CI workflow_dispatch | NEW-PR-4 | 需 CI 触发 |
| 真实设备手测 | 49 项验收 blocked | Windows + 模拟器 | NEW-PR-6 后续 | 手测卡模板已就绪 |
| WS soak 验证 | 30min/10k+ 未执行 | 真实 Electron | #296 后续 | 需设备 |
| r6 覆盖升级测试 | 回滚验证 | r6 安装环境 | NEW-PR-6 后续 | 验证脚本已就绪 |
