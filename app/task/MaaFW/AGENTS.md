# `app/task/MaaFW` 说明

MaaFW 是**通用引擎**，不是专项：任何带 `interface.json` 的 MaaFramework 项目都由它运行。
专项适配那一套（原生编辑器会话、base 三态（shared/independent/native）、配置备份恢复）不适用，见末节。
本文件只记录代码里读不出来、但改错了会出事的约束。

## 布局与边界

- `embedded_manager.py`：宿主侧管理器——任务调度、更新时机、运行环境确认、用户配置副本与写回。
- `tools/embedded/maintenance.py`：宿主资源维护入口；公共 Config 注入脚本快照、完整加载状态与保留天数，`migration.py` 承接老副本采纳、组版本统一和旧更新状态清理。main 编排迁移后的启动清理，timer 触发每日原生日志清理。
- `api_service/`：`/api/scripts/maafw/*` 端点背后的全部业务（`common` 脚本解析 / 有效项目根 /
  同组候选，`embedded` 副本状态 / 导入 / 克隆 / 候选来源，`interface` 预览 / 包名 / 图片资源 / 项目图标，
  `update` 手动更新，`agent_env` 预备运行环境，`shell_instances` 外壳配置实例导入成用户）。
  **MFW 的 API 业务一律在这里实现，
  本目录的 `api.py` 只放端点模型与薄端点**：取参数 → 调这里的一个函数 → `XxxOut(**reply.out_fields())`
  （`MaaFWApiReply`）或把异常映射成 HTTP 错误；不在 API 层定义 MFW 私有辅助函数、常量或锁。
  公共 API 入口只组装路由；业务不得导入 `api.py` 或 `app.api`，worker 导入闭包不得碰它们。
  端点 docstring 会进 OpenAPI 生成物，搬业务时留在端点上原样不动。
- `tools/embedded/`：宿主与核心包之间**唯一**的接缝（`runner_task`、`runtime_route`、
  `update_credentials`、`update_mirrors`、`project_path`、`env_cache`、`game_package`、
  `game_resolution`、`update_progress`、`embedded_project`、`option_secrets`、`shell_instances`、
  `default_snapshot`、`env_confirm`、`update_session`）。
  要读 `Config`、发通知、碰宿主模型，只能在这里和 `embedded_manager.py` 里做。
- `tools/core/`：六个核心包（interface / runner / runtime_pool / agent_env /
  project_update / controller_win32），按零宿主耦合设计。已知例外只有
  `project_update/updater.py` 引了 `app.utils.constants`——它只在宿主进程里跑；不要再加新的。
- **worker 子进程**（`runner/worker.py`）以 `python -m` 启动，其导入闭包内的
  `app.*` 只能落在 `app.task.MaaFW.tools.core.` 之下，由
  `tests/task/test_maafw_core.py` 钉死。v5.5.0-beta.4 全员 MFW 挂掉，
  就是链路上多了一处 `from app.utils import ...`。要放宽这条边界，在那个测试里显式加白名单并在
  PR 里说明，不要只改这段文字。
- **宿主 ↔ worker 协议**（`tools/core/worker_protocol.py`，只依赖标准库）：事件格式、两边共用的常量
  （`DETAIL_LOG_PREFIX`、信号取值与证据截图 kind）、日志去向规则、分帧与通道都在这一处，宿主不再
  复制 runner 的常量（`runner.py` 一导入就加载 maa，宿主引不了它）。
  - **job 经 worker 的 stdin 传**、写完就关，不落盘（计划里有解密后的密码选项）。升级前写过的
    `data/maafw_runner_jobs/*.json` 残留照旧按 1 小时清扫（`runner_task._sweep_legacy_runner_jobs`）。
    worker 仍认一个 job 文件路径参数，只为兜「旧宿主进程拉起新 worker」的升级窗口。
  - **事件走独立通道：Windows 命名管道**（`WorkerEventServer`：只进不出、名字随机、只有一个实例、
    拒绝远程连接），管道名与一次性令牌随 job 交给 worker；worker 按名字打开（`EventChannelClient`），
    先发带令牌的 `hello`，之后一个事件一条消息，按帧传（4 字节头、单片 ≤ 1 MB、整条不限长，接收端只为
    内存设 64 MB 上限，超了丢这一条、记一句、接着读）。stdout 只剩原生诊断，照旧逐行进 `.worker.log`。
    **不要换成本机套接字**：worker 原生崩溃 / 被结束时，套接字对端收到 RST，宿主还没读走的数据被
    Windows 直接丢掉（实测宿主读取滞后 50 ms 就 10 次 10 次丢事件、连结果一起丢——结果发出后在
    `runner.shutdown()` 里崩溃，就成了「没有结果」去重试）；命名管道与 stdout 一样，写的一方没了，
    已写进去的照样读得出。两端句柄都不带安全属性建 / 开，不可继承：宿主同时拉起的模拟器 / 游戏、
    worker 拉起的 adb / agent 都带不走（常驻的继承者会让读的一方等不到 EOF）。
    宿主用一个后台线程读（重叠 I/O + 100 ms 轮询，随时能停，不依赖事件循环实现），事件循环积压超过
    32 MB 时先停读，worker 的写跟着等（同 stdout 写满）。worker 退出后（`worker_exited()`）把管道里
    剩下的读完、读到 EOF 就结束，从没打开过的立刻结束；兜底最多再读 5 s。
  - **建不起通道就退回 stdout 旧格式**（一行一个 JSON 事件）：宿主建管道失败、worker 打不开、打开后
    写入出错（宿主令牌不对 / 握手超时 / 读到坏数据都会关管道）都退回，原因各记一行进 `.worker.log`；
    宿主一直按行解析 stdout，运行照常。选退回而不是报错：旧格式是跑了很久的路径，通道建不起来的原因
    （安全软件拦截之类）用户处理不了，而 job 仍走 stdin，退回也不会让密码落盘。非 Windows 上没有这条
    通道，直接用旧格式、不记。
  - **日志去向在发出时定**：日志 / 错误事件带 `audience`（`ui` / `worker_log`）与 `level`
    （`info` / `warning` / `error`），宿主照字段办。runner 自己知道去向的行发出时就标好
    （`MaaFWRunner._log_detail` 发 `[MaaFW 详情]` 行、`[MaaFW Tasker] 开始/成功/失败` 回声、
    「MaaFW 任务执行失败」原文回显），失败 / 超时类的带 `warning` / `error`；只经 `send_log` 传文案的
    （agent 与环境准备转来的输出等）由 worker 的 `_emit` 按 `worker_protocol.forwards_to_ui` 补
    `audience`。不带 `audience` 的旧格式事件和 stdout 上的原生诊断仍按同一个函数判。`level` 目前只随
    事件带着，宿主不据它改界面或 app.log。新增的 runner 日志知道去向的就用 `_log` / `_log_detail`。
  - 新增事件类型照旧：worker 里 `_emit({"type": ..., ...})`，宿主在 `runner_task` 的 `handle_event`
    里按 `type` 加一个分支，两条传输都会经过它；宿主不认识的类型忽略。

## 项目目录与运行

- **有效项目根只从一处取**：`tools/embedded/embedded_project.resolve_maafw_project_root`
  ——**永远是** `data/mfw/<脚本 uuid 前 12 位>/` 的视图，没有"路径模式"。`Info.Path` 只是
  导入的来源，运行时不读它（开发者模式下运行前检查会扫一遍它决定要不要重导，跑的仍是视图）；
  导入完成后用户删掉来源也无妨。源码形态的视图同样以 interface 所在目录为根（`assets/` 平铺到视图根，
  见「源码形态」），所以项目根永远等于视图根、永远有 `interface.json`。manager 三处、`runner_task`、
  `api_service/update.py`（`/maafw/update`）都走它；`/maafw/preview`、`/maafw/agent-env/prepare`、
  `/maafw/game-package` 带 `scriptId` 时也按脚本解析，`path` 只在没有脚本时兜底。
  新增任何"读项目目录"的代码不要再各自读 `Info.Path`。唯一的例外是 `runner_task` 的运行前架构自检
  （`describe_project_runtime_architecture_mismatch`）：只在副本自带的 MaaFramework 与本机架构不符时，
  只读地看一眼来源里有没有本机能用的那份，好在报错里说「重新导入即可」还是「换发行包」；不把来源
  当项目根，来源不在也照常报错。视图可能还没建（刚选目录、来源换了目录、
  被手删），各入口先经 `ensure_embedded_copy`（调用方持该视图的项目预约）：视图不在或 `Info.Path`
  与导入报告里的 `sourcePath` 不是同一目录就导入一次；来源不在而视图健康时什么都不做；健康但
  没有标记的老副本就地采纳一次，采纳失败就报错、本次不运行。有标记、但标记挂的载荷在本机不完整
  （目录没了，或清单没了 / 读不出，`payloads.payload_complete`）的按视图现状重新登记一次
  （`adopt_view(replace_lost=True)`，谱系沿用标记里的，不按 interface 重算），失败只告警、照常
  运行——不补的话更新永远以一份没有清单的载荷为基准、建不成新版本。开发者模式、以及视图还挂在
  开发者载荷上的（标记带 `followSource`，或载荷版本带 `+dev` 本地段——关掉开关时组里没有正式
  版本、来源也不在就会这样）不重新登记：视图里是开发者的改动，不能以正式版本号进普通渠道。组 latest 只剩目录没有清单时同样按丢了处理（`latest_entry` 不返回它，
  `register` 允许同版本新登记顶替）。
- **载荷 + 视图**：项目内容按「谱系 + 版本 + 内容哈希」登记成不可变**载荷**
  （`data/mfw/.payloads/<谱系>/<版本>-<hash8>/` + 同名 `.json` 清单，`project_update/payloads.py`），
  全局一份；每个脚本一棵**视图**（`data/mfw/<12hex>/`，路径永不变，所有按路径键的缓存 /
  备份桶都不用改键；隔离 venv 不按路径，按依赖跨视图共用），满足共用谓词的文件是载荷 / 共用库的硬链接，小文件拷贝，运行期产物私有。
  视图根上的 `.auto_mas_view.json`（谱系、载荷、版本、物化时刻、`switchedBy`、`envConfirmedFor`、
  开发者模式的 `followSource`）是物化事实的唯一来源，不进指纹、不进任何清单，只随目录原子换入、
  不原地改——例外是 `switchedBy` 打完日志后清除、`envConfirmedFor` 确认后写入，以及载荷没换时
  改写 / 摘掉 `followSource`（见下面「跟随来源目录」）。
  谱系键 = `mirrorchyan_rid` > `github` > `name`；**组 = 谱系 + `Update.Channel`，同组永远挂同一个
  载荷**（`lineage.json` 的 `latest[channel]` 只前进，同版本不换 id——例外只有三个：latest
  自带的 MaaFramework 在本机加载不了而新登记的能加载，见 `payloads._replaces_unloadable_latest`；
  新登记的按更高的投影规则版本建（投影补齐、按新规则重新导入同版本），且不是「本机加载不了换掉
  能加载的」，见 `payloads._replaces_older_projection_latest`；新登记的已与官方发行包核对过
  （清单 `releaseCheck.result=clean`）而 latest 是导入来的、又没核对过，规则版本不比它低，见
  `payloads._replaces_unverified_latest`——更新得来的 latest（`source.kind=update`，含区间差量）
  就是发行包的精确投影，视同核对过（`payloads.release_settled`）：核对只比多余的文件、不比内容，
  本地改过的导入不能顶掉原版；`_same_version_rank` 同口径）。「只前进」另有一个例外：手动更新
  把项目发错的高主版本号拉回权威源的版本（`register(misnumbered_rollback=True)`，判定见
  `updater._is_misnumbered_current`），只在 latest 是主版本号更高的正式版时顶替它；自动更新不回退。
  **换不换只在一处判定**：`payloads.decide_latest` 按有序规则表 `LATEST_RULES`（私有渠道
  `always_advance` → 组里没有 latest → latest 不完整 → 版本更高 → 发错版本号回退 → 上面三个同版本
  例外，都不管就保留），迁移时同版本挑一份用同口径的 `same_version_sort_key`；加新例外就往表里加
  一条，别在 `register` 里另写判断。登记时 debug 日志记下定结论的规则。登记与迁移挑同版本之外，
  改写 latest 的只有两处，都不是新例外、不进表：投影补齐后的跟随改指（`projection_heal.repoint_latest`：
  别的渠道已把同一份载荷补齐成新载荷，本渠道 latest 还指着旧的就跟过去，不比版本、不看加载性），
  以及启动期摘掉不再算引用的私有渠道 latest（`embedded_project._prune_follow_source_latest`，见
  「跟随来源目录」的「回收」）。
  开发者模式的脚本例外：它的组是
  谱系 + 私有渠道 `dev:<视图名>`，见下一条。
  谱系 / 载荷 / 版本都不进 `ScriptConfig.json`；**唯一新增的配置项**是下一条的开关
  `Embedded.FollowSource`。
- **跟随来源目录（开发者模式，`Embedded.FollowSource`，默认关）**：给在本地发行包里改东西修 bug
  的开发者用（视图 + 组 latest 让「改来源不生效、改视图被换版本冲掉」）。仍然在视图上跑，只是：
  - **组换成私有渠道** `dev:<视图名>`（`embedded_project.effective_channel`）：组同步、同组传播
    （`GroupMember.channel`）、导入登记、启动期统一到组版本都按它，所以同项目的其它脚本与官方更新
    碰不到它，它的导入也推不动普通渠道。登记用 `payloads.register(always_advance=True)`：私有渠道
    每次导入都前进、不比版本；普通渠道不传，语义一字不改（传了照旧前进，`register` 记一行告警）。
    私有渠道建出的载荷（清单 `channel` 是
    `dev:`）不参与 `settle_same_version_latest` 挑普通渠道的 latest；版本另带 PEP 440 本地段
    `+dev`（`follow_source_payload_version`：`1.5.0` → `1.5.0+dev`，已有本地段的追加 `.dev`），
    所以没有这条过滤的老代码按「版本字符串相等」挑同版本候选时也挑不中它，载荷 id 也与同内容的
    正式载荷不同（`1.5.0+dev-<hash8>`，`+` 本来就在 id 允许的字符里）。视图标记的 `version` 是这个
    带 `+dev` 的载荷版本（界面与「沿用上次同步」的告警里看得出是本地改过的），`Embedded.SourceVersion`
    仍记 interface 里的原版本。
  - **察觉变化**：运行前检查（`ensure_embedded_copy(follow_source_check=True)`，只有 manager 的
    `_check` 传）与手动重新导入。按投影白名单给来源算签名（`follow_source_signature`：投影会带走的
    文件的源相对路径 + 大小 + mtime_ns，≤ 1 MB 的再加内容 blake2b，大文件只看大小与修改时间；外加
    签名格式与投影规则版本），与视图标记 `followSource.signature` 比，路径或签名不同就重新导入；签名在
    复制之前算。老格式签名的标记一定对不上，升级后第一次运行前重导一次，不报错。内容没变（只改了修改
    时间）登记出的就是视图正挂的那份，不重建视图、只原地改 `followSource`。日志一行
    （`describe_follow_source_sync`）：「来源目录有 N 个文件变化（前 5 个路径），已重新导入」/「来源
    目录未变化」，N 按新旧载荷清单的 sha256 比。预览、准备环境等入口不扫来源。
  - **读不了来源时沿用上次同步的版本**（`_sync_follow_source` → `_keep_last_follow_source_sync`）：
    来源目录不在、读文件被拒（`PermissionError`）、`interface.json` 暂时不在或解析失败、投影规则拒绝
    （junction / 符号链接，规则不变）等任何读取 / 投影失败，都**照常在当前视图上跑**，运行日志写一行
    醒目的「【警告】开发者模式读取来源目录失败：原因；本轮沿用上次同步的版本 X（同步于 …）运行」。
    源码形态的脚本，这一条和上面的同步日志开头都写「源码形态」（`_follow_source_label`），与界面上的标签一致。
    只有视图本身不在（没有可跑的副本）才按导入失败处理。「立即同步」不走这条退路，照常报失败原因。
  - **离开开发者载荷不留「本地改过」档**：`_realize_view` 按新旧载荷清单的 `channel` 是不是 `dev:`
    判断（`is_follow_source_manifest`），不看是哪条代码路径进来的——开发者导入、关掉开关、克隆后第一次
    组同步、关掉后被兄弟导入 / 同组传播换走，只要切换的一端是开发者载荷，就既不按同版本「只补缺」也不
    把视图与旧载荷的差异当本地修改留档（那些差异就是从来源同步来的）。
  - **立即同步**（脚本页状态行旁的按钮，`/maafw/embedded/sync` → `api_service.embedded.sync_embedded`）：
    按当前 `Info.Path` 强制重导进私有渠道，**不看签名**（补上修改时间没变而漏检的改动）；内容与视图相同
    时不重建视图、只刷新同步时间。返回的 `message` 就是结果（N 个文件变化 / 内容未变化）。脚本运行中
    （`is_locked`）、项目正在更新、视图预约被占用、来源目录不在都直接拒绝，不排队、不打断。
  - **不更新**：运行前 / 运行后自动更新跳过（`_run_project_update` 开头一行日志）、投影补齐不查，
    `/maafw/update` 的检查与应用都拒绝（`UPDATE_FOLLOW_SOURCE`，源码形态是 `UPDATE_SOURCE_FORM`）。
  - **源码形态**（见下面「源码形态」）一律处在这种模式：`follow_source_enabled` 对导入报告
    `sourceForm` 为真的脚本恒真，开关在界面上锁在开着；源码形态的导入不管调用方传什么都进私有渠道。
  - **关掉**（标记还带 `followSource` 时，`_leave_follow_source`）：回到 `Update.Channel` 组的 latest
    （私有文件照常带，不留本地改过档，见上一条）；视图已在 latest 上就只摘掉 `followSource`；组里还
    没有载荷就按来源正常导入一次；来源也不在就留在当前版本。
  - **复制 / 克隆不继承**：「复制脚本」把新脚本的 `Embedded.FollowSource` 写成关；`/maafw/embedded/clone`
    本来就不抄这个开关。源脚本挂的是开发者载荷时，目标挂源原渠道（`Update.Channel`）组的 latest，
    不复用本地改过的那份（`clone_embedded_copy(group_channel=…)`）；组里还没有正式版本就抛
    `FollowSourceCloneUnavailable`：克隆接口改按源的来源目录正常导入（目标自己的组，消息里说明），
    来源也不在就拒绝并让用户直接选目录；「复制脚本」先不建视图，第一次运行前按继承的 `Info.Path` 导入。
    源码形态没有正式渠道，克隆一律走按来源导入，目标继承 `sourceForm` 报告，照样处在开发者模式。
    缺视图重建（复制后第一次运行、来源也不在）同样不继承：`_rebuild_from_group` 与视图不完整的重建
    走 `_formal_group_target`，普通渠道组里没有正式版本时不退到兄弟挂的开发者载荷，按重建失败报错。
  - **开发者载荷不进普通渠道**：`propagate_payload` 对非私有渠道遇到开发者载荷直接不传播（调用方拿错
    渠道也兜得住）；导入接口按导入**之后**的实际渠道传播——首次选源码目录时导入前还是普通渠道，
    导入中才认出源码形态、换成私有渠道。
  - **回收**：私有渠道的 latest 只在脚本还在、开着开关、视图还在这个谱系上时算引用；其余由启动期
    `collect_payload_garbage(follow_source_views=…)` 从 `lineage.json` 摘掉（本进程起来之后登记的不碰），
    被新导入顶掉的、关掉开关或删脚本留下的开发者载荷随后按普通规则回收，视图挂着的照样留。
- **源码形态**（`ProjectionRules.source_layout`，导入报告 `sourceForm`）：interface 在 `assets/`
  这类子目录里、声明的路径越出它落在来源根上（M9A 式源码仓：`assets/interface.json` +
  `"child_exec": "python", "child_args": ["-u", "./../agent/main.py"]`，根上 `agent/`、
  `requirements.txt`，没有 `python/` 与 `maafw/`）。只在导入（`strict`）时认；以前整包拒绝。
  - **视图 = 发行包的平铺布局**：`assets/` 里的提升到副本根，`assets/` 之外的（`agent/`、`runner/`、
    `config/`、`requirements.txt`、≤ 64 MB 的小顶层条目）原样放到副本根（`output_path`），与项目自己
    打包时得到的布局相同；平铺后与 `assets/` 里同名的根上条目丢掉并告警。项目根 = interface 所在目录
    = 视图根，`{PROJECT_DIR}`、`{RESOURCE_DIR}/../..` 这类相对资源的写法在视图里与发行包一致。
  - **interface 不改写**：越出项目根的 agent 入口由 `interface.agent_entry.flattened_entry_path`
    兜底（去掉开头的 `../` → `agent/main.py`），投影（`cfa_agent_entry`）与 planner 共用；CFA 的固定
    兜底 `agent/main.py` 是它的特例。不改写是因为 runner / planner / 预览 / 导入检查都按 base_dir
    解析路径，平铺之后一处兜底就全对，而改写 interface 要在每份载荷里维持一份与来源不同的文件。
  - **运行时**：裸 `python` → 隔离 venv（按视图根的 `requirements.txt`，见下面「隔离 venv 跨视图共用」）；没自带原生库 →
    runner 按声明（范围）解析出确切版本，agent 的 maafw 钉成**同一个确切版本**（宿主准备时传
    `environment.maafw_version`，worker 传实际加载的 binding 版本，见
    `runner.environment.resolve_project_maafw_requirement(runner_maafw_version=…)`）——照抄范围让 pip
    自己挑会落到协议不同的版本上。这条对**所有没自带原生库的项目**都成立，不限源码形态（没自带
    `maafw/` 的发行包以前照抄范围，升级后依赖哈希变了，会重建一次隔离 venv）；自带原生库（确切版本）
    的项目不受影响。
  - **这次导入走不走私有渠道只看开关**（`follow_source_switch_on` / `import_channel`）：源码形态由导入
    按这次的投影布局自己认、强制进私有渠道；导入前的报告是上一次的结果，源码形态的脚本改选成发行包
    目录时它还写着 `sourceForm`，按它判会把发行包登记成开发者载荷。导入完成、报告写回之后，组同步与
    传播照旧按 `effective_channel`。
  - **始终跟随来源目录**（见上面「跟随来源目录」），不做项目更新；界面上显示「源码形态」标签。导入报告里的
    `bundledMaaFWVersion` 只认被投影带走的原生库（源码仓里躺着的 `dist/maafw` 不算）。
  - **只放行运行时映射得回来的越界**：越出 `assets/` 的声明目前只有 agent 的第一个 Python 入口有运行时
    映射（`flattened_entry_path`）。`resource.path`、原生 agent 可执行文件、controller / languages 等其它
    越界声明导入时就拒绝（`ProjectionError`，说明哪条声明、怎么改），不让用户看到导入成功却建计划时
    「路径越界」。要支持新的越界写法，先补运行时映射再放行。
  - `"child_exec": "uv"`（`uv run …`）**不支持**：uv 按项目自己的锁文件另建环境，maafw 未必与运行用的
    MaaFramework 同版本。导入时报清楚的错（`agent_entry.describe_uv_agent`），老副本在准备运行环境时报同一句。
- **投影**：按 interface 白名单（`project_update/projection.py`；`build_projection_rules` 按声明类别
  分在 `_ProjectionScan` 的 `_scan_*` 里，扫完再判源码形态、依赖清单、自带原生库、小顶层条目），
  **白名单之外的顶层条目
  剩余 ≤ 64 MB 的也带走**（MaaEnd 的 `data/`、`locales/`，MaaYYs 的 `assets/答案.csv`，M9A 的
  `data/activity` 都没在 interface 里声明却是 agent 运行时要读的；更大的顶层目录、根上没声明的
  exe / dll、.NET 外壳的 `libs/` 才是外壳运行时）。**能确认是外壳才剔，确认不了一律保留**（规则
  第 2 版）：按名字剔的只剩顶层的界面程序（MFAAvalonia / MXU / MFW / MaaPiCli）、Qt 界面运行时与
  顶层运行期目录（`cache/ logs/ temp/ update/ backup/`、MFAAvalonia 旧版自更新的 `temp_res/` 等，
  导入的多半是用户在用的目录）。**`debug/` 不在其中**：里面除了日志还有项目读回的持久状态（MaaEnd
  的 `debug/record/` 用 `random_salt.txt` 算账号 ID，MPA 的 `debug/*_zone_offset.json`），它不进载荷
  （`payloads.PAYLOAD_STRIP_ROOT_DIRS` 登记前整个剔），导入时直接从来源的 `debug/` 挑状态文件（不是
  日志、截图、临时文件，单个 ≤ 1 MB；**不看投影去留**，截图多了 `debug/` 会超过 64 MB 被整个丢）作为
  视图私有文件放进视图（`embedded_project._runtime_state_seed`，视图里已有的不覆盖），之后随切换原样带着走；
  没声明的顶层目录是 Python 解释器、.NET 托管库 / RID 资产、标准形态的 MaaFramework 原生库目录
  （库直接在目录里，或目录里只有原生库）的，按内容确认后整目录剔；只是某处带着一份原生库的只剔那几个
  库文件（`ProjectionRules.confirmed_shell`）；任何深度都剔的只有 `__pycache__` 这类没有歧义的缓存、
  版本库目录、`.pyc/.log/.tmp` 后缀与 MaaFramework 的 `.lib` 导入库。外壳是冻结的 Python 程序时（根上直接躺着没人
  声明的 `python312.dll`，Maa_bbb 的 MFW.exe 就是），它散在根目录的二进制依赖包（带 `.pyd`，或
  `*.libs` / `*.dist-info`）也不带：agent 子进程的 `PYTHONPATH` 是项目根，`backports/zstd/`
  这种没有 `__init__.py` 的半截包会变成命名空间包盖住真正的模块——副本上 pip 就是这样崩的。
  视图路径由脚本 ID 推出（`embedded_copy_dir_name`：uuid 去连字符取前 12 位，短是为了 pyc 前缀树
  与深层 site-packages 不撞 MAX_PATH）、不进配置、不可手改；来源目录一个字节不动、也不由 MAS 删。脚本页
  「选择本地目录」就是 `/maafw/embedded/reimport`：投影成载荷、登记进脚本所在渠道的组，视图切到组的
  latest——导入的比组新、或同版本而投影规则版本比组的 latest 高（组的载荷是旧规则建的）、或同版本
  已与官方发行包核对过而组的 latest 是没核对过的导入（见下面「旧版本残留与发行包核对」；latest 是
  更新得来的原版时不换）就推进整组（空闲的兄弟立即切），其余相同或更旧的就上组当前版本（「导入时
  版本」那行日志仍是所选目录的版本）。开发者模式下登记进私有渠道、就是它的 latest。没有 enable /
  disable 这种开关路由——唯一的开关是 `Embedded.FollowSource`（上面「跟随来源目录」，仍在视图上跑），
  `Embedded.*` 里其余只有报告、来源版本与导入时间。删脚本连带删视图；载荷与共用库的回收在启动期。
- **换版本 = 切视图**（`embedded_project.switch_view`，§3.2）：在 `data/mfw/.staging/` 里按新载荷重建
  链接森林、把视图私有文件带过去（同谱系才带；`.pycache` 不带）、被本地改过的受管文件以新版本为准并
  留档到 `data/maafw_project_state/<视图哈希>/local-modified/<from>→<to>-<时间>/`、标记先写进
  staging，再两次目录 rename 换入；journal 在 `data/mfw/.switch/`，启动期 `recover_switches` 按盘上
  状态收尾（没有「重跑切换」这一档）。**写穿防线**：往 staging / 视图 / 载荷放文件一律
  `blob_store.place_fresh`（独占新建，已存在的目标只摘目录项）；旧视图私有、新载荷也有的路径以载荷
  为准——唯一例外是 `contracts.RUNTIME_STATE_FILES`（M9A 账号记录这类运行期状态）：视图里有就原样
  带过去，不比内容、不留档，否则换版本会把它换回导入那天的内容或当成删掉的文件丢掉（用户导入的多半
  是自己一直在用的目录，里面早有这些文件）。切换方向无关：升级、改渠道降级、迁移统一都是这一条。
  例外中的例外是 `contracts.VERSION_BOUND_STATE_FILES`（M9A 热更新的 `data/manifest_cache.json`）：
  它和随版本发布的 `data/` 表成对，换到另一个载荷时只取新载荷那份（没有就不要），带视图这份会让
  缓存比数据新、热更新一直跳过；同一载荷上重建视图（采纳、修复）时照常带。它必须是
  `RUNTIME_STATE_FILES` 的子集（`_realize_view` 先判它、再判运行期状态，不在后一张表里的同载荷重建时
  会按受管文件处理），落点：`contracts.py` 里 `RUNTIME_STATE_FILES` 按构造并入它，加版本绑定的文件
  只往它里面加。自带解释器里的 maafw
  binding（`…/site-packages/maa/`、`maafw-*.dist-info/`）也不按受管文件处理：它是准备运行环境
  钉回的（或 agent 部署脚本升级的），切换时一律以新载荷为准，不留档、不当私有文件带过去，
  下次准备再按新原生库钉回（`embedded_project._is_maafw_binding_path`）。
- 内置运行从不启动项目自带的界面程序（MFW.exe / MFAAvalonia / MXU），副本去掉的只有外壳、
  .NET 托管库、界面用的运行时、缓存与日志。**项目自带的运行时原样带走**：MaaFramework 原生库
  目录（`maafw/`，MFAAvalonia 布局下是 `runtimes/win-x64/native`）与 agent 自带的解释器目录
  （`python/`）。理由是真机上两个项目两种死法：M9A 的 agent 写死 Python >=3.13,<3.14，用宿主
  3.12 建的隔离 venv 起来即退（宿主只看到「Agent 进程已退出」）；MaaYYs 的 Go agent.exe 启动
  时从 `<项目>/maafw` 加载 MaaFramework，找不到直接 fatal。自带的 DLL 可能是自定义构建、
  site-packages 里可能有 requirements.txt 没写的包，「按版本从运行池重建等价环境」验证不完。
  原样就是原样：分类表在这三个目录里不起作用，只剔 `__pycache__`——CPython 发行版本来就有
  `pip/_internal/operations/build` 这种叫 `build` / `debug` 的目录，投影掉了副本上 pip 直接
  ModuleNotFoundError（Maa_bbb 真机踩到）。
  带走之后 runner（`project_maafw_runtime_path` 优先项目自带）与 agent 用的就是发行包里那份，
  与路径模式完全一致；运行池只在项目本来就没自带时兜底——也与路径模式一致。代价是省下的
  比例：MaaYYs 29%（Go agent，196→138 MB）、M9A 57%（Python 3.13 自带 158 MB，660→283 MB）。
  `contracts.py` 里那个 `.auto_mas_maafw_native_runtime.json` 只剩指纹忽略用，没有代码再往
  项目里铺运行时。
- **旧版本残留与发行包核对**（`project_update/release_check.py`）：导入目录是旧版本被新包覆盖过的，
  新版已删掉的 pipeline 会跟着进载荷，节点重名让 MaaFramework 整包拒收（MAA_Punish v3.12.7 的
  `auto_battle.jsonc`）。导入（普通渠道，`embedded_project._verify_import_release`，硬时限、核对不了照旧
  导入）与运行时资源包加载失败（`runner_task._recover_resource_failure` → `view_release_check`，每次运行
  一次）各核对一次：依据是缓存的同版本完整包 → GitHub 资产中央目录（Range），残留口径同
  `apply._import_origin_orphans`（资源目录含控制器的 `attach_resource_path`）。导入时残留不进载荷、进报告
  `excludedReasons`（原因 `not-in-release`）；运行时建「旧载荷减残留」的同版本载荷、顶替 latest（只顶
  没核对过的导入，更新得来的原版视同核对过）、切视图，然后不重启游戏 / 模拟器立刻再跑一次（不占重试
  次数，日志里这一次不编号）。运行时看的是**本视图自己挂的**载荷：视图不在组 latest 上（同组兄弟已清理
  过、传播时本脚本正在跑）就经组同步切过去再核对，视图换了就重跑——只看组 latest 会对着残留还在的
  视图说「没有多余的文件」。**只在同一版本内切**：组 latest 已是另一个版本时运行中不切（interface、运行
  计划、运行环境确认都是按本视图的版本做的），留给下次运行前的组同步；等锁时被推到新版本、视图跟着换了
  （`CleanOutcome.version_changed`）也不重跑。发行包过不了 `range_delta._check_layout`（解压时会改名的
  条目、重名条目、只差大小写的目录）记为核对不了、不删文件：条目名与落盘文件对不上，照条目名比会把
  正式文件当残留删掉。导入时核对的后台线程超时后由 `release_check.TreeGate` 挡住，`verify_tree`
  返回后不再读 staging（调用方紧接着就把它改名成载荷）。「项目下次更新时会自动清掉」只对导入来的载荷
  说（下次更新一律全量包、跑 `_import_origin_orphans`）；更新得来的走差量包只按删除表删，不做这个承诺。
  结果记在清单 `releaseCheck`。资源包加载失败
  （`MaaFWRunResult.resourceFailure`）一律不重试，消息按原生 ERR 行说出原因（`resource_failure.py`，
  优先读本次 `.maafw.log`：stdout 那份按控制台代码页转过，中文可能成了 `?`）。
- **按内容共用文件**（`project_update/blob_store.py`）：共用谓词只有一个，
  `projection.is_shared_path(rel, size, private_paths)`——≥ 64 KB、首段不是 `config/ debug/ logs/
  temp/ cache/ .pycache/ .mas-update*`、后缀不是 `.lock .sha256 .pth .log .tmp`、不在 `*.dist-info`
  里、不在谱系学到的 `privatePaths` 里（不再按后缀白名单）。满足的按 sha256 存进
  `data/maafw_blobs/<ab>/<sha256>`，载荷与视图里是指向它的 NTFS 硬链接，同样的字节只存一份；导入、
  更新构建新载荷、视图物化都走它。三条铁律：**永远不往已有文件里写**（硬链接没有写时复制）；小文件
  不进库（锁文件、`.pth`、dist-info 这类最可能被原地改写，M9A 的 bootstrap 就往 `python/*.lock` 里
  追加写）；链接失败就退回复制。可写的东西靠四层挡住：尺寸、排除表、运行期新建即新 inode、运行
  收尾的写穿巡检（`tools/embedded/view_audit.py`：nlink>1 且修改时间晚于物化时刻才读 sha，确认就
  隔离 blob、记 `privatePaths`、标载荷 `damaged`；`damaged` 的载荷下次更新只要全量包）。回收在启动期：`MaaFWMaintenanceService.clean_embedded_copies`
  删无人引用的载荷（`embedded_project.collect_payload_garbage`：引用集 = 视图标记 ∪ 未完成切换的 to，
  谱系还有视图时再加它的 latest（私有渠道的 latest 只在开着开发者模式时算，见「跟随来源目录」）；一个视图都不剩的谱系整个收走，视图丢了但脚本还在的按导入来源保住；
  本进程起来之后建的不收。回收跑在后台、API 已在服务：删之前要在该谱系的 `lineage_lock` 内按盘上最新
  状态再判一次，否则判定之后刚登记的载荷会被一起删掉；整谱系收走时放锁后还会删锁文件和空目录，
  所以 `DurableFileLock` 的等待方碰到目录没了要重建再等，不能把这次撞车报给调用方），随后 `MaaFWMaintenanceService.clean_runtime_blobs` 删 `st_nlink == 1` 的 blob。本机实测：inode 被映射（DLL 已加载）时
  删不掉的是它的最后一个链接，与进程经由哪个名字加载无关——视图里的名字（含正被经由加载的
  那个）都能删，只要库里的 blob 还在（见 `blob_store.py` 模块说明）。
- **同一项目再建一个脚本**走 `/maafw/embedded/sources`（候选）+ `/maafw/embedded/clone`
  （`embedded_project.clone_embedded_copy`）：从源脚本挂着的载荷物化目标视图（源正在切换就取 journal
  的目标），不读源视图、不要源空闲、源的运行期状态不带；只预约目标（源还是没采纳的老副本、只能按目录
  克隆时才预约源，源被占用就拒绝）；`Info.Path` 与
  `Embedded.*`（开发者模式开关除外）沿用源（两者必须成对继承），`Update.Channel` 也沿用源——
  复用的就是源那一版，渠道不跟着走的话第一次运行前的组同步会把它切到默认渠道的版本；类型随项目。
  「复制脚本」（`Config.add_script`）复用同一个函数。
  源挂的是开发者载荷时不复用它，见「跟随来源目录」里的「复制 / 克隆不继承」。
  视图与来源都没了时，`ensure_embedded_copy` 从同来源兄弟的谱系（没有兄弟就按载荷清单记的导入来源
  反查）按本脚本渠道的 latest 重建——来源可删这句承诺靠它兜底。更新包下载缓存
  `data/maafw_update_cache` 按 源 + 版本 + 文件名 命中（Mirror 酱按包的 sha256：它的一次性下载地址每次都变），启动期 `MaaFWMaintenanceService.clean_update_cache`
  删 7 天没碰过的（`transport.prune_update_cache`）。
- **启动期一次性迁移**（`MaaFWMaintenanceService.migrate_embedded_copies_to_payloads`，排在各项回收之前，整段
  在后台任务里跑、不挡主定时器；期间拿不到视图预约的运行按「正在切换版本」跳过一次）：没有标记的老
  副本逐个采纳（`embedded_project.adopt_view`：**载荷内容以视图自身为准**——按视图自己的 interface
  算投影白名单，白名单内、不是已知运行期状态 / 日志的全部进载荷，内容取视图现状；更新器清单与来源
  目录只用来标 `origin`，不决定去留，否则「来源旧、视图新」会登记出残缺载荷）。全部采纳完再统一定
  同版本的 latest（`settle_adopted_latest`：自带 MaaFramework 在本机能加载的优先，其次有清单背书
  的、文件集合是超集的、文件多的优先，与脚本顺序无关），然后把每个组统一到 latest（运行中 `is_locked` 的脚本跳过，留给它的收尾同步或下次
  运行前检查；切过的标记记 `switchedBy=迁移`）；同版本合并时被切视图独有、或同路径内容不同的文件
  旧内容进 `local-modified` 留档。采纳失败的原样保留、下次再试。导入与采纳都把脚本记着的来源目录记进
  `lineage.json.knownSources`：视图丢了反查谱系重建、整谱系回收认「脚本还在」都看它（更新得来的载荷
  清单里没有导入目录）。
  没有待采纳副本时仍复核 latest 与视图，补完上次在采纳后中断的收尾；候选只取采纳标记的
  `adoptedChannel` 与本轮渠道相符的视图及组现有 latest，不用当前配置渠道给旧视图重新归组，也不以
  清单初次登记渠道推断共享载荷归属。`adoptedChannel` 只随成功采纳的标记原子换入，重建丢失载荷时
  保留原事实、普通切换不继承；缺少此事实的旧标记仅沿用组现有 latest。采纳也跳过运行中脚本。
  取消先等正在执行的文件操作结束，再释放尚未移交的预约并清除 `migration_active`。
- **发行包形态与源码形态**：发行包（interface 在包根，自带 `python/` / `maafw/` 或不带）照常导入、
  照常更新。M9A 式源码仓（`assets/interface.json`、agent 在 `assets/` 外）按上面「源码形态」平铺导入，
  始终跟随来源目录、不做项目更新（`child_exec: uv` 不支持，见「源码形态」）。被 CFA（MFW-PyQt6）源码热更新过
  的目录是另一种平铺：它把 `assets/` 平铺到包根、`agent/` 放包根，interface 留着源码写法的 agent（识宝的
  `../agent/main.py`）；入口按 `interface/agent_entry.py` 的兜底解析（投影与 planner 共用），长期保留，
  不在导入时改写载荷里的 interface；第一次走 MAS 更新后就是发行包写法。
- Python agent 的解释器三种落法（`agent_env/planner.py`）：项目自带 `python/python.exe` 存在 →
  `project_python`；声明的是自带 Python 模式但文件不存在，或者裸写 `python` 让 PATH 去找
  （PI v2 示例与 MAA_Punish 的写法）→ 隔离 venv（`isolated_venv`，按依赖跨视图共用，见下一条）；
  其余 → `external`。目录里没有 Python **不是错误**。裸 `python` 不能原样交给 PATH：
  worker 跑在运行池 venv 里，Windows 上 `CreateProcess` 先按父进程（基解释器）所在目录找，
  且用的是父进程的 PATH，传给子进程的 `env["PATH"]` 不参与查找，结果永远是没装 `maa` 的
  基解释器。隔离 venv 只装 `requirements.txt` 写的（`maafw` 钉成自带原生库的版本）；**压根
  没有 `requirements.txt` 时按同一版本补一条 `maafw`**——MFW-PyQt6「嵌入式 Agent」模式
  （FOS / MAA_Punish，`CFA_setting.json` 里 `embedded=true`）把 maa 冻进外壳自己的程序里，发行
  包不写依赖，不补的话 agent 一句 `import maa` 就退出。写了清单但没声明 maafw 的照旧不追加。
  **项目自带 Python**（`project_python`）里的 binding 也必须与自带原生库同版本：项目自己的部署
  脚本会 `pip install --upgrade maafw` 升到 PyPI 最新（Maa_bbb v1.12.8 实测 5.13.1/协议 8 对原生库
  5.11.1/协议 7），表现只有一句「AgentClient 连接超时」。准备运行环境时对**内嵌视图 / 更新时新载荷的 staging**把它钉回
  原生库版本（副本是我们铺的；用户自己的目录只说明不动），环境指纹把该 dist-info 名算进去，
  否则钉回那一步会被缓存跳过；失败路径的诊断（`_describe_agent_maafw_mismatch`）两边都说清。
  **钉回挡不住 agent 运行期自己升级**（MAA_bbb 的 `agent/deploy/deploy.py` 在 agent 启动后
  `python -m pip install --upgrade -i <镜像> MaaFw`，新 `maa` 包与 runner 的旧原生库混用、自定义动作
  静默失败、任务照报成功）：worker 起 Python agent（`project_python` / `isolated_venv`）时给它的环境挂
  `PIP_CONSTRAINT` / `UV_CONSTRAINT`（`runner._inject_agent_pip_constraint`），约束文件
  `data/maafw_agent_constraints/maafw_agent_<路径哈希>.txt` 只写 `maafw==<与钉回同一来源的版本>`
  （`environment.agent_maafw_pip_constraint`）。三条别改错：**项目自己钉了 maafw 就不挂**
  （requirements.txt / pyproject `[project].dependencies` 的确切版本、离线目录里的 `maafw-*.whl`，或声明
  的范围不含该版本）——M9A 钉 5.12.3 而自带库 5.13.0、MaaStarResonance 钉 5.12.1 而自带库 5.11.1，
  挂上约束它们的自装直接 ResolutionImpossible。「自钉」**只认这三处**（根 requirements.txt 及其 `-r`
  展开、pyproject `[project].dependencies`、离线 wheel）：只在 `agent/requirements.txt`、
  optional-dependencies、dependency-groups 或 `[tool.poetry]` 里钉版本的项目会被当成没钉而挂上约束，
  遇到真实项目再扩来源；**值写 `file:` URI**——pip 与 uv 都按空格拆这两个
  变量，装在带空格目录里的裸路径会让项目的 pip 整条报错；**文件只写 ASCII**——pip 读没有 BOM 的约束
  文件按本机代码页解码。目录由宿主经 `AUTO_MAS_MAAFW_AGENT_CONSTRAINT_DIR` 交给 worker（不进 agent
  环境），没设就不挂；pip 带 `--isolated` 时会忽略这个变量。
  **没装也补装**：健康检查报缺模块、自带解释器里压根没有 binding 时（换版本时视图不带它，而
  MaaTOT 这类「首次启动自己装依赖」的项目有自己的「已装过」标记、不会再装），走同一条钉回路径
  按原生库版本补装一次，装上再检查一次；补装失败与钉回失败一样只记日志。之后**三个条件同时满足**
  才照常起 agent、让它自己装：失败是缺模块；项目带自装材料（requirements.txt / pyproject.toml、
  `*.whl`、`get-pip.py`）；**补装之前** site-packages 里根本没有 binding（没有 `maafw-*.dist-info`
  也没有 `maa/`，补装失败后的半装状态不算）。出厂就带 binding 的项目（M9A、MaaStellaSora、MaaFgo、
  MaaNTE 也都有 requirements.txt）缺别的模块照旧拦。
  **三个调用方三种口径**（`_prepare_project_python_env` 的 `lenient`，经 `prepare_agent_envs` /
  `prepare_project_environment` / `_prepare_project_environment_sync` 的 `lenient_health_check`
  传下来，**缺省严格**，漏改的调用点不会被放宽）：
  - **运行时宽松（报错照跑）**：worker 起 agent 前（`runner.prepare_agent_python_envs`）与宿主
    运行前 / 运行后的环境确认（`_ensure_project_environment`）。检查不管因为什么失败都先试补装，
    复检仍失败就写一行醒目的【警告】（原因照原文）、照常起 agent。原因记进结果的
    `agents.healthWarnings`：这次不写环境缓存、不记 `envConfirmedFor`（下次照样重查，编辑页
    不会因此显示「已就绪」）；agent 很快退出时「Agent 进程已退出」的报错后面带
    「运行前检查发现：<原因>」。
  - **更新预检严格**（上面的三条件规则）：预检决定新版本换不换上来，放宽的话缺模块的坏版本会
    顶掉能用的旧版本、之后每次运行都失败，只能等项目出新版。
  - **编辑页手动准备严格**：失败照旧报出来。手动更新、同组传播后的确认、投影补齐也走缺省严格。
  site-packages 里残留多份 `maafw-*.dist-info`（M9A v4.9.0 出厂就带 5.12.3 + 5.13.0）时，钉回前
  先把版本不是最高的那些记录目录**挪进**副本根下的 `.maafw-repin-stash-*`：pip 按目录顺序取第一份
  记录、我们取最高版本，不挪的话 pip 要么说「已满足」什么都不做，要么只卸掉旧记录，两种结果下次
  准备都还要再钉、改了记录集合的那次还会被当成并发改动「拒绝缓存旧运行环境」
  （`agent_env/env._stale_maafw_dist_infos`）。**只有 pip 成功且复读版本一致才删暂放目录**；pip 失败
  （断网、中继挂了、索引缺版本）或复读不一致就原样挪回——dist-info 集合是指纹输入，失败时集合必须
  回到钉回前，否则离线本来能过的项目会被拒绝缓存（钉回「任何一步失败只记日志，不拦准备」）。
- **隔离 venv 跨视图共用**（`agent_env/venv_share.py`，方案「MFW副本复用与版本切换」§7-5）：目录
  `config/maafw_agent_venvs/maafw_venv_<16hex>`，键 = 装进去的依赖清单（洗过、maafw 钉成确切版本、
  补过引导包，即 manifest 的 `requirements`）+ maafw requirement + 宿主身份（平台 / 架构 / 解释器实现
  与小版本），任一不同就是另一个目录；同一项目建几个脚本、依赖没变的新版本都用同一份，只装一次。
  - **本地依赖退回按视图隔离**（`venv_share.is_local_requirement`，PR #1711 审查 P2）：pip 以各自项目
    目录为 cwd 安装，`./wheels/foo-1.0-py3-none-any.whl` 这一行在两个项目里可能是两份不同的 wheel；
    按文本共用时后准备的视图命中前一个的 manifest、跳过安装，用的是别人的包。清单（含 `-r` 展开后的
    子清单）里只要有一条本地依赖，键里就加视图路径（`isolatedProject`，manifest 里也记这一项），
    重建判据也照改动前的按路径隔离：目录名虽仍是 16 位，比完键还比项目路径 + interface + 依赖清单
    ——视图路径换版本不变，`requirements` 文本不变而本地包内容变了时，只比键会跳过安装、跑上一版的包。
    认作本地：含 `/` 或 `\`、以 `.` 开头、Windows 盘符、不带路径的本地归档名（`.whl` / `.zip` /
    `.tar.gz` 等，照 pip）、`file:` 与 `git+file:` 一类链接、`名字 @ file:...` / `名字 @ ./...`；
    远程 URL（`https://`、`git+https://`、`名字 @ https://...`）照旧按文本；`-e` / `--editable` 读清单时
    就报错，到不了键。宁可多认（只是少共用）不可漏认（会串用）。**不按内容哈希**：wheel 可能上百 MB、
    目录没有有界又可靠的指纹，而键在建计划、每次准备、启动期回收都要算；真实语料（walkref 的 m9a、
    Maa_bbb）没有本地依赖，退回隔离只影响少数项目。纯 PyPI / 远程 URL 清单的键不加字段，与加这条
    规则前逐字一致，已建好的共用目录照常命中。
  - **宿主身份不含具体的引导解释器**：宿主与 worker 挑出来的本来就可能不同（worker 的
    `sys.executable` 是运行池 venv），按它分会在宿主刚建好的旁边再建一份；它记在 venv 的
    `pyvenv.cfg`，引导解释器没了照旧按「基解释器已不存在」重建。解释器小版本（本进程的
    `sys.version_info`，引导解释器与它同版本）进键：发版换了 Python 小版本时不沿用旧版本建的那份。
  - **计划阶段不一定知道最终目录**：项目没自带原生库、只声明范围的，maafw 要等 runner 解析出版本
    才定。`compute_isolated_venv_path` 先看本视图的引用记录（`.refs/<视图路径哈希>.json`：上次准备
    实际用的目录 + 当时建计划算出的键，键对得上才信），`prepare_agent_envs` 再按确切版本定一次并
    **改写计划**（`isolatedVenvPath` / `executable` / `command[0]`），worker 起 agent 与结果里的计划都
    是改写后的。新增读计划里 venv 路径的地方要在准备之后读，或者走 `compute_isolated_venv_path`。
  - **重建判据**：共用目录只比 manifest 的 `venvKey` 与 `requirementsHash`；`projectPath` /
    `interfaceHash` 只记建它的视图，不参与——否则另一个视图、依赖没变的新版本会把别人正在用的
    删了重建（本地依赖退回隔离的目录例外，见上，它只有本视图用）。目录名与本项目的键对不上直接拒绝（`_prepare_isolated_venv_env`），不按本项目判据动它。
    重建先把旧目录改名成 `<名>.trash-<随机>` 再删（改名是原子的，不再像 `rmtree(ignore_errors)` 那样
    删一半）；改名只在有人以不带共享删除的方式开着里面的文件时失败，这时报「正被占用」、不动它。
  - **运行中的 venv 没有锁保护**：agent 跑着时不持锁，改名也挡不住它（10-27 实测：Windows 上运行中的
    `Scripts\python.exe`、已由 ctypes 加载的 DLL 都不挡整个 venv 目录改名，删完存活进程再 import 就
    `ModuleNotFoundError`）。共用 venv 不被别的视图删掉，靠的是「键相同就不重建」：共用目录只在基解释器
    没了、结构不完整、依赖清单缺失或损坏时重建，那时它对同键的所有视图都已不能用（本地依赖退回隔离的
    目录另在 interface 变化时重建，键含视图路径、只有本视图用，与改动前相同）。要放宽重建判据，
    先补运行期的租约（如 worker 起 agent 前持共享锁）。
  - **并发**：准备期间持 `isolated_venv_guard`（本进程线程锁 + `.locks/<名>.lock` 字节锁，宿主与
    worker 跨进程也串行），等线程锁、等锁文件都在日志写「正由另一处准备」，两段合计 30 分钟超时；
    等的一方只会看到建好的或没建的。锁文件一般不删，回收删掉目录后才去掉（`discard_venv_lock_file`：
    `*.trash-*` 总删，正常名只在 Windows 上删）。
  - **升级前按路径建的老目录**（`maafw_venv_<12hex>`）不迁移、不改名（venv 不可搬家）：共用目录还没
    建、老目录按老判据（项目路径 + interface + 依赖清单都没变）还能用时第一跑沿用它，不重建、不联网；
    项目一更新或同依赖的共用目录建好就换过去。
  - **回收**（启动期 `MaaFWMaintenanceService.clean_agent_venvs` → `planner.collect_orphan_agent_venvs`）：存活 =
    各存活视图引用记录里的目录 ∪ 建计划会算出的目录 ∪ 没有引用记录的视图的老目录；存活视图的引用
    记录读不出来就整轮不回收。照旧跳过刚动过的，锁被占的也跳过；无主的引用记录一并删。
  - **更新预检不参与共用**：仍建在池根下的 `precheck_agent_venvs`，但每个 staging 一个子目录
    `s<staging 路径哈希 10 位>`（`precheck.precheck_staging_agent_root`），用完整个删掉
    （`precheck.cleanup_precheck_agent_venv`）。不能让预检 venv 在 `precheck_agent_venvs` 下按键共用：
    上次预检被杀或没删干净的同键残留会被判「要重建」，而 `_reset_isolated_venv` 只肯重建
    `maafw_agent_venvs` 下的目录，预检直接失败、记成 `other`，这个版本的运行前自动更新就停住了；
    两个同依赖的预检并发时，先结束的也会删掉另一个正在用的那份。没有「预检那份直接提升为正式 venv」。
- **项目自带 Python 的健康检查要和 agent 真跑时用同一份原生库**（`agent_env/env._build_project_python_probe_env`）：
  M9A 的发行包不在自带解释器的 `site-packages/maa/bin` 放库，agent 在 `import maa` 之前自己把
  `MAAFW_BINARY_PATH` 指到 `runtimes/<rid>/native`（它的 `agent/maafw_paths.py`）。检查沿用 pip 的环境、
  这个变量已被剔除，所以 `maa/bin` 不在、项目自带库（`MaaFramework.dll` + `MaaAgentServer.dll`）又齐时
  由检查替它指过去；不这么做，导入的 M9A 全部卡在「项目 Python 或 MaaFW Agent 模块不可用」，
  更新预检也永远过不去（v5.6.0 真机）。`maa/bin` 在时不设，照旧用 wheel 自带那份。
  runner 起 agent 时按同一个函数（`agent_env/env.project_python_agent_binary_path`）给 agent 设
  `MAAFW_BINARY_PATH`（agent PATH 里 runner 那份原生库目录也排在项目目录最前）：M9A 见到已设就沿用，
  不再自己按 `runtimes/` → `maafw/` 的顺序找，两份原生库并存时也与 runner 同一份。原生 agent
  （Go / C++）固定从 `maafw/` 加载、指不过去，runner 选的不是它且版本不同时启动前就报混装
  （`runner._check_native_agent_runtime`），不等连接超时。
  检查失败时界面与报错第一行只给 traceback 的最后一行（项目目录换成 `<项目>`：任务结果与预检失败通知
  只取第一行、再截 200 / 120 字），完整输出逐行带 `[MaaFW 详情] ` 前缀、只进 `.worker.log` / 后端
  日志——worker 转发（worker 发事件时据此定 `audience`）、`embedded_manager._append_update_log`、编辑页准备环境（`api_service/agent_env.py`）
  与手动更新（`api_service/update.py`）四处都按这个前缀拦在界面外，新增的日志出口也要拦。子进程输出进日志一律按结尾截（`runtime_pool/_shared.output_tail`），
  截开头会正好丢掉异常那一行——那次现场所有日志都断在 `File "D:\douy`。
- `Run.RunTimeLimit` 是套在单个用户整次 MaaFW 运行上的**硬超时**，与其他专项的"日志停滞超时"
  不同义。截止时刻随 job 交给 worker（`runDeadlineAt`）：到点 worker 自己 post_stop 当前任务、
  截一张 `timeout` 图、把已完成的任务连同 `timedOut=True` 正常回传；宿主的 `asyncio.wait_for`
  只在其后加一段宽限（`_RUN_DEADLINE_GRACE_SECONDS`）兜底，worker 没停下才强杀，那时才没有截图
  和进度。`Run.TaskTimeLimit` / `TaskTimeLimitOverrides` 是单任务时限：只停卡住的那个任务，计划里
  第一个任务或特调声明的关键任务（`abortRoundMessage`）结束本轮，其余记一条失败后继续；继续之前先等
  停止真正生效（`_wait_task_deadline_stop`，上限 `TASK_STOP_SETTLE_SECONDS`），否则下一个任务会被
  框架以 task_id=0 拒掉。例外是特调声明的收尾任务（`nonfatal_entries` → `nonFatalMessage`，如 M9A 的关闭游戏）：它失败、
  超时、打转或被脚本侧强停都只截图记一行、不计入本轮失败（超时同样先等停下；停下时恰好又被脚本侧强停就跳过本轮剩余任务），且优先于上面两条；契约见 `tools/embedded/flavor.py`。
  特调声明的不可选任务（`unselectable_entries`，如 M9A 的小游戏）更早一步：`/maafw/preview` 给它们填
  `unselectableReason`（核心包的预览不认识特调，在 `api_service/interface.py` 补），用户页不让选；
  运行时在 `decorate_selection` 之前剔掉、按原因合并记一行，不进计划，所以上面几项声明对它不起作用。
- **原地打转检测**（`Run.LoopGuard`，脚本级开关，**实验性、默认关**；纯逻辑在
  `tools/core/runner/loop_guard.py`）：只看 `Node.Recognition.*` 与 `Node.PipelineNode.*`，按节点名
  找周期 ≤ 8 步的循环，连续各轮都有物理动作（Click / Swipe / 按键…，Custom 与 DoNothing 不算，等待型
  轮询本来就该一直等；没有物理动作的一轮让轮数与时长从头数，否则空等很久后第一次点击会被当场判卡死）、≥ 200 轮、持续 ≥ 10 分钟、最近 30 轮识别结果指纹 ≤ 4 种、单轮中位 ≤ 20 秒
  才判卡死（≥ 100 轮 / 5 分钟先记一行 `[MaaFW 详情]` 的「疑似」）。阈值用生产 `history` 里的 MaaFW 运行单元标定
  （2026-10-04 回放 09-04～10-04 共 129 个）：正常 0 误报，M9A 均衡刷材料划到底那种卡死在循环开始约 10 分钟时检出，MaaEnd 抢委托
  的刷新轮询不判。命中后收尾与单任务时限**同一口径**（`_handle_loop_guard` 紧跟
  `_handle_task_deadline`，截图 kind `loop`），而且必须在 `_external_stop_active` 之前——停止是我们
  自己 post_stop 的，晚了会被当成脚本侧强停、跳过本轮剩余任务。通知里缺 `reco_details` /
  （Succeeded 的）`action_details` 的老 MaaFramework 整次运行不检测：缺失当成「指纹恒定」会必中。
  `Node.PipelineNode.Failed` 在 5.12+ 上本来就只有 `name` / `node_id`，不算缺失。项目可在节点上写
  `"attach": {"auto_mas_loop_guard": false}` 豁免（有意转圈的轮询节点）；**不放进
  `attach.auto_mas`**：`run_signal.parse_signal_spec` 遇到未知键会忽略整个信号节点，而且写了
  `auto_mas` 的节点会被 MAS 强开。豁免随信号节点同一趟 `get_node_data` 扫描收集，binding 列不出
  节点时退回命中时按名字查。
- **结构化运行记录**（第 19 条）：worker 经 `_emit` 发 `{"type": "record", "data": …}`，事件形状、阶段名、
  结局与类别**只在** `tools/core/runner/run_events.py` 定义（换传输通道时只搬它）。runner 的各收尾分支用
  `_mark_task_outcome` 记结局，task_end 在下一个任务开始或本轮结束时才发——新增收尾分支要跟着记，漏记的
  按穿出的异常归类。宿主 `tools/embedded/run_record.py` 按尝试归并，存进该尝试 history 的
  `data["maafw_run_record"]`（snapshot，读用 `read_run_record`，旧历史没有这个键），驱动调度台进度
  （`UserItem.progress`）与推送（`tools/embedded/run_report.py`：最后一次尝试的逐任务时间线；最后没成功
  时单列各次的原地打转 / 单任务超时）。推送里的失败原因只用 `userMessage`（宿主还没投递任务就抛的
  异常用异常原文，同样过 `human_reason` 过滤）与失败类别的固定说法；`errorMessage`（节点链、框架失败
  事件、原生栈）不进推送，仍照旧写进任务日志、history 状态与调度台完成面板。记录是旁路，
  **不参与重试判断**。
- Win32 下 `Game.LaunchMode` 只有两态：`DirectExe`（默认，MAS 启动、结束后一律关闭）与
  `AttachOnly`（其他方式启停，MAS 只接管窗口）。关不关只看 `opened_game`，没有开关；
  DirectExe 下发现游戏已在运行时也只接管、不关。`Game.UnityResolution`（Off / 1920x1080 /
  1280x720）走
  `game_resolution.py`：按 `<exe>_Data/app.info` 反查 `HKCU\Software\<公司>\<产品>`，
  只改 Unity 播放器的 `Screenmanager *` 值，不碰游戏自有的那层（星铁的
  `GraphicsSettings_PCResolution`、终末地的 `video_resolution_*`），效果要实机验证。
  这个通用选项**不做逐游戏适配**（2026-10-04 定，理由见 `game_resolution.py` 文件头），
  游戏自有层由该游戏的特调或专项自己调。
- **项目的运行前设置（interface `pretask`）在每次尝试里跑**，不像用户级「脚本前任务」只跑一次：
  MaaEnd 的「🚀启动游戏（PC）」就是它，此时 `Game.LaunchMode` 是 AttachOnly、`opened_game` 为假，
  MAS 既不拉起也不关游戏。第一次尝试照常跑；它自己失败按普通失败重试；成功过之后的重试只在客户端
  已经不在时重跑（`_pretasks_need_rerun`：MAS 刚关掉自己起的游戏 / 模拟器——关的时候报错也算，
  `_close_*` 不论成败都清 `opened_*`、下一轮会重新拉起，见 `_reset_client_for_retry`；或 Win32 下
  控制器窗口找不到——队列末尾的「关闭游戏」任务会把它关掉）。游戏还开着不重跑，免得项目的启动脚本
  对着已在运行的游戏再走一遍。重跑前先清掉「已成功」标记：重跑到一半失败（窗口已被拉起）时，下一轮
  看到窗口在也不能跳过。2026-10-17 生产：以前放在重试循环外，第 2、3 次各 2 ms 报「未找到匹配
  MaaFW Win32 controller 的窗口」；启动器失败时整次运行一轮都不重试。
  - **等的是 pretask 进程退出，不是输出管道 EOF**（`_run_pretasks`）：它拉起的游戏 / 启动器常常继承
    了输出管道，`communicate()` / `Process.wait()` 都要等管道关闭，会一直卡到游戏退出（本机实测：
    子进程不重定向输出就继承，`close_fds` 管不住）。所以只轮询 `returncode`，退出后最多再读
    `_PRETASK_OUTPUT_DRAIN_SECONDS`，剩下的交给后台读到 EOF（只写后端日志），输出按行实时进运行日志。
    打码在 `_PretaskOutputPump` 里做，转去后端日志的那段输出也过同一套打码，别挪回 sink 里。
    只有到了行尾（`\n`、单独的 `\r`、`\r\n` 算一次）或 EOF 的段落才打码交出，`\r` 一到就交（进度
    实时可见）；没到行尾的半行留在缓冲里，`detach` 只换 sink、不把它写出——密码被拆在切换前后两段
    时，两段各自整串替换都匹配不上（PR #1710 审查）。
  - **时限沿用 `Run.RunTimeLimit`**，一次尝试里全部 pretask 合计；超时与停止只结束 pretask 进程和
    「一路都是脚本解释器」的后代（`_snapshot_pretask_script_descendants`），游戏、启动器及它们起的
    任何进程都不碰。清理跑在独立任务里、用 `asyncio.shield` 等（`pretask_cleanup`）：超时清理途中
    用户点停止，清理照样做完，`_shutdown_runner` 等的是同一个清理任务。
  - **exec 越出项目目录**（`..` 上跳过头、绝对路径）：投影与运行计划同一口径（`agent_entry.
    bundled_python_escape_path`）——以 `python/python.exe` 结尾的相对写法映射回项目自带的 Python
    （MFABD2 发行包的 `../../python/python.exe`，按 MFAA 的工作目录 `resource/base` 写的），其余
    这一条 pretask 只告警、运行时跳过，不再让整份投影作废（Sentry AUTO-MAS-BACKEND-NM）；越界的任意
    程序仍然不运行。
- 启动后再等（#889 起没有单独的键，上限就是 `Game.WaitTime`）：游戏是**本轮刚起来的**才生效——
  桌面游戏是 MAS 拉起、或接管时窗口是等出来的，从窗口出现起算；模拟器（ADB）是 MAS 随模拟器把
  游戏冷启动（进程原本不在，`DeviceInfo.app_launch == "launched"`，见 `emulator2/applaunch.py`），从拉起
  完成起算；游戏进程已在（在前台 `already-running`、从后台切回前台 `resumed`）、没认出包名、拉起失败
  都不等。宿主把「最早可下发时刻」写进 job
  （`taskStartNotBefore`），worker 在资源 / controller / agent 初始化完成后每秒截一帧，两条提前
  放行：连续 5s 画面没变（静态登录页）；或连续 20s 有内容哪怕一直在动（`runner.py` 的
  `STARTUP_SCREEN_CONTENT_SECONDS`）。黑屏 / 纯色把两个计数都清零，截不到图就等满上限。
  游戏早就在跑、重试轮次、AttachOnly 都不等。真机数据（2026-09-19）：终末地主界面每秒 3~6%
  抽样点在动、崩坏三登录页 22~38%，「没变」对它们永远不成立；终末地在窗口后 22s、主界面
  还没出来时下发首个任务照样成功。背景：终末地窗口出现后登录界面要 22~31s 才渲染，MaaEnd 的
  SceneManager 见画面十几秒不变就判「环境识别异常」失败，beta.5 runner 启动变快（窗口→下发
  7~9s）后每次冷启动都撞上。
  - **模拟器冷启动按读盘放行**：上面两条按画面提前放行只用于桌面。模拟器路径上宿主传
    `taskStartGateMode="disk_quiet"`（`runner._wait_task_start_disk_quiet`）：`Game.WaitTime` 仍是上限，
    worker 每秒经 controller 的 `post_shell` 读一次客体 `/proc/vmstat` 的 `pgpgin`（累计读入 KB）算读盘
    速度，画面有内容且读盘连续 8 次（每秒一次）低于 1 MB/s 就提前下发；到上限画面有内容就按上限下发，
    还是黑屏 / 纯色就继续等到出画面，从开始等算满 `TASK_START_GATE_MAX_SECONDS` 照常下发；截不到图或
    读不到 pgpgin（controller 不支持 shell、没有这一行等）退回按时间、等满上限；计数变小时增量记 0。
    老 binding（实测 5.12.3、5.14.0b1）没给 `MaaControllerPostShell` / `MaaControllerGetShellOutput`
    声明 ctypes 签名，64 位句柄一传就 `OverflowError`；调用前由 `runner._declare_shell_signatures`
    按 5.14.2 的签名补上，binding 自己声明过就不动。
    **不用 `/proc/diskstats`**：adb shell 用户读它和 `/sys/block/*/stat` 都被 SELinux 拒绝（API 34 魔改
    AVD，Enforcing），pgpgin 不需要 root、不随 dm 叠层重复计数，实测与整块盘 diskstats 读速误差 < 2%。阈值、窗口、采样间隔是 `runner.py` 的 `DISK_QUIET_*` 常量。核心只认这个
    模式，不判断设备类型。真机数据（2026-10-16 魔改 AVD 实测）：终末地加载页和动态标题都一直在动、
    都有内容，「20s 有内容」在拉起后 37~48s、仍在加载资源时就放行，冷启动到标题要 76~96s；CPU 与
    出帧也是标题比加载更忙（星铁标题只有 35 fps），都不能当判据；读盘量这套阈值在终末地 8 轮、
    1999 1 轮冷启动里都在到标题后 7~15s 放行。
    **反例**：读盘安静、画面有内容、但还没到标题的阶段都会提前放行。星铁一轮在 logo / 健康提示页
    （拉起后 17~24s，读盘 0~0.2 MB/s）上，拉起后 25s 就放行，比标题（64s）早 39s；另一轮在加载页上
    等登录约 80s，26s 就放行，比标题（150s）早 124s。这些阶段只能交给项目自己识别（MaaEnd 等的
    启动任务本来就会等标题），闸门不去猜。
    **着色器编译不处理**（2026-10-17 定）：
    - 清掉游戏自己的管线缓存（终末地的 `vulkan_pso_cache.bin`）后冷启动，标题前要编译约 320s。
      编译期间 6 个 vCPU 跑满，读盘约 0.15 MB/s，出帧约 0，到标题共 412s。闸门在拉起后约 66s 就放行。
    - 实际场景不会出现脚本等编译：用户跑脚本前必然手动登录过一次，那次已经编完。宿主显卡的着色器
      缓存清不清，实测看不出差别。
    - **做带游戏自更新的风味专项时必须处理**：游戏自更新以后可能重新编译，而脚本会在没人手动登录的
      情况下直接撞上。M9A 特调已经有游戏 APK 更新，但它的启动等待由 M9A 自己处理；新做的风味如果
      依赖这道闸门，就要先补上下面这一条，再放开自更新。
    - 以后要处理的话，可以在放行条件里再加「这 8s 里每秒出帧都 ≥ 5」，并把模拟器上的上限放宽到能
      盖住编译（终末地约 420s）。
      - 编译期间每秒最多 2 帧，≥3 就挡得住，取 5 留了余量；标题最低是星铁的约 36 帧，加上 30 Hz 档
        帧率还会减半，所以阈值不宜取 20。
      - 实测两轮编译都改在标题后 8~9s 放行，其余各轮的放行时刻不变。
      - 这一条只为挡编译。星铁 logo / 健康提示页本身有 48~60 帧，加载页等网络时有 60 帧，出帧判据
        都挡不住（阈值取 20 时 logo 页那轮被挡住，是因为碰巧有一秒只有 17.9 帧）。
    - 出帧数的来源：魔改 AVD 读截图共享内存里的帧号，其他模拟器读 SurfaceFlinger 的帧时间戳。
    通用默认等待时间因此是 120s（`MaaFWConfig.DEFAULT_GAME_WAIT_TIME`），M9A 特调 15s。
- **连上控制器后先截一张图**（`runner._prime_first_screencap`，每次连接一次，在启动画面判定与
  首个任务之前），不是多余代码：控制器没截过图时 binding 的 `cached_image` 抛
  `Failed to get cached image.`、`resolution` 是 (0, 0)，而有的项目的 agent 在 tasker sink 里于
  任务 Starting 时就读这两个值（M9A v4.10.0 的 `aspect_ratio` sink 读到 0 直接 `post_stop`，
  ADB 路径第一个任务一开始就被停掉）。MFAAvalonia 连上后同样先截一次
  （`MaaProcessor.MeasureScreencapPerformanceAsync`）。截图失败只记日志、不拦运行。
- 用户配置在 `check()` 时深拷贝成副本跑，`final_task` 解锁后**整表写回**（#720 / #737）。
  改任何运行期写用户字段的逻辑，都要用落盘探针验证，只看内存会误判成已生效。
- **空任务队列不留着**（`tools/embedded/default_snapshot.py`）：`Task.TaskSnapshot` 为空时运行会回落到
  预设或默认勾选（`run_plan.resolve_default_snapshot`），所以建用户、读用户（`Config.get_user`）与运行前
  检查（上锁之前）都按这同一个函数把它写成实打实的队列，用户页上看到的就是要跑的。项目还没导入时
  什么都不写、留给下一次；默认队列定格在写入那一刻，项目以后改了预设不再自动跟。别在前端另写一份规则。

## interface.json

- 加载器递归解析 `import`；`.json` 先 `json` 后退 `json5`，带 `//` 注释的 JSONC 可读；不认识的
  顶层字段（如 `telemetry`）忽略并告警。项目拆分资源（MaaEnd v2.28 的 `AutoEssence/`）
  不需要 MFW 侧适配。
- 预览的任务表里会多出 `__MXU_PRETASK__*` 伪任务（MXU 壳的前置任务），预设里也会出现；
  比较任务数时要减掉。
- 选项 `type` 支持 `select / scan_select / switch / checkbox / input / hotkey`，后端下发与
  前端 `MaaFWTaskOptionEditor.vue` 两侧都有；未知 type 前端有兜底提示。
- **input 的 `default` 是字段初值**（PI v2 规范；MaaPiCli、MFAAvalonia 的 `TaskLoader` 把
  `input.Default` 写进配置、MXU、MFW-PyQt6 都这样用）。快照里没填的字段存空串（不写 default、
  不迁移），建覆盖时回落：字符串字段没存或存的正好是 `""` 才算没填（纯空白串算有值、原样下发），
  default 原样用、不 strip，default 为空串或没写就不回落（`pipeline_override._string_input_fallback`）；
  数字 / 布尔 strip 后为空才算没填（`_coerce_input_value`）。password 字段不回落。特调可以声明例外
  （`flavor.no_default_fallback_inputs`，两条建计划的路都传；`/maafw/preview` 把这些字段的 `default`
  置成 null，用户页就不会把它显示成「没填时的值」）：M9A 的自定义兑换码 default 是字面量
  「占位」，旧版迁移专门把预填的它清成空串，agent 遇到交不过去的码会中断整个兑换。以前「default 只当
  占位提示、没填就下发空串」的取舍（#478）已撤销：语料里 11 个项目因此拿到坏 override（MaaEnd 表达式缺
  右操作数、MRA 的 `expected: [""]`、MaaStellaSora agent 里的 `float("")`）。
- **全局选项每个用户只存一份**：`global_option` 连同各 case 下挂的子选项
  （`task_config.build_global_option_map`）的值在 `Task.TaskSnapshot.globalOptions`。覆盖顺序
  照 PI / MXU / MaaPiCli：全局组按全局表，资源 / 控制器 / 任务组按任务自己的值，后叠的盖前面
  （`MaaFWPipelineOverrideBuilder.build_task_pipeline_override(..., global_options=)`）。所以同一
  选项也被任务 / 资源 / 控制器自己引用时，它在任务的选项表（`build_task_option_maps`，不按当前
  资源 / 控制器过滤）里、按任务存值、面板照常显示；只有对某任务「只属于全局」的选项，任务上的值
  不生效、迁移与导入都折进全局表。别把两类合成一张表：v5.6 的「全局盖过同名任务选项」与 PI 示例
  （战斗划火柴）的结果不同。特调走 `task_ids` 那条路时必须把 `select_snapshot_tasks` 给的
  `global_options` 一并传给 `build_plan`（漏了不报错，全局选项静默回到默认值）；特调往
  `task_options` 写的只属于全局的选项，这一实例以它为准（`extract_task_global_overrides`，依赖
  归一后的任务选项里不会有这类键；判「只属于全局」必须与快照归一同用**不按当前资源 / 控制器过滤**
  的表，否则一个还被未选中资源引用的全局选项，归一补出的默认值会被误当成特调写入、盖掉用户的全局值）。pretask 不吃全局表。计划的 `globalOptions` 是全局层的取值，
  同一选项任务自己也有值时任务 `options` 里看不到它，打码收集两处都看。旧配置迁移
  （`normalize_snapshot`，前端 `maafwGlobalOptions.ts` 同一口径）：全局表里缺或坏的项，取队列里
  第一个勾选的、带合法值、且对它只属于全局的实例，再没有取未勾选的。预设写在任务上的只属于全局的
  值进全局表（先写的为准）；外壳导入以 MXU `globalOptionValues` / MFW-PyQt6 的全局表为准（现行版本存在
  `Resource.task_option.setting_options`、根层 `global_options` 写空，老版本存在根层；两边合并，同名以
  `setting_options` 为准）。
  **降级兼容双写**：保存时（`option_secrets.prepare_user_task_snapshot` →
  `mirror_global_options_to_tasks`）把只属于全局的选项的全局值抄到每个任务实例上——旧版运行期按任务
  读它们，旧版用户页保存会丢掉 `globalOptions`，升级回来靠这些副本迁移找回。新版运行期与前端
  都不看副本（归一 / `withoutMaaFWGlobalOnlyOptions` 丢掉），去掉双写前要先确认没人会降级。
- **保存的值对不上当前 interface 不静默**：项目改了 case 名后，归一会把 select / switch 的旧值换回
  默认、checkbox 里对不上的项丢掉（值本身不改）。`runner_task` 建计划前按原始快照
  （`run_plan.describe_stale_option_values`：全局表里存着的项 + 勾选实例自己的选项，不看迁移前的
  旧配置、坏值形状与降级副本）把这些列成计划提示，运行日志开头「MaaFW 运行计划提示」里各一句，
  与「interface 内已无该任务」的跳过同一个思路。开发者模式下改 interface 最容易撞上。
- input 字段 `password: true`（PI v2.10.0）的值在 `Task.TaskSnapshot` 里（`taskOptions` 与
  `globalOptions` 两处，`option_secrets._SECRET_SECTIONS`）是带 `mas-dpapi:` 前缀的
  DPAPI 密文：`Config.update_user` 写入前按 interface 加密（`tools/embedded/option_secrets`），
  `runner_task` 建计划前只在内存副本里解密；前端只看到密文、显示「已设置」。没有前缀的是旧明文，
  照常使用、下次保存时加密。checkbox 的 `min_count` / `max_count`（v2.10.1）由加载器放宽成自洽值，
  运行计划里不满足就报错（`MaaFWCheckboxCountError`），不静默截断。密码原文会随 override 进
  MaaFramework 自己写的项目日志 `debug/maafw.log`：`Tasker::post_task` 用
  `LogInfo << VAR(pipeline_override)` 记整份 override（INFO 级，不是只在 DBG 下），覆盖失败时
  `LogError` 再记一遍。**这份文件由框架直接写，MAS 管不了**，里面的密码是原文。MAS 自己的出口对
  **长度至少 4 个字符**（`MIN_REDACTED_SECRET_LENGTH`）的密码值都已打码
  （`option_secrets.redact_secret_text`，按文本全局替换成「<已隐藏>」）：`runner_task` 复制到
  历史详情中 `native_log` 角色的原生日志附件、转发的 worker 事件（事件通道与 stdout 退回格式都先解析、
  只打码给人读的文本，见 `_redact_worker_event`）、stdout 上的原生诊断与 stderr、`.worker.log`、pretask 输出。更短的值**不打码**
  （有意为之，本地测试钉住）：一两个字符全局替换会把日志里所有同样的字符都换掉，日志就没法看了。
  input 值下发失败的计划告警对密码字段一律不带原值、与长度无关（`MaaFWInputValueError(secret=True)`）。
  项目更新撤掉了 password 标记的字段，快照里留着的密文建计划前照样在内存里解开（解不开的告警、丢值，
  不中断整轮），它们与当前仍是 password 的字段同一口径：值进打码集合
  （`option_secrets.collect_run_password_values`），字段记进快照的 `secretInputs`，下发失败的告警同样不带原值。
  新增任何落盘 / 转发日志的路径都要过它；agent 进程自己写的日志同样不在 MAS 控制内。
  项目有 password 输入框、或本次有要打码的值时，`worker_log` 附件第一行是以 `LOG_REDACTION_MARKER` 开头的打码说明：
  前端问题包导出（`frontend/electron/services/maafwIssueReportService.ts`）凭它认定这次的
  `worker_log` / `native_log` 附件已打码才往包里放，项目 `debug/` 目录与没有这一行的旧副本一律不收。
  项目 agent 自己写的日志（M9A `debug/custom/*.log`、MaaEnd `debug/go-service*.log`、MaaFgo
  `bbcdll/*.log` …）由 `runner_task` 挨着 `.maafw.log` 另存：运行开始记下视图里每个 `.log`
  的大小与开头，收尾只取本次新写的部分拼成临时日志并按 `project_log` 角色归档（每段一行分隔头；
  单个取末尾 2 MB、一次运行总量 8 MB，按行切；按该脚本**全部用户**的密码打码，
  `tools/embedded/project_logs.py`）。`debug/maafw*.log` 不在其中。问题包按附件角色识别，
  `project_log` 与 `worker_log` 同一条件收（有密码输入框时只收写的时候就打过码的那次）；
  整包备份通过历史快照保留数据库与附件的对应关系。打码按每个写法的 UTF-8 / GBK / UTF-16LE 字节替换
  （`option_secrets.secret_byte_pairs`，`.maafw.log` 同用）。
- 加载器写的告警（`logger.warning`）由加载器旁听收集、挂在模型上（`interface_load_warnings`），
  随磁盘缓存保存，进运行计划的 `warnings`（运行日志开头）与导入报告；只给后端看的用
  `extra=_LOG_ONLY`。发行包的毛病能降级就降级：缺 import 文件、scan_dir 不在、缺
  interface_version（按 2）、input 的 default 写成数字、数字输入没填 / 填错（跳过该选项的
  覆盖）、任务或资源的 controller / resource 名写错（原样保留、只是匹配不上）都是告警，
  不整份拒绝。没缺 import 文件时引用了没定义的选项照旧整份拒绝（与 MaaPiCli 一致）。
- 任务表里同名任务出现多次、`repeatable` + `repeat_count`（MFAA 私有扩展）都展开成
  `__MAS_DUP__` 重复实例（`task_config.build_default_task_instances` / `build_repeat_instance_ids`，
  前端「添加任务」按 `repeatCount` 一次加 N 份），不做 runner 循环。select 的私有 `default`
  **故意不认**：作者自己的 MXU / MFAA 壳都不认，认了反而比作者更激进。
- `pipeline_override` 按**递归深合并**叠加（`runner/pipeline_override.deep_merge_pipeline_override`，
  与 CFA 一致）：同一任务里任务自身与各选项对同一节点同一字段都给对象时，子键逐层合并，数组与
  标量后者覆盖前者。MFAA / MXU（普通任务）把各份覆盖交给 MaaFW 逐个应用，同一节点的同名字段
  **整体替换**（`attach` 例外）。所以多个选项分头写同一个 `custom_action_param` / `action` 子键
  的项目在 MAS 里跑出来的覆盖与它们自己的壳不同：全语料 MaaYuan 558 处、MPA 209 处、MaaNTE 2 处
  （都是壳里后写的选项把先写的子键整个冲掉，MAS 两边都留）。这是有意的取舍——深合并不丢作者
  分头写的字段，MXU 自己的特殊任务也是先深合并再下发；不要为了「和 MFAA 一致」改成整体替换。
- `agent.timeout`（秒）只决定等 agent 连上的预算（`runner.agent_connect_budget_seconds`，不写 /
  -1 = 10 分钟），连上后照旧不限时；interface 写死的 `agent.identifier` 运行时拼上实例后缀，
  纯数字（TCP 端口）原样用。

## 更新

- 开着开发者模式（`Embedded.FollowSource`）的脚本**不更新**：自动更新跳过、手动检查与应用都拒绝，
  以来源目录为准（见「跟随来源目录」）。下面说的都是普通模式。
- 下载源 / CDK / 渠道 / 时机**只看脚本级 `Update.*`，不做全局兜底**
  （`tools/embedded/update_credentials.py`）；全局的 `Update.MirrorChyanCDK` / `Update.Channel`
  服务的是 MAS 自身更新。
- **唯一带全局兜底的是代理**：脚本级 `Update.ProxyAddress` 留空跟随全局（设置 → 其他 →
  网络代理），填了只走自己的，同时管更新包下载与运行环境安装（池的 uv / pip、agent venv）。
  解析走 `resolve_update_proxy_url`，日志里只能出现 `describe_proxy` 的「脚本级 / 全局 /
  未配置」——地址可能带 `user:pw@`。别改用 `Config.proxy`：那个属性每次访问都往日志写一行
  「使用代理: <地址>」。
- GitHub 加速镜像是**只有全局**的一项：`Update.GitHubMirror`（`Auto` / `Off`），脚本级没有
  对应字段。清单在 `tools/embedded/update_mirrors.py`，与前端 `mirrorService.ts` 的 gh-proxy
  组同源，改一处要同步另一处。只对 `github.com/<owner>/<repo>/releases/download/...` 生效，
  Mirror 酱的一次性签名地址套前缀会把签名打坏，所以按源分流而不是按地址。
  **没有 sha256 摘要时核心包整个忽略镜像**：经第三方转发的字节必须能校验。
- **一个组只更新一次**（`tools/embedded/view_update.run_view_update`，运行前 / 运行后 / 手动三条路
  共用）：谱系锁（进程内）内先把触发脚本同步到组的 latest，再发现（`current` = 组版本）→ 下载一次
  （取消令牌、GitHub 镜像、按触发脚本解析的代理、进度全部透传）→ 在 `.staging/payload-*` 里从当前
  载荷 + 包建新载荷（`payloads.build_from_package`）→ 在 staging 上预检一次（钉回 binding 也在这里，
  写的是 staging）→ `finalize` 并入共用库 → `register` 登记 → 切触发脚本的视图 → 同组空闲脚本立即切
  （运行中的跑完再切：`_check` 的组同步与 `final_task` 的收尾同步——收尾同步只在用户全部正常跑完时做，
  停止 / 崩溃留给下一次 `_check`；pending 是派生状态，不落字段）。切过的兄弟连同预约交给后台环境确认
  线程（`view_update.propagate_and_confirm`）。运行环境「确认过哪个载荷」记在视图标记的
  `envConfirmedFor`（确认成功才写，同谱系切换带旧值）：`_check` 看到 `payload ≠ envConfirmedFor` 就由
  `main_task` 在用户任务前补确认，拿不到预约时据此说「正在切换版本」。
  视图与旧载荷全程一个字节不动：失败 / 预检不过 / 取消都只是丢 staging，没有回滚与中断恢复。
  下载完成之后到登记之前取消 = 丢 staging（「正在中止更新（丢弃未完成的新版本），请稍候」，60 s
  宽限）；登记之后不再响应取消。手动 `/maafw/update` 运行中照旧拒绝（`api_service/update.py` 的 `UPDATE_SCRIPT_BUSY`），整段
  持本视图预约，切完在预约里确认一次运行环境再放手（前端那次 prepare 会被 `envReady` 短路）。
  手动更新的「应用」在后台跑（`api_service/update_job.py`）：同一脚本进行中再点只接上那一份，HTTP
  请求断开不影响更新；过程（推送过的进度事件）与结果按脚本登记在进程内，编辑页打开时经
  `/maafw/update/job` 接回，保留到这个脚本下一次手动更新开始或后端重启。没有停止入口。
  `run_view_update` 的四个调用方（自动、手动、投影补齐、发行包核对）一律经
  `tools/embedded/update_session.UpdateSession` 组装参数（组与候选、预约、锁时限、停止令牌、
  代理 `UpdateProxy`、进度出口、预检）；更新编排里的运行环境确认（预检、切换后确认、传播后的
  后台确认）一律走 `tools/embedded/env_confirm`，不要再延迟导入 manager 调
  `_prepare_project_environment_sync`。`env_confirm` 的 `resolve_*` / `build_update_precheck`
  与 `UpdateSession.precheck` / `precheck_builder` 里有函数内导入，只在事件循环上调，交给
  `asyncio.to_thread` / 核心包工作线程的是解析好的可调用对象。核心包发的进度事件是 dict，消费方先经
  `core/project_update/progress.UpdateProgressEvent.of` 转成类型化模型再读。
- 差量 / 全量只看当前载荷：`source.kind=update`（更新得来的，清单逐文件记包内哈希，指纹就是它
  现在的指纹——载荷不可变）才要差量包，本地导入的一律全量；按旧投影规则建、缺的文件又没补上的
  载荷（清单 `projectionRevision` 低于 `projection.PROJECTION_REVISION`）也只要全量包；清单里还留着
  换外壳前旧布局原生库（`origin=import`、按上一个包的清单判是被淘汰的位置）的也只要全量包，清完就回到
  差量。差量基线用 `apply.py: _validate_plan_base`
  对载荷清单校验。
- **投影规则改版**：规则改动会让已登记的载荷少文件时，`PROJECTION_REVISION` 加一，并在
  `project_update/projection_legacy.py` 留一份上一版规则的复刻。运行前检查与手动检查更新时
  （`tools/embedded/view_heal.py`）按「当前规则留、载荷那一版剔、载荷里没有」比对一次（依据：导入目录 →
  缓存的完整包 → GitHub 发行包的 HTTP Range），缺了就用「旧载荷 + 取回的文件」建同版本新载荷、登记
  （`register` 允许规则版本更高的同版本载荷顶替 latest）、切组。新载荷是旧载荷的超集、共同路径内容
  相同且版本号相同，切换按「同内容」走（`embedded_project._is_content_superset` → `fills_only`；版本号不同的：视图里已有的文件
  （`data/manifest_cache.json`、热更新改过的受管文件）原样保留、不留档，只落新增的文件，M9A / MaaEnd
  不会因此重跑热更新。结果记在载荷清单的 `projectionCheck`，
  同组只查一次（`project_update/projection_heal.py`）。全量包清的是旧载荷里 `origin=package` 且不在包内的，加上 `origin=import`、位于新
  interface 资源目录内、不在包内的（`apply._import_origin_orphans`：资源目录是 `resource[].path` 加控制器的
  `attach_resource_path`——MAA_Punish 的 `resource/pgr_win32` 只挂在后者上，漏算时上游删掉的 pipeline
  永远清不掉；用户内容目录与运行时目录不碰），
  再加上 `origin=import`、在被新包淘汰的外壳原生库位置上、不在包内的
  （`projection.abandoned_native_runtime_files`）：位置只有顶层 `maafw/`、`runtimes/<rid>/native`、
  `runtimes/<rid>` 与包根上的 MaaFramework 原生库，新包在某处带主库、旧的另一处也有主库而新包那处没有，
  那一处就清——MXU 换 MFAAvalonia 的导入目录里 `maafw/` 5.9.2 与 `runtimes/win-x64/native` 5.14.0
  并存，runner 与 agent 各挑一份、每次等满连接超时。判据只看新包（投影过滤后）的清单、不比版本；**这条**
  规则里自带解释器的 `site-packages/maa/bin` 是正牌的第二份库（可以更旧），不当被淘汰的位置清。
  导入时同样的混装只在报告里提示、不删。
  最后再加上 `origin=import`、位于新包**整体接管的目录**里、不在包内的（`projection.package_takeover_dirs` /
  `takeover_orphans`）。接管目录只有三类，且新包里确实带着这个目录下的文件：MaaFramework 原生库布局里
  明确的 `maafw/`、`runtimes/<rid>/native`（有界搜索找到的任意目录，比如只在 `bin/` 里放了
  `MaaFramework.dll`，不算）；随附的 `MaaAgentBinary/`；项目自带解释器所在目录（目录名是
  `EMBEDDED_PYTHON_DIR_NAMES` 之一或新包里结构上确是解释器目录，投影保守模式下不认）。与声明的资源目录、
  agent 代码目录（`child_args` / `pretask` 参数所在目录）相等、包含或落在其内的一律不算——
  `child_exec: ./agent/python.exe` 时解释器目录就是 `agent/`。不清的话新旧两版混在一起（M9A v4.11.0 导入
  → v4.11.1 后自带解释器里两份 `maafw-*.dist-info`、两份 `charset_normalizer`），导入后直跳与链式更新
  得到的载荷也不一样。于是自带解释器里 `site-packages/maa/bin` 在新包不带时也会被清（M9A v4.9.0 →
  v4.11.x 清 16 个 DLL）：与全新安装新版本的结果相同，健康检查照常把 `MAAFW_BINARY_PATH` 指到项目
  自带库。**代价**：导入时带进来的、用户手装进自带解释器的包，第一次全量更新（整包或区间）就被删掉，
  MAS 不负责重装（准备运行环境只做健康检查与 maafw 钉回），能不能装回来要看项目自己的部署脚本。资源目录
  与接管目录之外别处的导入文件仍然一直是 `origin=import`、任何一次全量包都不清：#659 第一版按「包自己铺的
  顶层目录」扫，把 MXU 写在 `preset/` 里的用户预设删了，`tasks/`、`assets/` 同理可能混着用户内容。
  `.mas-update` / `.mas-update-cache` 是更新器的保留目录；`debug` / `logs` / `temp` / `__pycache__` /
  `.pycache`、`config/maa_option.json` 与视图标记不计入指纹（agent 子进程与环境准备设了
  `PYTHONPYCACHEPREFIX=<项目根>/.pycache`，镜像树里项目根出现两遍，路径长到会撞 MAX_PATH 时不设
  前缀，见 `host_environment.project_pycache_prefix`）。
- 全量与差量包的落地条目都只从 `apply.py: build_package_plan` 枚举（`files` / `hashes` /
  `deleted` 三张表，按投影白名单过滤）。要改"哪些文件落盘"只动这一处。唯一的旁路是下面的
  区间差量：它按同一套投影规则（`package_projection_rules`）在中央目录骨架上算好条目表直接传进
  `build_from_package(package_entries=...)`，改投影规则时两边自然一致，改枚举口径（跳过哪些
  条目、包根怎么认）时要同步 `range_delta._check_layout`。
- **GitHub 源按区间差量**（`project_update/range_delta.py`，#1118）：要的是全量包（GitHub 源
  一律如此）时，先用 HTTP Range 读发行包的中央目录，按 CRC32 + 大小与当前载荷逐条目比，只取回
  变了的条目，没变的从当前载荷搬，在 `.staging/rpk-*` 里拼成虚拟全量包（与整包解压的 `pkg-*`
  分开：里面没变的文件是旧载荷 / 共用库的硬链接，退回整包绝不往里解压），再按全量包语义建新载荷
  ——与整包下载逐字节一致、载荷 id 相同（识宝 v1.13.3→v1.13.4 取回约 3.5 MB，整包 185 MB）。
  清单 `source.mode=range`、`projectionRevision` 照全量记；进度与结果的 `package_type` 报
  `delta`（前端显示增量）。只直连 `github.com`、不走加速镜像（区间字节只有条目级 CRC，没有整包
  sha256 可校验）；区间这一路任何一步失败（回 200、区间不符、CRC 错、超时、取回超过资产 40% 或
  3000 个条目……）都丢掉这一批，同一次更新里照常下整包（可走镜像），用户停止照常取消。当前载荷
  damaged、旧投影规则、旧布局原生库残留时不走区间（`updater._range_delta_blocker`，先保守）；
  本地导入的载荷可以走。环境变量 `AUTO_MAS_MAAFW_FORCE_FULL_PACKAGE=1` 一律下全量包（Mirror 酱
  也不要差量包），供验收比对与应急，不进配置、不上界面。
  **直连速度保护**（`range_delta.RangeSpeedGuard`）：只在退回的整包真能走加速镜像时设（镜像没关、
  有镜像、资产有 sha256，与 `transport.download_resumable` 同一判据）——国内直连 GitHub 常年
  100 多 KB/s，40% 预算的上限要十几分钟，不如按镜像下整包；没有更快的路可退时不设。从读文件
  目录起按花在网络上的时间测吞吐，样本够了（≥ `SPEED_GUARD_MIN_SAMPLE_SECONDS` 3 秒或
  ≥ `SPEED_GUARD_MIN_SAMPLE_BYTES` 512 KB）就逐块估「网络已用时 + 剩余字节 / 吞吐」（读到包尾结束记录后
  先按读完中央目录还剩多少估，定好取回计划后按整次计划估），超过
  `SPEED_GUARD_BUDGET_SECONDS`（120 秒）放弃；网络已用时超过 `SPEED_GUARD_HARD_LIMIT_SECONDS`
  （1.5 倍，180 秒）无论估多少都放弃。时间只算花在网络请求里的（本地列大小、算规则、逐文件 CRC、
  链接复制都不算：慢盘不该把区间拖成「太慢」，退回整包也要做同样的本地活），不另设墙钟上限；
  单次读取 30 秒没数据由读取超时兜住。放弃走的是同一条退回路径（先报 full、丢 `rpk-*`、整包走镜像）。
- 预检备忘按**谱系 + 目标版本**记（`.payloads/<谱系>/precheck-<版本>.json`），组共有：一个成员预检
  过某版本失败，组里谁也不再为它下包；只有运行前 / 运行后自动更新读它，手动更新等于强制重试。
- "检查更新"走 `version_only`，不换下载地址——带 CDK 换地址会扣 Mirror 酱当日额度。
- 所以更新检查从不验证 CDK。编辑页 CDK 输入框下的小字（剩余天数 / CDK 有问题）走单独的
  `/maafw/mirror-cdk` → 宿主通过 `from app.services import update_transport` 调用 `update_transport.query_mirror_cdk_status`：
  先不带 CDK 拿最新版本，再带 CDK、
  `current_version` 写成这个最新版本查一次——已是最新时服务端不签发下载地址、不扣额度，但照样校验
  CDK（2026-10-11 实测错 CDK 一律 HTTP 403 + 7002）。别把第二次的 `current_version` 改回项目版本。

## 与专项的区别（别照搬）

- 没有 `ScriptConfig.py`，没有原生编辑器会话；已接入通用配置备份恢复
  （mas 池为纯字段侧车 + native 项目池，见 `tools/restore_service.py`）。
- 用户配置上的 `Info.Base`（shared/independent/native）和 `Info.IfQuickConfig` **都没有 MaaFW 运行代码消费**：
  用户页上的任务队列就是唯一的任务来源（`runner_task.py` 建计划处有说明），这两个字段只在
  配置备份恢复里原样带着。不要在 MaaFW 上按三态写逻辑。
- 新的 `interface.json` 项目默认用 MaaFW 类型即可运行；需要更精细的控制时（原生编辑器会话、
  登录/切号、按游戏语义组织的专属界面、对上游资源文件的动态读取等）可以立专项，MaaEnd 就是
  这种情况。立专项时在专项目录写明它比通用 MaaFW 多控制了什么。

## 测试与排障

- 改 `tools/core/` 先跑 `tests/task/test_maafw_core.py`：核心最小回归，进仓库、长期保留，只收
  缺一条就要命的（worker 导入闭包、宿主与 worker 之间的 job 和结果、agent 的 maafw 钉版与
  原生库一致、agent venv 失效判定）。收录标准见 `tests/AGENTS.md`「核心最小回归」；其余 MaaFW
  测试照旧只在本地跑。
- 夹具要照抄真实输出的形状（interface 加载结果、更新器返回、运行计划），臆造键名会让
  "读错键"类缺陷全程绿灯。
- 本地边界测试会在临时目录建很深的树，`--basetemp` 用短路径（如 `%TEMP%\mfwt\pt`），
  否则 Windows 报 `WinError 206`，看起来像代码坏了。
- 排障先从历史详情读取 `native_log` 附件：agent 协议版本不匹配之类只记在那里，
  宿主日志只有一句"连接超时"。agent 自己的 DEBUG 日志、Go agent 的 panic 在 `project_log` 附件中。
