# 成熟前端工程的流程、工具与规范

调研日期：2026-11-08。适用范围：AUTO-MAS 的 Vue 3、TypeScript、Electron、Ant Design Vue 前端，以及小型开源团队和 AI 协作。本文用于建立判断框架，不构成新的重构实施计划。

后续进展（2026-11-09）：已在当前未提交工作区完成[设置模块试点](../plans/2026-11-08-frontend-settings-pilot.md)，包括静态字段契约、选项归属、开发入口和前端单测 CI。第 7 节保留调研时的现状记录，具体落地与验证以试点记录为准。

文中的「官方事实」来自对应项目的官方文档；「建议」是结合本项目约束作出的工程判断；「本地事实」只陈述本次实际查看的文件，不推断团队是否一直执行这些规则。

## 1. 成熟度首先体现为可重复的工作方式

**建议：前端收口的核心，是让同类问题有稳定的归属、实现入口和验收方式。** 新开发者或 AI 接手一项需求时，应能回答：行为是什么、代码放哪里、复用什么、谁拥有状态、保存成功意味着什么、怎样验证、由谁确认。

工具可以约束格式、类型和部分依赖规则，无法自行决定业务状态的归属、交互是否合理、一个抽象是否值得存在。Google 的评审指导把整体设计、功能影响和复杂度列为评审重点，并提醒不要提前实现尚未出现的通用需求。[官方来源：代码评审关注点](https://google.github.io/eng-practices/review/reviewer/looking-for.html)

一个与本项目更接近的实际例子是使用 Vue 的 GitLab：其官方前端流程在编码前要求考虑 API、可复用 UI、代码位置、验证和变更大小，随后进入实现、自查、评审与合并后验证。这说明流程应覆盖实现前后的决策和反馈。[官方来源：GitLab 前端开发流程](https://docs.gitlab.com/development/fe_guide/getting_started/)

## 2. 一项前端需求通常经过什么流程

下表是适合本项目的建议工作流，并非声称所有成熟团队采用同一套流程。小改动可以在任务说明和 PR 中完成；跨模块改动才需要独立设计记录。

GitLab 的架构流程也按影响范围选择方式：简单改动在 MR 中处理，复杂或影响广泛的架构工作才需要更完整的设计记录。成熟流程并不意味着每个按钮调整都先写 RFC。[官方来源：GitLab 前端架构流程](https://docs.gitlab.com/development/fe_guide/architecture/)

| 阶段 | 先明确什么 | 应留下什么 | 进入下一步的依据 |
| --- | --- | --- | --- |
| 需求与范围 | 用户遇到的具体问题、操作入口、成功标准、明确排除项 | 几条用户可观察的验收条件 | 可以判断做完与没做完 |
| 交互与状态 | 正常、加载、空数据、失败、禁用；保存、取消、重试、离开页面的含义 | 状态表或简单草图；复杂交互才做原型 | 状态转移和反馈没有歧义 |
| 技术设计 | 模块职责、已有复用点、状态与数据的所有者、API/IPC 契约 | 简短设计说明、类型/契约、参考实现 | 不产生第二套事实来源或并行入口 |
| 实现 | 按既定边界完成一个可运行的纵向切片 | 代码、必要文案和相应验证 | 该切片可独立演示和评审 |
| 验证与评审 | 需求是否满足；是否破坏相邻行为；结构是否便于继续修改 | 静态检查结果、相关行为证据、UI 演示 | 自动检查与人工评审分别完成 |
| 合并与维护 | 兼容、发布说明、需要观察的失败和后续清理责任 | 可回溯的变更记录、必要观测与迁移说明 | 新入口可用，旧入口有明确去向 |

建议按一个完整职责拆分变更，避免一次重排目录、升级工具、重写页面和改变保存行为。Google 推荐小而自洽的变更；新 API 应包含真实使用者，合入后系统仍能工作，没有适用于所有项目的固定行数标准。[官方来源：小规模变更](https://google.github.io/eng-practices/review/developer/small-cls.html)

## 3. 应统一哪些开发规范

### 3.1 模块与依赖

**建议：先规定职责和允许的依赖，再决定目录名称。** 最少应区分应用装配、路由页面、模块内部组件与流程、跨模块能力、请求契约、Electron 能力。

页面负责组合；独立业务区域隐藏自己的状态和生命周期；共享层只接受真实存在的复用需求。把大页面整体搬进 `useXxx()`，或者新增一个转发几十个参数的组件，并没有自动形成更好的边界。行数限制可作为防止继续膨胀的辅助门槛，不能代替职责评审。

FSD 是一套组织前端代码的架构方法，包含分层、业务切片和公共接口等约定；其官方文档也建议在现有架构确实造成困难时再考虑迁移，并允许渐进采用。[官方来源：FSD 概览](https://feature-sliced.design/docs/get-started/overview)

**建议：本项目可借鉴业务边界与依赖方向，不应仅为套用目录模板启动全量迁移。** 判断结构是否改进，可以看修改一个功能是否仍需同时理解多个无关页面，以及新增一个专项是否必须重复修改多份映射。

### 3.2 状态、请求与保存

Vue 官方指出，允许任意组件直接修改全局状态会降低可维护性，建议集中表达状态变更的动作；Pinia 为共享状态提供协作约定和开发工具支持。[官方来源：Vue 状态管理](https://vuejs.org/guide/scaling-up/state-management.html)

TanStack Query 的职责是获取、缓存、同步和更新服务端状态。服务端数据可能被其他参与方修改，存在异步与过期问题，其生命周期不同于客户端局部状态。[官方来源：Vue Query 概览](https://tanstack.com/query/latest/docs/framework/vue/overview)

结合上述区别，建议明确以下归属：

| 状态 | 默认归属 | 必须明确的行为 |
| --- | --- | --- |
| 弹窗开关、当前输入、未提交表单 | 最窄的组件或模块 | 关闭、重开、切换对象是否重置 |
| 跨页面共享的客户端会话状态 | 现有 Pinia store | 谁能修改、何时清理、是否需要持久化 |
| 后端权威数据及其请求状态 | 现有 Vue Query/业务 API 层 | 查询键、失效、刷新、错误展示归属 |
| 本地偏好和持久配置 | 已有配置所有者 | 重启恢复、校验和版本兼容 |

建议为每种保存交互确定契约：即时保存、排队保存和显式提交分别复用对应模式；统一错误反馈、请求边界和并发规则。不要仅因外观一致，就把不同保存时机强行合并。异步场景应说明旧请求结果、重复点击、切换对象和组件卸载怎样处理。

### 3.3 UI、设计系统与可访问性

Ant Design Vue 官方提供通过 `ConfigProvider` 配置全局 Design Token、Component Token 和主题算法的能力，包括暗色主题。[官方来源：Ant Design Vue 定制主题](https://github.com/vueComponent/ant-design-vue/blob/main/site/src/vueDocs/customize-theme.zh-CN.md)

**建议：设计系统至少包含三部分：共享视觉值、可复用组件、反复出现的业务交互模式。** 采用 Ant Design Vue 只解决了其中一部分。项目仍需约定页面标题和操作区、筛选与表格、表单与校验、保存反馈、危险操作、空/加载/错误状态的用法，并提供少量可运行的参考页面。

GOV.UK 的设计系统贡献标准会检查新组件或模式是否有用、是否重复，并在发布前检查可用性、一致性与适用面。可复用模式需要证据和维护规则，不能只凭视觉相似就加入公共组件。[官方来源：GOV.UK 贡献标准](https://design-system.service.gov.uk/community/contribution-criteria/)

颜色、间距、字号、圆角和层级应由共享 token 驱动；键盘操作、焦点、可识别标签、暗色和长文案应进入验收条件。只有真实复用的业务模式才需要封装，避免为了统一名称再包装所有基础按钮。

### 3.4 类型与桌面能力边界

Vue 官方说明，Vite 的开发服务器和打包过程默认只做 TypeScript 转译，不进行类型检查；Vue SFC 的命令行检查应使用 `vue-tsc`。[官方来源：Vue 与 TypeScript](https://vuejs.org/guide/typescript/overview.html)

TypeScript 的 `strict` 开启一组更严格的类型检查；升级编译器可能引入新的类型诊断。[官方来源：strict 配置](https://www.typescriptlang.org/tsconfig/strict.html)

**建议：类型检查应独立于构建执行。** 组件 props/events、领域类型、生成的 HTTP 客户端、preload 暴露的能力均应有明确契约。外部输入的运行时校验仍应放在实际接收它的边界，静态类型不能证明外部数据必然符合声明。

Electron 官方建议启用上下文隔离和进程沙箱、校验 IPC 消息发送者，并避免直接向不可信内容暴露 Electron API。[官方来源：Electron 安全指南](https://www.electronjs.org/docs/latest/tutorial/security)

**建议：桌面前端必须把 renderer、preload 和 main 的能力归属纳入规范。** 页面调用受限、可描述的业务能力，避免任意 Node/IPC 能力在视图层蔓延。此处是设计要求，本次没有审计项目安全实现。

## 4. 工具各自解决什么问题

以下为建议的工具职责划分。名称可以替换，职责不应遗漏；已有工具能满足要求时优先复用。

| 职责 | 本项目已有入口或可用选择 | 解决的问题与局限 |
| --- | --- | --- |
| 编辑反馈 | 支持 Vue/TS 的 IDE；Vue - Official 扩展 | 尽早发现模板和类型问题；不能代替 CI |
| 启动与构建 | 现有 Vite Plus、Electron 启动器、Yarn | 保持开发环境和依赖安装可重复；构建成功不代表行为正确 |
| 代码静态约束 | 现有 oxlint、oxfmt、`vue-tsc` | 分别约束部分代码问题、格式和类型；不能证明模块设计合理 |
| 调试与归因 | 浏览器 Network/Performance、Vue Devtools、现有日志 | 理解组件树、状态和性能证据；先测量再决定优化 |
| 数据与接口 | 现有 OpenAPI 生成、业务 composables、Vue Query | 保持契约和请求生命周期一致；生成类型不能决定 UI 业务语义 |
| 行为验证 | 现有测试入口与 Playwright E2E 工具 | 按受影响契约选择最小有效范围；需要隔离环境和可靠预期 |
| UI 状态展示 | 先使用参考组件/页面；按需求考虑 Storybook | 复现难到达的状态并展示用法；样例本身需要维护 |
| 架构与债务反馈 | 已有审计脚本；必要时增加依赖边界规则 | 定位新增重复和错误依赖；先定义正确边界再自动化 |
| 协作与合并 | 任务说明、PR、CI、评审 | 将意图、证据和责任连起来；通过检查并非自动认可设计 |

Vue 官方推荐 VS Code 配合 Vue - Official，并说明 Vue Devtools 可检查组件树、状态和性能。[官方来源：Vue 工具链](https://vuejs.org/guide/scaling-up/tooling.html)

## 5. 验证应守住行为，而不是追逐数量

Vue 官方区分单元、组件和端到端验证，强调组件测试应关注公开接口及用户输入造成的输出，不依赖私有状态和内部方法。[官方来源：Vue 测试指南](https://vuejs.org/guide/scaling-up/testing.html)

Playwright 官方建议验证用户可观察的行为、隔离测试数据与浏览器状态，并优先使用角色、文本等用户可感知的定位方式。截图比较还要求稳定环境，因为系统、浏览器、字体等因素会影响渲染。[官方来源：最佳实践](https://playwright.dev/docs/best-practices)、[视觉比较](https://playwright.dev/docs/test-snapshots)

**本项目建议：** 沿用 `.agents/skills/mas-testing/SKILL.md` 和 `frontend/TESTING.md`，先复用能证明目标行为的检查。纯逻辑、异步保存和关键跨模块流程按风险分别验证；UI 变更提供真实界面证据。不要以测试数量、每组件一个测试或覆盖率比例作为本项目的默认完成标准。

目前的前端测试运行于 node，项目规范未采用常规 DOM 挂载测试栈。因此 Vue 官方工具示例不能直接变成在本次任务中引入 jsdom 或 Vue Test Utils 的理由。若未来现有方式持续无法覆盖稳定的重要交互，再单独评估测试栈调整。

## 6. 可选工具的采用条件

**Storybook：** 官方将它定位为独立开发和记录 UI 状态的工作环境，stories 可描述 props、数据和事件条件，并用于展示与测试；官方支持渐进采用。[官方来源：Why Storybook](https://storybook.js.org/docs/get-started/why-storybook)

建议在共享组件增多、状态难以在完整应用中复现、相同模式不断被重新实现时考虑引入。前提是共享组件已能脱离整页上下文使用，主题/i18n/桌面能力替身有可维护的接入方式，并有人维护样例。先建立真实组件契约，再建立目录。

**依赖边界检查、Stylelint 和更强审计：** 这是建议选择，而非成熟项目必装清单。前者需要先达成模块规则；Stylelint 需要具体的 CSS 问题和可执行规则；重复检测结果需要人工区分偶然相似与真正的共同职责。没有这些前提，新增工具只会增加配置和例外。

**AI 协作：** 建议给 AI 提供精简规则、明确入口、正确参考实现、验收条件和真实检查命令。可以自动判定的规则交给工具，职责和行为仍交给评审。新抽象应带真实使用者；所谓迁移完成应以旧入口的使用者已迁走、旧路径已删除为证据，不能只看新目录已创建。

## 7. 对 AUTO-MAS 已核实的事实与含义

本次直接查看 `frontend/package.json`：项目使用 Yarn 4.18.1；已有 Vue、TypeScript、Electron、Ant Design Vue、Pinia、Vue Query、Playwright；已有 `lint`、`format:check`、`typecheck`、`test`、`e2e`、`e2e:check`、OpenAPI 生成，以及 baseline/i18n/unused/duplicates 审计入口。项目附属 Skills 还明确了模块归属、状态、API、UI 和验证约束。

**由此可以判断：本项目具备不少工程工具和书面规则，不能简单归因为缺少工具。** 这些事实不能证明规则已持续执行、边界已在全项目落地或现有 CI 足以阻止继续分化。

进一步核对当前工作区，能作出的有限结论如下：

- 已有可推广的基础：renderer 开启 `strict`（[tsconfig.app.json](../../frontend/tsconfig.app.json) 第 8 行），[ThemeTokenBridge.ts](../../frontend/src/components/ThemeTokenBridge.ts) 第 9–11 行把 AntD 最终 token 同步到主题层；设置页已复用 `SectionCard`、`SettingRow`（如 [TabBasic.vue](../../frontend/src/views/setting/TabBasic.vue) 第 23–24 行）。应先核查覆盖范围，而非重新选 UI 库。
- 自动验证尚有缺口：检索全部 `.github` 工作流与 composite actions，未发现 `yarn test`、`vp test` 或 Vitest 调用；[format-check.yml](../../.github/workflows/format-check.yml) 第 69–89 行运行 lint、renderer 类型、格式、词表及 Node 基础设施检查，第 85 行明确浏览器 E2E 按项目策略在本机执行。
- Electron 已有 CI 编译：[ci-package.yml](../../.github/workflows/ci-package.yml) 第 49 行调用 Windows 打包 action，该 [action.yml](../../.github/actions/build-windows-unpacked/action.yml) 第 38 行执行 `yarn build`，而 [package.json](../../frontend/package.json) 第 17–18 行包含 Electron `tsc`。它处于较重的打包路径，不能说 Electron 完全未被验证。
- 逐文件 Vue 尺寸门禁位于 [audit-baseline.mjs](../../frontend/scripts/audit-baseline.mjs) 第 43 行起及工作流第 55–56 行；这两处是当前未提交的 WIP，不能当作 `origin/dev` 已有能力。它限制文件增长，不能判断职责划分是否合理。

## 8. 检查与限制

- 本文仅新增调研文档；未修改业务代码、依赖、测试、CI 或既有实施计划，也未安装工具、创建提交或推送。
- 检查结果：从 `frontend/` 执行 `node node_modules/markdownlint-cli2/markdownlint-cli2.mjs ../docs/research/2026-11-08-frontend-engineering-workflow.md`，退出码为 0；`git diff --check` 退出码为 0；新增文件另行检查无尾随空格、以换行结束。
- 资料来自上述官方文档，反映各工具的能力和推荐用法；没有调查行业采用率，不能据此声称所有成熟团队都采用某一工具或架构。
- 未对完整前端、历史 PR、实际发布和协作过程做审计；没有验证所有现存脚本能运行，也没有性能、覆盖率或安全合规结论。
- 本次仅检查新增 Markdown 的格式与差异；未运行应用构建、业务测试、浏览器测试或真实账号/模拟器流程，因为本文不改变运行行为。
