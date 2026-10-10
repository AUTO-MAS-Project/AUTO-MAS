# E2E 测试流程清单

目标是验证用户从配置、调度到结果查看与恢复的完整链路，并让每个 PR 只运行相关流程。当前已有普通浏览器用例、冷启动用例和作者本机真实调度用例；下表是覆盖目标，尚未实现的流程需在对应 PR 中补充。

真实流程使用 PR 作者本机已有的脚本安装、用户配置及可选模拟器，不依赖 MAS 提供游戏资源或专用账号。入口按 MAS 的公开配置和调度契约工作，支持 BetterGI 等专项；需要模拟器的专项按配置执行模拟器步骤，不接入 USB、手机、实体设备或硬件校准链路。

## 按 PR 选择

`frontend/e2e/run.mjs` 是唯一启动入口：它创建临时工作目录、启动 Playwright 和两个开发服务，并在服务退出后删除临时目录。若系统 `TEMP/TMP` 被配置到 `frontend` 内，入口会改用 `frontend` 外的专用临时目录，避免 Vite 监听运行数据。不要绕过它直接运行 `playwright test`。

首次准备本机环境时，在仓库根目录安装 Python 开发依赖，再安装前端依赖和 Playwright Chromium：

```powershell
uv sync --group dev
Set-Location frontend
yarn install --immutable
yarn playwright install chromium
```

之后的 E2E 命令都从 `frontend/` 执行。MuMu 只有在启动时明确报 `WinError 740`（需要提升权限）才需要改用管理员 PowerShell 重跑；其他模拟器默认不要求管理员权限。

从 `frontend/` 运行：

```powershell
yarn e2e:check
yarn e2e:init
yarn e2e:smoke
yarn e2e:queue
yarn e2e:scheduler
yarn e2e --grep '@queue|@scheduler'
yarn e2e:real
yarn e2e:report
yarn playwright show-report playwright-report/real
```

`e2e:check` 运行 harness 自检和 E2E TypeScript 检查；`e2e:init` 运行隔离后端冷启动流程。`e2e:report` 打开浏览器 HTML 报告；真实流程使用 `playwright show-report playwright-report/real`。`--grep` 是正则表达式，空值默认运行 Playwright 配置中的默认集合。默认配置排除所有 `@real` 用例；真实流程由作者本机运行，不访问共享 CI 账号、模拟器或游戏资源。真实命令从当前检出的分支启动，`dev` 与 `release/*` 均可验证各自代码。E2E 不阻断合并，PR 作者按改动选择需要的流程，并手动附上经过检查的截图或摘要。

结果按模式隔离：

| 模式 | 测试产物 | HTML 报告 |
| --- | --- | --- |
| 普通浏览器 | `frontend/test-results/browser/` | `frontend/playwright-report/browser/` |
| 作者本机真实流程 | `frontend/test-results/real/` | `frontend/playwright-report/real/` |

当前实现的范围：

- `@smoke`：首页、计划、队列、调度、历史、设置页面导航。
- `@queue`：新建队列、改名、修改启动设置、离开再返回检查持久化。
- `@scheduler`：无任务时禁止启动，添加和批量关闭空闲调度台。
- `@init`：隔离后端冷启动，等待健康与后台初始化就绪，并确认明日方舟 PC 工具关闭时不阻塞启动。
- `@real @game-schedule @account`（另带 `@emulator` 或 `@script-install`）：同一条通用真实调度流程按所选脚本是否绑定模拟器执行前置检查，再验证唯一用户选择、真实调度、任务终态和公开完成事件中的用户结果。BetterGI 可复用入口；运行前需有对应本机安装与有效配置。

## 为单个 PR 添加流程

- 文件使用 `frontend/e2e/<场景>.pw.ts`，从 `./fixtures` 导入 `test`、`expect`，按用户路径操作 UI。复用 `app.goto()` 和 `app.evidence()`，不要直接改页面内部状态。
- 用 `test.describe('@标签', ...)` 命名流程；有真实游戏副作用的用例必须带 `@real`。`--grep` 接收正则：`@queue|@scheduler` 是 OR；`(?=.*@real)(?=.*@my-feature)` 是 AND。`'@real @my-feature'` 只匹配标题中相邻且顺序一致的文本，不是通用 AND 选择器。
- 普通一次性流程用 `yarn e2e --grep '@my-feature'` 运行。新增长期标签只需要在对应 spec 和本文档中说明用途，不需要维护 CI 标签映射。
- 真实一次性流程用 `pwsh -NoProfile -File ./e2e/run-real.ps1 -Grep '(?=.*@real)(?=.*@my-feature)'` 运行；它复用已选脚本和用户的 MAS 配置，并将所需数据复制到临时目录。入口按脚本是否绑定模拟器决定是否执行模拟器步骤。新专项若有不同于标准 MAS 用户配置目录的前置数据，作者需扩展 seed 契约并补自检。
- 功能或 bugfix 的一次性流程属于 PR 验证产物；跑完并检查证据后，按仓库规则在合并前删除。跨功能且长期稳定的公共流程才保留。
- 凭据从本机已有配置读取，不写进 spec、仓库、PR 输入或证据。真实流程只分享精选截图和摘要，完整报告不能视为已脱敏。

一次性真实流程的最小结构：

```ts
import { expect, test } from './fixtures'

test.describe('@my-feature', () => {
  test('用户可以进入本 PR 修改的页面', async ({ app, page }) => {
    await app.goto('/scheduler')
    await expect(page.getByText('Scheduler', { exact: true }).first()).toBeVisible()
    await app.evidence('my-feature-scheduler')
  })
})
```

这是可运行的浏览器流程示例，不代表新功能已经验证。真实模拟器、游戏调度或账号相关改动，应在 `real-integration.pw.ts` 的用户路径上增加与改动对应的断言、超时等待、失败清理和证据；不要复制空测试体作为验证。真实用例必须带 `@real`，并通过本机真实入口运行。专项作者需声明真实运行所需安装、配置与可选模拟器条件；PR 证据只能说明被测 commit、环境和断言的结果。

## 必要流程清单

| 优先级 / 范围 | 用户实际操作与验收 | 所需环境 |
| --- | --- | --- |
| P0 `@smoke` | 启动、初始化、首页入口、核心页面导航；空态、加载态和返回正常。 | 干净临时配置 |
| P0 `@queue` | 队列和队列项的新增、编辑、重排、删除；定时项启停和持久化；刷新后顺序一致。 | 隔离后端；部分场景需脚本配置 |
| P0 `@settings` | 安全设置持久化；保存失败回滚；仅在受控通知替身下验证通知。 | 临时配置与通知替身 |
| P1 `@scheduler` | 缺任务/模式/用户时禁止启动；单用户、多用户、队列范围、禁用项、重复启动、停止终态。 | 确定性执行器或真实脚本 |
| P1 `@scheduler` | 循环预览、到期执行、重试、恢复入口、运行时修改与删除保护。 | 可控时钟或真实时间流程 |
| P1 `@history` | 按日期和用户搜索；展开日志；无结果、坏记录和刷新恢复；运行结果与历史一致。 | 隔离历史数据 |
| P1 `@recovery` | 页面切换、renderer 刷新；WS 断线、延迟、重复、乱序和快照失败；重连后状态与日志收敛。 | 受控网络故障与确定性任务 |
| P2 模拟器 | 搜索/纳管、实例绑定、离线启动、ADB 就绪、重复操作、超时/失败提示、关闭恢复。 | 作者已有模拟器和 TCP ADB |
| P2 游戏调度 | 游戏包安装检查；选择脚本和用户；真实启动、公开结果、日志、失败、取消和重跑。 | 作者已有游戏与受支持脚本 |
| P2 账号 | 用户范围、禁用用户、配置持久化、不同用户隔离；登录、切号和失效凭据由脚本专项验证。 | 作者已有用户配置 |
| P2 社区账号 | 账号组增删改、排序、启停、持久化及签到边界。 | 独立可控 fixture；当前真实流程不复制社区配置、不执行签到 |

## 作者本机真实流程

`yarn e2e:real` 调用 [`run-real.ps1`](../../frontend/e2e/run-real.ps1)，设置 `AUTO_MAS_E2E_REAL=1` 后委托唯一入口 `run.mjs`。以下变量必须配置，缺失时入口报错：

| 环境变量 | 含义 |
| --- | --- |
| `AUTO_MAS_E2E_SCRIPT_ID` | 已配置且本机可运行的脚本 UUID |
| `AUTO_MAS_E2E_USER_ID` | 脚本下已启用用户 UUID |
| `AUTO_MAS_E2E_ACCOUNT_NAME` | 配置中该用户的名称 |

`AUTO_MAS_E2E_TEMPLATE_ROOT` 可选，默认当前仓库根目录；worktree 使用原工作区配置时显式指向原工作区。模板需有 `config/ScriptConfig.json`；绑定模拟器时还需对应 `config/EmulatorConfig.json`，用户的计划字段（MAA/BAAH 为 `Info.StageMode`、MaaEnd 为 `Info.SanityMode`、MSS 为 `Info.PlanMode`）引用计划时还需 `config/PlanConfig.json`。模拟器 ID 和实例索引从所选脚本绑定读取并校验，也可通过 `AUTO_MAS_E2E_EMULATOR_ID`、`AUTO_MAS_E2E_EMULATOR_INDEX` 限定目标；未绑定模拟器的脚本可省略它们。密码和密文按不透明配置透传，须在能解密原配置的 Windows 身份下运行。

`run.mjs` 校验目标后，只保留选中的脚本和一个启用用户；若脚本绑定模拟器，也只保留对应模拟器。入口登记了当前所有专项配置类型：MAA、General、Okww、OkNte、SRC、MaaEnd、MaaFW/M9A、HSR、BetterGI、ZzzOd、BAAH、Whimbox、MSS；未知类型会直接失败并要求专项作者补充适配。通知配置会从临时用户副本移除。普通专项按原样复制 `data/<scriptId>/{Default,<userId>}/{ConfigFile,Infrastructure}`；BetterGI 额外复制选中用户的 `OneDragon`、`ScriptGroup`、`GlobalDomain` 和 `GlobalStygian`，这些是 MAS 当前公开的 BetterGI 用户副本目录。临时环境不复制全局设置、队列、工具/社区配置、通知密钥、历史、`Temp`、备份池或上次运行的恢复事务。BetterGI 和其他把原生配置留在安装目录的专项，其安装根目录与脚本资产仍由专项配置指向本机已有安装，入口不复制或解析上游安装目录。

MAS 配置和托管数据在临时副本中运行，原 `config/`、`data/` 不被覆盖；脚本安装路径仍指向本机真实安装，正常的配置注入/恢复可能改变游戏状态或消耗资源。临时目录不能隔离这些外部副作用，作者应选择合适的现有脚本与用户。

流程顺序为：确认无运行任务和唯一目标用户 → 若脚本绑定模拟器，必要时启动并等待操作完成、在线及 ADB 就绪 → 在调度台选择脚本及用户 → 启动一次真实调度 → 等待任务终态并核对公开完成事件中的目标用户状态 → 保存证据。未绑定模拟器时跳过模拟器步骤。`finally` 停止仍运行的任务，只关闭本次由测试启动的模拟器；已在线实例不由测试额外关闭。统一入口等两个服务退出后再删除临时目录。

真实入口在机器级临时目录建立原子锁（Windows 为 `%SystemRoot%\Temp\AUTO-MAS`），同一台电脑同时只允许一个真实 E2E；强制结束进程后若留下锁文件，确认没有测试运行再手动删除该锁文件。新增专项时，专项作者必须先把类型加入入口白名单，再按实际 MAS 数据归属扩展 seed 自检和公开前置条件。

真实模式不会自动复制后端原始日志，也不把完整后端输出附加到报告。`real-e2e-summary.json` 记录起止时间、阶段、调度状态、账号完成情况和清理状态；Playwright 只附加用例明确生成的精选截图和摘要。完整 HTML 报告、断言错误和终端输出仍可能包含本机信息，分享前人工检查。

该用例验证脚本公开上报的用户结果；`accountResultAccepted` 表示任务级结果为成功、脚本状态为「完成」，且目标用户状态为「完成」或调度器接受的「部分失败」，不等同于账号全部步骤成功。`taskAndEmulatorCleanupStatus` 只表示任务已终止及测试启动的模拟器已关闭，不验证脚本安装目录的原生配置是否恢复。流程不读取或反推上游内部状态，也不单独识别游戏前台、登录画面或切号结果。历史页面、社区账号/签到和 Electron 主进程不在当前真实用例中。

## 等待与证据约定

- 用可见状态、API 响应、公开任务结果和带超时的轮询等待；不使用固定长 `sleep`。测试 debounce、轮询、重连退避时可注入短延迟，但要和真实启动/运行耗时区分。
- 对绑定模拟器的脚本，`POST /api/emulator/operate` 仅表示操作已排队；须等待 `EmulatorManager:emulator.operation.finished`，再确认设备状态。HTTP 200 本身不能证明启动完成。
- 调度初始状态来自 `GET /api/dispatch/runtime-snapshot`，后续状态来自 WebSocket；`POST /api/dispatch/start`、`/stop` 是真实入口，`GET /api/dispatch/task/{task_id}` 查询终态。调度成功不等于每个游戏用户成功，因此真实用例还检查目标用户的公开完成结果。
- 普通流程失败时保留截图、trace、video；fixture 可附加隔离后端 `debug/app.log`，关键成功步骤可显式截图。开发者从本机结果目录中挑选脱敏证据附到 PR。
- 真实模式关闭自动截图、trace、video 和后端进程输出；spec 只附加精选截图及 `real-e2e-summary.json`。真实 HTML 报告、断言错误和终端输出仍可能包含本机信息，不能宣称完整报告已脱敏。附到 PR 前人工检查，不要直接上传整个 real 结果目录。
- 密码、Cookie、Token 和无关个人信息不得出现在共享证据中。真实流程可能产生游戏内副作用，失败时也必须执行清理。

Playwright 资料：[标签和注解](https://playwright.dev/docs/test-annotations)、[CLI 选择器](https://playwright.dev/docs/test-cli)、[截图与 trace 配置](https://playwright.dev/docs/api/class-testoptions)。

## 仓库链路位置

- 页面入口：[`frontend/src/router/index.ts`](../../frontend/src/router/index.ts) 的 `/plans`、`/queue`、`/scheduler`、`/history`、`/settings`、`/emulators`、`/gamesign`；首页快捷启动在 [`useHomeQuickStart.ts`](../../frontend/src/views/home/useHomeQuickStart.ts)。
- 队列配置：[`queue/index.vue`](../../frontend/src/views/queue/index.vue)、[`QueueItemManager.vue`](../../frontend/src/views/queue/components/QueueItemManager.vue)、[`TimeSetManager.vue`](../../frontend/src/views/queue/components/TimeSetManager.vue)；后端 CRUD 在 [`app/api/queue.py`](../../app/api/queue.py)。
- 调度和运行态：[`useSchedulerLogic.ts`](../../frontend/src/views/scheduler/useSchedulerLogic.ts)、[`useTaskRuntimeState.ts`](../../frontend/src/composables/useTaskRuntimeState.ts)、[`app/api/dispatch.py`](../../app/api/dispatch.py)；循环执行、预览和重试在 [`app/core/task_manager.py`](../../app/core/task_manager.py)。
- 模拟器与账号：[`app/api/emulator.py`](../../app/api/emulator.py)、[`Emulator.vue`](../../frontend/src/views/Emulator.vue)、[`app/api/scripts.py`](../../app/api/scripts.py)、[`TabGameSign.vue`](../../frontend/src/views/gamesign/TabGameSign.vue)。
- 历史与设置：[`useHistoryLogic.ts`](../../frontend/src/views/history/useHistoryLogic.ts)、[`app/api/history.py`](../../app/api/history.py)、[`setting/index.vue`](../../frontend/src/views/setting/index.vue)、[`app/api/setting.py`](../../app/api/setting.py)。
- 代表性延迟：日志合并 200 ms、停止完成宽限 1.5 s、快照失败重试 3 s；循环预览每 5 s 刷新，执行空闲等待与重试分别为 60 s / 30 s。相关模块见调度和运行态链路。

## PR 验证记录

每个带 E2E 验证的 PR 正文记录具体场景、所用命令、被测 commit SHA、工作区是否 dirty、实际结果、截图或 summary 的证据位置，以及未覆盖范围或运行限制。不要只写“E2E 通过”。可直接使用以下模板：

```text
- E2E 场景：<验证的用户功能与路径>
- 命令：`<实际执行的命令>`
- Commit：`<完整 SHA>`；工作区：<clean / dirty（说明差异）>
- 结果：<通过/失败/未运行及实际观察>
- 证据：<截图和/或 real-e2e-summary.json 路径>
- 限制：<未覆盖场景、环境前置条件或无；不得把未验证范围写成已通过>
```
