# AUTO-MAS v6 Claude Code 长期规则

## 执行环境

- 当前系统为 Windows。
- 默认终端必须使用 PowerShell 7（pwsh），禁止使用 Windows PowerShell 5.1。
- 所有终端命令必须采用 PowerShell 语法，禁止输出或执行 Bash、sh、zsh 专用命令。
- PowerShell 7 可执行文件优先使用 `pwsh.exe`。
- 所有源码、配置、日志和文档统一使用 UTF-8。
- 禁止使用依赖 Bash 的 `rm -rf`、`cp -r`、`export`、`grep`、`sed` 等命令。
- 对应操作使用 `Remove-Item`、`Copy-Item`、`$env:NAME=...`、`Select-String` 或 `rg`。
- 执行命令前确认当前 PowerShell 主版本至少为 7。

## 每次开始必须读取

- D:\AM6-Handoff\GOAL.md
- D:\AM6-Handoff\ROOT_WORKSPACE_AGENTS.md
- D:\AM6\AGENTS.md
- D:\AM6\PROGRESS.md（存在时）

长期目标以 `D:\AM6-Handoff\GOAL.md` 为准。

## 长期执行要求

持续实际修改、测试和修复，不要只做分析或方案。

优先顺序：

1. 完成 UI 与现有功能收口。
2. 修复功能性和生产错误。
3. 完成 WebSocket v2 全量迁移。
4. 完成 Config v2 全量迁移。
5. 最后处理安全、格式和发布收尾。

不得覆盖或丢弃现有修改，不得 commit、push、reset、stash。
当前禁止生成 Alpha 包。

每完成一组工作，更新 `D:\AM6\PROGRESS.md`，记录：

- 已完成内容
- 修改文件
- 验证命令和结果
- 当前问题
- 未完成事项
- 下一步动作

更新完成后继续推进，不要把一次回复结束视为长期目标完成。
