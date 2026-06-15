# AUTO-MAS Skills

本仓库是 AUTO-MAS 官方 Agent Skill 的权威来源。主程序仓库只保留最小
`AGENTS.md` 入口，并指向本仓库与文档站；不要在主程序仓库维护完整 Skill 副本。

## 仓库分工

- 主程序：<https://github.com/AUTO-MAS-Project/AUTO-MAS>
- 开发文档与贡献规范：<https://doc.auto-mas.top/developer/>
- Agent Skill 与工程规则：<https://github.com/AUTO-MAS-Project/skills>

分支、提交信息、版本记录、Issue/PR 正文规范以文档站为准。代码风格、模块边界、
数据模型、API 契约、专项适配等 Agent 执行规则以本仓库的 `mas-*` Skill 为准。

## 已有 Skill

- `mas-skills`：统一入口，用于按任务类型分发并组合后端规范类 skill。
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

## 主程序仓库中的本地副本

主程序仓库不应提交完整 `skills/` 副本。若开发者在本地把本仓库检出到主程序目录旁边，
该检出仅作为本地缓存；规则冲突时以本仓库最新内容为准。
