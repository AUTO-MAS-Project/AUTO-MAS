# 案例：M9A（MFAA 线）

以 **MaaFramework 管线 + 任务队列** 为核心。字段与文件现场读 `app/task/M9A/` 与 `views/M9AUserEdit/` 确认。

## 两个上游的角色区分

| 上游 | 角色 |
| --- | --- |
| [M9A](https://github.com/MAA1999/M9A) | 游戏侧 MaaFramework 项目本体（管线、资源、agent） |
| [MFAA / MFAAvalonia](https://github.com/trler/MFAA) | MaaFramework 通用 GUI（Avalonia / C#），`interface.json` 声明 resource / task / controller |

**MAS 不重复实现识别节点，也不嵌入 Avalonia 运行时**——只负责拉起、目录、日志、队列消费。Vue 表面独立实现，字段与后端配置一致即可。

排障时勿与 `MaaEnd`（MXU 线）混淆。

## 本线最关键的一条：不靠 CLI 传队列

MFAA 形态**通常不把「本次要跑的任务队列」托付给一条启动参数**。编排靠：

1. **写盘**：启动进程前把队列、模拟器等写入助手目录下的运行 JSON。
2. **启动**：`open_process(exe)`，无额外 CLI（或仅环境/路径类，以上游 README 为准）。
3. **自动跑**：助手程序内部读取已写入的配置后进入执行。

**用户改配置在 MAS 自己的编辑页完成，不走 ScriptConfig 全屏拉起 MFAAvalonia 点保存。** 新专项若属本线，别硬套「命令行自启 + 调本体 UI 保存」。

外置 GUI 若改为 MXU（Tauri + React）而配置模型不同，重新评估是否更接近 **MXU 线**（见 [examples-maaend.md](./examples-maaend.md)）。

## 上游 interface.json 与 MAS 侧的语义对齐

表达层不同、语义同构，设计任务列表 UI 与默认值时对照：

| `interface.json` | MAS 侧 |
| --- | --- |
| `task[]` 的 `name` / `entry` / `default_check` / `repeatable` / `repeat_count` | 可选任务元数据；勾选与默认选中 |
| 任务**顺序**（列表顺序） | 队列 JSON + 队列 Section + draggable |
| `resource[]` 多服路径叠加 | 脚本/用户目录、资源根路径 |
| `controller[]`（Adb / Win32 等） | 模拟器与连接方式，与 `check()` 的 ADB 分支一致 |
| `focus` 日志/节点事件协议 | 以 `LogMonitor` + 前端 message 为主，**不必复刻富文本日志格式**，但阶段语义应对齐 |

## 陷阱

- **任务队列 JSON 与前端队列项类型必须严格对齐**；上游任务入口 `entry` 变更时须回归。
- **上游发版后核对任务渲染与默认队列是否需同步**（资源/任务名变更不会报错）。
- 拖拽排序后要清理状态（历史上出过 bug）。
- 队列持久化与 AutoProxy 消费两端要对得上，只改一端会静默跑错任务。

## 同框架新专项

仍为 MaaFramework + 任务队列 JSON → 复制本线：复制任务目录与表面、改 `ScriptType` / Hub / 类型声明；schema 变更后重新生成 OpenAPI，**勿手改生成模型**。脚本级字段少时可保持薄 ScriptEdit。

参考 PR：[#154](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154) 全量表面 + 后端（体验类改动宜单独 PR）
