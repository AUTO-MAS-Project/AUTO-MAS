# app/task/M9A — M9A 是 MaaFW 的特调类型，不是专项

进这个目录之前先读 `app/task/MaaFW/AGENTS.md`：M9A 的运行、更新、内嵌副本、通知、失败截图、
周期任务、代理次数……全部是 MaaFW 引擎的既有语义，这里一行都没有重写。本目录只有四个文件：

- `managed.py`：**受管任务**的唯一规则。entry `StartUp`（启动游戏）、`SwitchAccount`（切换账号）、
  `Close1999`（关闭游戏）由 MAS 全权控制，不许留在用户队列里；按 entry 判，不按任务名。
  启动 / 关闭一律移除；切换账号只数「勾选且账号非空」的——恰好 1 个：账号进 `Info.Account`、从队列移除
  （`Info.Account` 原来非空且不同时队列值优先，原值追加进备注）；0 个：直接移除、不动账号；≥ 2 个且脚本
  资源是官服：队列里的切号原样保留（启动 / 关闭照删），备注与启动通知写明拆成几个用户，运行期拒绝该用户；
  ≥ 2 个但资源不是官服：切号只在官服生效、从没跑过，直接移除。下面四个入口都调它，不要另写一份：
  运行前装饰、启动整理、旧版迁移 / beta.1 补救、写 `Task.TaskSnapshot` 的保存入口。
  「资源是不是官服」在运行前装饰、启动整理、保存入口三处一律取引擎的
  `tools/core/runner/run_plan.resolve_run_selection`（脚本资源留空时按控制器回落：PC 控制器回落到
  「国际服（EN）」，不是 `interface.resource[0]`）；装饰与保存钩子由引擎把结果作 `resource_name` 传入，
  启动整理自己按原始 JSON 调它。别在特调里另写回落。
  **保留态的判据是队列内容本身**（有效切号 ≥ 2 且官服），不是标记：普通保存交回同一份队列照样判成
  保留、不会被抹掉；用户删到只剩 1 个，下一次保存就收进「账号」。前端不许过滤已在队列里的受管任务再
  保存——那样会绕过这条判据把保留态抹掉。
- `flavor.py`：`FLAVOR` 对象（满足 `app/task/MaaFW/tools/embedded/flavor.py` 的 `MaaFWFlavor` 协议）。
  它做的事穷举如下，多一件都没有：
  1. `matches_project(interface)`：`mirrorchyan_rid == M9A` / `github` 指向 `MAA1999/M9A` / `name == m9a`，
     任一命中即认领——导入完成后引擎据此把脚本类型定成 `M9AConfig`（不命中的项目导进 M9A 脚本会变回
     `MaaFWConfig`，类型由项目决定、双向自动、uid 不变）。
  2. `decorate_selection(...)`：运行前先把勾选列表里三类受管任务**全部剔掉**（连同它们的选项），再按
     固定顺序补：`StartUp` 放队首；脚本资源为「官服」且有账号时 `SwitchAccount` 紧跟启动、账号填进它
     第一个 input 选项；`Close1999` 放队尾。用户排的顺序不影响这三项。账号取 `Info.Account`，但队列里
     恰好残留一个有效切号时取它（与启动整理的结果一致）。官服且有效切号 ≥ 2 时写用户日志并抛
     `M9ASplitRequiredError`——引擎把它当成运行计划构建失败，该用户记「异常」、发错误通知、不跑，其它
     用户照常。剔完是空队列就什么都不补。按 entry 找不到就写一行用户日志跳过。**不**过滤 standalone、
     **不**结束 `M9A.exe`、**不**碰重试 / 周期 / 超时 / 更新。
  3. `sanitize_task_snapshot(...)`：引擎的**可选**快照整理钩子（契约写在 MaaFW `flavor.py` 的模块
     说明里）。`Config.update_user`（用户页保存、导入外壳配置建用户）与配置恢复回填用户字段时，按
     `managed.py` 整理快照并返回要一并写的 `Info.Account` / `Info.Notes`；拆分提示不在这里写。
  4. `ensure_game_updated(...)`：引擎的**可选**游戏更新钩子（契约写在 MaaFW `flavor.py` 的模块
     说明里，不在协议里），转给 `game_update.py`。
- `game_update.py`：脚本 `Run.GameUpdateMode` 不是 `Off` 时，模拟器启动后、第一个任务前比对
  官服客户端版本。只查资源为「官服」且拉起的包名是 `com.shenlan.m.reverse1999` 的，其余 `Skipped`。
  直链取自官网版本配置接口（`pageVersion` 从官网 `assets/js/api.js` 里读，读不出用写死的兜底值），
  版本号按 HTTP Range 只读直链安装包的清单（`app/utils/game_apk.fetch_remote_apk_version`，直链文件名
  里没有版本号）。本机 versionCode 高于官网包（其他渠道装的，如 MuMu 应用中心：3.9.0 是 210、
  官网 4.0.0 是 170）时 Android 不许降级、官网包永远装不上，两种模式都直接判失败、不下载。
  否则落后时 `Check` 判失败提示手动更新，`AutoInstall` 下载到 `data/GameApk` 后
  `adb install -r`、装完复查，安装包成败都删。下载 / 安装各 60 分钟上限，写死不做配置。
- `migration.py`：旧版 M9A 专项配置（`Run.IfPsychubeDailyOnce`、`Task.Queue`、`Data.LastPsychubeDate`…）
  → MaaFW 形状的一次性迁移，以及「通用 MaaFW 脚本指向 M9A 项目 → 换类型标签」。在
  `Config.init_config` 里 **`ScriptConfig.connect()` 之前**改原始 JSON（`ConfigBase.load` 只认类里
  声明的条目，旧键在加载那一刻就丢并写回盘）。改写前备份 `ScriptConfig.json.m9a-legacy-<时间戳>.bak`
  留三份；幂等。逐字段口径见 `docs/设计参考/M9A风味专项-语义稿-20260918.md` §3–§7；
  几个不能照抄的地方：`Run.RunTimeLimit` 固定 120（旧值是日志停滞阈值，MaaFW 是整轮硬超时）、
  `Update.AutoUpdateMode` 必须显式写 `AfterRun` / `Off`（引擎对缺省回落 `BeforeRun`）、
  用户级服务器 → 脚本级资源（不一致的用户停用 + 备注）、CDK 按 MFAA `config.json` 的 `DownloadCDK`
  → MAS 全局 CDK → GitHub 推导一次。input 值只清兑换码「占位」这一个预填哨兵（别的 default 是能跑的
  真值，引擎对 string 空值不回落 default）；快速配置来源的队列里三类受管任务是陈旧数据，直接剔；实例文件
  来源的「切换账号」先带着选项翻译出来，再按 `managed.py` 落地（1 个进 `Info.Account`，多个照搬进队列并
  在备注与通知里提示拆分）。v5.6.0-beta.1 的迁移清了输入值、丢了实例文件里的切号，
  `repair_m9a_migration_losses` 在迁移之后按 `.m9a-legacy-*.bak` 补回一次（切号同样按 `managed.py`：
  1 个进 `Info.Account`、不回队列；多个且现状顺序没动过才原位补回队列），看过备份就留
  `ScriptConfig.json.m9a-repaired` 标记、不再重做。补救之后 `normalize_m9a_managed_entries` 对全部
  M9A 用户按 `managed.py` 整理一遍（每次启动都跑、幂等，改了才写盘并备份
  `ScriptConfig.json.m9a-managed-<时间戳>.bak` 留三份、才发「M9A 任务队列已按新规则整理」通知；拆分提示
  已在备注里的不重复写、不重复通知；读不到 interface 的脚本跳过，下次启动再整理）。

配置类在 `app/models/config.py`：`M9AConfig(MaaFWConfig)` / `M9AUserConfig(MaaFWUserConfig)` 同形，只改
`DEFAULT_SCRIPT_NAME`、`USER_CONFIG_CLASS`、`FLAVOR`。`FLAVOR` 是字符串 `"app.task.M9A.flavor:FLAVOR"`，
由引擎按需导入——`app.models` 不能反向 import `app.task`。`app/core/task_manager.py` 的 `_MANAGER_BOOK`
按类型精确查表，`M9AConfig` 单独登记到 `MaaFWEmbeddedManager`；`app/core/config.py` 里所有
`isinstance(…, MaaFWConfig)` 分支天然覆盖 M9A，不要再加 `isinstance(…, M9AConfig)` 分支。

前端没有 M9A 专用页面：脚本页 / 用户页 / 创建流程都是 MaaFW 的组件按 `scriptType === 'M9A'` 取一张
flavor 文案表。表里的 `managedTaskEntries` 与 `managed.py` 的 `MANAGED_ENTRIES` 是同一组：通用用户页
按它把受管任务挡在「添加任务」与预设模板之外，已在队列里的照常显示；`managedAccountTask`
（`SwitchAccount` + 官服）是拆分判据，只有页面上生效的资源在其中、有效切号 ≥ 2 时才给「拆分前不会运行」
的警告，其余残留只给轻提示（`frontend/src/views/EditView/User/maafwManagedTasks.ts`）。改一边要同步另一边。#799 的配置备份恢复走 MaaFW 的两个池（`data/<sid>/MaaFWBackups/{mas,native}`）；
旧 `M9ABackups/` 不再被列出、不支持恢复、原地保留。

要给 M9A 加任何"专项行为"之前先问：这是不是所有 MaaFW 项目都该有的？是就做进引擎；不是就问用户
值不值得为它多一条特调逻辑——特调逻辑只能经 `FLAVOR` 钩子进入，`app/task/MaaFW/` 里不出现 M9A 逻辑（注释举例不算）。
