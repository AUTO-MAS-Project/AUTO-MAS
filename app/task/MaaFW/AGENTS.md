# `app/task/MaaFW` 说明

MaaFW 是**通用引擎**，不是专项：任何带 `interface.json` 的 MaaFramework 项目都由它运行。
专项适配那一套（原生编辑器会话、脚本/用户/直控三态、配置备份恢复）不适用，见末节。
本文件只记录代码里读不出来、但改错了会出事的约束。

## 布局与边界

- `embedded_manager.py`：宿主侧管理器——任务调度、更新时机、运行环境确认、用户配置副本与写回。
- `tools/embedded/`：宿主与核心包之间**唯一**的接缝（`runner_task`、`runtime_route`、
  `update_credentials`、`update_mirrors`、`project_path`、`env_cache`、`game_package`、
  `game_resolution`、`update_progress`）。
  要读 `Config`、发通知、碰宿主模型，只能在这里和 `embedded_manager.py` 里做。
- `tools/core/automas_maafw_*`：六个核心包（interface / runner / runtime_pool / agent_env /
  project_update / controller_win32），按零宿主耦合设计。已知例外只有
  `project_update/updater.py` 引了 `app.utils.constants`——它只在宿主进程里跑；不要再加新的。
- **worker 子进程**（`automas_maafw_runner/worker.py`）以 `python -m` 启动，其导入闭包内的
  `app.*` 只能落在 `app.task.MaaFW.tools.core.` 之下，由
  `tests/task/test_maafw_worker_import_isolation.py` 钉死。v5.5.0-beta.4 全员 MFW 挂掉，
  就是链路上多了一处 `from app.utils import ...`。改 runner 子树前先跑这个测试。

## 项目目录与运行

- 项目根有两类来源，改语义时要分开数：
  - **按脚本配置读 `Info.Path`** 的六处：`embedded_manager.check` / `_run_project_update` /
    `_ensure_project_environment`、`runner_task`、`api/scripts.py` 里的 `/maafw/update`
    （按 scriptId 取脚本配置）与更新源外壳提示。
  - **由请求显式传 `path`** 的两个端点：`/maafw/preview`、`/maafw/agent-env/prepare`，前端
    把编辑页当前的路径传过来，不经过脚本配置。
  要改项目根语义，先把第一类收敛到一个助手，再决定第二类是继续收 `path` 还是改按 scriptId 解析。
- 内置运行从不启动项目自带的界面程序（MFW.exe / MFAAvalonia / MXU）。MaaFramework 原生运行时
  由运行池提供，运行时以覆盖层铺进 `<项目>/maafw/` 并留 `.auto_mas_maafw_native_runtime.json`
  标记；带标记的 `maafw/` 是运行期产物，指纹与更新都把它当产物处理。
- Python agent 的解释器三种落法（`agent_env/planner.py`）：项目自带 `python/python.exe` 存在 →
  `project_python`；声明的是自带 Python 模式但文件不存在，或者裸写 `python` 让 PATH 去找
  （PI v2 示例与 MAA_Punish 的写法）→ 该项目专属隔离 venv（`isolated_venv`，按项目路径哈希
  定位）；其余 → `external`。目录里没有 Python **不是错误**。裸 `python` 不能原样交给 PATH：
  worker 跑在运行池 venv 里，Windows 上 `CreateProcess` 先按父进程（基解释器）所在目录找，
  且用的是父进程的 PATH，传给子进程的 `env["PATH"]` 不参与查找，结果永远是没装 `maa` 的
  基解释器。
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
- **连上控制器后先截一张图**（`runner._prime_first_screencap`，每次连接一次，在启动画面判定与
  首个任务之前），不是多余代码：控制器没截过图时 binding 的 `cached_image` 抛
  `Failed to get cached image.`、`resolution` 是 (0, 0)，而有的项目的 agent 在 tasker sink 里于
  任务 Starting 时就读这两个值（M9A v4.10.0 的 `aspect_ratio` sink 读到 0 直接 `post_stop`，
  ADB 路径第一个任务一开始就被停掉）。MFAAvalonia 连上后同样先截一次
  （`MaaProcessor.MeasureScreencapPerformanceAsync`）。截图失败只记日志、不拦运行。
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
  `debug` / `logs` / `temp` / `__pycache__` 与 `config/maa_option.json` 不计入指纹。
- 全量与差量包的落地条目都只从 `apply.py: build_package_plan` 枚举（`files` / `hashes` /
  `deleted` 三张表）。要改"哪些文件落盘"只动这一处，孤儿清理、基线、回滚会自然跟随。
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
