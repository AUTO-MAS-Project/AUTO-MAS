# frontend/e2e

浏览器端到端测试：用真实的 Vite dev server + 真实 Python 后端跑 MAS 的主要用户流程。
这是**本地开发工具**，不是 CI 门禁。

## 命令（都在 `frontend/` 下执行）

| 命令 | 作用 |
| --- | --- |
| `yarn e2e` | 跑全部浏览器用例（自动分配端口、隔离数据根） |
| `yarn e2e e2e/queue.pw.ts` | 只跑一个文件；参数原样透传给 `playwright test` |
| `yarn e2e --grep '@queue'` | 按标签过滤 |
| `yarn e2e --grep '@queue' --headed` | 有头模式观察交互 |
| `yarn e2e:ui` | Playwright UI 模式 |
| `yarn e2e:check` | 启动器契约单测 + e2e 的 tsc 类型检查（改完 fixtures / run.mjs 先跑它） |
| `yarn e2e:report` | 列出最近 10 份报告并打开选中的那份 |
| `yarn e2e:real` | 真实脚本/账号/模拟器流程（默认被 `@real` 排除） |

启动器只允许是 `e2e/run.mjs`，不要直接调 `playwright test`：它负责预检（前端依赖、Playwright 浏览器）、端口分配、隔离数据根与产物目录。
预检失败会直接说清「该执行哪条命令」，不等到十几条用例一起报「元素找不到」：

- 依赖缺失 → `frontend/` 下 `yarn install`
- 浏览器没下载 → `frontend/` 下 `yarn playwright install chromium`（Playwright 升级会换浏览器版本，缓存里的旧版不算数）

## 文件

| 文件 | 说明 |
| --- | --- |
| `run.mjs` | 唯一入口：依赖预检 → 建隔离数据根 → 分配空闲端口 → 起 Playwright |
| `fixtures.ts` | 所有用例共用的 `test` / `expect`，提供导航、断言兜底、接口直连与诊断采集 |
| `harness.check.mjs` | 启动器契约单测（`node:test`），`yarn e2e:check` 会跑 |
| `*.pw.ts` | 用例；文件名即领域，`test.describe('@tag ...')` 里的标签用于过滤 |
| `emulator.pw.ts` | 模拟器配置：空状态说明与两种添加入口、手动添加 → 改名 → 刷新仍在 → 删除回空状态 |
| `scheduler.pw.ts` | 调度台：空调度守卫、电源操作下拉的 9 个信号都有译文、建队列后选中它即可启动并看到运行范围 |
| `script-editors.pw.ts` | 14 种脚本类型的编辑页各开一次（带 `:id` 的页面 `@routes` 覆盖不到） |
| `script-create-flow.pw.ts` | 从「New managed script」走向导建脚本：一步类型与两步类型各一条 |
| `plan.pw.ts` | 计划管理：空状态 → 新建 → 默认名跟随界面语言 → 改名刷新仍在 → 删除回空状态；四种计划类型各建一次 |
| `real-integration.pw.ts` / `real-batch.mjs` | `@real` 流程与批量跑真实目标 |

## 用例契约

```ts
import { expect, test } from './fixtures'

test.describe('@queue 队列', () => {
  test('入队后出现在队列里', async ({ app, page }) => {
    await app.goto('/queue')                     // 哈希路由 + 等应用挂载（失败会报 Vite 原始错误）
    await expect(page.getByText('Queue')).toBeVisible()
    const plans = await app.api.get<unknown[]>('/plan/list')  // 直连后端，自动解包 { code, data }
    await app.evidence('queue-after-enqueue')    // 全页截图，作为本次运行的证据
  })
})
```

fixture `app` 提供：

- `goto(route)`：拼 `/#<route>` 导航 → 等 `#app` 挂载（25 秒，优先报 Vite 编译错误而不是「元素找不到」）→ 等 hash 稳定 → 点掉启动期「Got it」弹窗并把内容记进 `diagnostics.startupWarnings`。
- `evidence(name, maskSelectors?)`：全页截图并 attach 到报告。
- `api.get<T>(route, params?)` / `api.post<T>(route, body?)` / `api.raw`：用 `page.request` 直连后端（`http://127.0.0.1:<AUTO_MAS_E2E_BACKEND_PORT>`），非 200 / 非 JSON / `code!==200` 都抛带 URL 的可读错误。
- `ignore({ console, warning, pageError, request, serverError })`：声明**预期内**的错误（如故意把接口打成 500）。规则只作用于当前用例。
- `expectNoUnexpectedErrors(hint?)`：手动提前校验一次；用例结束还会自动校验一次。
- `diagnostics`：`consoleErrors` / `consoleWarnings` / `pageErrors` / `failedRequests` / `serverErrors` / `startupWarnings` / `suppressed`。

### 兜底断言

每个用例结束时自动判失败的情形：

| 类别 | 判据 | 放行方式 |
| --- | --- | --- |
| 控制台报错 | `console.error` 且不是框架警告 | `app.ignore({ console: [/.../] })` |
| 控制台警告 | Vue / antd 的 `Warning: ...`、`console.warn` | **默认不阻断**，去重后 attach 成 `page-warnings.json`；`AUTO_MAS_E2E_STRICT_WARNINGS=1` 时判失败，可用 `app.ignore({ warning: [/.../] })` 逐条放行 |
| 未捕获异常 | `pageerror` | `app.ignore({ pageError: [/.../] })` |
| 请求失败 | `requestfailed`（默认放过 `/api/info/*/activity` 与 favicon） | `app.ignore({ request: [/.../] })` |
| 服务端 5xx | 任意响应 ≥500 | `app.ignore({ serverError: [/.../] })` |

放行规则必须写明**为什么**这条错误是预期内的；被放行的条目会记进 `diagnostics.suppressed`，失败时一并附在报告里。

### 全局巡检

- `routes.pw.ts`（`@routes`）：16 条路由逐条断言「渲染出来了、落在预期 hash 上、页头文案正确」，并受同一套兜底断言约束。新增路由要在这里登记期望值。
- `i18n.pw.ts`（`@i18n`）：把界面切成英文后逐路由扫中文，命中即失败（`LEARN_ALLOWLIST` 只减不增）。
- `combox-i18n.pw.ts`（`@i18n`）：英文界面下打开队列脚本下拉与调度台任务下拉，断言选项不含汉字。后端 combox 接口曾直接返回中文 label（「未选择」「队列 - x」），现在靠 `ComboBoxItem` 的 `labelKey/kind/name/scriptType` 字段在前端拼装（`src/utils/comboxLabel.ts`）；造出来的脚本/队列会先改成 ASCII 名，避免把用户数据误判成界面泄漏。
  词表本身的漏翻由 `src/i18n/locales.test.ts` 兜（中文每条 key 都必须在 en / ja 里有译文、占位符一致），改文案先跑它。

用例的初始化、接口桩与兜底断言都挂在 **context fixture** 上，所以同一个 spec 里即使只取 `page` 也受同一套约束——历史上有过「只取 page 的调试用例静默跳过全部初始化」的坑。

浏览器预览（`src/utils/browserDevElectronAPI.ts`）只实现了被测路径需要的 Electron 能力；缺成员表现为 `xxx is not a function` 的控制台报错，会被兜底断言抓到。补实现时用 `Partial<ElectronAPI>` 标注，别退回 `as unknown as ElectronAPI`——那会把签名错误和缺成员一起藏掉。

### 用例之间共享数据根

非 real 模式一次 `yarn e2e` 只起一个后端、一个数据根，整套用例跑在同一个空目录上。
文件执行顺序不要当成约定，每条用例都得能在「别的用例刚跑完」的状态下自己立起来。

因此**任何创建脚本/队列/计划的用例必须自己清理**（`try/finally` 调删除接口）：

- 清理**不许吞异常**（`.catch(() => {})`）。吞掉的删除失败会让残留数据留到下一个文件，
  症状出现在别人身上，排查只能靠猜；`combox-i18n.pw.ts` 就这样静默漏过一个队列，
  把 `queue.pw.ts` 的「空状态」断言带崩了。
- 清理完再查一次列表、断言真的空了（`queue.pw.ts` 的 finally 是范例）：删除接口返回 200 不等于数据没了。
- 断言「空状态」的用例，前置检查失败时要把**现有的那条数据点出来**，
  报错信息写清「有别的用例留下了队列数据」，而不是让下一个人对着 `No queues` 找不到发呆。
- `harness.check.mjs` 的「造数据的用例必须把造出来的数据删掉」会静态检查
  「用了 `/api/<res>/add` 就必须出现 `/api/<res>/delete`」；真的需要例外时往 `CLEANUP_EXEMPTIONS` 里登记原因。
  该检查看不到「点按钮造数据」的路径，那类用例只能靠上面的约定和 finally 自查。

同理，断言时段文案（如首页问候语）的用例不要锁死具体措辞，用忽略大小写的正则。

标签：`@smoke @init @queue @scheduler @settings @history @recovery @notify @routes @i18n @config @editors @plan @emulator @mascot @real`。
新增用例必须挂在已有标签下（或新增标签并在这里登记），否则 `--grep` 过滤不到。

## 产物与排障

- 截图 / trace / video：`test-results/<browser|real>/<runTag>/`
- HTML 报告：`playwright-report/<browser|real>/<runTag>/index.html`，用 `yarn e2e:report` 打开
- 后端日志：隔离数据根的 `debug/app.log`，失败时自动 attach 成 `backend-app.log`
- `[e2e] 后端 X / 前端 Y，产物目录 Z`：启动时打印，用来分辨并行运行的是哪一次

| 现象 | 通常原因 |
| --- | --- |
| 启动即报「前端依赖未安装或与 package.json 不一致」 | `frontend/` 下先 `yarn install` |
| 「前端编译失败，应用没有启动：...」 | Vite 编译错误，原文已附在消息里 |
| 「应用在 25 秒内没有挂载」 | 前端 dev server 没起来；先单独跑 `yarn vp dev` |
| 大量用例报「元素找不到」 | 通常是应用整体没起来，先看第一条失败的原始错误 |
| 数据根要保留排查 | `AUTO_MAS_E2E_KEEP_ROOT=1` |
| 固定端口 / 复用数据根 | `AUTO_MAS_E2E_BACKEND_PORT`、`AUTO_MAS_E2E_FRONTEND_PORT`、`--in-place` |