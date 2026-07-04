# release/v5.2.0-withplugin 合并记录（第二阶段）

> 日期：2026-07-04
> 前置：第一阶段（5 个 feat 分支合并）见本文档下方或 git 历史 `01cbe029`
> 本阶段：`origin/release/v5.2.0-withplugin.0.0.1`（feat/PluginSystem 后续，含完整插件框架 + uv 包管理切换）合入 `dev_v2`
> 关键提交：合并 `5eed9cb9`；后续修复 `f24e7773`（用户提交）、`627d6888`（notify 注解 + pyproject 清理 + 测试导入修复）

## 一、已完成

### 1. 合并（49 个冲突文件，全部解决）

**后端冲突决策：**

| 文件 | 决策 |
|---|---|
| `app/plugins/`（`__init__.py`/`event_bus.py`/`event_contract.py`） | **取 release 侧**。release 是完整插件框架（30+ 模块：loader/manager/lifecycle/context/market/uv_backend 等），取代第一阶段手接的 event_bus 骨架 |
| `app/core/task_manager.py` | **取 release 侧**（provider 分发 + PluginEventFactory 全生命周期事件），再回补 dev_v2 的两个功能：`resume_from_script_id`（断点续跑，含 add_task 参数与 TaskInfo 传递）和 `final_task` 末尾的游戏签到触发（`MainTimer.try_game_sign_for_task`） |
| `app/core/script_types.py`（新文件，含冲突后修改） | **手工扩展**：release 只注册 SRC/MaaEnd/General 三种 provider，已补齐 MAA/M9A/MaaFW/Okww/HSR 共 8 种（`_register_builtin_providers`），并同步扩展 `_bind_builtin_script_config_models`（sub_config_type + related_config 绑定）。editor_kind 采用 `builtin:maa`/`builtin:m9a`/`builtin:maafw`/`builtin:okww`/`builtin:hsr` |
| `app/core/config.py` | 取 release 的 provider 化 `add_script`/`add_user`（走 registry），删除 dev_v2 的 isinstance 链；VERSION 保留 `v5.4.0-beta.1` |
| `app/models/config.py` | 取并集（release 的 PluginConfig 类 + dev_v2 的全部脚本配置类）；MaaEnd WaitTime 校验器取 dev_v2 的 `RangeValidator(60, 9999)`（来自 240fec0c 有意修改） |
| `app/task/__init__.py` | 取 release 的懒加载模式，`_LAZY_EXPORTS` 扩展到全部 8 个 Manager |
| `app/task/MAA/`、`app/task/general/manager.py` | release 删除了这些（改为插件承载），**已恢复 dev_v2 版本**——因插件源码（script_maa 等）不在仓库内，删除会导致 MAA 完全不可用 |
| `app/task/MaaEnd/`（AutoProxy/ScriptConfig/tools/login） | 取 dev_v2（历史更新，含 release 侧同源提交） |
| `app/api/emulator.py` | 取 release（走 PluginManager.service），模拟器功能依赖 emulator 插件 |
| `app/api/__init__.py`、`main.py` | 取并集：release 的 ws/plugins/plugin_gateway 路由 + dev_v2 的 qr_login 可选路由。注意 scripts/plan/emulator/queue 路由现在由 `auto_mas_core` 插件的 `get_core_plugin_routers()` 注册 |
| `app/utils/LogMonitor.py` | 合成：release 的 EOF 检测（bline 为空即 break，修 #155 卡死）+ dev_v2 的 1 秒节流回调 |
| `app/utils/constants.py` | 保留 dev_v2 的 FORBIDDEN_PATH 常量（`app/models/ConfigBase.py` 引用它们） |
| `app/__init__.py` | 并集（plugins + task 懒导入） |
| `requirements.txt` | 并集：PyYAML + watchdog |
| `res/html/*.html` 4 个模板 | release 删除，**已恢复**（HSR/M9A/MAA/MaaEnd/general 的 notify.py 仍引用） |
| `res/version.json` | 保留 v5.4.0-beta.1 结构，并入 release 的插件系统条目与 #155 修复条目 |
| `.gitignore` | 并集：dev_v2 全部 + release 的 `/environment/`、`/plugins/*`（仅 auto_mas_core 入库） |

**前端冲突决策：**

| 文件 | 决策 |
|---|---|
| `frontend/src/views/Scripts.vue`、`ScriptTable.vue` | **取 release 侧**（descriptor 驱动：`registryApi.getScriptTypes()` + `normalizeScriptRecord` + available 标记）。⚠️ 这丢弃了第一阶段合入的 ScriptCreateDialog 新建弹窗和"复制脚本"功能，见"未完成"§2 |
| `frontend/src/utils/scriptRegistry.ts`（release 新文件） | **手工扩展**：`getScriptIcon`/`getScriptTypeTagColor` 补 M9A/Okww/HSR 图标与颜色；`BUILTIN_SCRIPT_TYPES` 补全 7 类；`getScriptEditPath`/`getUserCreatePath`/`getUserEditPath` 重写为 `BUILTIN_EDITOR_SEGMENTS` 映射表（与后端 editor_kind 一一对应） |
| `frontend/src/router/index.ts` | 取并集（脚本用 Python 处理）：dev_v2 全部内建路由（maa/m9a/maafw/hsr/general/okww）+ release 的 schema/plugin 通用路由。⚠️ dev_v2 的 `/plans`、`/emulators` 等页面路由被 release 的 `createPageRoutes(FALLBACK_PAGE_DECLARATIONS)` 动态机制取代，`/emulators` 不在 FALLBACK 列表中，见"未完成"§3 |
| `frontend/src/types/script.ts` | 合成：`ScriptType = string`（插件开放集合），新增 `BuiltinScriptType` 字面量类型保留穷举能力；`Script` 接口取并集（dev_v2 的 config 联合类型 + release 的 schema/editorKind/available 等字段） |
| `frontend/src/components/AppLayout.vue` | 取 release（声明式菜单 + HMR 遮罩 + 背景层）。⚠️ dev_v2 的 `/update-download-dev` 开发菜单项丢失，见"未完成"§4 |
| `frontend/src/views/WSdev.vue` | 取 release（后端路由前缀已改为 `/api/ws`） |
| `frontend/src/views/Home.vue`、`UpdateDownloadModal.vue`、MAA 系列编辑页、`MaaEndScriptEdit.vue`、`GeneralScriptEdit/UserEdit` | 取 dev_v2（release 侧无实质变更或为旧版） |
| `frontend/package.json` | 版本保留 `v5.4.0-beta.1` |

### 2. uv 包管理切换（已验证）

- uv 0.11.26 已安装（`C:\Users\10163\.local\bin\uv.exe`）
- `pyproject.toml` 的 workspace members 原声明 20 个插件目录，但仓库只有 `plugins/auto_mas_core` → 已运行 `python scripts/sync_plugin_workspace.py --write` 同步为实际目录（此为 627d6888 中 pyproject.toml 删 57 行的原因）
- `uv lock` 成功（261 包）；`uv sync --group dev` 成功；uv 环境下全量导入链验证通过
- 运行时 uv 查找顺序：`environment/python/Scripts/uv.exe` → PATH → `AUTO_MAS_UV_EXE` 环境变量（`app/plugins/uv_backend.py`）
- ⚠️ pyproject 锁 `maafw==5.8.1`，requirements.txt 是 `maafw==5.10.2`，见"未完成"§6

### 3. 合并后修复（含 627d6888）

- `app/task/general/tools/notify.py`：加 `from __future__ import annotations`——release 把 `GeneralUserConfig` 导入移到 `TYPE_CHECKING` 块但签名用了运行时求值的注解，导入即 NameError（uv 环境验证时发现）
- `tests/plugins/test_event_bus.py`：`EventDispatchError` 改从 `app.plugins.event_bus` 导入（release 版 `__init__.py` 不再导出它）

### 4. 已通过的验证

- 后端全量 AST 解析 0 错误
- `uv run python -m unittest discover tests`：28/28 通过
- script_type_registry bootstrap：8 种类型全部注册，modes/editor_kind 正确
- `apply_script_type_registry_to_global_config` + `validate_script_type_registry`：missing=[]，sub_config_type 含全部 9 类（8 内建 + PluginScriptConfig）
- 无冲突标记残留；version.json/package.json JSON 有效

## 二、未完成 / 待办（按优先级）

### 1. 前端 typecheck 未收敛【进行中被中断】
最后一次 `vue-tsc` 后台任务只输出了 `4 src/views/Plugin.vue`（管道被截断，结果不完整）。
**怎么做**：`cd frontend && npx vue-tsc --noEmit -p tsconfig.app.json`，将结果与 dev 基线的 15 个预存错误对比（基线清单见第一阶段文档 §3.4），只修合并新引入的。`src/views/Plugin.vue` 的 4 个错误是 release 新文件，需要看具体报错。

### 2. 新建脚本弹窗 / 复制脚本功能丢失【功能回归，最重要】
Scripts.vue/ScriptTable.vue 取了 release 侧，第一阶段合入的 `ScriptCreateDialog`（views/scripts/components/，文件仍在但无人引用）和"复制脚本"（`handleCopyScript`/`copyingScriptId`，后端 `add_script(script, script_id)` 复制路径仍在）被丢弃，release 用回旧的 typeSelect 弹窗。
**怎么做**：把 `ScriptCreateDialog` 重新接入 release 版 Scripts.vue——数据源从 `scriptCreateFlow.ts` 的静态 `SCRIPT_TYPE_OPTIONS` 改为 `availableScriptTypes`（descriptor 列表），提交走现有 `handleAddScript` 的 registry 流程；"更多→复制脚本"下拉参照第一阶段 ScriptTable 实现（git show `e1889bc6:frontend/src/components/ScriptTable.vue`）。

### 3. `/emulators` 与 `/plans` 路由确认【疑似断链】
release 的页面路由由 `FALLBACK_PAGE_DECLARATIONS`（frontend/src/router/pageDeclarations.ts）+ 后端 `BUILTIN_PAGES`（app/core/page_registry.py）动态生成，两处都无 `/emulators`；模拟器页面预期由 emulator 插件声明，但该插件源码不在仓库。Home.vue（dev_v2 版）仍有跳转 `/emulators` 的入口。
**怎么做**：短期把 emulators 加进 `FALLBACK_PAGE_DECLARATIONS` 和 `BUILTIN_PAGES`（组件 `Emulator`，路径 `/emulators`）；或确认插件缺失时的降级策略。`/plans` 已在两个列表中，无需处理。

### 4. AppLayout 丢失的开发菜单项
dev_v2 的 `/update-download-dev`（更新下载测试页，视图文件 `UpdateDownloadDev.vue` 仍在）未进 release 的声明式菜单。
**怎么做**：在 `FALLBACK_PAGE_DECLARATIONS` 与 `BUILTIN_PAGES` 的 dev 段加一条（dev_only: true），或在 AppLayout 的 `onMenuClick` 恢复动态 addRoute 逻辑（git show dev_v2 历史版本）。

### 5. WebSocketService 生成代码未再生
后端 ws 路由前缀已从 `/api/ws_debug` 改为 `/api/ws`，但 `frontend/src/api/services/WebSocketService.ts`（openapi 生成）里 url 仍是 `/api/ws_debug/*`——WSdev 页面调试功能会 404。
**怎么做**：启动后端后重新生成 openapi 客户端（项目常规流程，`frontend/src/api` 目录头部注释标注了生成器 openapi-typescript-codegen），或手改 url。

### 6. maafw 版本不一致
`pyproject.toml`: maafw==5.8.1（release 侧，配套 `6a467c75` "降级 maafw 版本至 5.8.1"）；`requirements.txt`: maafw==5.10.2（dev_v2 侧 MaaEnd 适配）。uv 环境装的是 5.8.1。
**怎么做**：跑一次 MaaEnd/MaaFW 实际任务确认 5.8.1 是否够用；统一两处版本（requirements.txt 长期应废弃，以 pyproject 为准）。

### 7. 端到端启动验证未做
仅验证了导入与单测，未实际 `uv run python main.py` 起后端 + `yarn dev` 起前端跑通：插件系统启动（auto_mas_core 路由挂载、system 插件 bootstrap 会尝试 uv 安装 emulator 插件——该插件源码不在仓库，需观察降级行为）、8 种脚本类型的 CRUD、MAA 配置流程。
**怎么做**：`uv run python main.py` 看 lifespan 日志（重点：`ensure_uv`、`PluginManager` 启动、`validate_script_type_registry` 警告）；前端 `yarn dev:fullstack`；逐类型建脚本 + 添加用户 + 进编辑页。

### 8. 事务性收尾
- stash 里有一条 `gitignore-before-release-merge`（.gitignore 的 `.ace-tool/` 行），本次合并的 .gitignore 已含该内容语义，确认后 `git stash drop`
- 未跟踪文件：`.ace-tool/`、`docs/superpowers/`、`frontend-code-review.md`（均为本地工作文件，不入库）
- dev_v2 未推送（本地领先 origin/dev_v2：合并提交 + f24e7773 + 627d6888 + 本文档）

## 三、验证命令速查

```bash
# 后端
uv lock && uv sync --group dev
uv run python -m unittest discover tests          # 期望 28 OK
uv run python -c "from app.core.script_types import script_type_registry; script_type_registry.bootstrap(); print([p.type_key for p in script_type_registry.list()])"
# 期望: MAA SRC MaaEnd M9A MaaFW Okww HSR General

# 前端
cd frontend && yarn install
npx vue-tsc --noEmit -p tsconfig.app.json
# 插件 workspace 变更后
python scripts/sync_plugin_workspace.py --check
```
