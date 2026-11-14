# app/task/M9A — M9A 是 MaaFW 的特调类型，不是专项

进这个目录之前先读 `app/task/MaaFW/AGENTS.md`：M9A 的运行、更新、内嵌副本、通知、失败截图、
周期任务、代理次数……全部是 MaaFW 引擎的既有语义，这里一行都没有重写。本目录只有五个文件：

- `managed.py`：**受管任务**的唯一规则。entry `StartUp`（启动游戏）、`SwitchAccount`（切换账号）、
  `Close1999`（关闭游戏）由 MAS 全权控制，不许留在账号队列里；按 entry 判，不按任务名。
  启动 / 关闭一律移除；切换账号只数「勾选且账号非空」的——恰好 1 个：账号进 `Info.Account`、从队列移除
  （`Info.Account` 原来非空且不同时队列值优先，原值追加进备注）；0 个：直接移除、不动账号；≥ 2 个且脚本
  资源支持切号：队列里的切号原样保留（启动 / 关闭照删），备注与启动通知写明拆成几个账号，运行期拒绝该账号；
  ≥ 2 个但资源不支持切号：切号从没跑过，直接移除。「资源支持切号」的口径只在
  `managed.supports_account_switch` 一处：官服按原有规则；`Run.LoginMode` 为 `Mas`（登录由 MAS 完成）时
  一律不支持——四个入口都按它判，不要再各自读资源名。下面四个入口都调它，不要另写一份：
  运行前装饰、启动整理、旧版迁移 / beta.1 补救、写 `Task.TaskSnapshot` 的保存入口。
  「资源是不是官服」在运行前装饰、启动整理、保存入口三处一律取引擎的
  `tools/core/runner/run_plan.resolve_run_selection`（脚本资源留空时按控制器回落：PC 控制器回落到
  「国际服（EN）」，不是 `interface.resource[0]`）；装饰与保存钩子由引擎把结果作 `resource_name` 传入，
  启动整理自己按原始 JSON 调它。别在特调里另写回落。
  **保留态的判据是队列内容本身**（有效切号 ≥ 2 且资源支持切号），不是标记：普通保存交回同一份队列照样判成
  保留、不会被抹掉；用户删到只剩 1 个，下一次保存就收进「账号」。前端不许过滤已在队列里的受管任务再
  保存——那样会绕过这条判据把保留态抹掉。
- `flavor.py`：`FLAVOR` 对象（满足 `app/task/MaaFW/tools/embedded/flavor.py` 的 `MaaFWFlavor` 协议）。
  它做的事穷举如下，多一件都没有：
  1. `matches_project(interface)`：`mirrorchyan_rid == M9A` / `github` 指向 `MAA1999/M9A` / `name == m9a`，
     任一命中即认领——导入完成后引擎据此把托管类型定成 `M9AConfig`（不命中的项目导进 M9A 脚本会变回
     `MaaFWConfig`，类型由项目决定、双向自动、uid 不变）。
  2. `decorate_selection(...)`：运行前先把勾选列表里三类受管任务**全部剔掉**（连同它们的选项），再按
     固定顺序补：`StartUp` 放队首；脚本资源支持切号且有账号时 `SwitchAccount` 紧跟启动、账号填进它
     第一个 input 选项；`Close1999` 放队尾。用户排的顺序不影响这三项。账号取 `Info.Account`，但队列里
     恰好残留一个有效切号时取它（与启动整理的结果一致）。支持切号且有效切号 ≥ 2 时写账号日志并抛
     `M9ASplitRequiredError`——引擎把它当成运行计划构建失败，该账号记「异常」、发错误通知、不跑，其它
     用户照常。剔完是空队列就什么都不补。按 entry 找不到就写一行账号日志跳过。**不**过滤 standalone、
     **不**结束 `M9A.exe`、**不**碰重试 / 周期 / 超时 / 更新。
  3. `sanitize_task_snapshot(...)`：引擎的**可选**快照整理钩子（契约写在 MaaFW `flavor.py` 的模块
     说明里）。`Config.update_user`（账号页保存、导入外壳配置建用户）与配置恢复回填账号字段时，按
     `managed.py` 整理快照并返回要一并写的 `Info.Account` / `Info.Notes`；拆分提示不在这里写。
  4. `ensure_game_updated(...)`：引擎的**可选**游戏更新钩子（契约写在 MaaFW `flavor.py` 的模块
     说明里，不在协议里），转给 `game_update.py`。
  4a. `ensure_logged_in(...)`：引擎的**可选**运行前登录钩子（契约写在 MaaFW `flavor.py` 的模块
     说明里，不在协议里），转给 `login.py`。只有 `Run.LoginMode == "Mas"` 时真正做事，
     其余情况返回空串；失败抛 `MaaFWLoginRequired`（本轮按普通失败重试）。
  5. `abort_round_entries` / `nonfatal_entries`：引擎的**可选**声明（契约同上）。切换账号失败就
     结束本轮、照常重试；**启动游戏（`StartUp`）不在名单里**（上游一直只声明切号：它失败不代表
     游戏用不了，按普通任务失败继续）；关闭游戏（`Close1999`）失败、超时或打转
     只截图记一行，不算本轮失败、不重试。
  6. `skip_on_retry_entries`：引擎的**可选**声明（契约同上）。列的是 v4.11.3 全部非受管任务的 entry，
     本次运行里完成过的重试时不再补跑；**逐个写出**，M9A 新增的任务默认照旧补跑，确认重跑无意义再加。
     受管三项每次尝试都要重做，不列。
  7. `unselectable_entries`：引擎的**可选**声明（契约同上）。五个小游戏（`8bit`、`CritterCrash`、
     `MusesBoxStartParty`、`PreStormProtocolStart`、`CompleteInduction`）要用户先手动停在对应页面，
     M9A 没有导航：账号页不让选（已在队列里的照常显示、给一句提示），运行时剔掉并记一行。
     优先于上面三项声明，`skip_on_retry_entries` 里的同名 entry 留着不动。
  8. `no_default_fallback_inputs`：引擎的**可选**声明（契约同上）。只列「自定义兑换码」的
     「兑换码」字段：引擎对没填的字符串字段回落 interface 的 default，而它的 default 是字面量
     「占位」，旧版迁移专门把预填的它清成空串（`migration._clean_input_values`），agent 遇到交不过去
     的码会中断整个兑换、后面真正的兑换码也不交。其余字段照常回落。
  9. `retype_notice_lines(...)`：引擎的**可选**钩子（契约同上）。导入项目后脚本换成 / 换出 M9A 时，
     系统通知里说明启停与切号；「账号栏改掉或清空」只在脚本已有账号时说。
- `game_update.py`：脚本 `Run.GameUpdateMode` 不是 `Off` 时，模拟器启动后、第一个任务前比对
  官服客户端版本。只查资源为「官服」且拉起的包名是 `com.shenlan.m.reverse1999` 的，其余 `Skipped`。
  直链取自官网版本配置接口（`pageVersion` 从官网 `assets/js/api.js` 里读，读不出用写死的兜底值），
  版本号按 HTTP Range 只读直链安装包的清单（`app/utils/game_apk.fetch_remote_apk_version`，直链文件名
  里没有版本号）。本机 versionCode 高于官网包（其他渠道装的，如 MuMu 应用中心：3.9.0 是 210、
  官网 4.0.0 是 170）时 Android 不许降级、官网包永远装不上，两种模式都直接判失败、不下载。
  否则落后时 `Check` 判失败提示手动更新，`AutoInstall` 下载到 `data/GameApk` 后
  `adb install -r`、装完复查，安装包成败都删。下载 / 安装各 60 分钟上限，写死不做配置。
- `login.py`：`Run.LoginMode == "Mas"` 时的 B 服原生登录（`ensure_logged_in` 钩子）。MAS 启动模拟器
  （连带拉起游戏）之后、第一个任务之前，用 `adb` 截图 + `app.tools.common.ocr` 识别哔哩哔哩登录面板：
  点「隐私政策提示」里唯一的「同意」，在「登录记录」里按 `Info.Account`（登录记录里显示的完整昵称）
  含汉字的昵称提取汉字后完整匹配，无汉字的昵称按 OCR 原文精确匹配，唯一命中才选中并点「登录」。
  登录面板退出后由同一 worker 执行 M9A 的公开 `StartUp`。成功后宿主在剩余登录时限内核对 UID，连续两张新截图与 `Info.GameUID` 一致才放行后续任务。
  如果一开始就在主页，UID 一致直接继续，确认不符时经设置 → 账号 → 退出 → 返回登录，然后重新选号。
  主页退出导航及 `login_assets/` 的两个模板来自 MAA1999/M9A（AGPL-3.0，原始提交
  [e03c1c6](https://github.com/MAA1999/M9A/tree/e03c1c60e51bff35c909aad96c58fde58a117946/resource/base/image/SwitchAccount)）。
  游戏已登录停在标题页时，
  MAS 不知道当前是哪个号，为保证切到目标账号，先点标题页右下角退出图标 → 唯一的「确认」→ 等「登录记录」
  出现再选号。`adb` 子进程走 `app/utils/common/process/runner.py` 的受管入口：任务被停止时命令随作用域
  回收，截图分支保留 PNG 原始 bytes（不能按文本解码）。
  **边界**：自动同意只复用全局 `Config.setting.Function.IfAgreeBilibili`（默认关），关着时不点、
  提示手动处理并停止；既认不出登录记录也认不出标题页且无法识别主页 UID（例如加载中）时明确停止，
  不把"没认出登录页"当成功；这段等待的预算取 `Game.WaitTime`（冷启动加载画面同样认不出，不能按
  固定 60 秒截断慢启动的客户端），总时长仍受登录主循环 240 秒约束；所有循环先查总时限，
  `adb input tap` 失败直接抛错。
  坐标全按屏幕宽高取比例（16:9 实测值），面板 / 标题页布局改版要跟着改。失败抛
  `MaaFWLoginRequired`（文案直接给用户看，本轮按普通失败重试）；`CancelledError` 照常上抛。
  引擎侧只在登录成功后才记「已登录」，客户端被重试重启时会清掉标记、下一轮重新验证。
  依赖：ADB controller + `Game.PackageName` 填 B 服包名（`com.shenlan.m.reverse1999.bilibili`，
  没填时按这个包名拉起）。脚本资源不是「B 服」或实际要启动的包名不是 B 服包时直接报错，
  不拿错客户端去走哔哩哔哩登录面板。`Run.LoginMode` 默认 `Project`（M9A 项目自己登录），只在 M9A 脚本有。
  这是**临时补位**：上游 M9A 的 interface 已声明 B 服资源（任务运行可用），但「切换账号」仍只声明
  官服、没有按 B 站昵称选号的入口；上游补齐等价入口后移除这里的 B 服退出、选号及启动补位（立项时未单独向上游提
  PR：本实现属于 MAS 侧运行前编排，上游入口补齐前无法复用）。
- `migration.py`：旧版 M9A 专项配置（`Run.IfPsychubeDailyOnce`、`Task.Queue`、`Data.LastPsychubeDate`…）
  → MaaFW 形状的一次性迁移，以及「通用 MaaFW 脚本指向 M9A 项目 → 换类型标签」。在
  `Config.init_config` 里 **`ScriptConfig.connect()` 之前**改原始 JSON（`ConfigBase.load` 只认类里
  声明的条目，旧键在加载那一刻就丢并写回盘）。改写前备份 `ScriptConfig.json.m9a-legacy-<时间戳>.bak`
  留三份；幂等。逐字段口径见 `docs/设计参考/M9A风味专项-语义稿-20260918.md` §3–§7；
  几个不能照抄的地方：`Run.RunTimeLimit` 固定 120（旧值是日志停滞阈值，MaaFW 是整轮硬超时）、
  `Update.AutoUpdateMode` 必须显式写 `AfterRun` / `Off`（引擎对缺省回落 `BeforeRun`）、
  账号级服务器 → 托管级资源（不一致的用户停用 + 备注）、CDK 按 MFAA `config.json` 的 `DownloadCDK`
  → MAS 全局 CDK → GitHub 推导一次。input 值只清兑换码「占位」这一个预填哨兵（别的 default 是能跑的
  真值，保留；兑换码清成空串后靠 `no_default_fallback_inputs` 不被引擎回落成「占位」）；覆写常规配置来源的队列里三类受管任务是陈旧数据，直接剔；实例文件
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
由引擎按需导入——`app.models` 不能反向 import `app.task`。`app/task/MaaFW/registration.py` 的家族声明
显式把 `M9AConfig` 登记到 `MaaFWEmbeddedManager`，宿主生成的运行索引按类型精确匹配；`app/core/config/manager.py` 里所有
`isinstance(…, MaaFWConfig)` 分支天然覆盖 M9A，不要再加 `isinstance(…, M9AConfig)` 分支。

前端没有 M9A 专用页面：托管页 / 账号页 / 创建流程都是 MaaFW 的组件，按脚本实际类型取特调注册表里
M9A 的描述对象（`frontend/src/views/EditView/MaaFWFlavor/m9a/index.ts`，写法见
`frontend/src/composables/useMaaFWFlavor.ts` 文件头）。托管页的两个独占下拉都挂在插入点
`scriptPage.slots.besidePackageName`（同目录、按需加载）：「游戏更新」（`Run.GameUpdateMode`，对应
`game_update.py`，`M9AGameUpdateField.vue`）与「登录方式」（`Run.LoginMode`，对应 `login.py`，
`M9ALoginModeField.vue`，Project / Mas 与后端字面量一致）。描述对象里的 `userPage.managed.entries` 与 `managed.py` 的
`MANAGED_ENTRIES` 是同一组：通用账号页按它把受管任务挡在「添加任务」与预设模板之外，已在队列里的照常显示；
`userPage.managed.accountTask`
（`SwitchAccount` + 官服）是拆分判据，只有页面上生效的资源在其中、有效切号 ≥ 2 时才给「拆分前不会运行」
的警告；`Run.LoginMode == "Mas"` 时用户页把 accountTask 置空（切号由 MAS 完成、后端会直接移出残留），
其余残留只给轻提示（`frontend/src/views/EditView/User/maafwManagedTasks.ts`）。改一边要同步另一边。#799 的配置备份恢复走 MaaFW 的两个池（`data/<sid>/MaaFWBackups/{mas,native}`）；
旧 `M9ABackups/` 不再被列出、不支持恢复、原地保留。

要给 M9A 加任何"专项行为"之前先问：这是不是所有 MaaFW 项目都该有的？是就做进引擎；不是就问用户
值不值得为它多一条特调逻辑——特调逻辑只能经 `FLAVOR` 钩子进入，`app/task/MaaFW/` 里不出现 M9A 逻辑（注释举例不算）。
