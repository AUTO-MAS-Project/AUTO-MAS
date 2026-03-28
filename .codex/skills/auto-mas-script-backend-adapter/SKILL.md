---
name: auto-mas-script-backend-adapter
description: AUTO-MAS 脚本专项适配后端开发指引。用于编写或修改 MAA、SRC 及同类脚本接入相关后端代码，尤其适用于 app/task 下的 manager、AutoProxy、ManualReview、ScriptConfig、tools，以及 app/models/config.py、app/models/schema.py、app/core/task_manager.py 中与脚本类型接入、配置校验、运行流程、配置文件备份回滚、通知和结果汇总有关的逻辑；当需求聚焦脚本类型接入、用户级子任务或脚本运行配置闭环时使用。
---

# AUTO-MAS 脚本专项适配后端

当需求聚焦某一种脚本类型的接入、扩展或专项适配时，优先使用这个 skill，而不是泛化成普通后端修改。
默认把脚本接入视为一条完整链路：校验、准备、执行、汇总、通知、回滚。

## 快速开始

1. 先确认目标是新增脚本类型，还是修改现有 MAA / SRC / 通用脚本流程。
2. 先读 [`references/script-adapter-map.md`](./references/script-adapter-map.md) 确认模块关系。
3. 动手前用 [`references/adapter-checklist.md`](./references/adapter-checklist.md) 过一遍受影响环节。
4. 先找 manager，再顺着 `check()`、`prepare()`、`main_task()`、`final_task()`、`on_crash()` 读完整链路。
5. 修改后验证导入、状态同步、配置回滚和结果汇总是否仍然闭环。

## 常见任务

### 新增或扩展脚本类型

1. 参考现有 `app/task/MAA/manager.py`、`app/task/SRC/manager.py`、`app/task/general/manager.py` 的结构。
2. 明确该脚本类型支持的任务模式，并同步维护 `METHOD_BOOK` 或等效注册表。
3. 在 `check()` 中补齐路径、可执行文件、配置文件、模拟器和运行前置条件校验。
4. 在 `prepare()` 中处理配置锁定、用户配置加载、原始文件备份、运行依赖初始化。
5. 在 `main_task()` 中按用户或任务项组织执行。
6. 在 `final_task()` 中做解锁、汇总、通知、配置回滚和临时目录清理。
7. 在 `on_crash()` 中补齐状态落地、日志和前端错误反馈。

### 修改现有 MAA / SRC 逻辑

- 优先保持 manager 结构对称，避免相似流程持续分叉。
- 如果差异只在资源路径、文件名或校验条件，优先抽共性，再保留少量脚本特例。
- 即便需求只在单一脚本类型，也要回查 `app/core/task_manager.py`、schema、配置模型和结果汇总是否受影响。

### 修改用户级子任务

#### `AutoProxy`

- 关注自动执行主链路：用户级校验、启动环境、注入配置、运行脚本、监控日志、汇总结果、更新用户状态。
- 修改时同时检查 `ProxyTimes`、`LastProxyDate`、运行次数限制、通知汇总和 WebSocket 输出。
- MAA 与 SRC 在日志解析、配置写入和运行前错误处理上有差异，改动时不要只测一侧。

#### `ManualReview`

- 这是人工介入流程，核心在于发起提问、等待选择、落地结果，而不是全自动跑完。
- 修改时重点回查 `Broadcast` / WebSocket 交互、消息 ID、问题类型、超时或取消路径，以及确认结果如何写回用户和任务状态。

#### `ScriptConfig`

- 这是配置生成与回存流程，核心闭环是“停旧进程 -> 写配置 -> 启脚本 -> 回存配置目录”。
- MAA 主要关注 `gui.json`、`gui.new.json`，SRC 主要关注 `src.json`、`deploy.yaml`。
- 不要只改模板文件而漏掉备份、回滚、持久化路径或进程清理。

## 约束

- `check()` 返回的是面向用户和前端的错误信息，新增校验时要可读、可定位。
- `prepare()` 中的备份和回滚是关键安全措施，除非需求明确改变，不要删除。
- 修改用户筛选逻辑时，回查 `Status`、`RemainedDay` 等已有过滤条件。
- 修改任务状态时，保持 `script_info.status`、用户状态、WebSocket 推送和异常路径一致。
- 新增脚本类型时，同时检查 `app/core/task_manager.py`、`app/models/config.py`、`app/models/schema.py` 是否要同步扩展。
- 修改用户级子任务时，不要只盯当前文件；还要回查 manager 如何调度它，以及 `final_task()` 如何汇总它的结果。

## 验证

- 运行 `python -m compileall main.py app`。
- 至少验证目标脚本类型的 manager 和对应子任务模块仍能正常导入。
- 回查是否破坏既有 `AutoProxy`、`ManualReview`、`ScriptConfig` 流程。
- 如果改了备份或回滚逻辑，确认临时目录路径和清理流程仍完整。
- 如果改了通知或结果统计，确认 `final_task()` 仍输出完整汇总。
- 如果改了 `ManualReview` 交互，确认广播和 WebSocket 往返仍然可用。

## 参考

- 脚本适配结构图：[`references/script-adapter-map.md`](./references/script-adapter-map.md)
- 脚本适配检查清单：[`references/adapter-checklist.md`](./references/adapter-checklist.md)
