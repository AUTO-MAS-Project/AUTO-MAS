# 集成 wheelhouse：构建、锁定与离线安装

发布物必须由 `scripts/build_complete_integration_wheelhouse.ps1` 生成。它串联两个阶段：

1. `build_integration_wheelhouse.ps1` 从源码快照构建 23 个插件 distribution，并核验 21 个唯一插件入口；该阶段输出只是 `plugin-seed-only`，不能随应用发布。
2. `complete_integration_wheelhouse.ps1` 解析宿主与插件的完整 Windows x64 / CPython 3.12 闭包，优先下载锁中精确指定的兼容 wheel；若包没有兼容 wheel，则下载锁定 sdist 并在离线、无依赖解析、无构建隔离模式下生成单个 wheel。所有输入先复核大小和 SHA-256，最终 wheel 再复核兼容标签与 `METADATA` 后才进入发布目录。

## 源码范围

构建器默认读取以下仓库，但所有路径均可通过参数覆盖：

- 当前集成工作树：`AUTO-MAS`、browser、OK Script、OK-WW；
- `plugins/automas-hsr`；
- `plugins/automas-m9a`；
- `plugins/automas-maafw`；
- `plugins/automas_mxu_import`；
- `plugins/automas-maaend-adapter`；
- `plugins/automas_script_maa`。

每个项目先被复制到全新的暂存目录，再从副本运行 `uv build --wheel --offline --no-sources --no-build-isolation`。外层独立仓库不会出现 `dist`、`build` 或 `egg-info`，其未提交内容、Git 历史和配置也不会被修改。

构建基线是 23 个 distribution 和 21 个 `auto_mas.plugins` / `automas.plugins` 入口。三个新增官方插件的入口为：

- `mxu_import = automas_plugin_mxu_import.plugin:Plugin`；
- `maaend_adapter = maaend_adapter.plugin:Plugin`；
- `script_MAA = script_maa.plugin:Plugin`。

## 一键执行

该命令会调用 uv 及指定 Python。按照工作区规则，实际运行前必须通过工具权限机制明确批准用途。

```powershell
& .\scripts\build_complete_integration_wheelhouse.ps1 `
    -OutputDirectory 'D:\artifacts\AUTO-MAS-complete-wheelhouse-20260722' `
    -ExcludeNewer '2026-07-22T00:00:00Z'
```

当前可用工具并不全部位于同一个解压目录：

- uv：`environment\python\Scripts\uv.exe`（已探测为 uv 0.11.30）；
- Python：`build\environment-tar\environment\python\python.exe`（CPython 3.12.0）；
- Git：`build\environment-tar\environment\git\bin\git.exe`。

一键脚本会先查找 `EnvironmentRoot\python\Scripts\uv.exe`，再兼容当前工作区的 `environment\python\Scripts\uv.exe` 布局。若布局变化，应显式传入 `-UvPath`、`-PythonPath`、`-GitPath` 与 `-EnvironmentRoot`；不要假定单独解压的环境归档必然已经包含 uv。

若未传 `-ExcludeNewer`，闭包完成器从插件 seed 的确定性 `source_date_epoch` 推导截止时间，而不是使用运行时的“现在”。同一个 epoch 也会作为 sdist 构建的 `SOURCE_DATE_EPOCH`，并固定 `PYTHONHASHSEED=0`。正式发布仍建议显式记录截止时间。输出目录、seed 目录和两个暂存目录都必须是新目录；脚本不会清空或覆盖已有目录，失败现场（包括每个 sdist 的独立构建子目录和日志）会保留供审计。默认 runtime staging、每个 `b*/w` 构建目录以及独立的 `p*` pip 临时目录刻意采用短名称，以给 pip 内部多层临时 wheel/cache 路径留出足够的 Windows `MAX_PATH` 余量。

## 闭包与锁定规则

宿主 `pyproject.toml` 的直接依赖必须全部使用 `==` 固定。完成器先生成宿主闭包，再以宿主闭包的每个精确版本作为 constraints 解析“宿主 + 插件外部依赖”闭包。两个锁必须为每个受保护宿主包选择完全相同的来源类型、HTTPS URL、文件名、大小和 SHA-256；任何漂移都会使构建失败。源只允许安全 basename，所有下载、seed 读取和发布路径都必须再次解析并证明位于其指定目录内。

锁中若存在兼容 CPython 3.12 / Windows x64 wheel，完成器绝不退回 sdist；只有完全没有兼容 wheel 时，才接受包含 HTTPS URL、正整数大小和 SHA-256 的 `.tar.gz` 或 `.zip` sdist。构建命令固定等价于：

```powershell
<固定 Python> -m pip wheel --no-deps --no-build-isolation --no-index --no-cache-dir --wheel-dir <全新目录> <已验签 sdist>
```

因此构建后端必须已存在于固定 Python 环境，完成器不会联网补装构建依赖。`runtime-lock.json` 和 `manifest.json` 始终记录最终 wheel 的文件名、大小和 SHA-256；由 sdist 生成时还记录原始 sdist 的 URL、文件名、大小、SHA-256 以及确定性构建参数。

最终 `runtime-lock.json` 把 wheel 划分为互斥的三个 scope：

- `host_runtime`：只安装到 `.venv`；
- `plugin_runtime`：宿主闭包没有、但插件需要的第三方依赖，只安装到 `plugins/pypi/site-packages`；
- `plugin`：23 个本地构建的插件 wheel，只安装到插件 target。

同一规范化 distribution 不得跨 scope；23 个插件及其 21 个 group/name/value 入口必须同时在 `manifest.json` 与 `runtime-lock.json` 中唯一出现。完成器还保留标准 `pylock.host.toml` 和 `pylock.combined.toml`，用于复核解析来源。pylock 格式遵循 [PyPA pylock.toml 规范](https://packaging.python.org/en/latest/specifications/pylock-toml/)。

完整输出至少包含：

- 所有最终精确 wheel（发布目录中不保留 sdist）；
- `manifest.json`（schema 3，完整文件大小与 SHA-256）；
- `runtime-lock.json`（schema 1，安装 scope 与入口契约）；
- `pylock.host.toml`；
- `pylock.combined.toml`。

## 应用运行时契约

Electron 在使用 wheelhouse 前会校验 manifest、runtime-lock、自身哈希、所有 wheel 哈希、23/21 计数、入口三元组和 scope 互斥性。插件 seed、缺失 lock、未声明 wheel、哈希不符或入口不完整都会失败关闭，不会退回源码或 PyPI。

安装命令只允许精确的本地 wheel 绝对路径，等价于：

```powershell
uv pip install --python <目标 Python> --no-index --no-deps <wheel1> <wheel2> ...
```

锁定路径禁止 `--upgrade`、`--index-url`、`--extra-index-url`、`--find-links` 和包名动态解析，同时清除 uv/pip index 环境变量并启用离线模式。宿主闭包不会被复制到插件 target，因此插件不能用自己的依赖覆盖宿主固定版本。

`.venv` 和插件 target 都先在同卷新目录安装并验证，再通过 rename 切换。切换前写入 crash journal；启动时如发现未完成事务，会优先恢复旧目录。所有 uv/Python 子进程都有超时并在 Windows 上终止整个进程树。插件 promotion 前会用 `.venv` Python 的隔离进程逐一加载锁中 21 个入口，模块缺失、依赖缺失、入口值漂移或超时均阻止切换。

## 发布接入

只有完整输出目录可以替换工作树的 `plugins/wheels`。不要复用或增量补齐旧目录；发布流程应把完整目录作为一个经过审计的原子资源导入。Electron Builder 会携带 `*.whl`、`manifest.json`、`runtime-lock.json` 和两个 pylock 文件，集成快照 marker 同时固定 manifest schema 3、runtime-lock schema 1、23 个插件 distribution 与 21 个入口。

静态验证可运行：

```powershell
yarn.cmd --cwd .\frontend build:main
yarn.cmd --cwd .\frontend test
```

这两条命令不构建 wheel；真实 wheel 构建和闭包解析仍必须单独获批后执行一键脚本。

## 2026-07-22 v6 Alpha c2 发布记录

当前 v6 Alpha 快照为 `v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1`，完整 wheelhouse 位于 `build/w/c2`。`res/integration-snapshot.json` 将其声明为 `bundled-snapshot`，并固定下面的 manifest、runtime-lock、计数与 Core 版本。工作树中的旧候选和历史备份仍只用于审计，不得冒充 c2 交付物。

| 项目 | c2 实际值 |
| --- | --- |
| manifest schema | 3 |
| runtime-lock schema | 1 |
| wheel / 发布目录文件 | 127 / 131 |
| host runtime / plugin runtime / plugin | 95 / 9 / 23 |
| 宿主直接固定依赖 | 31 |
| 唯一 entry point | 21 |
| Core distribution | `auto-mas-core==6.0.0a1` |
| 发布目录字节数 | 153,619,542 |
| `manifest.json` SHA-256 | `7123F7CA99A843E34C189F99744CECB568BD82A348B1457ED634438CECAD199B` |
| `runtime-lock.json` SHA-256 | `8A1CA0B31634AE2E63E55440C34C3A38998E3D20F68CA55CB6E620DA94EF3069` |

31 是宿主 `pyproject.toml` 的直接、精确固定依赖数；锁解析后的宿主闭包为 95 个 distribution。加上 9 个仅插件使用的运行时依赖和 23 个插件 distribution，最终恰为 127 个 wheel。发布目录另含 `manifest.json`、`runtime-lock.json`、`pylock.host.toml` 与 `pylock.combined.toml`，所以文件总数为 131。

洁净验收在全新 `build/clean-runtime-alpha-c2/validated-staging` 中使用 CPython 3.12 隔离模式执行。机器结果 `verification-route-first-final.json` 与 `verification-direct-final.json` 均为 `exit_code=0`、`errors=[]`：

- 宿主运行时 distribution：95/95；
- 插件 target：32/32，即 9 个 plugin runtime + 23 个 plugin distribution；
- entry point：21/21 发现且 21/21 加载，真实 API 路由优先导入后仍无契约差异；
- 显式 no-config 插件：15/15，有效配置为 `{}`；
- source/editable 回退：0。

Config v2 在本 Alpha 中默认运行于 `shadow` 模式：旧 JSON 仍是权威源，只做预检和安全的影子输出；该 wheelhouse 验收不代表已启用 Config v2 authoritative 模式。

本记录覆盖构建闭包、哈希、隔离安装和插件加载契约，不包含真实游戏、真实账号或真实设备 E2E。涉及 HSR、M9A、MaaFW、MAA、MaaEnd、ADB/Win32 控制器的业务效果仍需在受控测试账号与设备上单独验收。
