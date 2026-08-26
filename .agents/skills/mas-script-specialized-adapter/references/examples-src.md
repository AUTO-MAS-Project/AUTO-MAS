# 案例：SRC 线（Alas / SRC 系）

上游参照 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) 一类基于 Alas 框架的脚本。AUTO-MAS 面向「由 MAS 拉起、监控日志的 SRC 兼容可执行体」，**不在本仓复刻其 `webapp` 配置界面**，但对接排障时应理解其框架习惯。

文件与字段现场读 `app/task/SRC/` 与 `views/SRCUserEdit/` 确认。

## 线内特征

无 MAA/MaaEnd 式全屏配置遮罩，无 M9A 式队列 JSON 编辑，无专用计划表；侧重 **exe 路径、模拟器、Stage、通知**。脚本页是**单文件大表单**风格（`form-section` + 字段 `@blur` 保存）——**不急于拆文件，真放不下再拆**。

## 新游戏是否要新建 ScriptType（关键判据）

| 情况 | 决定 |
| --- | --- |
| 与现有 SRC 配置 schema、任务语义**一致** | 继续用 `ScriptType === 'SRC'` |
| 配置模型或任务模式**分叉** | 新建 `ScriptType` + 复制 `app/task/SRC/` 骨架 + 新 EditView，仍走 SRC 线表面模式 |
| 出现**强队列 + 管线**语义 | 重新评估是否该归 **MFAA 线**，别硬塞进 SRC Section |

新专项前必问：可执行体是否共用同一套 schema？是否需要 `METHOD_BOOK` 之外的新任务模式（需要则同步扩展前端任务模式选项与展示文案常量）？模拟器/登录/包名是否与现有常量冲突？用户侧是否仍只需 BasicInfo + Stage + Notify？

## 上游概念对照（心智模型，非文件映射）

| 上游 | MAS 侧关注点 |
| --- | --- |
| `tasks/` `module/` `route/` 任务调度 | `AutoProxy` 主循环、任务模式、`METHOD_BOOK` |
| `webapp/` 或 GUI 配置 | **不复刻**；由编辑页写回 config |
| `config/` 与运行数据目录 | 与配置任务、用户目录读写路径对齐，遵守 `data/{scriptId}/...` 约定 |
| 模拟器 + 包名/进程 | 模拟器字段 + `manager.check()`；业务常量集中在 `app/utils/constants.py` |

## 必守不变量

- `check()` 的前置条件（任务模式在 `METHOD_BOOK` 内、配置类型正确、**模拟器 Id/Index 必填**）要与前端表单**同步**——新接入的 Alas 系脚本同理。
- 复制任务目录时保留 `METHOD_BOOK` 形状，除非明确要删模式。
- Section 通过 `emit('save')` 聚合写库，**不在 Section 内散落 API 调用**。
- Hub / 路由 / `useScriptApi` 分支补全（见 [架构线判据 · 前端表面通用约定](./script-frontend-architectures.md#前端表面通用约定)）。
