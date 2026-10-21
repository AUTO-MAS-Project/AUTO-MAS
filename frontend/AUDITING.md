# 前端本地治理工具

从 `frontend/` 使用项目 Yarn 4 执行，先 `yarn install --immutable`。工具版本由
`package.json` 和 `yarn.lock` 固定。报告用于定位候选，不是 CI 门槛，不自动删除文件。

```powershell
yarn audit:baseline
yarn audit:baseline <基线提交>
yarn audit:unused
yarn audit:unused --reporter json > ../.dev/frontend-governance/knip.json
yarn audit:duplicates
```

重定向报告前创建本地目录：`New-Item -ItemType Directory -Force ../.dev/frontend-governance`。
原始报告保存在 Git 忽略的 `.dev/frontend-governance/`，不提交。

## 统计口径

`audit:baseline` 统计 Git 跟踪的文件与未忽略的新文件；传提交时只统计该提交的树。
按物理行（含空行）统计 `.ts`、`.vue`、`.css`，排除 `.test.*` / `.spec.*`。
渲染层、生成 API、词表、Electron 分开计算，构建产物不计入。
比较业务实现时只看相同组，不把锁文件、生成物或文件搬迁算成代码治理收益。

## Knip 入口与候选解释

`knip.json` 保留三个渲染入口：主应用、桌宠、桌宠菜单；保留 Electron main、普通
preload 和两个桌宠 preload，以及构建脚本、E2E 启动器、浏览器流程、单元测试、
`*.typecheck.ts` 类型契约入口。开发路由由路由表的动态导入进入调用图。

Vue 解析由 Knip 自带 Vue 插件启用；`@/*` 与 Vite / TS 一样指向 `src/*`。
生成 API 继续参与引用解析，但不报告它们的未使用导出；不能据此手删生成文件。
项目边界不包含 `dist`、`dist-electron`、`node_modules` 或本地验证产物。

Playwright 插件禁用配置执行：本项目 `playwright.config.ts` 只允许隔离启动器提供
数据根后加载；Knip 不应该启动或伪造运行环境。对应入口在 `entry` 中显式列出。
`pwsh` / `tasklist` 是系统命令，不是缺失的 npm 依赖。

未使用候选使 Knip 返回 1，这是报告行为。对每条候选核对：真实调用者、动态入口、
扩展公开入口、打包器隐式加载和类型校验入口；工具执行失败和未使用候选要分别处理。
尤其不要把 MaaFW 的 `pageKit` 扩展出口直接视为死代码。

## 复制片段

`.jscpd.json` 扫描手写 `src` 和 `electron`，排除生成 API、词表、声明文件、单元测试。
固定使用 mild 模式、至少 5 行且 70 token，输出终端报告和 JSON。
Vue SFC 中的脚本、模板、样式分别以 TypeScript、HTML、CSS 报告；分析结果另有
Vue 容器计数，不能把所有格式的行数相加当成源码物理行数。

先按格式、文件对和业务含义检查复制片段，再决定复用或保留。相似 UI 不必共享
业务联动；具有相同代码的扩展契约也不一定应该合并。

工具配置依据：[Knip 项目范围](https://knip.dev/guides/configuring-project-files)、
[jscpd 项目说明](https://github.com/kucherenko/jscpd)。

## 验证

前端检查使用当前 `package.json`：`yarn lint`、`yarn typecheck`、`yarn format:check`。
行为测试按影响面选择，本机需要限并发时用 `yarn test --maxWorkers=4`。
浏览器验证先运行 `yarn e2e:check`，再通过 `yarn e2e --grep '<标签>'` 启动隔离环境。
独立检出必须检查自己的 `.env`；源码运行前按根目录说明使用 `.env.example`。
一次性回归探针遵守 [TESTING.md](TESTING.md)，留在本地，不扩充长期测试集。
