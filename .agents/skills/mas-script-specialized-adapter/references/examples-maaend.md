# 案例：MaaEnd（MXU 线）

MaaFramework **PI V2** 生态 + **MXU 通用 GUI** 承载配置会话。落盘与字段现场读 `app/task/MaaEnd/` 与 `app/utils/constants.py` 确认。

## 两个上游的角色区分（最容易混）

| 上游 | 角色 |
| --- | --- |
| [MaaEnd](https://github.com/MaaEnd/MaaEnd) | 游戏侧 MaaFramework 项目本体，发行含 `MaaEnd.exe` 与资源 |
| [MXU](https://github.com/MistEO/MXU) | **PI V2 通用 GUI 客户端**（Tauri + React），解析 `interface.json`，用户配置在 `config/` |

MXU 可对接任意符合 PI V2 的 Maa 项目；本仓 `MaaEnd` 类型指「按已落地的 MXU 线对接 MaaEnd.exe 生态」。

**MAS 不实现识别节点，也不打包 MXU 应用**——只负责进程、目录、`mxu-*.json` 读写、`runtime_bridge`。任务逻辑在上游资源与 agent 中。

## 与 MFAA 线（M9A）的分界（选型关键）

| 维度 | MXU 线（MaaEnd） | MFAA 线（M9A） |
| --- | --- | --- |
| 外置 GUI | MXU（Tauri + React，PI V2） | MFAAvalonia（Avalonia，C#） |
| 自动跑 | 在 `mxu-*.json` 写 autoRun 类字段再启 exe；可对照壳 CLI 决定是否拼启动参数 | 写任务 JSON 后启 exe，**不依赖 CLI 传队列** |
| 用户改配置 | **ScriptConfig 遮罩**拉起本体保存复杂项，其余 Section 写用户目录 / `runtime_bridge` | 仅 Vue + 后端写配置，**不调 Avalonia 壳做配置会话** |
| 用户页 | 遮罩 + 多 Section | 队列 + draggable，无典型遮罩 |

**新专项若外置 GUI 是 MFAAvalonia 而非 MXU，别套 MXU 遮罩流程**，改看 [examples-m9a.md](./examples-m9a.md)。

## 落点线索（搜代码用）

- `config/mxu-MaaEnd.json`：MXU 侧实例配置，AutoProxy / ScriptConfig 读写。
- `__MXU_*` 任务名前缀（如 `__MXU_KILLPROC__`）：与 MXU 内置选项约定一致，常量集中在 `app/utils/constants.py`。
- `runtime_bridge`：运行前生成/同步外置程序所需配置。
- controller 类型（Win32 / ADB 等）要与表单、MXU controller 语义一致。

## 陷阱

- **上游发版后核对 `mxu-*.json` 字段与 `__MXU_*` 任务名是否变更**——协议漂移不会报错，会静默跑错任务。
- 配置遮罩语义与在 MXU 里手动改 `config/` 目的一致、入口不同；不要两边各写一份逻辑。
- 用户级配置与脚本级 `Default/ConfigFile` 的来源语义要与 MXU `config/` 对齐。

## 同框架新专项

新游戏仍发布为 PI V2 + MXU 壳时：先确认外置 GUI 确实是 MXU → 读上游 `interface.json` / `config/` 说明 → 复制任务目录与表面、改 `ScriptType`、Hub、`mxu-*.json` 文件名常量 → 需要横切计划时再加计划表。

参考 PR：[#133](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133) 全量对接 · [#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152) 计划表 · [#165](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/165) hotfix
