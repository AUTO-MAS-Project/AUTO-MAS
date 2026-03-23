---
name: auto-mas-backend-dev
description: AUTO-MAS 项目后端开发指引。用于修改 main.py、app/api、app/core、app/services、app/models、app/task、app/utils 中的后端代码，尤其适用于 FastAPI 路由、Pydantic 数据模型、任务调度、配置持久化、WebSocket 通信、后端排障与重构；当需求涉及后端分层归属、接口契约、运行时状态流转或配置读写一致性时使用。
---

# AUTO-MAS 后端开发

按 AUTO-MAS 现有分层和运行方式开发，不要把仓库当成普通 FastAPI 示例项目处理。
涉及跨模块行为时，先看引用资料，再决定改动落点。

## 快速开始

1. 先判断问题属于接口层、模型层、编排层、脚本运行层还是通用工具层。
2. 先读 [`references/backend-map.md`](./references/backend-map.md) 确认模块职责。
3. 涉及 API 契约、任务生命周期、配置落盘时，再读 [`references/dev-workflow.md`](./references/dev-workflow.md)。
4. 只改最小且完整的一组文件，避免把同一行为拆散到多处半改。
5. 完成后做针对性验证，再汇报结果和未验证风险。

## 常见任务

### 修改 HTTP / WebSocket 接口

- 在 `app/api/` 中实现或调整路由。
- 在 `app/models/schema.py` 中补齐请求体、响应体和状态字段。
- 新增路由模块时，同时检查 `app/api/__init__.py` 和 `main.py` 是否需要注册。
- 保持现有 `OutBase` / `...Out` 返回风格一致。
- 如果该能力也会被 WebSocket 命令触发，同时检查 `app/api/ws_command.py` 和对应广播逻辑。

### 修改任务调度或运行时状态

- 先读 `app/core/task_manager.py`，再进入 `app/task/` 下的目标实现。
- 将 `app/core/config.py` 视为共享状态与持久化枢纽。
- 修改状态流转时，保留现有 WebSocket 推送、通知、副作用和落盘行为。
- 遇到脚本类型分支时，同时确认 `Maa`、`Src`、`General`、`MaaEnd` 等路径是否需要同步。

### 修改配置或持久化逻辑

- 先确认字段定义位于 `app/models/config.py` 还是 `app/models/schema.py`。
- 再检查 `app/core/config.py` 中的读取、保存、迁移、广播流程。
- 默认兼容已有数据和配置文件，不要破坏历史版本的读取路径。

## 约束

- 优先遵守现有分层：`app/api` 负责传输，`app/services` 负责服务副作用，`app/core` 负责全局编排，`app/models` 负责数据模型，`app/task` 负责脚本运行时逻辑，`app/utils` 负责通用工具。
- 即使现有风格不完全标准，也优先保持仓库内一致性。
- 默认这是 Windows 优先项目，避免引入仅适用于 Linux 的路径、命令或进程假设。
- `main.py` 包含管理员提权和应用生命周期初始化；涉及启动流程时要额外谨慎。
- 如果不确定一个行为从哪里触发，先搜索 WebSocket 广播点和 `Config` 写入点，再决定改动位置。

## 验证

- 结构性 Python 改动后运行 `python -m compileall main.py app`。
- 涉及启动、路由注册、schema 变更时，补做目标模块导入或最小调用验证。
- 涉及运行时文件时，同时检查仓库根目录下 `debug/`、`data/`、`config/` 的副作用。
- 未实际启动并验证成功前，不要声称后端已经完整跑通。

## 参考

- 架构和模块边界：[`references/backend-map.md`](./references/backend-map.md)
- 实施流程和验证顺序：[`references/dev-workflow.md`](./references/dev-workflow.md)
