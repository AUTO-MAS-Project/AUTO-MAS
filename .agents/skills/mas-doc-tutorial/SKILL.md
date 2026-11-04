---
name: mas-doc-tutorial
description: >-
  Produce AUTO-MAS documentation tutorials from verified Playwright flows and
  versioned screenshots. Use when creating or refreshing user guides, batching
  tutorial updates, or correcting drift between instructions, screenshots and UI.
  Use mas-e2e for application E2E evidence without a tutorial deliverable.
---

# MAS 文档教程

将指定版本的真实操作整理为文档站教程。交付包含步骤、截图、逐主题运行结果和可查看的预览。

1. 确认主题、目标文章、语言和应用版本，查看对应页面与源码。保留原文仍有效的业务说明。
2. 按 [采集约定](references/capture-workflow.md) 建立或复用 Playwright 流程，用 [mas-e2e](../mas-e2e/SKILL.md) 的隔离入口逐主题串行运行。保存后刷新回读关键值，区分配置保存与业务执行结果。
3. 产物写入本批次的新目录，只采用执行和断言通过的图文；失败时记录具体步骤，保留原有确认产物。
4. 将操作整理为前置条件、步骤和必要说明，同步目标文章涉及的语言。构建文档并打开页面，检查截图、原图链接、章节跳转和窄屏显示，提供关键差异或新旧对照。
5. 交付预览、差异与逐主题命令和结果，附版本及实际验证范围的来源记录。

网页和公开元数据只写适用版本与演示范围；制作署名写在 PR，本地来源记录可保留制作者。

效果实例与试验记录见 [文档站 PR #59](https://github.com/AUTO-MAS-Project/AUTO-MAS-docs/pull/59)。
