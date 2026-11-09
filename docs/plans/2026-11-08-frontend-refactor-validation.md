# 前端重构执行与验证记录

## 交付范围

方案见 [前端渐进重构落地方案](2026-11-08-frontend-refactor.md)。本轮完成 U1–U4 的登记、路由、尺寸门禁与行为验证；存量编辑器和样式仍按方案逐页迁移，不将本轮描述为整个前端重构完成。

工作位置仅为 `E:\desktop\AUTO-MAS`，分支 `refactor/frontend-adapter-registry-20261108`，基线 `9aab1ff2b610be534a32d17a9a136acb01715398`。运行环境为 Windows、Node v24.14.1、Yarn 4.18.1；所有结果对应此基线上的未提交改动。

## 工作区清理

清理前已备份各工作树 HEAD、未提交代码、未跟踪文件及需要保留的本地资料；16 个附加 checkout 移至仓库外的同盘归档位置，Git 登记已清除。`git worktree list` 只剩主工作区。所有本地分支与 stash 保留，Git bundle 和本地资料 ZIP 均已校验。

备份与恢复说明位于 `E:\desktop\AUTO-MAS-workspace-backups\20261108-cleanup-5394e720\README.md`。主工作区原来的通知设置改动单独保留在有名称标记的 stash 中；清理后重新同步最新 dev，再开始实现。主工作区的配置、数据和依赖未删除。

两个受权限保护的旧 `.pytest_cache` 目录仍保留，会导致 Git 输出读取警告，但不属于本轮代码改动。旧 `pytest-of-YS` 目录已移至外部备份的 `retired-main-test-caches`。

## 实现结果

- U1：`audit:baseline --check <base-ref>` 逐文件检查尺寸，包含新文件、旧文件与 Git 识别的重命名；CI 获取事件中的精确 base SHA 后执行同一入口。
- U2：14 个脚本类型的静态资料集中到低层表；图标接口、创建卡片顺序、搜索别名、标签色及 MFW 的领域所有权保持。
- U3：生成 33 条普通专项入口，保留 12 条 MFW 入口与 1 条养成入口。列表与创建流程共用具名跳转，MFW 创建后的 setup、history state、canonical query/hash 保持。
- U4：补充真实的新建与列表导航、账号编辑和刷新回读场景，复用配置来源卡片、计划表与养成流程。

唯一修改的 Vue 组件为 `Scripts.vue`：基线 995 行，最终 931 行。此项属于局部导航维护，未增加业务区域；保留其余职责与保存逻辑，仍为超限存量组件。没有新增 Vue 组件、样式系统、请求依赖或生成客户端改动。

## 已执行检查

下列 Yarn 命令在 `frontend/` 运行。

| 检查 | 结果及边界 |
| --- | --- |
| `yarn test --maxWorkers=4` | 48 个文件、264 项通过；涵盖公共保存与应用基础设施的既有测试 |
| 路由、分析事件和创建卡片的相关单元测试 | 通过；保护旧入口、标题、参数、排序、别名和有限事件属性，不启动 Electron 或游戏 |
| `node --test scripts/audit-baseline.check.mjs` | 6 组真实临时 Git 仓库检查通过；原脚本上旧报告通过、新门禁契约失败，新增门禁后通过 |
| `yarn audit:baseline --check 9aab1ff2b610be534a32d17a9a136acb01715398` | 检查 335 个 Vue 文件，0 处违反尺寸上限；不代表超限存量已清空 |
| `yarn lint` | 通过 |
| `yarn typecheck` | 通过；修正新增分析事件测试的路由 fixture 类型后重跑通过 |
| `yarn format:check` | 全量通过 |
| `yarn audit:i18n --check` | 通过；无缺译、源码缺 key 或占位符不一致 |
| `yarn e2e:check` | 通过；隔离启动器契约与 E2E 类型检查 |
| `yarn e2e --grep '@script-navigation'` | 1 条通过；真实新建、列表跳转、账号字段保存及刷新回读 |
| `yarn e2e --grep '@script-navigation\|@universal-plan\|@maa-cultivate-management'` | 计划表与养成 2 条通过；该轮导航测试暴露单选卡片重名定位，修正后以上一行的独立运行通过 |
| `yarn e2e --grep '@config-mode-cards'` | 1 条通过；General、MaaEnd、Whimbox 的语言、明暗与窄容器场景 |
| `yarn build --dir` | 通过；真实懒加载编译、Electron 编译和 Windows 未安装目录构建完成 |
| `yarn build` | 前端和 Electron 编译完成；NSIS 运行生成的辅助 EXE 时失败，约 120 秒后进程退出码为 null，完整安装包流程未通过 |
| 方案与 `AUDITING.md` 的 Markdown 检查 | 通过 |
| 工作流 Action 引用、`git diff --check` | 完整 SHA 固定检查及差异检查通过 |

首次浏览器运行暴露了测试定位问题：Ant Design 图标文字进入按钮可访问名称，且 General 同时是分组标题与选项标题。新导航测试按实际 radio 语义定位；复用计划表测试修正图标按钮定位及当前主题控件定位。未改变生产 UI 来迁就测试，未减少保存或刷新断言。

## 遥测与限制

独立代码审查已完成：正确性、对抗性、测试、结构与项目标准五个检查均无可行动问题。审查收据 `20261108-frontend-d3c66717` 已保存在上述外部备份目录的 `review/review.json`，完整安装包限制同样记录在收据中。

复用 `registerRouterAnalytics` 的 `screen_view` 观察者及创建流程的原结果所有者；路由种类来自实际登记。没有新增采集事件，也未放宽 `analyticsScriptType` 的有限白名单。单元测试确认输出中不包含脚本或账号标识。

浏览器场景使用隔离后端与合成数据，不证明真实游戏、模拟器、账号执行或安装后运行。未运行远程 CI；未创建提交、推送或 PR。此轮为用户不可见重构，未新增功能公告碎片，未来 PR 按方案使用 `skip-changelog`。

完整 NSIS 安装包构建未通过，不能将未安装目录构建成功表述为安装包验证成功。没有修改打包配置来绕过该失败；渲染构建仍报告调度模块同时静态和动态导入的提示，此轮未处理该无关入口。
