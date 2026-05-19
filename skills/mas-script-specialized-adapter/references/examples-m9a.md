# 案例：M9A 专项适配

## 已合并 / 相关 PR

| PR | 状态 | 说明 |
|----|------|------|
| [#154](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154) | merged | 完整适配 M9A 模块 |
| [#183](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/183) | closed Draft | 用户编辑页体验优化、服务器适配、预设模板 |
| [#181](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/181) | closed Draft | 虚拟用户与自动更新 |

## #154 全量适配（摘要）

与 MaaEnd #133 同构，按 M9A 领域替换：

### 后端

- `app/task/M9A/`（或项目内实际目录名）：Manager、AutoProxy、ScriptConfig 等
- `M9AConfig` / `M9AUserConfig` + schema
- `SCRIPT_BOOK` / `USER_BOOK`、`task_manager` 注册
- 与 M9A 客户端/管线相关的配置同步逻辑（PR 描述中的 pipeline、任务队列 JSON）

### 前端

- `M9AScriptEdit.vue`、`M9AUserEdit.vue` 及 Section 组件：
  - `TaskQueueSection`、`TaskOptionRenderer`、`BasicInfoSection`、`NotifyConfigSection`
- `router`：`/edit/m9a`、用户 add/edit 路由
- `Scripts.vue`、`ScriptTable.vue`、`useScriptApi.ts`
- `assets/M9A.png`
- 队列相关：`QueueItemManager`、`TimeSetManager` 对 M9A 类型的支持

### 注意

- OpenAPI 模型文件为生成物，随后端 schema 变更后**重新生成**，不要手改。
- 若当前分支尚未包含 M9A，以 `main` 上 #154 合并提交为参照 cherry-pick 或对照 diff。

## #183 体验向增量（摘要）

在 #154 基础上：

- 用户编辑页 UI 重构（任务队列、选项渲染）
- 服务器/资源适配、账号切换
- 预设模板、虚拟用户方案（与 #181 相关）

**建议**：P0 先合 #154 形态的全量适配，体验类改动单独 PR，避免与 schema 大改交织。

## 与 MaaEnd 的差异点（规划新专项时）

| 维度 | MaaEnd | M9A（#154） |
|------|--------|-------------|
| 外部程序 | MaaEnd.exe + mxu 配置 | M9A 管线 / 任务队列配置 |
| 用户配置重心 | 协议空间、理智、登录 | 任务队列、选项渲染、多服务器 |
| 计划表 | 有 `MaaEndPlanConfig`（#152） | 按 PR 是否引入计划 consumer 而定 |
| UI 复杂度 | TaskConfig + 森空岛等 | TaskQueueSection 等 |

## 自检（M9A）

- [ ] 任务队列配置可持久化并在 AutoProxy 中消费
- [ ] 用户编辑页能表达 M9A 特有字段（非照搬 MaaEnd 表单）
- [ ] 队列/调度界面可选 M9A 脚本类型时不报错
