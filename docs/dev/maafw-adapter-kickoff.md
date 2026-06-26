# MaaFW 通用适配开工全文

把本文作为新对话的开工上下文使用。目标是继续完成 AUTO-MAS 的 MaaFW 通用适配，并以 `docs/dev/maafw-adapter-alignment.md` 作为需求权威。

## 开工请求

请在 `C:\Users\qiyin\Documents\GitHub\AUTO-MAS-with-M9A` 继续完成 MaaFW 通用适配。先不要盲写代码，必须先读并遵守：

- `AGENTS.md`
- `.agents/skills/mas-skills/SKILL.md`
- `.agents/skills/mas-script-specialized-adapter/SKILL.md`
- 涉及前端 / UI 时再读：
  - `.agents/skills/mas-frontend-standards/SKILL.md`
  - `.agents/skills/mas-frontend-ui/SKILL.md`
- 本需求文档：
  - `docs/dev/maafw-adapter-alignment.md`

开工前先确认当前分支、远端、工作区状态。不要回滚用户或上一轮已有改动。当前工作区很可能已经有 MaaFW 相关脏改，需要先读 diff 后再继续。

## 背景

用户希望把 MaaFW 适配做成通用线，M9A 和 Maa_bbb / 识宝小助手都能正常走 MaaFW 线运行。需求核心不是新增 M9A 专项，而是让 MaaFW Project Interface 能在 AUTO-MAS 里被解析、配置、运行、更新。

本轮范围只做 ADB / 模拟器，不做 PC / PlayCover 运行支持。

## 参考仓库与文档

必须核对：

- M9A: <https://github.com/MAA1999/M9A>
- Maa_bbb: <https://github.com/miaojiuqing/Maa_bbb>
- MaaFramework: <https://github.com/MaaXYZ/MaaFramework>
- MirrorChyan docs: <https://github.com/MirrorChyan/docs>
- MaaFW 快速开始: <https://maafw.com/docs/1.1-QuickStarted>
- MaaFW Project Interface V2: <https://maafw.com/docs/3.3-ProjectInterfaceV2#interface-json>
- MaaFW Hub: <https://hub.maafw.com/>
- MaaFW 社区项目: <https://maafw.com/community/projects>

本地参考包：

- `C:\Users\qiyin\Downloads\Maa_bbb-win-x86_64-v1.12.5`
- `C:\Users\qiyin\Downloads\M9A-win-x86_64-v3.22.1`

本地源码参考：

- `C:\Users\qiyin\Documents\GitHub\Maa_bbb`
- 如本地没有 M9A 源码，可临时克隆 `MAA1999/M9A` 只读检查。

网络受限时，按 Codex 工具规则请求授权；不要编造上游事实。

## 已确认的脚本现状

M9A:

- 本地 `v3.22.1` 的 `SwitchAccount.json` 是旧版，有切号任务但没有 option。
- M9A 最新发布版 `v4.0.0` 已有 `目标账号(可选)` option：
  - input 字段 `账号`
  - 通过 `pipeline_override` 写入 `SwitchAccountSelect.custom_action_param.account`
  - 没有密码 option
- M9A `interface.json` 有 `version`、`github`、`mirrorchyan_rid`、`mirrorchyan_multiplatform`。

Maa_bbb:

- 发布包 `Maa_bbb-win-x86_64-v1.12.5` 的 `interface.json` 有：
  - `version: v1.12.5`
  - `github: https://github.com/miaojiuqing/MAA_bbb`
  - `mirrorchyan_rid: Maa_bbb`
  - `mirrorchyan_multiplatform: true`
  - `桌面端` Win32 和 `安卓端` Adb controller
  - 多个 ADB resource / client
- 源码里的 `assets/interface.json` 可带注释且版本可能为空；运行和更新以实际应用目录的 interface 为准。

## 已确认需求

脚本配置页：

- 选择 MaaFW 项目目录并读取实际目录下的 `interface.json` / `interface.jsonc` 及其 imports。
- 本轮只显示 ADB controller / ADB resource。
- PC / PlayCover 本轮不显示、不运行。
- 如果脚本没有 ADB controller，允许保存但运行前提示暂不支持。
- 保留 resource / client 选择，只列出支持 ADB 的 resource。
- 模拟器选择放脚本页；用户页不再选 ADB。
- 不提供手动 ADB 地址输入。
- 一个脚本配置绑定一个客户端/resource 和一个模拟器实例。

ADB / 模拟器：

- 完全联动 MAS 模拟器管理。
- 运行前通过 MAS 现有接口启动 / 打开模拟器并等待 ADB。
- 已启动则复用。
- 运行后是否关闭模拟器走 MAS 现有配置能力。
- LDPlayer / MuMu 需要传 MaaFW extra：
  - LDPlayer: `extras.ld.enable/index/path/pid`
  - MuMu: `extras.mumu.enable/index/path`
- 其他模拟器不传 extra，只传基础 ADB 信息。

用户页：

- 顶部账号 / 密码栏始终显示并可填写。
- 账号 / 密码只作为 AUTO-MAS 记录字段。
- 不自动勾选任务，不置顶，不同步到 MaaFW option，不适配旧 M9A “切到最后一个账号”。
- 固定 tagInfo：账号 / 密码仅用于 AUTO-MAS 记录，不会自动传入脚本；需要传参请在下方任务选项中配置。
- 新 M9A 要传目标账号时，用户必须在 `切换账号` 任务自己的 `目标账号(可选)` option 中填写。

任务 option UI：

- 做成 MaaFW 通用能力，不写死 M9A 特判。
- 双栏 UI：
  - 左栏任务列表：勾选、排序、选择任务。
  - 右栏：上半 option 表单，下半任务说明。
- 没有 option 但有说明时只显示说明。
- option 与说明都没有时显示空状态。
- 左栏保持简洁，说明和图片放右栏。
- option 图标显示在右栏对应控件旁，任务图标显示在右栏标题旁。
- 任务和 option 按当前 ADB controller / resource 过滤。
- 当前 resource 不可用的已保存任务隐藏但不删除，切回后恢复。

option 类型与字段：

- 实现前必须核对 MaaFW 官方 Project Interface 文档，不只看本地 schema。
- 本地 M9A / Maa_bbb schema 当前有 `input/select/checkbox/switch`。
- 若官方文档还有新增 option 类型，本轮需要补齐，除非风险过高再找用户确认。
- 支持通用字段：`label`、`description`、`icon`、`controller`、`resource`、`default`、`pipeline_override`、嵌套 `option`。
- `input` 支持 `inputs`、`pipeline_type`、`verify`、`verify_error`。
- 未识别新类型不丢数据，UI 提示不支持。

输入校验：

- 根据 `pipeline_type` 用对应控件：
  - `int` / `integer`: 整数输入
  - `float` / `double` / `number`: 小数输入
  - `bool` / `boolean`: 开关或下拉
  - `string` 或缺省: 普通输入
- 类型转换失败拦截保存。
- `verify` 正则失败拦截保存。
- 有 `verify_error` 用脚本错误文案，否则显示“输入不符合脚本要求”。
- 输入过程中可轻提示，保存时正式拦截。

任务说明 / 图片 / HTML：

- 渲染 `task[].description`、option description、input description。
- 直接文本渲染 Markdown + 安全 HTML。
- 相对文件路径按脚本目录读取后渲染。
- URL 只显示链接，不主动联网抓内容。
- 保留安全白名单 HTML，如 `span/br/b/strong/em/a/img`，过滤脚本类内容。
- 图片相对路径按脚本目录解析，只允许脚本目录内路径。
- 图片右栏自适应显示，点击预览放大。

同路径防重入：

- 同一路径 MaaFW 脚本已有任务运行时，再次启动同路径任务直接跳过。
- 路径比较使用规范化脚本根目录：绝对路径、Windows 大小写不敏感、去掉末尾斜杠。
- 不同目录副本允许并行。
- 跳过状态在调度台显示为“跳过”，并写明原因。
- 实现前查看脚本调度台 / 队列对类似跳过事件的现有处理方式，沿用现有风格。

更新：

- 更新信息从脚本本地 interface 读取：
  - `version`
  - `github`
  - `mirrorchyan_rid`
  - `mirrorchyan_multiplatform`
- 用户不填写 GitHub 仓库地址。
- 脚本页显示：
  - 是否启用自动更新
  - 更新源 MirrorChyan / GitHub
  - 渠道稳定版 / 测试版
  - 当前版本 / 最新版本
- 内测版不提供入口。
- 渠道暂时只做 `stable` / `beta`。
- MirrorChyan：
  - 显示 CDK 输入。
  - 优先使用 MAS 全局 Mirror 酱 CDK。
  - 脚本页 CDK 是可选覆盖值。
  - RID 从 `interface.mirrorchyan_rid` 读取。
  - 多平台参数按 `mirrorchyan_multiplatform` 自动追加。
- GitHub：
  - 使用 `interface.github`。
  - 显示 GitHub token / API key 输入。
  - 优先使用 MAS 全局更新源 / GitHub 统一配置。
  - 脚本页 token / API key 是可选覆盖值。
  - 稳定版建议取最新非 prerelease。
  - 测试版建议取最新 prerelease；无 prerelease 时提示无测试版。
- `interface.version` 为空时禁用自动更新，并提示脚本未声明版本。
- 自动更新允许运行时后台检查 / 下载，不在运行中替换目录。
- 同路径任务结束后自动安装，安装全自动。
- 手动更新时，同路径正在运行则禁用或拦截。
- 手动 UI 建议拆成“检查更新”和“立即更新”。

暂缓：

- PC / PlayCover 运行支持。
- MaaFW preset。
- 顶部账号 / 密码与任务队列联动。

## 重点代码位置

优先阅读这些文件和 diff：

- `app/task/MaaFW/interface_models.py`
- `app/task/MaaFW/interface_loader.py`
- `app/task/MaaFW/task_config.py`
- `app/task/MaaFW/pipeline_override.py`
- `app/task/MaaFW/AutoProxy.py`
- `app/task/MaaFW/manager.py`
- `app/task/MaaFW/project_updater.py`
- `app/task/MaaFW/run_plan.py`
- `app/models/config.py`
- `app/models/schema.py`
- `frontend/src/types/script.ts`
- `frontend/src/views/EditView/Script/MaaFWScriptEdit.vue`
- `frontend/src/views/EditView/User/MaaFWUserEdit.vue`
- `frontend/src/views/EditView/User/MaaFWTaskOptionEditor.vue`
- `tests/test_maafw_interface_loader.py`

已有脏改可能涉及上面文件。不要直接覆盖，先 `git diff` 理解已有实现，再按需求收敛。

## 实施建议顺序

1. 读 `docs/dev/maafw-adapter-alignment.md`，确认本文没有过期。
2. 核对 MaaFW 官方文档，尤其 Project Interface V2 option 类型、description、icon、controller/resource 过滤、preset、global_option。
3. 核对 MirrorChyan docs 和 MaaFW Hub / 社区项目字段，确认更新参数。
4. 读取 M9A 最新 release / HEAD 的 `SwitchAccount.json`、`interface.json`。
5. 读取本地 Maa_bbb 发布包 `interface.json` 和代表性 task option。
6. 审查当前 MaaFW 代码 diff，清掉和最终需求冲突的旧联动逻辑：
   - 顶部账号 / 密码不得同步 option。
   - 不得自动勾选 / 置顶切号任务。
   - 不得保留手动 ADB 地址输入。
7. 完成后端：
   - interface import 合并和字段模型。
   - ADB controller/resource 选择。
   - 模拟器管理联动和 LD/MuMu extra。
   - pipeline_override 根据任务 option 生成。
   - 同路径防重入。
   - 更新器 MirrorChyan / GitHub。
8. 完成前端：
   - 脚本页 ADB-only 配置、resource/client、模拟器实例、更新区域。
   - 用户页账号密码仅记录、固定 tagInfo。
   - 双栏任务 option 编辑器、说明/图片/icon、安全 HTML、校验。
9. 补测试。
10. 验证 lint/build/pytest。

## 验证建议

按改动范围选择验证，不要编造结果：

- `python -m pytest tests\test_maafw_interface_loader.py`
- `python -m py_compile app\models\config.py app\models\schema.py app\task\MaaFW\AutoProxy.py app\task\MaaFW\manager.py app\task\MaaFW\project_updater.py app\task\MaaFW\interface_loader.py app\task\MaaFW\pipeline_override.py`
- `yarn eslint src/views/EditView/Script/MaaFWScriptEdit.vue src/views/EditView/User/MaaFWUserEdit.vue src/views/EditView/User/MaaFWTaskOptionEditor.vue`
- `yarn vite build`
- 若触及 schema，提醒开发者通过生成器更新前端 OpenAPI 代码，不要手改 `frontend/src/api` 生成文件。

## 注意事项

- 当前仓库可能已有上一轮生成的 MaaFW 实现草稿，不能回滚用户改动。
- `frontend/src/api` 下生成文件不要手改。
- 用户希望先对齐再实现；如果官方文档与本文冲突，先总结差异并问用户。
- 代码实现要尽量通用，避免写死 M9A。
