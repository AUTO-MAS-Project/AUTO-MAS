# `app/task/MaaFW` 说明

MaaFW 是**通用引擎**，不是专项：任何带 `interface.json` 的 MaaFramework 项目都由它运行。
专项适配那一套（原生编辑器会话、脚本/用户/直控三态、配置备份恢复）不适用，见末节。
本文件只记录代码里读不出来、但改错了会出事的约束。

## 布局与边界

- `embedded_manager.py`：宿主侧管理器——任务调度、更新时机、运行环境确认、用户配置副本与写回。
- `api_service/`：`/api/scripts/maafw/*` 端点背后的全部业务（`common` 脚本解析 / 有效项目根 /
  同组候选，`embedded` 副本状态 / 导入 / 克隆 / 候选来源，`interface` 预览 / 包名 / 图片资源，
  `update` 手动更新，`agent_env` 预备运行环境，`shell_instances` 外壳配置实例导入成用户）。
  **MFW 的 API 业务一律在这里实现，
  `app/api/scripts.py` 只放薄端点**：取参数 → 调这里的一个函数 → `XxxOut(**reply.out_fields())`
  （`MaaFWApiReply`）或把异常映射成 HTTP 错误；不在 API 层定义 MFW 私有辅助函数、常量或锁。
  依赖只能 `app.api` → `api_service`，反向导入 `app.api` 禁止；worker 导入闭包不得碰它。
  端点 docstring 会进 OpenAPI 生成物，搬业务时留在端点上原样不动。
- `tools/embedded/`：宿主与核心包之间**唯一**的接缝（`runner_task`、`runtime_route`、
  `update_credentials`、`update_mirrors`、`project_path`、`env_cache`、`game_package`、
  `game_resolution`、`update_progress`、`embedded_project`、`option_secrets`、`shell_instances`）。
  要读 `Config`、发通知、碰宿主模型，只能在这里和 `embedded_manager.py` 里做。
- `tools/core/`：六个核心包（interface / runner / runtime_pool / agent_env /
  project_update / controller_win32），按零宿主耦合设计。已知例外只有
  `project_update/updater.py` 引了 `app.utils.constants`——它只在宿主进程里跑；不要再加新的。
- **worker 子进程**（`runner/worker.py`）以 `python -m` 启动，其导入闭包内的
  `app.*` 只能落在 `app.task.MaaFW.tools.core.` 之下，由
  `tests/task/test_maafw_worker_import_isolation.py` 钉死。v5.5.0-beta.4 全员 MFW 挂掉，
  就是链路上多了一处 `from app.utils import ...`。改 runner 子树前先跑这个测试。

## 项目目录与运行

- **有效项目根只从一处取**：`tools/embedded/embedded_project.resolve_maafw_project_root`
  ——**永远是** `data/mfw/<脚本 uuid 前 12 位>/` 的视图，没有"路径模式"。`Info.Path` 只是
  导入的来源，运行时不读它；导入完成后用户删掉来源也无妨。manager 三处、`runner_task`、
  `api_service/update.py`（`/maafw/update`）都走它；`/maafw/preview`、`/maafw/agent-env/prepare`、
  `/maafw/game-package` 带 `scriptId` 时也按脚本解析，`path` 只在没有脚本时兜底。
  新增任何"读项目目录"的代码不要再各自读 `Info.Path`。视图可能还没建（刚选目录、来源换了目录、
  被手删），各入口先经 `ensure_embedded_copy`（调用方持该视图的项目预约）：视图不在或 `Info.Path`
  与导入报告里的 `sourcePath` 不是同一目录就导入一次；来源不在而视图健康时什么都不做；健康但
  没有标记的老副本就地采纳一次，采纳失败就报错、本次不运行。
- **载荷 + 视图**：项目内容按「谱系 + 版本 + 内容哈希」登记成不可变**载荷**
  （`data/mfw/.payloads/<谱系>/<版本>-<hash8>/` + 同名 `.json` 清单，`project_update/payloads.py`），
  全局一份；每个脚本一棵**视图**（`data/mfw/<12hex>/`，路径永不变，所有按路径键的缓存 / venv /
  备份桶都不用改键），满足共用谓词的文件是载荷 / 共用库的硬链接，小文件拷贝，运行期产物私有。
  视图根上的 `.auto_mas_view.json`（谱系、载荷、版本、物化时刻、`switchedBy`）是物化事实的唯一
  来源，不进指纹、不进任何清单，只随目录原子换入、不原地改（`switchedBy` 打完日志后清除除外）。
  谱系键 = `mirrorchyan_rid` > `github` > `name`；**组 = 谱系 + `Update.Channel`，同组永远挂同一个
  载荷**（`lineage.json` 的 `latest[channel]` 只前进，同版本不换 id——唯一例外是 latest
  自带的 MaaFramework 在本机加载不了而新登记的能加载，见 `payloads._replaces_unloadable_latest`）。
  配置项零新增：谱系 / 载荷 / 版本都不进 `ScriptConfig.json`。
- **投影**：按 interface 白名单（`project_update/projection.py`），**白名单之外的顶层条目
  剩余 ≤ 64 MB 的也带走**（MaaEnd 的 `data/`、`locales/`，MaaYYs 的 `assets/答案.csv`，M9A 的
  `data/activity` 都没在 interface 里声明却是 agent 运行时要读的；更大的顶层目录、根上没声明的
  exe / dll、.NET 外壳的 `libs/` 才是外壳运行时）。外壳是冻结的 Python 程序时（根上直接躺着没人
  声明的 `python312.dll`，Maa_bbb 的 MFW.exe 就是），它散在根目录的二进制依赖包（带 `.pyd`，或
  `*.libs` / `*.dist-info`）也不带：agent 子进程的 `PYTHONPATH` 是项目根，`backports/zstd/`
  这种没有 `__init__.py` 的半截包会变成命名空间包盖住真正的模块——副本上 pip 就是这样崩的。
  视图路径由脚本 ID 推出（`embedded_copy_dir_name`：uuid 去连字符取前 12 位，短是为了 pyc 前缀树
  与深层 site-packages 不撞 MAX_PATH）、不进配置、不可手改；来源目录一个字节不动、也不由 MAS 删。脚本页
  「选择本地目录」就是 `/maafw/embedded/reimport`：投影成载荷、登记进脚本所在渠道的组，视图切到组的
  latest——导入的比组新就推进整组（空闲的兄弟立即切），相同或更旧就上组当前版本（「导入时版本」
  那行日志仍是所选目录的版本）。没有 enable / disable 这种开关路由，`Embedded.*` 里只有报告、
  来源版本与导入时间。删脚本连带删视图；载荷与共用库的回收在启动期。
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
  缓存比数据新、热更新一直跳过；同一载荷上重建视图（采纳、修复）时照常带。
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
- **按内容共用文件**（`project_update/blob_store.py`）：共用谓词只有一个，
  `projection.is_shared_path(rel, size, private_paths)`——≥ 64 KB、首段不是 `config/ debug/ logs/
  temp/ cache/ .pycache/ .mas-update*`、后缀不是 `.lock .sha256 .pth .log .tmp`、不在 `*.dist-info`
  里、不在谱系学到的 `privatePaths` 里（不再按后缀白名单）。满足的按 sha256 存进
  `data/maafw_blobs/<ab>/<sha256>`，载荷与视图里是指向它的 NTFS 硬链接，同样的字节只存一份；导入、
  更新构建新载荷、视图物化都走它。三条铁律：**永远不往已有文件里写**（硬链接没有写时复制）；小文件
  不进库（锁文件、`.pth`、dist-info 这类最可能被原地改写，M9A 的 bootstrap 就往 `python/*.lock` 里
  追加写）；链接失败就退回复制。可写的东西靠四层挡住：尺寸、排除表、运行期新建即新 inode、运行
  收尾的写穿巡检（`tools/embedded/view_audit.py`：nlink>1 且修改时间晚于物化时刻才读 sha，确认就
  隔离 blob、记 `privatePaths`、标载荷 `damaged`；`damaged` 的载荷下次更新只要全量包）。回收在启动期：`clean_maafw_embedded_copies`
  删无人引用的载荷（`embedded_project.collect_payload_garbage`：引用集 = 视图标记 ∪ 未完成切换的 to，
  谱系还有视图时再加它的 latest；一个视图都不剩的谱系整个收走，视图丢了但脚本还在的按导入来源保住；
  本进程起来之后建的不收。回收跑在后台、API 已在服务：删之前要在该谱系的 `lineage_lock` 内按盘上最新
  状态再判一次，否则判定之后刚登记的载荷会被一起删掉；整谱系收走时放锁后还会删锁文件和空目录，
  所以 `DurableFileLock` 的等待方碰到目录没了要重建再等，不能把这次撞车报给调用方），随后 `clean_maafw_runtime_blobs` 删 `st_nlink == 1` 的 blob。本机实测：inode 被映射（DLL 已加载）时
  删不掉的是它的最后一个链接，与进程经由哪个名字加载无关——视图里的名字（含正被经由加载的
  那个）都能删，只要库里的 blob 还在（见 `blob_store.py` 模块说明）。
- **同一项目再建一个脚本**走 `/maafw/embedded/sources`（候选）+ `/maafw/embedded/clone`
  （`embedded_project.clone_embedded_copy`）：从源脚本挂着的载荷物化目标视图（源正在切换就取 journal
  的目标），不读源视图、不要源空闲、源的运行期状态不带；只预约目标（源还是没采纳的老副本、只能按目录
  克隆时才预约源，源被占用就拒绝）；`Info.Path` 与 `Embedded.*`
  沿用源（两者必须成对继承），类型随项目。「复制脚本」（`Config.add_script`）复用同一个函数。
  视图与来源都没了时，`ensure_embedded_copy` 从同来源兄弟的谱系（没有兄弟就按载荷清单记的导入来源
  反查）按本脚本渠道的 latest 重建——来源可删这句承诺靠它兜底。更新包下载缓存
  `data/maafw_update_cache` 按 源 + 版本 + 文件名 命中，启动期 `Config.clean_maafw_update_cache`
  删 7 天没碰过的（`transport.prune_update_cache`）。
- **启动期一次性迁移**（`Config.migrate_maafw_embedded_copies_to_payloads`，排在各项回收之前，整段
  在后台任务里跑、不挡主定时器；期间拿不到视图预约的运行按「正在切换版本」跳过一次）：没有标记的老
  副本逐个采纳（`embedded_project.adopt_view`：**载荷内容以视图自身为准**——按视图自己的 interface
  算投影白名单，白名单内、不是已知运行期状态 / 日志的全部进载荷，内容取视图现状；更新器清单与来源
  目录只用来标 `origin`，不决定去留，否则「来源旧、视图新」会登记出残缺载荷）。全部采纳完再统一定
  同版本的 latest（`settle_adopted_latest`：有清单背书的、文件集合是超集的、文件多的优先，与脚本
  顺序无关），然后把每个组统一到 latest（运行中 `is_locked` 的脚本跳过，留给它的收尾同步或下次
  运行前检查；切过的标记记 `switchedBy=迁移`）；同版本合并时被切视图独有、或同路径内容不同的文件
  旧内容进 `local-modified` 留档。采纳失败的原样保留、下次再试。导入与采纳都把脚本记着的来源目录记进
  `lineage.json.knownSources`：视图丢了反查谱系重建、整谱系回收认「脚本还在」都看它（更新得来的载荷
  清单里没有导入目录）。
- **只支持发行包形态**：源码仓里 agent 写成 `"child_exec": "uv"`（`uv run agent/main.py`）
  这类开发者形态不支持、也不打算适配——发行包的打包流程会把它改写成
  `./python/python.exe`，导入发行包即可。
- Python agent 的解释器三种落法（`agent_env/planner.py`）：项目自带 `python/python.exe` 存在 →
  `project_python`；声明的是自带 Python 模式但文件不存在，或者裸写 `python` 让 PATH 去找
  （PI v2 示例与 MAA_Punish 的写法）→ 该项目专属隔离 venv（`isolated_venv`，按项目路径哈希
  定位）；其余 → `external`。目录里没有 Python **不是错误**。裸 `python` 不能原样交给 PATH：
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
- `Run.RunTimeLimit` 是套在单个用户整次 MaaFW 运行上的**硬超时**（`asyncio.wait_for`），
  与其他专项的"日志停滞超时"不同义；超时会丢掉本轮进度。
- Win32 下 `Game.LaunchMode` 只有两态：`DirectExe`（默认，MAS 启动、结束后一律关闭）与
  `AttachOnly`（其他方式启停，MAS 只接管窗口）。关不关只看 `opened_game`，没有开关；
  DirectExe 下发现游戏已在运行时也只接管、不关。`Game.UnityResolution`（Off / 1920x1080 /
  1280x720）走
  `game_resolution.py`：按 `<exe>_Data/app.info` 反查 `HKCU\Software\<公司>\<产品>`，
  只改 Unity 播放器的 `Screenmanager *` 值，不碰游戏自有的那层（星铁的
  `GraphicsSettings_PCResolution`、终末地的 `video_resolution_*`），效果要实机验证。
- 启动后再等（#889 起没有单独的键，上限就是 `Game.WaitTime`）：游戏是**本轮刚起来的**（MAS
  拉起，或接管时窗口是等出来的）才生效，从窗口出现起算，宿主把「最早可下发时刻」写进 job
  （`taskStartNotBefore`），worker 在资源 / controller / agent 初始化完成后每秒截一帧，两条提前
  放行：连续 5s 画面没变（静态登录页）；或连续 20s 有内容哪怕一直在动（`runner.py` 的
  `STARTUP_SCREEN_CONTENT_SECONDS`）。黑屏 / 纯色把两个计数都清零，截不到图就等满上限。
  游戏早就在跑、重试轮次、AttachOnly 都不等。真机数据（2026-09-19）：终末地主界面每秒 3~6%
  抽样点在动、崩坏三登录页 22~38%，「没变」对它们永远不成立；终末地在窗口后 22s、主界面
  还没出来时下发首个任务照样成功。背景：终末地窗口出现后登录界面要 22~31s 才渲染，MaaEnd 的
  SceneManager 见画面十几秒不变就判「环境识别异常」失败，beta.5 runner 启动变快（窗口→下发
  7~9s）后每次冷启动都撞上。
- 用户配置在 `check()` 时深拷贝成副本跑，`final_task` 解锁后**整表写回**（#720 / #737）。
  改任何运行期写用户字段的逻辑，都要用落盘探针验证，只看内存会误判成已生效。

## interface.json

- 加载器递归解析 `import`；`.json` 先 `json` 后退 `json5`，带 `//` 注释的 JSONC 可读；不认识的
  顶层字段（如 `telemetry`）忽略并告警。项目拆分资源（MaaEnd v2.28 的 `AutoEssence/`）
  不需要 MFW 侧适配。
- 预览的任务表里会多出 `__MXU_PRETASK__*` 伪任务（MXU 壳的前置任务），预设里也会出现；
  比较任务数时要减掉。
- 选项 `type` 支持 `select / scan_select / switch / checkbox / input / hotkey`，后端下发与
  前端 `MaaFWTaskOptionEditor.vue` 两侧都有；未知 type 前端有兜底提示。
- input 字段 `password: true`（PI v2.10.0）的值在 `Task.TaskSnapshot` 里是带 `mas-dpapi:` 前缀的
  DPAPI 密文：`Config.update_user` 写入前按 interface 加密（`tools/embedded/option_secrets`），
  `runner_task` 建计划前只在内存副本里解密；前端只看到密文、显示「已设置」。没有前缀的是旧明文，
  照常使用、下次保存时加密。checkbox 的 `min_count` / `max_count`（v2.10.1）由加载器放宽成自洽值，
  运行计划里不满足就报错（`MaaFWCheckboxCountError`），不静默截断。密码原文会随 override 进
  MaaFramework 自己写的项目日志 `debug/maafw.log`：`Tasker::post_task` 用
  `LogInfo << VAR(pipeline_override)` 记整份 override（INFO 级，不是只在 DBG 下），覆盖失败时
  `LogError` 再记一遍。**这份文件由框架直接写，MAS 管不了**，里面的密码是原文。MAS 自己的出口对
  **长度至少 4 个字符**（`MIN_REDACTED_SECRET_LENGTH`）的密码值都已打码
  （`option_secrets.redact_secret_text`，按文本全局替换成「<已隐藏>」）：`runner_task` 复制到
  `history/…/*.maafw.log` 的原生日志副本、转发的 worker stdout（协议行先解析、只打码给人读的
  文本，见 `_parse_worker_protocol_line`）与 stderr、`.worker.log`、pretask 输出。更短的值**不打码**
  （有意为之，本地测试钉住）：一两个字符全局替换会把日志里所有同样的字符都换掉，日志就没法看了。
  input 值下发失败的计划告警对密码字段一律不带原值、与长度无关（`MaaFWInputValueError(secret=True)`）。
  新增任何落盘 / 转发日志的路径都要过它；agent 进程自己写的日志同样不在 MAS 控制内。
- 加载器写的告警（`logger.warning`）由加载器旁听收集、挂在模型上（`interface_load_warnings`），
  随磁盘缓存保存，进运行计划的 `warnings`（运行日志开头）与导入报告；只给后端看的用
  `extra=_LOG_ONLY`。发行包的毛病能降级就降级：缺 import 文件、scan_dir 不在、缺
  interface_version（按 2）、input 的 default 写成数字、数字输入没填 / 填错（跳过该选项的
  覆盖）都是告警，不整份拒绝。
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
- 差量 / 全量只看当前载荷：`source.kind=update`（更新得来的，清单逐文件记包内哈希，指纹就是它
  现在的指纹——载荷不可变）才要差量包，本地导入的一律全量；差量基线用 `apply.py: _validate_plan_base`
  对载荷清单校验。全量包清的是旧载荷里 `origin=package` 且不在包内的，加上 `origin=import`、位于新
  interface 资源目录内、不在包内的（`apply._import_origin_orphans`：用户内容目录与运行时目录不碰）。
  `.mas-update` / `.mas-update-cache` 是更新器的保留目录；`debug` / `logs` / `temp` / `__pycache__` /
  `.pycache`、`config/maa_option.json` 与视图标记不计入指纹（agent 子进程与环境准备设了
  `PYTHONPYCACHEPREFIX=<项目根>/.pycache`，镜像树里项目根出现两遍，路径长到会撞 MAX_PATH 时不设
  前缀，见 `host_environment.project_pycache_prefix`）。
- 全量与差量包的落地条目都只从 `apply.py: build_package_plan` 枚举（`files` / `hashes` /
  `deleted` 三张表，按投影白名单过滤）。要改"哪些文件落盘"只动这一处。
- 预检备忘按**谱系 + 目标版本**记（`.payloads/<谱系>/precheck-<版本>.json`），组共有：一个成员预检
  过某版本失败，组里谁也不再为它下包；只有运行前 / 运行后自动更新读它，手动更新等于强制重试。
- "检查更新"走 `version_only`，不换下载地址——带 CDK 换地址会扣 Mirror 酱当日额度。

## 与专项的区别（别照搬）

- 没有 `ScriptConfig.py`，没有原生编辑器会话；已接入通用配置备份恢复
  （mas 池为纯字段侧车 + native 项目池，见 `tools/restore_service.py`）。
- 用户配置上的 `Info.Mode`（脚本/用户/直控）**没有任何 MaaFW 代码消费**；运行器只读
  `Info.IfQuickConfig`（关闭时按项目原生默认值跑，不下发任务快照与预设）。不要在 MaaFW 上
  按三态写逻辑。
- 新的 `interface.json` 项目默认用 MaaFW 类型即可运行；需要更精细的控制时（原生编辑器会话、
  登录/切号、按游戏语义组织的专属界面、对上游资源文件的动态读取等）可以立专项，MaaEnd 就是
  这种情况。立专项时在专项目录写明它比通用 MaaFW 多控制了什么。

## 测试与排障

- 夹具要照抄真实输出的形状（interface 加载结果、更新器返回、运行计划），臆造键名会让
  "读错键"类缺陷全程绿灯。
- 本地边界测试会在临时目录建很深的树，`--basetemp` 用短路径（如 `%TEMP%\mfwt\pt`），
  否则 Windows 报 `WinError 206`，看起来像代码坏了。
- 排障先看 `history/<日期>/…/<时分秒>.maafw.log`（`grep -a`）：agent 协议版本不匹配之类
  只记在那里，宿主日志只有一句"连接超时"。
