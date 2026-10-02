# 案例：MaaEnd（MXU 线）

MaaFramework **PI V2** 生态 + **MXU 通用 GUI** 承载配置会话。落盘与字段现场读 `app/task/MaaEnd/` 与 `app/utils/constants.py` 确认。

## 两个上游的角色区分（最容易混）

| 上游 | 角色 |
| --- | --- |
| [MaaEnd](https://github.com/MaaEnd/MaaEnd) | 游戏侧 MaaFramework 项目本体，发行含 `MaaEnd.exe` 与资源 |
| [MXU](https://github.com/MistEO/MXU) | **PI V2 通用 GUI 客户端**（Tauri + React），解析 `interface.json`，用户配置在 `config/` |

MXU 可对接任意符合 PI V2 的 Maa 项目；本仓 `MaaEnd` 类型指「按已落地的 MXU 线对接 MaaEnd.exe 生态」。

**MAS 不实现识别节点，也不打包 MXU 应用**——只负责进程、目录、`mxu-*.json` 读写、`runtime_bridge`。任务逻辑在上游资源与 agent 中。

## 与 MFAA 线的分界（选型关键）

MFAA 线目前没有在役专项：M9A 原是这条线的例子，已并入 MFW，成为 MaaFW 的特调类型，不再是专项。下表右列是这条线的设计口径。

| 维度 | MXU 线（MaaEnd） | MFAA 线 |
| --- | --- | --- |
| 外置 GUI | MXU（Tauri + React，PI V2） | MFAAvalonia（Avalonia，C#） |
| 自动跑 | 在 `mxu-*.json` 写 autoRun 类字段再启 exe；可对照壳 CLI 决定是否拼启动参数 | 写任务 JSON 后启 exe，**不依赖 CLI 传队列** |
| 用户改配置 | **ScriptConfig 遮罩**拉起本体保存复杂项，其余 Section 写用户目录 / `runtime_bridge` | 仅 Vue + 后端写配置，**不调 Avalonia 壳做配置会话** |
| 用户页 | 遮罩 + 多 Section | 队列 + draggable，无典型遮罩 |

**新专项若外置 GUI 是 MFAAvalonia 而非 MXU，别套 MXU 遮罩流程**；带 `interface.json` 的项目先用通用 MaaFW 类型，见 [examples-m9a.md](./examples-m9a.md)。

## 落点线索（搜代码用）

- `config/mxu-MaaEnd.json`：MXU 侧实例配置，AutoProxy / ScriptConfig 读写。
- `__MXU_*` 任务名前缀（如 `__MXU_KILLPROC__`）：与 MXU 内置选项约定一致，常量集中在 `app/utils/constants.py`。
- `runtime_bridge`：运行前生成/同步外置程序所需配置。
- controller 类型（Win32 / ADB 等）要与表单、MXU controller 语义一致。

## 陷阱

- **上游发版后核对 `mxu-*.json` 字段与 `__MXU_*` 任务名是否变更**——协议漂移不会报错，会静默跑错任务。
- 配置遮罩语义与在 MXU 里手动改 `config/` 目的一致、入口不同；不要两边各写一份逻辑。
- 用户级配置与脚本级 `Default/ConfigFile` 的来源语义要与 MXU `config/` 对齐。

## 配置恢复接入要求

已接入通用配置恢复（mas/native 双池 + 快速配置侧车 + viewOnly 查看会话），机制见 [config-restore.md](config-restore.md)；后续改动**必须符合**：

- **三态池**：脚本态=共享 `Default`、用户态=独立目录、**直控无 MAS 配置目录**——mas 池对直控用户为空（列表空、恢复报错），native 池不受影响。
- **会话包络与运行下发同 owner**：`ScriptConfigTask` 的下发源/回写目标用 `maaend_mas_config_dir`（owner 制），session 前归档该目录；运行前归档在 AutoProxy `set_maaend`（直控跳过）。
- **快速配置覆盖层侧车**：任务开关/理智任务选项/送货/采集等字段存在 UserData.Task、运行时才覆盖进 mxu 配置——mas 池用侧车承载并回填表单（对齐 ok-ww）。
- **直控会话的保留判定**：manager `_keep_script_config_changes` 必须排除 viewOnly（查看结束还原任务前快照，不保留 GUI 写回）。
- **预览词表固化、零本体运行时依赖**：任务名/基质刷取模式/地区等标签取自上游源码 zh_cn 词表摘录（`locales/interface/zh_cn.json`、`tasks/*/*.json` 的 option cases），固化进 MAS 侧；**不要读本体资源或调本体加载器做预览**。任务名缺失回退 `customName` → 原名；目标武器名数量大且随版本漂移，展示已选数量。

## 同框架新专项

新游戏仍发布为 PI V2 + MXU 壳时：先确认外置 GUI 确实是 MXU → 读上游 `interface.json` / `config/` 说明 → 复制任务目录与表面、改 `ScriptType`、Hub、`mxu-*.json` 文件名常量 → 需要横切计划时再加计划表。

参考 PR：[#133](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133) 全量对接 · [#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152) 计划表 · [#165](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/165) hotfix
