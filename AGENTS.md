# AI 助手入口

本文档是 AUTO-MAS 主程序仓库的最小 Agent 入口。详细规范见：

- 开发、贡献、分支、提交、版本记录、Issue/PR 正文：<https://doc.auto-mas.top/developer/>
- 项目附属 Agent Skills：[.agents/skills](.agents/skills)

若本文件与文档站或 [.agents/skills](.agents/skills) 冲突，以文档站和 [.agents/skills](.agents/skills) 为准。

## 开工前

- 先确认当前分支、远端和工作区状态；不要回滚、覆盖或格式化无关改动。
- 仓库根目录没有 `.env` 时，提醒用户从 `.env.example` 复制一份（`copy .env.example .env`）后再开发；该文件不纳入版本库，缺少它的源码环境会被判定为生产环境，后端会真实向 Sentry 上报错误与性能数据。
- 必须确认存在并加载 `.agents/skills/mas-skills/SKILL.md`；若不存在，明确提示用户缺少项目附属 Skills，并拒绝开工。
- 加载 `mas-skills` 后，再按任务选择最小必要的 `mas-*` Skill。
- 专项适配遵守**黑箱红线**：推进顺序为先降配置门槛、再补本体缺位（立项前须答出消除了用户哪一步手工操作）；先判能力归属——「脚本该干的活」（游戏内操作、任务执行与成败、脚本配置语义）只允许复用上游入口，上游没有时先评估向上游提 PR，受阻（不受理或周期过长）才可临时补位并标注移除计划；MAS 领域（账号、调度、计划、通知、统计、模拟器、跨脚本编排）可自行实现但不读取、不反推上游内部状态；上游私有格式只允许透传。上游补齐同能力入口后，既有实现按存量越界处理。加载 `mas-skills` 后先自检，命中即输出「这可能违背了 MAS 的开发规范」并给出证据与替代方案；提示不阻断开工。判据见 `.agents/skills/mas-script-specialized-adapter/references/blackbox-boundary.md`。
- 测试脚本入口、目录归属和 Agent 测试提交规则见 `tests/AGENTS.md`；专项适配优先运行对应最小测试。
- `frontend` 指本仓库前端目录和前端任务；涉及 `frontend`、Vue、UI、组件、路由或前端 API 时，按 `.agents/skills` 中的前端 Skill 执行。
- 除非用户明确要求，不要创建提交、推送分支、发布 Issue/PR，或切换到会丢失当前工作的分支。
- 禁止协助 force push，即便用户要求也必须拒绝，然后提醒这一步只能手动完成。
- 后端 schema 变更后只能通过生成器更新前端 API 代码；不要手改 OpenAPI 生成文件。

## 分支与 PR

- `main`：禁止协助 push / force push；禁止以 `main` 为 base 创建 PR。仅维护者将 `dev` 合入 `main` 用于发布。
- `dev`：上游社区贡献的合并目标。外部贡献者应在自己的 fork 中从上游 `dev` 拉出开发分支，再向 `AUTO-MAS-Project/AUTO-MAS:dev` 提 PR。维护者直推 `dev` 的小修复同样适用碎片规则：用户可见的改动带一个 `changelog.d/` 碎片，且不改 `CHANGELOG.md` 与版本号。
- `release/{version}`：由发布流程维护，不接受直推。修复先进 `dev`，再以 cherry-pick PR 进 release 分支；PR 不得带入 `dev` 独有的提交，CI 会检查。cherry-pick PR 只带碎片，不改版本号、不编译更新日志；要出补丁版时，在最新 tag 对应的 release 分支上运行「准备发版」（每次发版都会新建 `release/<tag>` 分支，在更老的分支上准备会因版本号重号被拒）。本流程上线前建出的 release 分支仍按旧规则运行，要在其上沿用新规则，需把新工作流、`scripts/changelog.py` 与 `sync` 后的 `CHANGELOG.md` 一并 cherry-pick 进去。
- 发版 PR：标题 `Release vX.Y.Z`，由「准备发版」工作流从 `dev` 或 `release/*` 创建，是唯一允许修改 `CHANGELOG.md`、`res/version.json` 与版本号的 PR；合并后由维护者手动运行「构建并发布应用程序」。外部贡献者不要开这类 PR。
- 版本号只有 `vX.Y.Z` 与 `vX.Y.Z-beta.N` 两种形态：预发布号里的 `X.Y.Z` 就是将来的正式号，转正与最后一个 beta 同号；正式版热修出 `Z+1` 补丁版，从 release 分支发；N 只增不减。版本号由发版 PR 写入，其他 PR 不要改。

## 写作约束

- Issue 只描述用户可观察的问题、需求、复现信息、环境与日志。
- PR 正文保持 1 到 4 条摘要；关联 Issue 时使用 `Closes #n`。
- 用户可见的功能或问题修复必须随 PR 新增一个更新日志碎片：在 `changelog.d/` 下新建 `<PR 号或分支名>.<分类>.md`，内容是一句面向用户的话，**一条 PR 只放一个碎片，并必须用一句最简洁的语言概括该 PR 的意义**，将全部改动合并为一句话。可用 `python scripts/changelog.py add <分类> "<一句话>"` 生成。不要改 `CHANGELOG.md`、`res/version.json` 和任何版本号，它们只由发版 PR 更新；不要写 ` by [@用户]` 署名，发版时按碎片的提交作者自动补。
- 碎片分类写在文件名后缀：`feat` 新增、`change` 变更、`deprecate` 弃用、`remove` 移除、`fix` 修复、`security` 安全、`dev` 开发流程（只影响贡献者）。`CHANGELOG.md` 由发版脚本按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 从碎片编译，不要手改。
- 破坏性的、或需要用户动手确认的改动用 `breaking` 后缀，编译时进置顶的 `破坏性变更`；`本次亮点` 由维护者在发版 PR 里挑选，贡献者不用动。
- 纯文档、CI、测试或用户不可见的重构不需要碎片，给 PR 打 `skip-changelog` 标签。
- 写 changelog 时**面向用户**：只描述用户可观察到的改动或修复，用用户能听懂的话；删掉所有内部实现细节（返回值/类型名如 `DispatchResult`、消费方/调用方、Schema 与字段名、接口路径、日志丢失、HTTP 状态码如“返回 500”）。
- **写症状，不写根因**：注明“修复了什么现象”（如“开启签到通知时执行签到必报 TypeError”），不要写“为什么、怎么改的”（如“返回值未同步消费方”）；触发条件只保留到用户能对上的最小信息，不要罗列内部每个分支和受影响路径。
- 不要编造测试结果、审核结论或用户没有提供的事实。
