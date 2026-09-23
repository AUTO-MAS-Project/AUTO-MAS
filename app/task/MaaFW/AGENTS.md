# `app/task/MaaFW` 说明

MaaFW 是**通用引擎**，不是专项：任何带 `interface.json` 的 MaaFramework 项目都由它运行。
专项适配那一套（原生编辑器会话、脚本/用户/直控三态、配置备份恢复）不适用，见末节。
本文件只记录代码里读不出来、但改错了会出事的约束。

## 布局与边界

- `embedded_manager.py`：宿主侧管理器——任务调度、更新时机、运行环境确认、用户配置副本与写回。
- `tools/embedded/`：宿主与核心包之间**唯一**的接缝（`runner_task`、`runtime_route`、
  `update_credentials`、`update_mirrors`、`project_path`、`env_cache`、`game_package`、
  `game_resolution`、`update_progress`、`embedded_project`）。
  要读 `Config`、发通知、碰宿主模型，只能在这里和 `embedded_manager.py` 里做。
- `tools/core/automas_maafw_*`：六个核心包（interface / runner / runtime_pool / agent_env /
  project_update / controller_win32），按零宿主耦合设计。已知例外只有
  `project_update/updater.py` 引了 `app.utils.constants`——它只在宿主进程里跑；不要再加新的。
- **worker 子进程**（`automas_maafw_runner/worker.py`）以 `python -m` 启动，其导入闭包内的
  `app.*` 只能落在 `app.task.MaaFW.tools.core.` 之下，由
  `tests/task/test_maafw_worker_import_isolation.py` 钉死。v5.5.0-beta.4 全员 MFW 挂掉，
  就是链路上多了一处 `from app.utils import ...`。改 runner 子树前先跑这个测试。

## 项目目录与运行

- **有效项目根只从一处取**：`tools/embedded/embedded_project.resolve_maafw_project_root`
  ——**永远是** `data/mfw/<脚本 uuid 前 12 位>/` 的副本，没有"路径模式"。`Info.Path` 只是
  导入的来源，运行时不读它；导入完成后用户删掉来源也无妨。manager 三处、`runner_task`、
  `api/scripts.py` 的 `/maafw/update` 都走它；`/maafw/preview`、`/maafw/agent-env/prepare`、
  `/maafw/game-package` 带 `scriptId` 时也按脚本解析，`path` 只在没有脚本时兜底。
  新增任何"读项目目录"的代码不要再各自读 `Info.Path`。副本可能还没建（升级前的老脚本、
  刚选目录、来源换了目录），各入口先经 `ensure_embedded_copy`：副本不在或 `Info.Path` 与导入
  报告里的 `sourcePath` 不是同一目录就导入一次；来源不在而副本健康时什么都不做。
- **内嵌副本**：按 interface 白名单投影（`project_update/projection.py`），**白名单之外的顶层条目
  剩余 ≤ 64 MB 的也带走**（MaaEnd 的 `data/`、`locales/`，MaaYYs 的 `assets/答案.csv`，M9A 的
  `data/activity` 都没在 interface 里声明却是 agent 运行时要读的；更大的顶层目录、根上没声明的
  exe / dll、.NET 外壳的 `libs/` 才是外壳运行时）。外壳是冻结的 Python 程序时（根上直接躺着没人
  声明的 `python312.dll`，Maa_bbb 的 MFW.exe 就是），它散在根目录的二进制依赖包（带 `.pyd`，或
  `*.libs` / `*.dist-info`）也不带：agent 子进程的 `PYTHONPATH` 是项目根，`backports/zstd/`
  这种没有 `__init__.py` 的半截包会变成命名空间包盖住真正的模块——副本上 pip 就是这样崩的。
  副本路径由脚本 ID 推出（`embedded_copy_dir_name`：uuid 去连字符取前 12 位，短是为了 pyc 前缀树
  与深层 site-packages 不撞 MAX_PATH）、不进配置、不可手改；来源目录一个字节不动、也不由 MAS 删。脚本页
  「选择本地目录」就是 `/maafw/embedded/reimport`：第一次是导入，之后是换来源或按当前来源重导；
  没有 enable / disable 这种开关路由，`Embedded.*` 里只有报告、来源版本与导入时间。
  导入在 `data/mfw/.staging/` 里投影完再原子换入，失败不动旧副本；副本缺失且来源
  还在时 check / preview / update 入口自修复。删脚本连带删副本。
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
- **副本之间按内容共用文件**（`project_update/blob_store.py`）：上面那些运行时目录里的一切，
  加上白名单内其它位置的模型 / 二进制文件（`projection.SHARED_CONTENT_SUFFIXES`：onnx / bin /
  pth / pyd / dll / so / 字体……；JSON、图片、脚本一律不算，项目 agent 热更新的就是它们），
  ≥ 64 KB 的按 sha256 存进 `data/maafw_blobs/<ab>/<sha256>`，副本里是指向它的 NTFS 硬链接，
  同样的字节只存一份；导入（`materialize_projection`）与更新落地（`apply.py`）都走
  `ProjectionRules.is_shared_file` 这一个谓词。同一项目的第二份副本因此只多小文件、项目热更新
  数据与日志（M9A 实测独占 116 MB → 41.5 MB）。三条铁律：
  **永远不往已有文件里写**（硬链接没有写时复制，更新器的 `_copy_path` / 回滚都是先删再写，
  内容没变的文件连碰都不碰）；小文件不进库（锁文件、`.pth`、dist-info 这类最可能被原地改写，
  M9A 的 bootstrap 就往 `python/*.lock` 里追加写）；链接失败就退回复制。回收在启动期
  `clean_maafw_runtime_blobs`（`st_nlink == 1` 即孤儿）。已知边界：A 在跑（DLL 被映射）时
  B 恰好要换同一份旧库会被挡住，事务照常回滚。
- **同一项目再建一个脚本**走 `/maafw/embedded/sources`（候选）+ `/maafw/embedded/clone`
  （`embedded_project.clone_embedded_copy`）：从源脚本的副本克隆，已共用的文件再挂硬链接、还没入库的
  模型经共用库放过去、`debug/` 与字节码不带，staging 建好再原子换入；源与目标各持项目预约，源运行中
  拒绝；`Info.Path` 与 `Embedded.*` 沿用源，类型随项目。「复制脚本」（`Config.add_script`）复用同一个
  函数。来源目录已删、副本又没了（复制脚本时源正忙没复制到副本、副本被手删）时，
  `ensure_embedded_copy` 在其它同来源、副本健康的 MFW 脚本里克隆一份再报错——来源可删这句承诺
  靠它兜底。更新包下载缓存 `data/maafw_update_cache` 按 源 + 版本 + 文件名 命中，启动期
  `Config.clean_maafw_update_cache` 删 7 天没碰过的（`transport.prune_update_cache`）。
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
  5.11.1/协议 7），表现只有一句「AgentClient 连接超时」。准备运行环境时对**内嵌副本**把它钉回
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
- 项目指纹在本地算（`project_update/contracts.py: project_fingerprint`），只用来防"计划与落地
  之间树被改动"，发布方不参与；差量包的基线校验用的是 MAS 自己上次落地记下的清单
  （`apply.py: _validate_plan_base`）。`.mas-update` / `.mas-update-cache` 是更新器的保留目录，
  `debug` / `logs` / `temp` / `__pycache__` / `.pycache` 与 `config/maa_option.json` 不计入指纹
  （agent 子进程与环境准备设了 `PYTHONPYCACHEPREFIX=<项目根>/.pycache`，pyc 全落那棵镜像树，
  它里面没有 `__pycache__` 这一层，漏掉它差量更新就永远退化成全量包）。镜像树里项目根出现两遍，
  安装路径长到会撞 MAX_PATH（`host_environment.project_pycache_prefix` 的预算）且没开长路径支持时
  不设前缀，pyc 退回源码旁——解释器写 pyc 失败是静默的，不设比每次启动全量重编译强。
- 全量与差量包的落地条目都只从 `apply.py: build_package_plan` 枚举（`files` / `hashes` /
  `deleted` 三张表）。要改"哪些文件落盘"只动这一处，孤儿清理、基线、回滚会自然跟随。
  内嵌脚本传 `projection=True`，三张表在 `_project_package_entries` 里按同一份白名单过滤，
  投影标记也在那里随包换入。
- 无可信基线时请求整包；整包落地也会清理包内资源目录下的孤儿文件，但保留用户内容目录与
  运行时目录（口径见 `tests/task/test_maafw_project_update_orphans.py`）。
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
- `test_maafw_project_update_orphans.py` 会在临时目录建很深的树，`--basetemp` 用短路径
  （如 `%TEMP%\mfwt\pt`），否则 Windows 报 `WinError 206`，看起来像代码坏了。
- 排障先看 `history/<日期>/…/<时分秒>.maafw.log`（`grep -a`）：agent 协议版本不匹配之类
  只记在那里，宿主日志只有一句"连接超时"。
