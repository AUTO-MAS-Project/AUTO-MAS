# app/task/M9A — M9A 是 MaaFW 的特调类型，不是专项

进这个目录之前先读 `app/task/MaaFW/AGENTS.md`：M9A 的运行、更新、内嵌副本、通知、失败截图、
周期任务、代理次数……全部是 MaaFW 引擎的既有语义，这里一行都没有重写。本目录只有三个文件：

- `flavor.py`：`FLAVOR` 对象（满足 `app/task/MaaFW/tools/embedded/flavor.py` 的 `MaaFWFlavor` 协议）。
  它做的事穷举如下，多一件都没有：
  1. `matches_project(interface)`：`mirrorchyan_rid == M9A` / `github` 指向 `MAA1999/M9A` / `name == m9a`，
     任一命中即认领——导入完成后引擎据此把脚本类型定成 `M9AConfig`（不命中的项目导进 M9A 脚本会变回
     `MaaFWConfig`，类型由项目决定、双向自动、uid 不变）。
  2. `decorate_selection(...)`：运行前在用户勾选的任务实例列表上加首尾——entry `StartUp` 放头、
     `Close1999` 放尾；脚本资源为「官服」且用户 `Info.Account` 非空时在启动之后插 entry `SwitchAccount`
     并把账号填进它第一个 input 选项。队列里已有的不重复加、不改用户自己配的选项；按 entry 找不到就写
     一行用户日志跳过。**不**过滤 standalone、**不**结束 `M9A.exe`、**不**碰重试 / 周期 / 超时 / 更新。
  3. `ensure_game_updated(...)`：引擎的**可选**游戏更新钩子（契约写在 MaaFW `flavor.py` 的模块
     说明里，不在协议里），转给 `game_update.py`。
- `game_update.py`：脚本 `Run.GameUpdateMode` 不是 `Off` 时，模拟器启动后、第一个任务前比对
  官服客户端版本。只查资源为「官服」且拉起的包名是 `com.shenlan.m.reverse1999` 的，其余 `Skipped`。
  直链取自官网版本配置接口（`pageVersion` 从官网 `assets/js/api.js` 里读，读不出用写死的兜底值），
  版本号按 HTTP Range 只读直链安装包的清单（`app/utils/game_apk.fetch_remote_apk_version`，直链文件名
  里没有版本号）。落后时 `Check` 判失败提示手动更新，`AutoInstall` 下载到 `data/GameApk` 后
  `adb install -r`、装完复查，安装包成败都删。下载 / 安装各 60 分钟上限，写死不做配置。
- `migration.py`：旧版 M9A 专项配置（`Run.IfPsychubeDailyOnce`、`Task.Queue`、`Data.LastPsychubeDate`…）
  → MaaFW 形状的一次性迁移，以及「通用 MaaFW 脚本指向 M9A 项目 → 换类型标签」。在
  `Config.init_config` 里 **`ScriptConfig.connect()` 之前**改原始 JSON（`ConfigBase.load` 只认类里
  声明的条目，旧键在加载那一刻就丢并写回盘）。改写前备份 `ScriptConfig.json.m9a-legacy-<时间戳>.bak`
  留三份；幂等。逐字段口径见 `docs/设计参考/M9A风味专项-语义稿-20260918.md` §3–§7；
  几个不能照抄的地方：`Run.RunTimeLimit` 固定 120（旧值是日志停滞阈值，MaaFW 是整轮硬超时）、
  `Update.AutoUpdateMode` 必须显式写 `AfterRun` / `Off`（引擎对缺省回落 `BeforeRun`）、
  用户级服务器 → 脚本级资源（不一致的用户停用 + 备注）、CDK 按 MFAA `config.json` 的 `DownloadCDK`
  → MAS 全局 CDK → GitHub 推导一次。

配置类在 `app/models/config.py`：`M9AConfig(MaaFWConfig)` / `M9AUserConfig(MaaFWUserConfig)` 同形，只改
`DEFAULT_SCRIPT_NAME`、`USER_CONFIG_CLASS`、`FLAVOR`。`FLAVOR` 是字符串 `"app.task.M9A.flavor:FLAVOR"`，
由引擎按需导入——`app.models` 不能反向 import `app.task`。`app/core/task_manager.py` 的 `_MANAGER_BOOK`
按类型精确查表，`M9AConfig` 单独登记到 `MaaFWEmbeddedManager`；`app/core/config.py` 里所有
`isinstance(…, MaaFWConfig)` 分支天然覆盖 M9A，不要再加 `isinstance(…, M9AConfig)` 分支。

前端没有 M9A 专用页面：脚本页 / 用户页 / 创建流程都是 MaaFW 的组件按 `scriptType === 'M9A'` 取一张
flavor 文案表。#799 的配置备份恢复走 MaaFW 的两个池（`data/<sid>/MaaFWBackups/{mas,native}`）；
旧 `M9ABackups/` 不再被列出、不支持恢复、原地保留。

要给 M9A 加任何"专项行为"之前先问：这是不是所有 MaaFW 项目都该有的？是就做进引擎；不是就问用户
值不值得为它多一条特调逻辑——特调逻辑只能经 `FLAVOR` 钩子进入，`app/task/MaaFW/` 里不出现 M9A 逻辑（注释举例不算）。
