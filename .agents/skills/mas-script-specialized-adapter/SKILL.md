---
name: mas-script-specialized-adapter
description: >-
  Review, add, or refactor AUTO-MAS specialized script adapters by upstream
  architecture, including MAA, SRC, MaaEnd/MXU, General, ok-script
  adapters such as Okww and OkNte, multi-engine adapters such as HSR, and the
  one-dragon line such as BetterGI, as well as per-adapter issue-bundle
  exports. Use when lowering user setup friction, judging whether a change
  stays inside the black-box boundary (barrier first, then capability
  ownership), or changing ScriptType registration, task lifecycle, config
  ownership, ScriptConfig sessions, Desktop Session (桌面分身), Electron
  integration, frontend edit surfaces, and verification.
---

# 专项适配

只写核心红线和决策依据；字段名、文件位置和接口签名直接读源码确认。

## 两条硬红线

1. **先降配置门槛**：先消除安装、路径选择、首配和编排的手工步骤，不做运行时不消费的冗余面板。
2. **守住黑箱边界**（详见 [blackbox-boundary.md](references/blackbox-boundary.md)）：
   - 游戏内操作、任务成败、脚本配置语义优先复用上游入口；上游私有格式只透传，不反推上游内部状态。
   - 运行期写原生配置必须在任务结束时完整还原（成功/失败/取消/崩溃全路径），不能还原即越界。

## 新插件与界面架构（三层积木）

独立插件通过 `ScriptAdapterPlugin` + `ScriptTypeDecl` 注册，界面（托管 / 账号 / 计划及后续扩展面）统一按三层组合：

1. **`mascore` 预设块（`HostBlock`）**：优先复用宿主内置业务块（如 `game_binding`、`config_restore`、`native_session`、`webhooks`），零前端代码。
2. **MAS 可组合组件（`DeclarativeBlock`）**：在 `ConfigModel` 上用 `ui()` / `select()` / `table()` 组合声明式控件，零前端代码。
3. **完全下游自定义（`PluginBlock`）**：仅对声明式画不出来的局部高交互卡片随 wheel 交付前端产物，必须配 `fallbackGroups` 兜底；壳层、配置锁、保存由宿主托管。

- 新增或外迁专项**禁止**再往主仓加静态 `entry.ts` 或整页 Vue；插件文案走包内单源三语 `i18n/{zh-CN,en-US,ja-JP}.json`。
- 完整目录边界与联调命令见 `docs/plugin-development.md`；标杆实现直接读本地 `plugins/src_adapter`。

## 按需查阅的参考

- 代码约定：[adapter-code-norms.md](references/adapter-code-norms.md) · 架构分类：[script-frontend-architectures.md](references/script-frontend-architectures.md)
- 子能力：[logbox-api.md](references/logbox-api.md) · [ocr-tools.md](references/ocr-tools.md) · [config-archive.md](references/config-archive.md) · [config-restore.md](references/config-restore.md) · [issue-report.md](references/issue-report.md) · [desktop-session.md](references/desktop-session.md)
- 存量旧专项参考：`references/examples-*.md`（仅维护对应旧专项时按需读）。
- 联动 Skill：调度/锁 `mas-task-scheduler`；前端/UI `mas-frontend-standards` + `mas-frontend-ui`；配置 `mas-data-model`。

## 验收

1. 跑 `tests/AGENTS.md` 对应的最小测试；涉及真机/游戏流程按 `mas-e2e` 说明前置条件与证据。
2. **下游联调防漂移**：改动主仓插件协议、三层积木、声明式表单或 `plugins/auto_mas_core/` 时，必须同步跑通本地 `plugins/src_adapter/tests/` 与主仓插件 UI 测试（命令见 `docs/plugin-development.md`），并记录双方 commit SHA。
