# E2E 测试指南

本仓库的 E2E 测试覆盖用户从配置、调度到结果查看与恢复的完整链路，分为两类：

- **浏览器隔离 E2E**：运行与 Electron 共用的 Vue 页面和真实 MAS 后端，验证渲染层交互与 HTTP/WebSocket 契约。
- **作者本机真实流程（`@real`）**：使用开发者本机已安装的脚本、真实账号与可选模拟器，通过 MAS 公开调度契约执行真机验收。仓库不附带任何游戏资源、脚本安装包或测试账号。

## 环境准备

首次运行前，在仓库根目录安装 Python 开发依赖，再安装前端依赖与 Playwright Chromium：

```powershell
uv sync --group dev
Set-Location frontend
yarn install --immutable
yarn playwright install chromium
```

后续所有 E2E 命令均在 `frontend/` 下执行。除 MuMu 明确报 `WinError 740` 需要管理员 PowerShell 外，其余场景无需提权。

## 隔离机制与启动入口

`frontend/e2e/run.mjs` 是唯一启动入口，不要直接绕过它调用 `playwright test`。

- **默认隔离**：自动创建一次性运行根目录（重定向 `TEMP/TMP`、后端数据根与本轮日志），启动后端与前端服务，测试结束后自动清理，不污染当前检出。
- **默认种子**：普通隔离模式在后端启动前通过 `HistoryStore` 写入 3 条已知历史记录（账号 A 今天成功/昨天失败、账号 B 八天前成功），无预置托管或账号，且固定关闭明日方舟 PC 工具。真实模式与 `--in-place` 不写入种子。

如需覆盖默认隔离行为，可使用以下参数或环境变量：

| 变量 / 参数 | 作用 |
| --- | --- |
| `AUTO_MAS_E2E_KEEP_ROOT=1` | 运行结束后保留临时目录并打印路径，便于排查写入结果 |
| `--in-place` 或 `AUTO_MAS_E2E_IN_PLACE=1` | 直接使用当前检出作为数据根（会写入 `config/`、`data/`、`history/`、`debug/` 且不清理，运行前需先关闭其他实例） |
| `AUTO_MAS_E2E_DATA_ROOT=<目录>` | 配合就地模式指向其他数据根（如 worktree 复用主检出配置） |
| `AUTO_MAS_E2E_TEMPLATE_ROOT=<目录>` | 真实模式的配置种子源，默认当前检出 |

## 常用命令

```powershell
# 基础设施自检（数据根隔离、种子白名单、真实运行锁、E2E 类型检查）
yarn e2e:check

# 按功能标签运行浏览器隔离用例
yarn e2e:init
yarn e2e:smoke
yarn e2e:queue
yarn e2e:scheduler
yarn e2e:settings
yarn e2e:history
yarn e2e:recovery
yarn e2e --grep '@queue|@scheduler'

# 运行作者本机真实流程
yarn e2e:real
yarn e2e:real --grep complete
yarn e2e:real --grep stop-restart
yarn e2e:real:all

# 可视化调试与查看报告
yarn e2e:ui
yarn e2e:report
yarn playwright show-report playwright-report/real
```

> `--grep` 接收正则表达式：`@queue|@scheduler` 为 OR；`(?=.*@real)(?=.*@my-feature)` 为 AND。默认配置会排除所有 `@real` 用例。

产物与报告路径：

| 模式 | 测试产物 | HTML 报告 |
| --- | --- | --- |
| 浏览器隔离 | `frontend/test-results/browser/` | `frontend/playwright-report/browser/` |
| 本机真实流程 | `frontend/test-results/real/` | `frontend/playwright-report/real/` |

## 合并门槛与提测范围

| 层级 | 内容 | 执行方 | 是否阻断合并 |
| --- | --- | --- | --- |
| CI 阻断 | Windows / Ubuntu 全量 pytest、格式与类型检查、changelog 碎片、`uv.lock`、打包检查、`yarn e2e:check` | CI | 是 |
| CI 提示 | revert 检查（标注近期删改的他人代码） | CI | 否 |
| 浏览器 E2E | `@smoke` 等隔离用例（纯前端交互 / UI 改动建议附截图） | 贡献者本机 | 否 |
| 真实流程 | `@real`（改动 `app/task/**`、专项适配、调度、模拟器时必须附 `real-e2e-summary.json` 关键字段与精选截图） | 作者本机 | 否 |

## 现有测试标签速查

所有渲染层用例均启用页面异常守卫，任何未捕获异常或 Vue 全局错误都会直接判失败。

- `@smoke`：经侧栏依次进入计划、队列、调度、历史、设置并返回首页，校验路由、菜单状态与页面内容。
- `@queue`（含 `@scheduler`）：队列增删改、添加脚本项并拖动排序、刷新回读与调度台联动。
- `@scheduler`：无任务禁止启动、添加及批量关闭空闲调度台。
- `@settings`：明暗主题切换与回读；历史保留天数保存失败回滚与恢复重试。
- `@i18n`：中英日切换与刷新回读；首次加载与切换遇到 HTTP 失败或批次版本不一致时的错误提示与回退。
- `@notify @webhook`：Webhook 增删改启停与本地接收端实收验证（仅隔离模式运行）。
- `@history`：按快捷时间、日历与账号筛选 3 条种子记录并核对详情日志（仅隔离模式运行）。
- `@recovery`：断线重连后提交隔离任务验证链路恢复；刷新期间健康接口异常与恢复。
- `@init`：后端冷启动，确认健康就绪且未初始化明日方舟 PC 工具。
- `@real @game-schedule @account`：
  - `complete`：通过 UI 启动单账号任务，运行中主动断线重连，核对公开终态并在历史页打开新增记录。
  - `stop-restart`：运行中点击停止，确认取消与运行时空闲后，再次启动新任务并停止收尾。

> 浏览器模式替代了 Electron 桥接，因此原生 IPC、托盘、系统通知与真实游戏结果需由各自集成测试或 `@real` 流程提供证据；页面刷新回读也不等同于后端重启持久化。

## 作者本机真实流程

`yarn e2e:real` 通过 [`run-real.ps1`](../../frontend/e2e/run-real.ps1) 设置 `AUTO_MAS_E2E_REAL=1` 并委托 `run.mjs` 启动。

### 目标选择

默认读取种子源下的 `config/scripts.yaml`，自动选中第一个包含已启用账号的托管及该账号并在日志中列出候选。如需指定目标，可按需设置环境变量（目标不存在时会直接报错，不会静默替换）：

| 环境变量 | 含义 |
| --- | --- |
| `AUTO_MAS_E2E_SCRIPT_ID` | 托管 UUID |
| `AUTO_MAS_E2E_USER_ID` | 账号 UUID |
| `AUTO_MAS_E2E_ACCOUNT_NAME` | 账号名称（须与配置一致） |
| `AUTO_MAS_E2E_EMULATOR_ID` / `AUTO_MAS_E2E_EMULATOR_INDEX` | 可选，覆盖托管绑定的模拟器实例 |

### 隔离与锁保护

- **配置裁剪**：只从种子源复制本次选中目标所需的托管、账号、计划与脚本资产，并剥离通知字段（不会触发真实推送）。原生配置留在安装目录的专项仍直接指向本机已有安装。
- **原子锁**：在机器级临时目录（Windows 为 `%SystemRoot%\Temp\AUTO-MAS`）建立排他锁，同一台电脑同时只允许跑一个真实 E2E。若进程被强杀残留锁文件，确认无运行测试后手动删除。
- **安全清理**：收尾时先停止任务并确认运行时空闲，再只关闭本次由测试启动的模拟器（原本在线的实例保持不动）。

### 批量跑全部专项

```powershell
Set-Location frontend
yarn e2e:real:all --list                      # 仅列出本机所有已启用账号目标
yarn e2e:real:all                             # 串行运行全部目标（每个目标独立隔离根）
yarn e2e:real:all --only MaaConfig,SrcConfig  # 仅运行指定专项
```

批量结果按目标存放在 `frontend/test-results/real-batch/<序号-专项-账号>/`，单个目标失败不中断后续目标，全部结束后汇总退出码。

## 新增用例与调试

### 添加流程

- 在 `frontend/e2e/<场景>.pw.ts` 中从 `./fixtures` 导入 `test` 与 `expect`，通过 `app.goto()`、`app.evidence()` 按真实用户路径操作，避免直接篡改内部状态。
- 用 `test.describe('@标签', ...)` 命名；有真实游戏副作用的必须带 `@real`。
- **用例准入原则（改坏必须变红）**：新增或修改用例后，先临时把被测行为改坏、确认用例会失败，再还原代码确认通过。永远不红的用例不应保留。
- 一次性浏览器探针跑完取证后在合并前删除；稳定、可复用的用户路径转为长期用例。

最小示例：

```ts
import { expect, test } from './fixtures'

test.describe('@my-feature', () => {
  test('用户可以进入目标页面', async ({ app, page }) => {
    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()
    await app.evidence('my-feature-scheduler')
  })
})
```

### 调试配置项

1. **找键名**：用 `--in-place` 跑一条只点界面的临时用例后 `git diff config/`，或对照组件与 `app/models/schema.py` / `app/core/config/manager.py`。
2. **造数据**：优先在用例内通过 UI 或 API 构造；其次在启动后端前写入配置文件或提供最小 profile。
3. **核对落盘**：用 `AUTO_MAS_E2E_KEEP_ROOT=1` 运行一遍，对照运行根里的实际配置和 `debug/app.log`。

### 等待与脱敏约定

- 用可见状态、API 响应、公开任务终态或带超时轮询等待，不用固定长 `sleep`。
- 绑定模拟器时，`POST /api/emulator/operate` 返回 200 只表示已排队，须等待 `EmulatorManager:emulator.operation.finished` 再确认设备状态。
- 调度初始状态读 `GET /api/dispatch/runtime-snapshot`，增量走 WebSocket，终态查 `GET /api/dispatch/task/{task_id}`。
- 严禁将密码、Cookie、Token 或未检查的完整 `real/` 报告直接贴入 PR；真实模式只分享经过人工检查的精选截图与 `real-e2e-summary.json` 关键字段。

### PR 验证记录模板

```text
- E2E 场景：<验证的用户功能与路径>
- 命令：`<实际执行的命令>`
- Commit：`<完整 SHA>`；工作区：<clean / dirty（说明差异）>
- 结果：<通过/失败/未运行及实际观察>
- 证据：<截图和/或 real-e2e-summary.json 路径>
- 限制：<未覆盖场景、环境前置条件或无>
```

## 常见失败排查

排查顺序建议：**环境 → 上游脚本 → MAS 自身 → 测试代码**。

1. **环境因素（真实模式）**：检查模拟器 ADB 端口占用、管理员权限、账号密码/客户端版本、网络代理与磁盘空间。优先看 `real-e2e-summary.json` 的 `stage` 字段与 `<运行根>/debug/app.log`。
2. **上游脚本因素（真实模式）**：若 `completion.accepted === false`，检查 `completion.outcome`、`scriptStatus` 与 `userStatus`，确认是否为上游识别或脚本异常。
3. **MAS 自身问题**：检查 Playwright trace、截图、HTML 报告及 WebSocket 消息流。
4. **测试代码问题**：用 `yarn e2e --grep "测试名称"` 单独复现，检查选择器变更、过严断言或前序状态残留。

典型超时参考（超时前已报错时先排环境，不要盲目拉长超时）：

- 页面交互：5–10 秒
- API 请求：10–30 秒
- 模拟器启停与 ADB 就绪：90 秒
- 短任务脚本（签到等）：5–10 分钟
- 长任务脚本（刷本/推图）：30–60 分钟

## 核心源码入口

- 页面与路由：[`frontend/src/router/index.ts`](../../frontend/src/router/index.ts)、[`useHomeQuickStart.ts`](../../frontend/src/views/home/useHomeQuickStart.ts)
- 队列配置：[`queue/index.vue`](../../frontend/src/views/queue/index.vue)、[`app/api/queue.py`](../../app/api/queue.py)
- 调度与运行态：[`useSchedulerLogic.ts`](../../frontend/src/views/scheduler/useSchedulerLogic.ts)、[`useTaskRuntimeState.ts`](../../frontend/src/composables/useTaskRuntimeState.ts)、[`app/api/dispatch.py`](../../app/api/dispatch.py)、[`app/core/task_manager.py`](../../app/core/task_manager.py)
- 模拟器与账号：[`app/api/games.py`](../../app/api/games.py)、[`app/api/scripts/`](../../app/api/scripts/)、[`index.vue`](../../frontend/src/views/gamesign/index.vue)
- 历史与设置：[`useHistoryLogic.ts`](../../frontend/src/views/history/useHistoryLogic.ts)、[`app/api/history.py`](../../app/api/history.py)、[`setting/index.vue`](../../frontend/src/views/setting/index.vue)、[`app/api/setting.py`](../../app/api/setting.py)
