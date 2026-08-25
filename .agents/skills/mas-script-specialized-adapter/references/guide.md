# 专项适配 · 补充说明

主文档见 [SKILL.md](../SKILL.md)；架构线判据见 [script-frontend-architectures.md](./script-frontend-architectures.md)；实现规范见 [adapter-code-norms.md](./adapter-code-norms.md)。

本文件只补主文档没展开的两件事：为何以前端表面为专项单位、PR 拆分节奏。

## 为何以前端表面为专项单位

`ScriptType` 在后端对应 `app/task/<Name>/`，但在协作视角上贡献者主要新增/修改的是 Vue 表面，这些表面通过 Hub 分支与路由绑定到类型，形成稳定的「专项入口」：

```
用户操作 -> Scripts.vue (Hub) -> router -> EditView/* -> *UserEdit/*Section
                |
                +-> useScriptApi / useUserApi -> API -> config.py / task/Xxx
```

后端模块是实现细节：字段须与表单 `formData` 结构一致，但**不应先写 task 再补一个空壳前端**。反过来只改前端不落后端注册同样不完整——两侧应同 PR 打通。

## 交付前最小验收

- [ ] 写清减少了哪一段用户手工操作，或补足了哪项脚本缺口
- [ ] 每个新增字段和按钮都有实际运行时消费者，无只存在于 schema 或表单的假功能
- [ ] 脚本原生 / MAS 适配层 / MAS 补位三者 owner 已定，保存与恢复路径只有一个事实来源
- [ ] 补位能力有失败提示、可回退行为、结束清理；上游不支持时不会静默误报成功
- [ ] 跑了对应最小专项测试；无用户价值的额外测试和入口不随适配提交

## 推荐 PR 拆分

| 阶段 | 前端 | 后端 |
| --- | --- | --- |
| P0 | Hub + 路由 + Script/User Edit + Section 最小集 | 模型 + Manager + 注册表 |
| P1 | 计划表 / 队列 UI | plan / queue 分支 |
| P2 | 体验优化、预设、虚拟用户 | 可仅前端 |

## 参考 PR

[#133 MaaEnd](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133) ·
[#152 计划表](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152) ·
[#154 M9A](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154) ·
[727aafb SRC 风格](https://github.com/AUTO-MAS-Project/AUTO-MAS/commit/727aafbaf5e21fc81e85e795a5cd5b77ac508e60)
