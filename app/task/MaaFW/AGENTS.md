# `app/task/MaaFW` 说明

MaaFW 是**通用引擎**，不是专项：任何带 `interface.json` 的 MaaFramework 项目都由它运行。
专项适配那一套（原生编辑器会话、脚本/用户/直控三态、配置备份恢复）不适用，见末节。
本文件只记录代码里读不出来、但改错了会出事的约束。

## 布局与边界

- `embedded_manager.py`：宿主侧管理器——任务调度、更新时机、运行环境确认、用户配置副本与写回。
- `tools/embedded/`：宿主与核心包之间**唯一**的接缝（`runner_task`、`runtime_route`、
  `update_credentials`、`project_path`、`env_cache`、`game_package`、`embedded_project`）。要读 `Config`、发通知、
  碰宿主模型，只能在这里和 `embedded_manager.py` 里做。
- `tools/core/automas_maafw_*`：六个核心包（interface / runner / runtime_pool / agent_env /
  project_update / controller_win32），按零宿主耦合设计。已知例外只有
  `project_update/updater.py` 引了 `app.utils.constants`——它只在宿主进程里跑；不要再加新的。
- **worker 子进程**（`automas_maafw_runner/worker.py`）以 `python -m` 启动，其导入闭包内的
  `app.*` 只能落在 `app.task.MaaFW.tools.core.` 之下，由
  `tests/task/test_maafw_worker_import_isolation.py` 钉死。v5.5.0-beta.4 全员 MFW 挂掉，
  就是链路上多了一处 `from app.utils import ...`。改 runner 子树前先跑这个测试。

## 项目目录与运行

- **有效项目根只从一处取**：`tools/embedded/embedded_project.resolve_maafw_project_root`
  ——内嵌脚本是 `data/maafw_projects/<脚本 uuid>/` 的副本，否则是 `Info.Path`。manager 三处、
  `runner_task`、`api/scripts.py` 的 `/maafw/update` 都走它；`/maafw/preview`、
  `/maafw/agent-env/prepare` 带 `scriptId` 时也按脚本解析，`path` 只在没有脚本时兜底。
  新增任何"读项目目录"的代码不要再各自读 `Info.Path`。
- **内嵌副本**：按 interface 白名单投影（`project_update/projection.py`），副本路径由脚本 ID
  推出、不进配置、不可手改；`Info.Path` 永远是来源目录，来源一个字节不动、也不由 MAS 删。
  导入在 `data/maafw_projects/.staging/` 里投影完再原子换入，失败不动旧副本；副本缺失且来源
  还在时 check / preview / update 入口自修复。删脚本连带删副本。
- 内置运行从不启动项目自带的界面程序（MFW.exe / MFAAvalonia / MXU）。副本里去掉了 `maafw/`
  与自带 `python/`，两者由运行池提供——但版本必须与来源自带的一致：agent 与 runner 之间有
  协议版本号，跨版本只表现为「AgentClient 连接超时」；agent 又常写死 Python 大版本
  （create-maa-project 模板要求 >=3.13,<3.14，宿主 3.12 建的隔离 venv 会被它拒绝，宿主只看到
  「Agent 进程已退出」）。投影时把两者写进副本根 `.auto_mas_maafw_projection.json`
  （`bundledMaaFWVersion` / `bundledPythonVersion`），runner 的 `probe_bundled_maafw_version`
  没原生库时读前者，`agent_env/env.py` 按后者向运行池要同大版本的解释器建隔离 venv（已有
  venv 版本不对就重建）；更新落地时随包换、进清单，也在环境指纹里。`contracts.py` 里那个
  `.auto_mas_maafw_native_runtime.json` 只剩指纹忽略用，没有代码再往项目里铺运行时。
- **agent 不是 Python 时，`maafw/` 整目录留在副本里**：Go / C++ 的二进制 agent 启动时从
  `<项目>/maafw` 加载 `MaaFramework.dll` / `MaaAgentServer.dll`（实测 MaaYYs 的 agent.exe，
  找不到直接 fatal 退出）。这时 runner 也用同一份库（与路径模式一致，项目的自定义构建随之保住），
  副本省下的比例会明显小于 Python agent 的项目（MaaYYs 29%，M9A 89%）。
- Python agent 的解释器三种落法（`agent_env/planner.py`）：项目自带 `python/python.exe` 存在 →
  `project_python`；声明的是自带 Python 模式但文件不存在，或者裸写 `python` 让 PATH 去找
  （PI v2 示例与 MAA_Punish 的写法）→ 该项目专属隔离 venv（`isolated_venv`，按项目路径哈希
  定位）；其余 → `external`。目录里没有 Python **不是错误**。裸 `python` 不能原样交给 PATH：
  worker 跑在运行池 venv 里，Windows 上 `CreateProcess` 先按父进程（基解释器）所在目录找，
  且用的是父进程的 PATH，传给子进程的 `env["PATH"]` 不参与查找，结果永远是没装 `maa` 的
  基解释器。
- `Run.RunTimeLimit` 是套在单个用户整次 MaaFW 运行上的**硬超时**（`asyncio.wait_for`），
  与其他专项的"日志停滞超时"不同义；超时会丢掉本轮进度。
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
- 项目指纹在本地算（`project_update/contracts.py: project_fingerprint`），只用来防"计划与落地
  之间树被改动"，发布方不参与；差量包的基线校验用的是 MAS 自己上次落地记下的清单
  （`apply.py: _validate_plan_base`）。`.mas-update` / `.mas-update-cache` 是更新器的保留目录，
  `debug` / `logs` / `temp` / `__pycache__` 与 `config/maa_option.json` 不计入指纹。
- 全量与差量包的落地条目都只从 `apply.py: build_package_plan` 枚举（`files` / `hashes` /
  `deleted` 三张表）。要改"哪些文件落盘"只动这一处，孤儿清理、基线、回滚会自然跟随。
  内嵌脚本传 `projection=True`，三张表在 `_project_package_entries` 里按同一份白名单过滤，
  投影标记也在那里随包换入。
- 无可信基线时请求整包；整包落地也会清理包内资源目录下的孤儿文件，但保留用户内容目录与
  运行时目录（口径见 `tests/task/test_maafw_project_update_orphans.py`）。
- "检查更新"走 `version_only`，不换下载地址——带 CDK 换地址会扣 Mirror 酱当日额度。

## 与专项的区别（别照搬）

- 没有 `ScriptConfig.py`，没有原生编辑器会话，没有配置备份恢复。
- 用户配置上的 `Info.Mode`（脚本/用户/直控）与 `Info.IfQuickConfig` **没有任何 MaaFW 代码
  消费**（#788 起运行器也不再读后者，用户页上配的任务队列就是要跑的内容）；两个字段只是
  还留在模型里。不要在 MaaFW 上按三态写逻辑。
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
