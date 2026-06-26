# MaaFW 通用适配需求对齐

本文记录 MaaFW 通用适配本轮需求。目标是在实现前先把边界、行为和待决问题对齐清楚。

## 目标

- MaaFW 脚本按 MaaFramework Project Interface 读取本地项目能力。
- M9A、识宝小助手 Maa_bbb，以及后续同类 MaaFW 项目尽量走同一条通用线。
- 本轮运行支持范围只做 ADB / 模拟器部分；PC / PlayCover 先记录方向，不做可运行承诺。
- 账号 / 密码栏对齐其他专项作为用户记录字段，不驱动 MaaFW 任务队列。
- 任务参数传递只通过任务自己的 option 编辑器完成。
- 更新接入 MirrorChyan / GitHub，但仓库地址、RID、当前版本从脚本本地 interface 读取，不让用户手填仓库地址。

## 已观察到的脚本现状

### M9A

- 本地下载目录 `M9A-win-x86_64-v3.22.1` 的 `resource/tasks/SwitchAccount.json` 是旧版：
  - 有 `切换账号` 任务。
  - 没有 `option`。
  - 行为是脚本原生的“切到最后一个账号”，AUTO-MAS 不做目标账号联动。
- M9A 最新发布版 `v4.0.0` 的 `SwitchAccount.json` 已支持目标账号：
  - `option`: `目标账号(可选)`。
  - input 字段: `账号`。
  - `pipeline_override` 将 `{账号}` 写入 `SwitchAccountSelect.custom_action_param.account`。
  - 当前没有密码 option。
- M9A 的 `interface.json` 提供：
  - `version`
  - `github`: `https://github.com/MAA1999/M9A`
  - `mirrorchyan_rid`: `M9A`
  - `mirrorchyan_multiplatform`: `true`
  - controller 包含 `ADB` / `PC` / `PlayCover`
  - 多个 resource/client，其中部分 resource 支持 ADB。

### Maa_bbb / 识宝小助手

- 发布包 `Maa_bbb-win-x86_64-v1.12.5` 的 `interface.json` 提供：
  - `version`: `v1.12.5`
  - `github`: `https://github.com/miaojiuqing/MAA_bbb`
  - `mirrorchyan_rid`: `Maa_bbb`
  - `mirrorchyan_multiplatform`: `true`
  - controller 包含 `桌面端` Win32 与 `安卓端` Adb。
  - ADB resource 包含 `官服`、`B服`、`OPPO渠道服`、`华为渠道服`、`应用宝渠道服`、`VIVO服`、`九游服`、`小米服`。
- 源码仓库里的 `assets/interface.json` 可带注释且 `version` 可能为空；运行和更新应以实际应用目录里的 interface 为准。
- Maa_bbb 自身配置里有 `Update.resource_update_channel`、`force_github`、`github_api_key`、`cdk` 等字段，但 AUTO-MAS 通用 MaaFW 适配应优先用自己的脚本配置承载更新选择，不直接依赖脚本 GUI 的配置文件。

## 脚本配置页

- 脚本页选择 MaaFW 项目目录，读取实际目录下的 `interface.json` / `interface.jsonc` 及其 `import`。
- 本轮只显示 ADB 相关 controller/resource。
- 如果脚本只有 PC / PlayCover，没有 ADB：
  - 允许保存脚本配置。
  - 运行前提示当前通用 MaaFW 只支持 ADB / 模拟器，脚本暂不可运行。
- 如果脚本同时声明 ADB / PC / PlayCover：
  - 只显示 ADB 可用项。
  - PC / PlayCover 不显示为可选运行目标，避免误以为已支持。
- 脚本页保留 resource/client 选择，只列出支持当前 ADB controller 的 resource。
- 一个 MaaFW 脚本配置只控制一种客户端/resource 和一个模拟器实例。
- 模拟器选择放在脚本页：
  - 用户页不再配置 ADB。
  - 不提供手动 ADB 地址输入。
  - 运行时从 MAS 模拟器管理拿 ADB 地址。
- 多开建议：
  - 推荐用户使用不同目录下的 MaaFW 脚本副本。
  - 同一路径下多条配置可能共享日志、缓存或运行文件，不能保证并发安全。

## ADB 与模拟器联动

- MaaFW ADB 完全联动 MAS 模拟器管理：
  - 运行前通过 MAS 现有接口启动 / 打开模拟器并等待 ADB。
  - 已启动则复用。
  - 运行后是否关闭模拟器走 MAS 现有用户 / 任务配置能力。
- 不让用户手动填写 ADB 地址或 emulator extra。
- LDPlayer / MuMu 传 MaaFW extra：
  - LDPlayer: `extras.ld.enable/index/path/pid`
  - MuMu: `extras.mumu.enable/index/path`
  - 其他模拟器不传 extra，只传基础 ADB 连接信息。

## 同路径防重入

- 同一路径 MaaFW 脚本已有运行任务时，再次启动同一路径任务直接跳过。
- “同一路径”按脚本根目录规范化比较：
  - 绝对路径
  - Windows 大小写不敏感
  - 去除末尾斜杠
- 不同目录副本允许并行。
- 跳过时需要在日志 / 任务状态中说明：同一路径脚本正在运行，已跳过。

## 用户页

- 用户页顶部账号 / 密码栏始终显示并可填写。
- 账号 / 密码仅用于 AUTO-MAS 记录：
  - 不自动勾选任务。
  - 不自动置顶任务。
  - 不同步到 MaaFW option。
  - 不适配旧 M9A “切到最后一个账号”的行为。
- `tagInfo` 固定说明：
  - 账号 / 密码仅用于 AUTO-MAS 记录，不会自动传入脚本；需要传参请在下方任务选项中配置。
- 旧 M9A 的 `切换账号` 任务照常显示并允许手动勾选，但它只是脚本原生任务，与顶部账号 / 密码无关。
- 新 M9A 要传目标账号时，用户在 `切换账号` 任务自己的 `目标账号(可选)` option 中填写。

## 任务与 option 编辑器

- MaaFW option 编辑器做成通用能力，不写死 M9A 特判。
- UI 采用双栏：
  - 左栏：任务列表，负责勾选、排序、选择当前任务。
  - 右栏：当前任务的 option 表单与任务说明。
- 左栏保持简洁：
  - 显示任务名、勾选状态、排序/拖拽信息。
  - 不显示长说明或图片。
- 右栏布局：
  - 上半部分 option 表单。
  - 下半部分任务说明。
  - 没有 option 但有说明时，只显示任务说明。
  - option 与说明都没有时，显示空状态。
- 任务和 option 按当前脚本配置的 ADB controller/resource 过滤显示。
- 已保存但当前 controller/resource 不可用的任务：
  - 用户页隐藏。
  - 保存时保留原始快照，不删除。
  - 切回对应 controller/resource 后应恢复。

## MaaFW option 字段支持

- 按 MaaFW Project Interface 文档完整实现 option。
- 本地 M9A / Maa_bbb 当前 schema 明确包含：
  - `input`
  - `select`
  - `checkbox`
  - `switch`
- 通用字段支持：
  - `label`
  - `description`
  - `icon`
  - `controller`
  - `resource`
  - `default`
  - `pipeline_override`
  - 嵌套 `option`
- `input` 额外支持：
  - `inputs`
  - `pipeline_type`
  - `verify`
  - `verify_error`
- 未识别的新类型：
  - UI 显示“不支持的配置项类型”。
  - 保存时保留已有数据，不丢配置。

## 输入控件与校验

- `input` 根据 `pipeline_type` 选择控件：
  - `int` / `integer`: 整数数字输入框。
  - `float` / `double` / `number`: 小数数字输入框。
  - `bool` / `boolean`: 开关或下拉。
  - `string` 或缺省: 普通输入框。
- 类型转换失败时拦截保存。
- `verify` 正则失败时拦截保存。
- `verify_error` 存在时使用脚本给的提示。
- 没有 `verify_error` 时显示“输入不符合脚本要求”。
- 字符串输入在编辑过程中可以轻提示，但以保存时校验为准。

## 任务说明、图片与图标

- MaaFW 标准说明来源：
  - `task[].description`
  - option 的 `description`
  - input 的 `description`
  - preset 的 `description` 后续再做
- `description` 支持：
  - 直接文本：渲染 Markdown + 安全 HTML。
  - 相对文件路径：按脚本目录读取后渲染。
  - URL：显示为可点击链接，不主动联网抓取内容。
- HTML 渲染：
  - 保留安全白名单，如 `span`、`br`、`b`、`strong`、`em`、`a`、`img` 等。
  - 过滤脚本类内容。
  - 样式只允许必要安全子集，用于还原 M9A 这类任务说明。
- 图片：
  - 支持 Markdown 图片。
  - 相对路径按脚本目录解析。
  - 只允许脚本目录内路径。
  - 绝对路径或 `../..` 越界路径不渲染为图片。
  - 右栏内自适应宽度显示。
  - 点击图片打开预览放大。
- `icon`：
  - 任务 icon 显示在右栏标题旁。
  - option icon 显示在对应控件旁。
  - 左栏不放 icon。

## preset

- MaaFW `preset` 本轮暂不实现。
- 后续可单独做一键应用任务勾选状态和 option 值。

## 更新能力

- 更新信息从脚本本地 interface 读取：
  - `version`
  - `github`
  - `mirrorchyan_rid`
  - `mirrorchyan_multiplatform`
- 用户不手填 GitHub 仓库地址。
- 脚本页显示更新设置：
  - 是否启用自动更新。
  - 更新源：MirrorChyan / GitHub。
  - 渠道：稳定版 / 测试版。
  - 当前版本 / 最新版本。
- 渠道暂时固定为：
  - `stable`: 稳定版。
  - `beta`: 测试版。
  - 内测版不提供入口。
- 如果 MaaFW 官方接口或脚本未来声明更多渠道，先不动态扩展；需要重新对齐需求后再做。
- 选 MirrorChyan 时：
  - 显示 Mirror 酱 CDK。
  - 优先使用 MAS 全局更新配置中的 Mirror 酱 CDK。
  - 脚本页 CDK 作为可选覆盖值。
  - RID 从 `mirrorchyan_rid` 自动读取。
  - 多平台参数按 `mirrorchyan_multiplatform` 自动追加 `os=win&arch=x64` 等。
- 选 GitHub 时：
  - 使用 `interface.github`。
  - 不让用户填写仓库地址。
  - 显示 GitHub token / API key 输入。
  - 优先使用 MAS 全局更新源 / GitHub 相关统一配置。
  - 脚本页 token / API key 作为可选覆盖值。
  - 稳定版建议映射到最新非 prerelease release。
  - 测试版建议映射到最新 prerelease；没有 prerelease 时提示无测试版更新。
- `interface.version` 为空时：
  - 禁用自动更新。
  - 显示“当前脚本未声明版本，无法判断更新”。
  - 源码目录常见版本为空；发布包一般应有版本。
- 自动更新：
  - 允许运行时后台检查 / 下载更新包。
  - 不在脚本运行中替换目录。
  - 同路径脚本任务结束后自动安装。
  - 安装全自动，无需用户确认。
- 手动更新：
  - 如果同路径脚本正在运行，禁用或拦截，不允许点击。
  - UI 建议拆成“检查更新”和“立即更新”。
  - “检查更新”只刷新最新版本和变更状态。
  - “立即更新”在脚本空闲时下载并安装；如果没有检查缓存，可以先自动检查一次。
- 安装阶段：
  - 必须等待同路径脚本空闲。
  - 避免覆盖正在使用的文件。

## 官方文档核对

- 实现前必须核对 MaaFW 官方 Project Interface 文档，而不只依赖本地 M9A / Maa_bbb schema。
- 重点页面：
  - <https://maafw.com/docs/1.1-QuickStarted>
  - <https://maafw.com/docs/3.3-ProjectInterfaceV2#interface-json>
  - 同站点 Project Interface V2 相关页面。
- 如果官方文档存在本地 schema 没覆盖的 option 类型或字段，本轮需要补齐，除非实现风险过高再回到需求确认。

## 暂缓范围

- PC / PlayCover controller：
  - 先不显示、不卡用户。
  - 后续方向是脚本页配置客户端，由 MAS 管客户端生命周期，类似 Okww / MaaEnd。
  - 本轮不实现，因为当前无法测试。
- MaaFW preset：
  - 本轮不做。
- 顶部账号 / 密码与任务队列联动：
  - 本轮明确不做。

## 调度台状态

- 同路径正在运行时被跳过的任务，最终状态显示为“跳过”。
- 实现前需要查看脚本调度台 / 队列对类似跳过事件的现有处理方式，沿用现有状态与提示风格。
- 跳过原因必须可见：同路径 MaaFW 脚本正在运行，已跳过本次启动。

## 参考资料

- M9A: <https://github.com/MAA1999/M9A>
- Maa_bbb: <https://github.com/miaojiuqing/Maa_bbb>
- MaaFramework: <https://github.com/MaaXYZ/MaaFramework>
- MirrorChyan docs: <https://github.com/MirrorChyan/docs>
- MaaFW 文档: <https://maafw.com/docs/1.1-QuickStarted>
- MaaFW Project Interface V2: <https://maafw.com/docs/3.3-ProjectInterfaceV2#interface-json>
- MaaFW Hub: <https://hub.maafw.com/>
- MaaFW 社区项目: <https://maafw.com/community/projects>
- 本地 Maa_bbb 发布包: `C:\Users\qiyin\Downloads\Maa_bbb-win-x86_64-v1.12.5`

## 开工全文

- 新对话可直接使用同目录下的 `maafw-adapter-kickoff.md`。
