# AUTO-MAS Skills

本目录是 AUTO-MAS 主程序仓库的附属 Agent Skills，用于沉淀本项目的 Agent
执行规则、工程约束和任务路由。主入口为仓库根目录 `AGENTS.md`，工程规则入口为
`mas-skills/SKILL.md`。

## 规则分工

- 开发文档与贡献规范：<https://doc.auto-mas.top/developer/>
- Agent Skill 与工程规则：本目录 `.agents/skills`

分支、提交信息、版本记录、Issue/PR 正文规范以文档站为准。代码风格、模块边界、
数据模型、API 契约、前端规范、专项适配等 Agent 执行规则以本目录的 `mas-*` Skill 为准。

## 已有 Skill

- `mas-skills`：统一入口，用于按任务类型分发并组合工程规范类 Skill。
- `mas-frontend-standards`：用于约束 Vue 3、TypeScript、Vite、Electron renderer、路由、API composable、状态、样式、表单与前端验证。
- `mas-frontend-ui`：用于约束 Ant Design Vue UI、桌面端业务布局、视觉 token、表单、表格、弹窗、反馈、拖拽与深色模式。
- `mas-api-contract`：用于约束 FastAPI 接口与 WebSocket 的请求、响应和错误契约。
- `mas-data-model`：用于规范后端数据模型的结构、类型、默认值和兼容性演进。
- `mas-function-design`：用于规范后端函数的职责划分、参数设计、返回约定和副作用控制。
- `mas-module-boundary`：用于约束后端模块分层、依赖方向和代码归属边界。
- `mas-code-standards`：用于应用 AUTO-MAS 的代码规范，规范内容主要从 `DLmaster_361` 在 `dev` 上的代表性提交中提炼，尤其适用于 Electron 初始化与服务层代码。
- `mas-schema-naming`：用于统一后端 schema 的命名方式，减少字段语义漂移。
- `mas-script-specialized-adapter`：用于新增或维护专项脚本适配，按脚本前端架构线完成问诊、前端表面与后端任务接入。
- `mas-plan-schedule`：用于新增、重构或审查计划表类型与调度配置。
- `grill-me`：用于对方案做高强度问诊，不属于 AUTO-MAS 工程规则 hub 的默认路由。

## 使用方式

1. AUTO-MAS 开发任务先读 `mas-skills/SKILL.md`。
2. 按任务意图选择最小必要的子 Skill。
3. 若任务涉及贡献流程、分支、提交、PR/Issue 正文或版本记录，回到文档站确认。
4. 若任务涉及主程序代码，仍需在主程序仓库中查看相邻实现并遵守本地风格。
