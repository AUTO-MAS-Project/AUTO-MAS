# Issue / Pull Request 指南

本文件面向终端用户、社区贡献者与 AI 助手。AI 助手可以按用户要求撰写
Issue / Pull Request 正文，但正文必须遵守下列内容边界；发布 Issue / PR
仍需用户明确授权。

## Issue

提交 Issue 时，请优先描述用户可观察到的问题或需求：

- 你想完成什么，或遇到了什么现象。
- 实际结果与预期结果分别是什么。
- 复现步骤、截图、日志或环境信息；无法稳定复现时说明触发条件。
- 若是功能建议，说明使用场景与期望体验。

Issue 不需要提供实现方案、API/Schema 设计、代码路径、行号、冗长验收清单或
“供开发参考”类元评论。

## Pull Request

- 外部贡献者应在自己的 fork 中从上游 `dev` 拉出开发分支。
- PR 目标选择 `AUTO-MAS-Project/AUTO-MAS:dev`。
- 不要向 `main` 发起 PR；`main` 仅用于维护者从 `dev` 发布。
- `release/{version}` 通常由发布流程和 cherry-pick 维护，外部贡献者不要直接改。
- 用户可见变更需要同步更新 `res/version.json`。
- 后端 schema 变更后，用生成器更新前端 API 代码；不要手改 OpenAPI 生成文件。

PR 正文建议保持简洁：

```md
## 摘要
-

Closes #
```

摘要通常 1 到 4 条即可。若没有关联 Issue，可以删除 `Closes #` 行。

AI 助手撰写 PR 正文时，不要编造测试结果、性能数据或审核结论；未运行的检查应如实标注未运行。
