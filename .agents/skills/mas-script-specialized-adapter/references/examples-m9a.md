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

## 配置恢复接入要求（MFAA 线形态）

接入通用配置恢复（`app/utils/config_restore.py` + `/backup/*` 端点 + `ConfigRestoreSection.vue`，见 [config-restore.md](config-restore.md) §1.1.4）时，本线与目录型专项（MAA/MaaEnd）的形态差异必须遵守：

- **无 per-user ConfigFile 目录**：mas 池是**纯字段侧车**（Info 核心 + Task.Queue 原始值），无目录部分、无播种、恢复即回填 UserData；配置来源（Mode）只预览不回填。
- **无 ScriptConfig 遮罩会话**：不提供「查看详细配置」（onDetail 不传即不渲染按钮）——M9A.exe 打开即读盘自动执行，没有「打开 GUI 停留等人看」的受控入口；归档三时机缺「会话包络」时机，只有进入编辑页（native）/ 退出编辑页（mas）/ 任务前（native，manager prepare 换出后、instances 清理前，此刻 config/ 仍是完整现场）。
- **队列侧车双份**：原始 Queue JSON（回填用）+ 展示快照（归档时经 interface.json 翻译成中文文本，预览零本体依赖）；自描述值（selected_cases/输入值）不依赖定义直出，index 类选项缺定义时降级原始值不臆造。
- **native 预览全实例反读**：M9A GUI 的实例文件是 `instances/` 下**任意命名**（实测为哈希，`default.json` 只是 MAS 的注入模板之一，不能只认它），逐个反读、每实例一个折叠面板（ZzzOd 实例列表同语义，`a-collapse`）；**实例显示名取 JSON 内 `InstanceName`，文件名仅作缺失回退**——MaaFramework 线的实例文件名普遍不是显示名。每实例摘要行（服务器资源/已启用任务/账号/连接地址/控制器）+ 该实例任务配置详情都折在同一个面板里；config.json 全局设置不进预览。
- **恢复按钮挂任务队列区标题行**（该专项核心配置区）；副作用：直控模式下队列区随 `v-if` 隐藏，恢复入口一并不可见——产品上可接受，勿为此把按钮挪回全局位置。
- 运行不修改 MAS 用户字段（只写 Data.* 运行记录），mas 池无「运行前归档」必要；native 归档必须覆盖直控+快速配置写入前的现场。
