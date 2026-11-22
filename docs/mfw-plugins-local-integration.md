# MFW 插件族本地联调

宿主不再内置通用 MFW、M9A、MSS（见 [maafw-plugin-migration.md](maafw-plugin-migration.md)）。只用发行版时什么都不用做：配置里有这三类托管，宿主启动时会从 PyPI 装上并启用对应插件；新用户在插件中心装 `auto-mas-maafw-adapter`、`auto-mas-m9a-adapter`、`auto-mas-mss-adapter` 即可。

本文写**要改插件包源码时**怎样把本地源码接进宿主、怎样确认装的是本地这份、怎样走一遍主路径和一次无害的真跑，以及怎样拿存量配置的副本演练升级。下面的命令和结果是 2026-11-22 在本分支实际跑通的（端口 36196，换成任何空闲端口都行）。

涉及的包：

- 六个插件：积木仓库 [AUTO-MAS-MaaFW](https://github.com/AUTO-MAS-Project/AUTO-MAS-MaaFW) 的 `packages/` 下三块服务插件（`maafw_agent_env`、`maafw_runner`、`maafw_project_update`），三个专项仓库（`maafw_adapter`、`m9a_adapter`、`mss_adapter`）。
- 三块库：同一积木仓库里的 `auto-mas-maafw-interface`、`auto-mas-maafw-native`、`auto-mas-maafw-adapter-kit`（专项共用库）。

## 1. 打库的 wheel

从积木仓库已提交的 HEAD 导出再打，不直接用工作目录（工作目录里残留的 `build\lib` 会混进 wheel）：

```powershell
$uv  = '<uv.exe>'
$w   = Join-Path $env:TEMP 'mfwl'
$src = Join-Path $w 'blk'
if (Test-Path $src) { Remove-Item -Recurse -Force $src }
New-Item -ItemType Directory -Force $src, "$w\wheels" | Out-Null
git -C <积木仓库> archive --format=tar -o "$w\blk.tar" HEAD
tar -xf "$w\blk.tar" -C $src
foreach ($p in 'auto-mas-maafw-interface', 'auto-mas-maafw-native', 'auto-mas-maafw-adapter-kit') {
    & $uv build --wheel "$src\packages\$p" --out-dir "$w\wheels"
}
```

## 2. 接入

从宿主树根：

```powershell
$b = '<积木仓库>\packages'
pwsh -NoProfile -File scripts\dev\link_mfw_plugins.ps1 `
  -AgentEnv "$b\auto-mas-maafw-agent-env" `
  -Runner "$b\auto-mas-maafw-runner" `
  -ProjectUpdate "$b\auto-mas-maafw-project-update" `
  -MaaFWAdapter <AUTO-MAS-MaaFW-Adapter 仓库根> `
  -M9AAdapter <AUTO-MAS-M9A-Adapter 仓库根> `
  -MssAdapter <AUTO-MAS-MSS-Adapter 仓库根> `
  -WheelDir "$env:TEMP\mfwl\wheels" `
  -RefreshLibraries
```

脚本在 `plugins\` 下给六个插件建目录联接（宿主把带 `pyproject.toml` 和 `src\` 的子目录当本地插件），并在 wheel 目录写 `uv.toml`（`[pip] find-links` 指向 wheel 目录）。联接被 `.gitignore` 忽略，不要提交。

`-RefreshLibraries` 删掉 `plugins\pypi\environment.json` 并清掉 uv 缓存里的三块库，下次启动重新解析、重装。**库重打过而版本号没变时必须加**，否则宿主沿用已装的旧库。插件源码改了不用加：本地插件直接从源码导入，积木改了重启后端，专项可以在插件中心重载。

## 3. 起后端

想从干净数据起，先停后端，把树根的 `config\ data\ debug\ history\ temp\` 和 `plugins\pypi\` 挪走（挪到 `$env:TEMP` 下备着，别删）。然后：

```powershell
$env:AUTO_MAS_ENV       = 'dev'
$env:AUTO_MAS_HTTP_PORT = '36196'
$env:AUTO_MAS_UV_EXE    = '<uv.exe>'
$env:UV_CONFIG_FILE     = "$env:TEMP\mfwl\wheels\uv.toml"
Start-Process .\.venv\Scripts\python.exe -ArgumentList main.py -WorkingDirectory . `
  -RedirectStandardOutput <日志目录>\out.txt -RedirectStandardError <日志目录>\err.txt -PassThru
```

- 必须是 `UV_CONFIG_FILE`：宿主解析插件依赖时命令行自带 `--find-links`，`UV_FIND_LINKS` 会被盖掉，只有 `UV_CONFIG_FILE` 里的 find-links 会合并进去。
- 常驻进程不要用管道接输出（子进程继承管道句柄，调用方一直等不到结束），重定向到文件。
- 日志在 stderr 那份文件里。首次启动约 20 秒（含「首次安装游戏管理插件」），日志有「插件依赖准备完成，开始加载插件」。

## 4. 确认装的是本地这份

`POST /api/plugin/list {}`：六个插件 `source=local`；版本号仍是 `0.1.0`（与 PyPI 上已发的同号）。

三块库装在 `plugins\pypi\site-packages`。**本地 wheel 与 PyPI 上的同版本号时，uv 拿哪一份没有保证**，要比一次文件：

```python
import hashlib, pathlib

site = pathlib.Path(r"plugins\pypi\site-packages")
blocks = pathlib.Path(r"<积木仓库>\packages")
for mod, pkg in [
    ("maafw_interface", "auto-mas-maafw-interface"),
    ("maafw_native", "auto-mas-maafw-native"),
    ("maafw_adapter_kit", "auto-mas-maafw-adapter-kit"),
]:
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    a = {p.relative_to(site / mod): h(p) for p in (site / mod).rglob("*.py")}
    b = {
        p.relative_to(blocks / pkg / "src" / mod): h(p)
        for p in (blocks / pkg / "src" / mod).rglob("*.py")
    }
    print(mod, "与源码一致" if a == b else "不一致")
```

2026-11-22 实测三块都与源码一致，装的是本地 wheel（`maafw_native` 的 `project_runtime.py` 本地版与 PyPI 0.1.0 不同，所以这次比对能区分两者）。不一致时清 uv 缓存（`uv cache clean <包名>`）、删 `plugins\pypi\environment.json` 再启动。

## 5. 启用

对插件注册项写 `info.enable`，只启用三个专项即可，三块积木按依赖一起启用：

```text
POST /api/plugin_registry/get     {}   → data 的键是注册项 uid，info.plugin_name 是插件标识
POST /api/config/triggers/write   {"configUid": "<注册项 uid>", "group": "info", "field": "enable", "value": true}   → data 是任务 uid
POST /api/config/triggers/result  {"taskId": "<任务 uid>"}   → data.state 为 succeeded
GET  /api/scripts/types                → 含 "M9A"、"MaaFW"、"MSS"
```

启用状态会落盘，之后重启自动启用。

## 6. 主路径

托管和账号接口的返回同时带 `info` 和 `Info`、`game` 和 `Game`，PowerShell 的 `Invoke-RestMethod` / 哈希表处理不了，用 Python 调。

```text
POST /api/scripts/add                      {"type": "MaaFW"}                  → scriptId（M9A / MSS 同理）
POST /api/scripts/maafw/embedded/reimport  {"scriptId": ..., "sourcePath": "<项目目录>"}
POST /api/scripts/maafw/preview            {"scriptId": ..., "path": ""}
POST /api/scripts/update                   {"scriptId": ..., "data": {"Info": {"Controller": ..., "Resource": ...}}}
POST /api/scripts/user/add                 {"scriptId": ...}                  → userId
POST /api/scripts/user/get                 {"scriptId": ..., "userId": ...}   → Task.TaskSnapshot 是默认队列
POST /api/scripts/user/update              {"scriptId": ..., "userId": ..., "data": {"Task": {"TaskSnapshot": "<json>"}}}
POST /api/scripts/add                      {"type": "MaaFW", "scriptId": <源托管>}   复制托管
POST /api/scripts/delete                   {"scriptId": ...}
POST /api/scripts/maafw/agent-env/prepare  {"scriptId": ..., "path": "", "force": false}
```

2026-11-22 的结果：

| 类型 | 项目 | 导入 | 预览 | 新账号默认队列 | 准备环境 |
| --- | --- | --- | --- | --- | --- |
| MaaFW | `D:\MAS\test\walkref\maabbb`（MAA_bbb v1.13.3） | 16.5 s | 36 个任务 | 14 个任务 | 21.6 s，isolated_venv |
| M9A | `D:\MAS\test\walkref\m9a`（v4.9.0） | 30.3 s | 29 个任务 | 9 个任务 | 2.7 s，project_python |
| MSS | `D:\MAS\test\mfw-src\StellaSora-v1.4.4` | 20.0 s | 15 个任务 | 空（这个版本没有 `default_check`，与内置时相同） | 2.6 s，project_python |

- 复制托管：新托管当场有自己的副本 `data\mfw\<前 12 位>`，`Embedded.FollowSource` 为 false，预览正常。
- 删除托管：副本当场删掉（0.15–0.45 s）。
- 密码字段：项目里没有带 `password: true` 的输入项，要验证就把项目拷到 `$env:TEMP`，加一个 `type: input`、`inputs[].password: true` 的选项，并改掉 `name`、`github`、`mirrorchyan_rid`（同身份同版本的导入会并进已有谱系、沿用旧载荷）。写入账号快照后，`config\scripts.yaml` 里是 `mas-dpapi:` 前缀的密文，接口读回也是密文，盘上搜不到明文。

## 7. 无害真跑

只用自己编的空白窗口程序，不拉真游戏、不开模拟器，不派发 ADB 控制器的托管。

1. 编一个注册 `UnityWndClass`、标题由第一个参数给、客户区 1280×720 的小程序（Windows PowerShell 5.1 的 `Add-Type -OutputAssembly x.exe -OutputType WindowsApplication`，窗口过程用 `DefWindowProcW`；标题里的中文从参数传，别写进 C# 源码）。M9A 的 agent 要求 16:9，800×480 不行。每个托管各拷一份 exe（`win_process` 的占用锁按 exe 路径算）。
2. 派发前确认桌面上没有类名 `UnityWndClass` 的窗口（ctypes `EnumWindows` + `GetClassNameW`）。
3. 建游戏目标：`POST /api/games/create {"type": "win_process", "data": {"info": {"name": ..., "path": "<exe>", "wait_time": 30}}}`，取返回里的游戏 uid 和设备 uid。
4. 改托管：`game: {game_id, device_id}`；`Device.Win32MouseMethod = 4`、`Win32KeyboardMethod = 4`（PostMessage，不抢鼠标键盘）；`Game.LaunchMode = "DirectExe"`；**`Game.Arguments` 写窗口标题**（加引号），MFW 由 MAS 启动游戏时用的是托管的 `Game.Arguments`，游戏目标里的「启动参数」不读；`Run.RunTimesLimit = 1`、`TaskTimeLimit = 1`（分钟）、`RunTimeLimit = 5`；`Update.AutoUpdateMode = "Off"`。窗口标题要匹配项目控制器的 `window_regex`：MAA_bbb 用「崩坏3 …」，M9A 用「Reverse: 1999 …」（M9A 的 PC 控制器只配国际服 / 港澳台资源，选「国际服（EN）」），MSS 用「StellaSora …」。
5. 账号快照只留一个任务：MaaFW「领取邮箱奖励」、M9A「领取奖励」、MSS「领取邮箱奖励」。
6. 派发：`POST /api/dispatch/start {"mode": "AutoProxy", "tasks": {"0": {"uid": "-", "children": {"0": {"uid": <scriptId>, "children": {"0": {"uid": <userId>}}}}}}}`，每 3 秒 `GET /api/dispatch/task/<taskId>` 看顶层 `status`。派发前设好停止条件：最多等 4 分钟，到点 `POST /api/dispatch/stop {"taskId": ...}`，再按进程树结束自己起的东西。

2026-11-22 三种各跑一轮，都在 1–2 分钟内结束：拉起假程序 → 认出窗口 → 起 worker（`-m maafw_runner.core.runner.worker`，本地源码布局）→ 连上 Win32 控制器（PrintWindow / PostMessage）→ 起 agent → 任务在空白窗口上超时（MaaFW「单任务超时（限制 1 分钟）」）或认不出画面失败（M9A「停在 ReturnMain」、MSS「停在 通用_返回主页」）→ 账号日志最后一行「已关闭本次由 MAS 启动的游戏」→ 假程序退出、worker 和 agent 退出、游戏目标的 `deviceUsage` 清空。派发状态是 `error`（任务没完成，符合预期）。

注意：M9A 的 agent 第一次启动会联网热更新约 11 个数据文件到副本里（项目自己的行为）；MSS 运行前会读一次星塔旅人公告页。

## 8. 存量配置升级演练

拿真实配置的副本看升级链路，**不派发任何运行**（里面是真实账号）。

1. 只读拷贝：`robocopy <正式版>\config <副本>\cfg /E /COPY:DT`（不带 `/MOV`、`/PURGE`、`/MIR`）。拷之前记下源目录每个文件的大小和修改时间，演练完再对一次。
2. 另建运行目录：`git archive HEAD` 解到 `<副本>\root`，`<副本>\cfg` 再拷一份到 `root\config`（`cfg` 留作升级前的样子），`plugins\pypi` 可以从联调树拷过来（省得首次安装游戏管理插件），`plugins\` 下照第 2 节建六个联接。`data` 不拷。
3. 起后端：工作目录设成 `root`，用本树的 `.venv\Scripts\python.exe main.py`，环境变量同第 3 节，另加 **`AUTO_MAS_BACKEND_REPO=1`**：开发后端因此暂停自动任务（定时队列、启动时运行、定时唤醒同步、签到都不跑，日志「开发后端默认暂停自动任务」）。开发环境下不写开机自启、不上报遥测。
4. 看：`config\legacy-maafw-plugin\` 下有没有备份、与原件是否逐字节相同；`/api/plugin/list` 里三个专项装的是哪一份；托管 / 账号 / 计划表的 UID、顺序、名称，队列里对它们的引用和定时项。比的时候只打印 UID、字段路径和布尔值，别把账号名、密码、手机号打进日志。
5. 要分清哪些变化是插件化带来的，用同一份副本在 `b8351bf0f`（删内置实现之前那个提交）的导出上再演练一遍，两边结果对比。
6. 再起一次，确认 `scripts.yaml` 和备份都不再变。
7. 停后端，先删掉 `root\plugins` 下的联接（`(Get-Item <联接>).Delete()` 只删联接本身），再删副本目录。

2026-11-22 用正式版配置演练的结果（10 个托管：7 个 MAA、1 个 MaaFW、1 个 M9A、1 个 HSR；7 个队列；2 个 MAA 计划表；没有 MSS）：

- `legacy-maafw-plugin\scripts.yaml` 与原件逐字节相同；没有 MFW 族计划表，所以 `plans.yaml` 没备份。第二次启动 `scripts.yaml` 和备份都没变。
- 三个专项是本地源码（`source=local`），三块库是本地 wheel；MAA 专项由宿主从 PyPI 补装（0.1.5）。没有旁挂，`unavailable` 为空。
- 托管、账号的 UID、顺序、名称全部不变；两个队列里对 MFW 族托管的引用和全部定时项不变；计划表顺序不变。
- 与内置实现那次（`b8351bf0f`）相比，只有 MFW 族多出插件配置类自带的小写 `info`、`custom_webhooks`、`notify` 键；M9A 账号的 `Info.Id` 两边都由明文的旧 `Info.Account` 加密而来，解密后相同（密文每次不同）。其余文件、其余托管、队列、计划表逐键相同。
- 相对正式版原件的其它变化（`Emulator` 换成 `game` 绑定、MAA 计划表多 `info`、HSR 账号 `Info.Server` 改名 `Info.Resource` 等）两边一样，来自宿主本身的升级段，不是插件化带来的。
- 没拷 `data`，启动维护因此把 `config\maafw_env_cache` 里 12 份运行环境缓存当作没人用回收了（只在副本里）。

## 9. 停后端、拆除

开发模式下 `POST /api/core/close` 只做清理、不退出。`.venv\Scripts\python.exe` 是启动器，真正监听端口的是它的子进程，按进程树停：

```powershell
$owner = (Get-NetTCPConnection -LocalPort 36196 -State Listen).OwningProcess
function Get-Tree($id) { Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object { $_; Get-Tree $_.ProcessId } }
$all = @(Get-CimInstance Win32_Process -Filter "ProcessId=$owner") + @(Get-Tree $owner)
$parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$owner").ParentProcessId
$all += @(Get-CimInstance Win32_Process -Filter "ProcessId=$parent" | Where-Object { $_.CommandLine -match 'main\.py' })
$all | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 36196 -State Listen -ErrorAction SilentlyContinue   # 应为空
```

拆联接：`pwsh -NoProfile -File scripts\dev\link_mfw_plugins.ps1 -Unlink`（只删联接，不碰目标仓库）。拆完不设 `UV_CONFIG_FILE` 再起，配置里有 MFW 族托管时宿主会从 PyPI 装发行版。

## 10. 遇到问题先看这里

- **安装报「插件 `xxx` 正在使用本地源码，请先移除该工程后再安装发行包」**：`plugins\` 下还留着联接，先 `-Unlink`。
- **派发后「游戏窗口在 60s 内未就绪」**：窗口标题没匹配上控制器的 `window_regex`。标题要写进托管的 `Game.Arguments`，游戏目标的「启动参数」MFW 不用。
- **新发的包插件中心里找不到**：数据站插件目录还没收录。起后端前设 `AUTO_MAS_PLUGIN_EXTRA_PACKAGES=auto-mas-maafw-adapter,auto-mas-m9a-adapter,auto-mas-mss-adapter`，刷新目录时按包名从 PyPI 补进来。
- 运行数据都在树根被忽略的 `config\ data\ debug\ history\ temp\ plugins\pypi\` 下。
- 插件包自己的已知问题见积木仓库 `docs/known-issues-0.2.0.md`。
