# E2E 测试流程清单

目标是验证用户从配置、调度到结果查看与恢复的完整链路，并让每个 PR 只运行相关流程。浏览器 E2E 运行 Electron 共用的前端页面与真实 MAS 后端，主要验证生产应用渲染层的用户交互和可见结果；浏览器本身不是单独发布的产品。原生桌面集成和外部脚本执行另有专项验证。

真实流程完全跑在 PR 作者本机的环境里：用的是他本机已安装的脚本、MAS 软件里已经配好的真实用户配置，以及可选的模拟器。MAS 官方仓库不提供也不附带任何游戏资源、脚本安装包或测试账号，仓库里只有代码和用例本身。入口只按 MAS 的公开配置和调度契约工作，支持 BetterGI 等专项；需要模拟器的专项按配置执行模拟器步骤，不接入 USB、手机、实体设备或硬件校准链路。

## 按 PR 选择

`frontend/e2e/run.mjs` 是唯一启动入口：它创建一个一次性的运行根目录（`TEMP/TMP` 重定向、后端数据根、本轮日志都在其中），启动 Playwright 和两个开发服务，并在服务退出后删除它。若系统 `TEMP/TMP` 被配置到 `frontend` 内，入口会改用 `frontend` 外的专用临时目录，避免 Vite 监听运行数据。不要绕过它直接运行 `playwright test`。

入口默认**隔离**：运行根下的 `data/` 是新建的数据根，用例新建的队列、改动的设置、写出的 `history/`、`debug/` 和 `data/data.db` 都落在那里，跑完随运行根一起删除，开发者的检出保持不动。普通隔离模式在后端启动前通过正式 `HistoryStore` 写入三条已知历史：账号 A 今天成功、昨天失败，账号 B 八天前成功，各有不同日志。没有预置脚本或账号，这些由相关用例单独准备、清理；入口固定关闭明日方舟 PC 工具，所以 `@init` 不会初始化它。真实模式和 `--in-place` 不写历史种子，种子失败则终止启动。

需要改动隔离行为时用这几个开关：

| 变量 / 参数                               | 作用                                                                                                                                                             |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AUTO_MAS_E2E_KEEP_ROOT=1`                | 跑完保留运行根并打印路径，用于查看测试到底写了什么                                                                                                               |
| `--in-place` 或 `AUTO_MAS_E2E_IN_PLACE=1` | 不隔离，直接把当前检出当作数据根运行；会写入 `config/`、`data/`、`history/`、`debug/` 且不清理，运行前先关掉自己启动的实例，避免两个后端同时写同一份配置与数据库 |
| `AUTO_MAS_E2E_TEMPLATE_ROOT=<目录>`       | 真实模式的配置种子源，默认是当前检出                                                                                                                             |

就地运行时仍可用 `AUTO_MAS_E2E_DATA_ROOT` 指向别的数据根（例如 worktree 里复用主检出的配置）：

```powershell
$env:AUTO_MAS_E2E_IN_PLACE = '1'
$env:AUTO_MAS_E2E_DATA_ROOT = (Resolve-Path ..).Path
yarn e2e --grep "@smoke"
```

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
yarn e2e:settings
yarn e2e:history
yarn e2e:recovery
yarn e2e --grep '@queue|@scheduler'
yarn e2e:real
yarn e2e:real:all
yarn e2e:ui
yarn e2e:report
yarn playwright show-report playwright-report/real
```

`e2e:check` 运行 harness 自检（数据根隔离、配置种子白名单、真实运行锁、启动参数不透传）和 E2E TypeScript 检查；`e2e:init` 运行后端冷启动流程。`e2e:ui` 打开 Playwright 可视化运行器（用例树、实时进度、逐步时间线、单条重跑，跑完保留在当前数据根里便于复现）；`e2e:report` 打开浏览器 HTML 报告；真实流程使用 `playwright show-report playwright-report/real`。`--grep` 是正则表达式，空值默认运行 Playwright 配置中的默认集合。默认配置排除所有 `@real` 用例；真实流程由作者本机运行，不访问共享 CI 账号、模拟器或游戏资源。真实命令从当前检出的分支启动，`dev` 与 `release/*` 均可验证各自代码。浏览器 E2E 不阻断合并，PR 作者按改动选择需要的流程，并手动附上经过检查的截图或摘要；E2E 基础设施契约（`frontend/e2e/harness.check.mjs`）随「格式检查」工作流在 CI 跑，改坏数据根隔离、配置种子或启动参数会直接失败。

### 合并门槛（三层）

| 层        | 内容                                                                                                                                          | 谁跑                   | 是否阻断合并 |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ------------ |
| 阻断      | Windows 与 Ubuntu 全量 pytest、格式检查、changelog 碎片、uv lock、打包检查、E2E 基础设施契约自检（`yarn e2e:check` 里的 `node --test`，秒级） | CI 托管 runner         | 是           |
| 提示      | revert 检查（标注近期删除的他人代码，不阻断合并）                                                                                             | CI 托管 runner         | 否           |
| 不阻断    | 浏览器 E2E（`@smoke` 等）                                                                                                                     | 贡献者本机，按改动选择 | 否           |
| 永不进 CI | `@real` 真实调度 / 游戏 / 账号流程                                                                                                            | 作者本机               | 否           |

`@real` 不进 CI：它需要本机脚本安装、用户配置和模拟器，托管 runner 无法复现；真实运行有游戏副作用；这些配置私有且不能提交。按改动路径要求：

| 改动路径                              | 要求                                                             |
| ------------------------------------- | ---------------------------------------------------------------- |
| 纯前端交互 / UI                       | 建议跑相关标签用例并附截图，不阻断                               |
| `app/task/**`、专项适配、调度、模拟器 | 必须附 `@real` 自证：`real-e2e-summary.json` 关键字段 + 精选截图 |
| 纯文档 / CI / 测试                    | 不需要                                                           |

结果按模式存放：

| 模式             | 测试产物                         | HTML 报告                             |
| ---------------- | -------------------------------- | ------------------------------------- |
| 普通浏览器       | `frontend/test-results/browser/` | `frontend/playwright-report/browser/` |
| 作者本机真实流程 | `frontend/test-results/real/`    | `frontend/playwright-report/real/`    |

当前实现的范围：

- `@smoke`：从首页点击真实侧栏进入计划、队列、调度、历史、设置，再返回首页，检查路由、选中菜单和页面内容。
- `@queue`（同时带 `@scheduler`）：UI 新建队列、改名、设置启动方式、添加两个脚本项并拖动排序；离开返回和刷新后回读；在调度台选择队列并勾选账号范围；取消和确认删除项、队列，核对两个页面同步变化。普通组不启动这些脚本。
- `@scheduler`：保留无任务时禁止启动、添加和批量关闭空闲调度台的独立场景。
- `@settings`：UI 切换明暗主题，检查实际外观及刷新回读；修改历史保留天数遇到业务拒绝或 HTTP 失败时显示错误并保留旧值，恢复后重试、刷新回读，最后恢复原设置。
- `@i18n`：UI 切换中英日语言，跨页面和刷新后核对选择与实际文案；首次资源加载遇到业务拒绝或 HTTP 失败时展示错误并允许重试；切换遇到 HTTP 失败或批次版本不一致时保留原语言，解除故障后重新选择成功。正常请求读取真实后端词表，故障只注入 HTTP 边界。
- `@notify @webhook`：从通知设置 UI 创建、编辑、禁用、重新启用和删除 Webhook；刷新后核对表单，以本地接收端的实际路径与正文验证投递；接收端拒绝时显示失败，恢复后在原页面重试。仅普通隔离模式执行，不向真实模式或就地模式中已有的通知目标发送测试消息。单独运行使用 `yarn e2e --grep '@webhook'`；`@notify` 还包含 Windows 系统通知集成。
- `@history`：UI 快捷时间和日历筛选三条已知记录，选择账号、打开记录，核对成功或失败状态及独有日志；空区间无记录，恢复日期后可以重新查询。该种子场景只在普通隔离模式运行，真实模式和 `--in-place` 显式跳过，避免向现有历史写入测试记录。
- `@recovery`：关闭已建立的主 WebSocket，原页面自动重连；随后通过 UI 启动一个没有安装路径和模拟器的隔离 MAA 任务，收到真实后端失败结果并展示，验证恢复后链路可用。另一条验证刷新期间健康请求失败及解除故障后的恢复，未重启后端进程。
- `@init`：后端冷启动，等待健康与后台初始化就绪；隔离模式的数据根必须没有启用明日方舟 PC 工具，并确认启动不会初始化它。
- `@real @game-schedule @account`（另带 `@emulator` 或 `@script-install`）：UI 创建单脚本队列并选择唯一目标账号。`complete` 场景在执行阶段断开并恢复 WS，核对同一任务后续消息、公开终态和账号结果，再经历史页面打开此次新增记录与日志；`stop-restart` 场景在账号执行阶段点击停止，确认取消与运行时空闲，再启动不同任务并取消收尾。需要作者本机已安装且能归档历史、运行时间足够执行中操作的目标，代码存在不代表已获真实运行证据。

上述渲染层场景共用页面异常检查：未捕获异常和 Vue 全局错误都会使测试失败。页面刷新只证明前端回读，不能证明配置经过后端重启仍然保留。浏览器运行时替代了 Electron 桥接，因此原生 IPC、窗口、托盘、系统通知和外部游戏成功需要各自的集成证据；这些边界不影响共用页面交互验证的有效性。

插件迁移接缝的首批回归可运行 `yarn e2e --grep '@i18n|@webhook'`。当前守护主线语言资源与内置通知渠道的用户行为；插件安装、启停、卸载和多来源语言资源尚未迁入主线，不能由这组结果推定已覆盖。

真实场景可分别运行：

```powershell
yarn e2e:real --grep complete
yarn e2e:real --grep stop-restart
```

真实收尾在启动响应缺失时仍从公开创建事件或匹配的运行快照找回任务，必要时停止并等待终态；只有运行时空闲已确认后才关闭测试打开的模拟器。任务身份或空闲状态无法确认时保留资源并令测试失败，需人工检查。此判断及历史种子的模式隔离由 `yarn e2e:check` 自检。

### 用例准入：改坏必须变红

一条 E2E 只有在被测代码真的坏掉时变红才算数。新增或修改用例后按这个办法验证一次：把被测行为改坏 → 跑这条用例 → 必须失败 → 还原。永远不红的用例直接删掉，它只会拖慢每次运行。

本轮补强已验证以下故障注入，验证后均已还原：

| 用例             | 改坏什么                           | 结果                           |
| ---------------- | ---------------------------------- | ------------------------------ |
| 页面错误检查     | 临时触发未捕获异常、Vue 全局错误   | 两条探针均失败                 |
| `@queue` 排序    | 排序请求返回成功，但不持久化顺序   | 离开页面再返回后的顺序断言失败 |
| `@history` 日志  | 将昨日记录的详情日志换为另一段内容 | 昨日日志标记断言失败           |
| 真实任务收尾自检 | 跳过运行时空闲确认                 | 清理顺序自检失败               |
| `@i18n` 批次版本 | 临时跳过词表响应的版本一致性校验 | 预期拒绝切换的断言失败 |
| `@webhook` 投递 | 临时让发送器直接报告成功而不发请求 | 接收端实际收包数量断言失败 |

## 为单个 PR 添加流程

- 文件使用 `frontend/e2e/<场景>.pw.ts`，从 `./fixtures` 导入 `test`、`expect`，按用户路径操作 UI。复用 `app.goto()` 和 `app.evidence()`，不要直接改页面内部状态。
- 用 `test.describe('@标签', ...)` 命名流程；有真实游戏副作用的用例必须带 `@real`。`--grep` 接收正则：`@queue|@scheduler` 是 OR；`(?=.*@real)(?=.*@my-feature)` 是 AND。`'@real @my-feature'` 只匹配标题中相邻且顺序一致的文本，不是通用 AND 选择器。
- 普通一次性流程用 `yarn e2e --grep '@my-feature'` 运行。新增长期标签只需要在对应 spec 和本文档中说明用途，不需要维护 CI 标签映射。
- 真实一次性流程用 `pwsh -NoProfile -File ./e2e/run-real.ps1 -Grep '(?=.*@real)(?=.*@my-feature)'` 运行；它直接使用当前检出里已调配好的脚本、用户和模拟器配置。入口按脚本是否绑定模拟器决定是否执行模拟器步骤。新增专项只需声明公开前置条件（脚本、用户、可选模拟器）并在本机配置里准备好。
- 本条只指无法复用的浏览器端一次性流程：跑完并检查证据后，在合并前删除；稳定、可重复的用户路径应转为长期 E2E 用例。可隔离、可重复运行的 pytest 回归测试不属于一次性流程，应按开发文档站「测试提交与维护规范」随实现提交并长期维护。
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

## 调试配置项

要断言某个设置或脚本配置项时，用例不能依赖开发者检出里的现状：默认隔离下的数据根是空的。按下面的顺序做。

1. **找到配置键。** 用 `--in-place` 跑一条只做界面操作的临时用例，改完控件后 `git diff config/`；或从组件字段反查后端字段（例如 [`StartupWindowSettings.vue`](../../frontend/src/views/setting/components/StartupWindowSettings.vue) 的 `UI.IfShowTray` 落到 `app/models/schema.py` 与 [`config.py`](../../app/core/config.py)）；运行根里的 `debug/app.log` 也会记下读取到的配置。
2. **选种子方式。** 优先级从高到低：用例里用 UI 或 API 自己造出来（默认隔离时这是唯一可靠的办法）；在 `run.mjs` 启动后端**之前**写配置文件；提交一份最小 profile 给用例复用。真实模式另有 `AUTO_MAS_E2E_TEMPLATE_ROOT` 指向的配置种子源。
3. **确认测试真的写进去了。** `AUTO_MAS_E2E_KEEP_ROOT=1` 跑一遍，把运行根与种子状态对比，把观察到的变化写进断言和清理步骤，不要凭记忆。

改完这些开关本身的行为后运行 `yarn e2e:check`：harness 自检守着隔离、种子白名单和启动参数，改坏了会直接失败。

## 必要流程清单

| 优先级 / 范围   | 用户实际操作与验收                                                                   | 所需环境                                                 |
| --------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------- |
| P0 `@smoke`     | 启动、初始化、首页入口、核心页面导航；空态、加载态和返回正常。                       | 本机现有配置                                             |
| P0 `@queue`     | 队列和队列项的新增、编辑、重排、删除；定时项启停和持久化；刷新后顺序一致。           | 本机后端；部分场景需脚本配置                             |
| P0 `@settings`  | 安全设置持久化；保存失败回滚；仅在受控通知替身下验证通知。                           | 本机配置与通知替身                                       |
| P1 `@scheduler` | 缺任务/模式/用户时禁止启动；单用户、多用户、队列范围、禁用项、重复启动、停止终态。   | 确定性执行器或真实脚本                                   |
| P1 `@scheduler` | 循环预览、到期执行、重试、恢复入口、运行时修改与删除保护。                           | 可控时钟或真实时间流程                                   |
| P1 `@history`   | 按日期和用户搜索；展开日志；无结果、坏记录和刷新恢复；运行结果与历史一致。           | 本机历史数据                                             |
| P1 `@recovery`  | 页面切换、renderer 刷新；WS 断线、延迟、重复、乱序和快照失败；重连后状态与日志收敛。 | 受控网络故障与确定性任务                                 |
| P2 模拟器       | 搜索/纳管、实例绑定、离线启动、ADB 就绪、重复操作、超时/失败提示、关闭恢复。         | 作者已有模拟器和 TCP ADB                                 |
| P2 游戏调度     | 游戏包安装检查；选择脚本和用户；真实启动、公开结果、日志、失败、取消和重跑。         | 作者已有游戏与受支持脚本                                 |
| P2 账号         | 用户范围、禁用用户、配置持久化、不同用户隔离；登录、切号和失效凭据由脚本专项验证。   | 作者已有用户配置                                         |
| P2 社区账号     | 账号组增删改、排序、启停、持久化及签到边界。                                         | 独立可控 fixture；当前真实流程不复制社区配置、不执行签到 |

## 作者本机真实流程

`yarn e2e:real` 调用 [`run-real.ps1`](../../frontend/e2e/run-real.ps1)，设置 `AUTO_MAS_E2E_REAL=1` 后委托唯一入口 `run.mjs`。

**默认零配置**：不用设任何变量。入口读你当前检出里 `config/ScriptConfig.json`，取第一个「用户已启用」的脚本与用户，并在启动日志打印选中目标（`[e2e] 真实 E2E 目标：<账号名>（脚本 … / 用户 …）`）。有多个可用用户时默认用第一个，同时列出全部候选。

只有想跑特定脚本或账号时才需要这三个变量（缺哪个补哪个，也可全给）：

| 环境变量                    | 含义                                 |
| --------------------------- | ------------------------------------ |
| `AUTO_MAS_E2E_SCRIPT_ID`    | 脚本 UUID，用于在多个脚本间挑选      |
| `AUTO_MAS_E2E_USER_ID`      | 该脚本下的用户 UUID                  |
| `AUTO_MAS_E2E_ACCOUNT_NAME` | 该用户的名称，和配置里的名字必须一致 |

指定的目标在配置里不存在时直接报错并列出现有候选，不会静默换成别的账号。

最小步骤：

```powershell
Set-Location frontend
yarn e2e:real --grep complete    # 默认账号的完成、重连与历史场景
yarn e2e:real --grep stop-restart # 默认账号的停止、再次启动与停止收尾
# 看 frontend/test-results/real/real-e2e-summary.json 与精选截图，贴到 PR
```

数据根里的配置需能直接跑通所选流程：`config/ScriptConfig.json` 有该脚本，绑定模拟器时 `config/EmulatorConfig.json` 有对应实例，用户的计划字段（MAA/BAAH 为 `Info.StageMode`、MaaEnd 为 `Info.SanityMode`、MSS 为 `Info.PlanMode`）引用计划时 `config/PlanConfig.json` 有该计划。模拟器 ID 和实例索引从所选脚本绑定读取，也可通过 `AUTO_MAS_E2E_EMULATOR_ID`、`AUTO_MAS_E2E_EMULATOR_INDEX` 限定目标；未绑定模拟器的脚本可省略它们。密码和密文按不透明配置透传，须在能解密原配置的 Windows 身份下运行。

真实模式同样使用隔离运行根：入口从配置种子源（`AUTO_MAS_E2E_TEMPLATE_ROOT`，默认当前检出）取出这一次真实运行需要的脚本、用户与计划配置写进运行根，只复制被选中条目的脚本资产，并剥掉用户配置里的通知字段，所以跑测试不会推真实通知；测试对队列、设置、历史和 `data/data.db` 的改动随运行根一起删除。种子源里没有被选中的脚本、用户和计划不会进入运行根。BetterGI 和其他把原生配置留在安装目录的专项，其安装根目录与脚本资产仍由专项配置指向本机已有安装，入口不复制或解析上游安装目录。

外部脚本使用本机真实安装；正常执行及配置注入/恢复可能改变游戏状态或消耗资源，作者应选择合适的现有脚本与用户。

两条场景均先确认无运行任务和唯一目标用户；若脚本绑定模拟器，必要时启动并等待操作完成、在线及 ADB 就绪，再通过 UI 创建队列并选择该账号。`complete` 启动一次任务、在执行中重连，核对公开结果并打开新增历史；`stop-restart` 启动后停止，确认取消与空闲，再启动新任务并停止收尾。未指定 `--grep` 时会运行两条场景。`finally` 停止仍运行的任务，确认空闲后只关闭本次由测试启动的模拟器；已在线实例不由测试额外关闭。统一入口等两个服务退出后再删除临时目录。

真实入口在机器级临时目录建立原子锁（Windows 为 `%SystemRoot%\Temp\AUTO-MAS`），同一台电脑同时只允许一个真实 E2E；强制结束进程后若留下锁文件，确认没有测试运行再手动删除该锁文件。新增专项时，专项作者只需声明公开前置条件（脚本、用户、可选模拟器），并在本机配置里准备好它们。

真实模式不会自动复制后端原始日志，也不把完整后端输出附加到报告。`real-e2e-summary.json` 记录起止时间、阶段、调度状态、账号完成情况和清理状态；Playwright 只附加用例明确生成的精选截图和摘要。完整 HTML 报告、断言错误和终端输出仍可能包含本机信息，分享前人工检查。

`complete` 验证脚本公开上报的用户结果及对应历史与日志；`accountResultAccepted` 表示任务级结果为成功、脚本状态为「完成」，且目标用户状态为「完成」或调度器接受的「部分失败」，不等同于账号全部步骤成功。`stop-restart` 以取消和再次启动验收，使用 `firstRunCancelled` 记录首次取消，不要求账号执行成功。`taskAndEmulatorCleanupStatus` 只表示任务已终止及测试启动的模拟器已关闭，不验证脚本安装目录的原生配置是否恢复。流程不读取或反推上游内部状态，也不单独识别游戏前台、登录画面或切号结果。社区账号/签到和 Electron 主进程不在当前真实用例中。

### 批量跑全部专项

`yarn e2e:real:all` 遍历本机 config 里每个「用户已启用」的脚本，逐个运行两条真实场景（[`real-batch.mjs`](../../frontend/e2e/real-batch.mjs)）：

```powershell
Set-Location frontend
yarn e2e:real:all --list                      # 只列目标，不跑
yarn e2e:real:all                             # 全部已启用专项，串行
yarn e2e:real:all --only MaaConfig,SrcConfig  # 只跑这些专项
```

- 每个目标一次独立运行：独立隔离数据根、独立真实运行锁，上一个目标的队列、历史和模拟器状态不会串到下一个；单个目标失败不中断后面的目标，结束时汇总 `PASS`/`FAIL` 并以非 0 退出码报告失败数。
- 结果按目标分别留在 `frontend/test-results/real-batch/<序号-专项-账号>/`，`real-e2e-summary.json` 仍在其中；HTML 报告只保留最后一次运行。
- 串行重启整套服务，每个目标的固定开销约 20-30 秒，加上真实任务本身，批量请留足时间；不支持 `--in-place`，批量必须每个目标独立数据根。
- 模拟器由每个目标自己的脚本绑定决定，批量会忽略外部传入的 `AUTO_MAS_E2E_EMULATOR_ID` / `AUTO_MAS_E2E_EMULATOR_INDEX`。

## 让 AI 助手跑测试

助手可以直接按下面的说法执行，不要绕过 `run.mjs` 与 `real-batch.mjs` 调用 `playwright test`。

| 说法                     | 助手执行                                              |
| ------------------------ | ----------------------------------------------------- |
| 改完 UI，看有没有跑坏    | `yarn e2e --grep '@smoke\|@<相关标签>'`               |
| 改过入口或种子规则       | `yarn e2e:check`                                      |
| 改到调度、任务或某个专项 | `yarn e2e:real`，或 `yarn e2e:real:all --only <专项>` |
| 只想看本机有哪些真实目标 | `yarn e2e:real:all --list`                            |

**PR 开出来到等 review 之间，助手必须主动把这张表交出来**：按改动路径列出相关命令、每条产出什么（截图、HTML 报告、`real-e2e-summary.json`）、然后问「要我现在跑哪条」。非真实命令助手可以直接跑；`@real` 只能作者本机跑，助手不得代为声称结果。约定见 [`.agents/skills/mas-e2e/SKILL.md`](../../.agents/skills/mas-e2e/SKILL.md) 的「After opening a PR」与 [`.agents/skills/pr/SKILL.md`](../../.agents/skills/pr/SKILL.md)。

## 等待与证据约定

- 用可见状态、API 响应、公开任务结果和带超时的轮询等待；不使用固定长 `sleep`。测试 debounce、轮询、重连退避时可注入短延迟，但要和真实启动/运行耗时区分。
- 对绑定模拟器的脚本，`POST /api/emulator/operate` 仅表示操作已排队；须等待 `EmulatorManager:emulator.operation.finished`，再确认设备状态。HTTP 200 本身不能证明启动完成。
- 调度初始状态来自 `GET /api/dispatch/runtime-snapshot`，后续状态来自 WebSocket；`POST /api/dispatch/start`、`/stop` 是真实入口，`GET /api/dispatch/task/{task_id}` 查询终态。调度成功不等于每个游戏用户成功，因此真实用例还检查目标用户的公开完成结果。
- 普通流程失败时保留截图、trace、video；fixture 可附加后端 `debug/app.log`，关键成功步骤可显式截图。开发者从本机结果目录中挑选脱敏证据附到 PR。
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

## 常见失败原因排查

E2E 测试失败时，按以下顺序排查：

### 1. 环境因素（真实模式）

- **模拟器状态**：ADB 端口被占用、模拟器管理员权限不足、多开索引冲突
- **账号配置**：用户被禁用、密码过期、游戏客户端更新后配置失效
- **网络问题**：游戏服务器维护、代理配置失效、DNS 解析超时
- **资源不足**：磁盘空间不足、内存不足导致模拟器崩溃

排查方法：检查 `real-e2e-summary.json` 中的 `stage` 字段，查看失败发生在哪个阶段；检查后端日志 `debug/app.log` 中的模拟器操作和脚本执行记录。

### 2. 上游脚本因素（真实模式）

- **脚本内部逻辑**：游戏更新后识别失败、新活动未适配
- **配置兼容性**：MAS 传递的配置格式与上游脚本预期不一致
- **脚本崩溃**：上游脚本未捕获异常导致进程退出

MAS 测试**不读取或推断上游脚本内部状态**，只验证 MAS 公开契约（任务状态、账号完成结果）。如果 `completion.accepted === false`，检查 `completion.outcome`、`completion.scriptStatus`、`completion.userStatus` 判断是否为上游问题。

### 3. MAS 自身问题

- **调度器逻辑**：任务状态转换错误、WebSocket 消息丢失
- **配置持久化**：队列配置保存失败、设置回滚不正确
- **前端交互**：按钮未正确禁用、表单验证逻辑错误
- **并发控制**：多任务冲突、资源竞争

排查方法：检查 Playwright trace、截图和 HTML 报告；对比 WebSocket 消息记录和 API 响应；重现问题时开启浏览器 DevTools。

### 4. 测试代码问题

- **等待超时**：硬编码超时太短、轮询条件不正确
- **选择器失效**：前端 DOM 结构变更、动态加载时机不对
- **断言过严**：检查了不稳定的字段（如精确时间戳）
- **清理不完整**：前一个测试遗留状态影响后续测试

排查方法：本地运行失败的单个测试用例（`yarn e2e --grep "测试名称"`），启用 headed 模式查看浏览器实际行为，检查 Playwright trace 中的元素定位过程。

### 5. 超时设置

不同场景的典型超时参考：

- **快速交互**（按钮点击、表单输入）：5-10 秒
- **API 请求**（配置保存、状态查询）：10-30 秒
- **模拟器操作**（启动、关闭、ADB 就绪）：90 秒
- **短任务脚本**（签到、领取奖励）：5-10 分钟
- **长任务脚本**（刷材料、推图）：30-60 分钟

如果测试在超时前就失败，不要盲目延长超时；先确认是否为环境或配置问题。

### 6. 日志与证据

失败时检查以下位置：

- `frontend/test-results/<browser|real>/` - Playwright 截图、trace、video，以及真实模式的 `real-e2e-summary.json`
- `frontend/playwright-report/<browser|real>/` - HTML 报告
- `yarn e2e:real` 走 [`run-real.ps1`](../../frontend/e2e/run-real.ps1)，需要 PowerShell（Windows）
- `<运行根>/debug/app.log` - 后端日志；默认随运行根删除，`AUTO_MAS_E2E_KEEP_ROOT=1` 时保留并打印路径，`--in-place` 时写在检出里
- 终端输出 - 测试过程中的 console.log 和错误栈

真实模式失败时，优先检查 `real-e2e-summary.json` 中的字段：

- `stage`: 失败发生在哪个阶段
- `scheduler`: 调度器最终状态
- `accountResultAccepted`: 账号结果是否被接受
- `completion`: 目标用户的完成状态详情
- `taskAndEmulatorCleanupStatus`: 清理是否成功
