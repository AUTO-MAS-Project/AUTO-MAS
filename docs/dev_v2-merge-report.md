# dev_v2 分支合并与修改记录

> 日期：2026-07-03
> 基线：`origin/dev` @ `a3c08b3f`（Revert "Merge pull request #266..."）
> 结果分支：`dev_v2`，共 6 个提交（5 个合并提交 + 1 个审查修复提交 `a6d94b3d`）

## 一、合并概览

按"插件核心优先、冲突面从小到大"的顺序合入 5 个分支：

| 顺序 | 分支 | 合并提交 | 内容 | 冲突文件数 |
|---|---|---|---|---|
| 1 | `feat/plugin-eventbus` | `1f85e5c5` | 插件事件总线（app/plugins/，442 行纯新增） | 0 |
| 2 | `origin/feat/mfw` | `12740946` | MaaFW 整合（新脚本类型，115 文件 +15506） | 1 |
| 3 | `origin/feat/gamesign` | `3d6d604f` | 游戏签到 + HSR 类型（115 文件 +10184） | 7 |
| 4 | `feat/script-create-dialog-redesign` | `e1889bc6` | 新建脚本弹窗重构 | 2 |
| 5 | `feat/refeactor_home` | `43b5a259` | 首页重构（three.js 卫星动画） | 1 |

合计相对 origin/dev：212 文件，+28801 / -3494。

## 二、冲突解决明细

### 1. feat/mfw：`frontend/eslint.config.mjs`
两侧在同一规则块附近各自加了配置。**取并集**：保留 mfw 侧新增的 `'no-unused-vars': 'off'`（TS 文件规则块），与 HEAD 结构合并。

### 2. feat/gamesign（7 个文件）

| 文件 | 决策 | 理由 |
|---|---|---|
| `res/version.json` | 取并集 | 发布说明，双方条目全保留（MaaFW 条目 + 游戏签到条目） |
| `frontend/src/views/setting/TabOthers.vue` | 取 HEAD（mfw 侧） | HEAD 多出的 GitHub token 输入框是 mfw 新增功能，gamesign 基于旧代码没有它 |
| `frontend/src/views/Scripts.vue`（2 处） | 取 HEAD | HEAD 是 mfw 引入的映射表方案（`SCRIPT_ROUTE_SEGMENTS`/`SCRIPT_DISPLAY_LABELS`，已含 8 种类型），gamesign 侧是三元链且缺 MaaFW；映射表覆盖 HSR，无信息丢失 |
| `frontend/src/components/UpdateModal.vue` | 取 HEAD | HEAD 是 dev 上更新的下载流程（`useUpdateDownload` composable）；gamesign 侧为旧 props 传递方案 + 调试日志 |
| `frontend/src/components/UpdateDownloadModal.vue` | `checkout --ours` | 同上，HEAD 含 dev 后续两个功能提交（后台下载、CNB 源切换、指定版本下载），gamesign 侧只是旧版本的格式化 |
| `frontend/src/views/EditView/Script/OkwwScriptEdit.vue` | `checkout --ours` | 逐词 diff 验证 gamesign 侧仅为 Prettier 格式化（属性换行），无实质修改；HEAD 含 okww 配置重构 |
| `frontend/src/components/ScriptTable.vue` | `checkout --ours` | 词级 diff 验证 gamesign 侧同为格式化差异；HEAD 含 mfw 的 MaaFW 分支渲染 |

### 3. feat/script-create-dialog-redesign（2 个文件）

| 文件 | 决策 |
|---|---|
| `frontend/src/components/ScriptTable.vue` | 取 redesign 侧："删除脚本"独立按钮 → "更多"下拉（复制/删除）+ 折叠用户按钮；验证 `handleCopy`/`handleDeleteConfirm`/`collapsedScriptIds` 等符号在 script 部分均存在 |
| `frontend/src/views/Scripts.vue` | 冲突两处均取 HEAD 的映射表方案（redesign 侧为过时的三元链，不含 MaaFW/HSR） |

### 4. feat/refeactor_home：`frontend/yarn.lock`
两侧各新增一个包（HEAD：`@tybys/wasm-util`；home：`@tweenjs/tween.js`），**取并集**。合并后 `yarn install --immutable` 校验通过。

## 三、代码审查结论与修复（提交 `a6d94b3d`）

合并完成后运行了三路并行审查（插件系统完整性 / 后端 mfw×gamesign 语义冲突 / 前端四分支交叉），外加 vue-tsc、eslint、Python AST 全量解析、后端单测。

### 3.1 高严重度（已修复）

#### ① 插件事件总线是"孤岛代码"——已合入但完全未接入
- **发现**：全仓库无任何 `EventBus` 实例化、无 `emit` 调用、无订阅者。事件契约（`task.start`/`script.exit` 等标准事件）无人发布。而本版本主打插件功能。
- **修复**：
  - `app/plugins/__init__.py` 新增全局单例 `event_bus = EventBus()` 并导出；
  - `app/core/task_manager.py` 在任务生命周期接入：`main_task` 开始发布 `task.start`，每个脚本执行前后发布 `script.start`/`script.exit`，`final_task` 发布 `task.exit`，载荷含 task_id/script_id/status 等；
  - 默认 `error_policy="continue"`，插件回调异常不影响主流程。

#### ② MaaFW 脚本类型在 UI 上完全无法创建（合并交叉断裂）
- **发现**：redesign 分支的 `scriptCreateFlow.ts` 早于 mfw 分支，`SCRIPT_TYPE_OPTIONS` 缺 MaaFW 选项；且 `EDIT_SEGMENT_BY_TYPE: Record<ScriptType, string>` 缺 `MaaFW` 键导致 **typecheck 编译错误**。新弹窗成为唯一创建入口后，MaaFW 无法创建。
- **修复**：`scriptCreateFlow.ts` 补 `MaaFW` 类型选项（文案对齐 Scripts.vue 的 "MaaFramework 项目"）与 `MaaFW: 'maafw'` 路由段。

#### ③ `tests/tools/test_contracts.py` 域名断言与实现不符（gamesign 分支内部自坏）
- **发现**：gamesign 后期提交 `e0911845` 把 stoken 兑换 URL 从 `passport-api.mihoyo.com` 改为 `api-takumi.mihoyo.com`（对齐 MihoyoBBSTools），但没同步更新自己分支早前写的测试断言，合并前该分支测试就是挂的。
- **修复**：更新断言为实际域名，测试更名 `test_stoken_exchange_uses_takumi_api_domain` 并注释来龙去脉。

#### ④ `Initialization/components/index.ts` 导出不存在的文件
- **发现**：`export { default as InitializationMain } from './InitializationMain.vue'`，该文件在所有分支上都不存在（dev 基线自带的坏导出），typecheck 报 TS2307，且无任何消费方。
- **修复**：删除该行导出。

### 3.2 中严重度（已修复）

| 问题 | 修复 |
|---|---|
| `MaaFWUserEdit.vue` 预设过滤引用 `MaaFWPresetInfo` 上不存在的 `controller`/`resource` 字段（后端 schema 确认无此字段，mfw 分支自身遗留） | 移除无效过滤，直接展示全部预设，注释说明 schema 依据 |
| `MaaFWUserEdit.vue:1318` 以 1 参调用 0 参的 `syncControllerResourceSelection` | 去掉多余实参 |
| `MaaFWUserEdit.vue` `orderedTasks` 类型收窄谓词不成立（`Boolean(task)` 不被 TS 认可） | 改为 `task !== undefined` 显式收窄 |
| `useGameSignAccountApi.ts` 未处理 `accountId`/`data` 可选性（OpenAPI 生成类型为可选） | `code !== 200 \|\| !accountId \|\| !data` 统一走异常分支 |
| `useSchedulerLogic.ts` 定时器类型 `ReturnType<typeof window.setTimeout>` 在 @types/node 环境下解析成 `NodeJS.Timeout`，与 `window.setTimeout` 实际返回的 `number` 冲突 | 显式声明为 `number` |
| `Scripts.vue` `router.push` 的 `state.scriptData` 不满足 `HistoryState` 索引签名 | 断言为 `HistoryState[string]`（运行时消费方 `history.state as any` 不受影响） |
| `ScriptTable.vue` 服务器标签注释写 "MAA、SRC、MaaEnd 和 HSR" 但条件不含 HSR（与 gamesign 原始代码核对：原始代码同样不含 HSR，是注释错误而非分支丢失） | 修正注释为 "MAA、SRC 和 MaaEnd" |
| 事件总线零测试覆盖 | 新增 `tests/plugins/test_event_bus.py`，11 个用例：优先级顺序、once 自动解绑、instance/global 作用域隔离路由、continue/raise 错误策略、按 listener_id/instance 解绑、重复注册、异步 handler、instance emit 缺 source_id 报错 |
| `event_bus.py` 重复注册同一 handler 时静默忽略新参数 | 补 warning 日志 |
| `event_bus.py` 锁语义与作用域隔离行为无文档（on/off 不加锁、global 与 instance 互不可见均为设计决策） | 在类 docstring 中明确线程模型与作用域语义 |

### 3.3 低严重度（已修复）

- `event_bus.py` 未使用的 `field` 导入 → 删除。
- `app/plugins/__init__.py` docstring 引用不存在的 `pyproject.toml` → 改写，并注明核心事件接入点位置。

### 3.4 记录在案、未修改（非本次合并引入 / 属产品决策）

| 事项 | 说明 |
|---|---|
| dev 基线预存的 15 个 typecheck 错误 | `VirtualLogViewer.vue`(6)、`StageConfigSection.vue`(4)、`scheduler-debug.ts`(2)、`EnvironmentPage.vue`、`maaEndProtocolSpace.ts`、`HSRScriptEdit.vue`、`HSRUserEdit.vue`、`AbyssConfigSection.vue`、`Logs.vue`、`history/index.vue` 各 1 —— 用 origin/dev 干净 worktree 复测确认全部预存，与合并无关，未动（避免污染合并审查范围）。修复后 dev_v2 错误数 19，其中新增的 0 个 |
| Scripts.vue 旧五弹窗死代码（约 700 行） | redesign 后 `typeSelectVisible` 等再无入口。与 redesign 分支原样一致（该分支自己也没删）。属功能重构收尾，建议后续单独 PR 清理，本次不动以降低合并风险 |
| ScriptTable `scriptsReordered` 事件无人监听、3 个 save-config handler 死代码 | 功能无影响，随死代码清理一并处理 |
| ScriptCreateDialog "confirm" 步骤分支不可达 | redesign 迭代残留，无功能影响 |
| 首页卫星动画不含 MaaFW/HSR/General 图标 | `satellite-icons/` 无对应素材，属功能覆盖缺口非错误，需设计资源 |
| `TYPE_BOOK`（`app/utils/constants.py`）键集不对称 | 现有查询路径不会触发 KeyError，保持原样 |
| `qr_login.py` 直接读写 `_game_sign_result_data` 私有属性 | gamesign 自身设计模式（tools.py 同款），非合并问题 |
| event_bus `on`/`off` 与 `emit` 锁不一致 | 已用文档声明"注册/注销须在事件循环线程调用"，未改实现（当前单事件循环场景安全，改 async 接口影响面大） |

## 四、验证结果

| 检查 | 结果 |
|---|---|
| 后端全量 AST 语法解析（app/ + main.py） | ✅ 0 错误 |
| 后端 import 链解析（含 MaaFW/gamesign 全模块） | ✅ 全部可解析 |
| 后端单测 `unittest discover tests`（.venv, Python 3.12） | ✅ 28/28 通过（含新增 11 个事件总线用例） |
| `app.core.task_manager` + `app.plugins` 实际导入 | ✅ 正常 |
| 路由重复检测（全 app/api/*.py method+path 扫描） | ✅ 无重复，mfw 与 gamesign 路由并存 |
| 合并残留标记（<<<<<<<）全仓扫描 | ✅ 零匹配 |
| `yarn install --immutable`（yarn.lock 并集校验） | ✅ 通过 |
| vue-tsc typecheck | 19 错误，全部为 dev 基线预存（基线 worktree 对照复测确认）；合并/修复引入 0 个 |
| eslint（本次改动文件） | ✅ 0 error（余留 warning 为项目既有风格） |

## 五、后续建议（未在本次执行）

1. **清理 Scripts.vue 旧创建流程死代码**（~700 行）——单独 PR，回归点：8 种类型创建、模板导入、复制脚本。
2. **补充卫星动画新类型图标**（MaaFW/HSR/General）。
3. **插件事件总线扩展接入**：目前只接了 task/script 生命周期骨架事件；`TASK_PROGRESS`/`TASK_LOG` 与各 Manager 内部粒度事件待插件框架后续模块（加载器、沙箱）落地时一并设计。
4. **修复 dev 基线预存的 15 个 typecheck 错误**——与本合并无关，建议独立小 PR。
