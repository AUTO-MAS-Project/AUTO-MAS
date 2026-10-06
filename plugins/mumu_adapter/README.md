# MuMu 模拟器游戏适配

贡献游戏类型 `mumu`。依赖 `auto_mas_core>=6,<7`。

## 源文件

| 文件 | 职责 |
|------|------|
| `plugin.py` | `GameAdapterPlugin`；``on_enable`` 清扫上次进程残留的配置备份 |
| `config.py` | `MuMuGame` / `MuMuDevice`：路径矫正、收窄 `_control`；设备 `session.backup` 订阅期备份（`dict[str, Any]`，原样存厂商 JSON）|
| `control.py` | `MuMuControl`（含 CLI、订阅钩子、稳定模式写入与还原；`config` 收窄为 `MuMuGame`） |
| `search.py` | 注册表搜索 → 未激活 `MuMuGame` |

继承宿主 `EmulatorEntry` / `EmulatorDeviceEntry` / `EmulatorControl`，并在插件内把 `_control` / `config` / `devices` 收窄到 MuMu 具体类型。

- **稳定模式与配置守卫已固化默认启用**，两个游戏级开关取消，逻辑挂在实例订阅生命周期上（订阅骨架在基类 `GameControl`，这里只实现两个品牌钩子）：
  - `_on_device_subscribed`（首个引用订阅后）：`setting -aw` 原样备份全部可写键 → 落 `session.backup` 并 commit（**先落盘再写第一笔**，抗崩溃）→ 单次写入「`expect` 里非 `None` 的项 + `resolution_mode=custom`」。分辨率与稳定项同走 `constants._WRITE_KEYS` 一张表、一套逻辑，怎么写由值的形态定：标量按值直写（不比对厂商当前值），元组是容许值表（当前档在表内就不动，越界写表首，如显存策略的 `("auto", "perf")` 把 `dis` 拨回 `auto`）。读空则报错，不写、不留半份备份（登记与失败撤销由基类管）。`expect=None` 时只备份，一个键都不写。
  - `_on_device_unsubscribed`（计数归零退订时）：写临时 JSON 走 `setting -p` **整份写回**，成功才清空 `backup`；失败保留备份并记警告（那是原值的唯一记录）。
  - `on_enable` 的 `sweep_backups`：`backup` 非空的设备逐台补做写回。
- **最小化 / 最大化走窗口句柄，不走官方 CLI**：`MuMuManager.exe` 只有 `show_window` / `hide_window` 两档（MuMu 自己的托盘显隐语义），没有最小化与最大化。故 `_window_state` 取 `data.main_wnd`（官方 `info` 原文，十六进制）下 `ShowWindow(SW_MINIMIZE/SW_MAXIMIZE)`，**不按 pid 搜窗** —— 同 `data.window_visible` 的口径：句柄缺失或已失效即报错，不去猜哪个窗是它的。跳进程 `ShowWindow` 投递即返回，故按 `GetWindowPlacement` 的 `showCmd` 轮询验位（`IsIconic` 的反面只是「没最小化」，普通窗口也满足，会把最大化误判成已到位；`IsZoomed` pywin32 未导出）。`show` / `hide` 仍交官方 CLI，两不相干。
- **`control.py` 分节编排：薄入口在前、实现在后**。通行面（`open` / `close` / `show` / `hide` / `minimize` / `maximize` / `launch_app` / `open_store` / `create_instance` / `delete_instance` / `install_app`）一律两行——`check_subscription` 校凭据、`execute` 交执行器，真正干活的是同名带下划线的 `_open` / `_close` / `_launch_app` / `_create` / `_install` 等，集中在「实现」一节：**它们不校凭据、不自己进执行器**，故可被别的实现直接 `await`。`execute` 泛型化（`Awaitable[T] -> T`）后返回值直接由它带回，`create_instance` 不必再用列表从 `-> None` 的闭包里偷渡 uid。
- **刷新只有门控循环一处**（`_loop`）：公开 `refresh()` 只开 10min 窗口；循环每轮按忙闲现算等待时长（`busy` 0.2s / 闲 1s），同步完成后敲一下节拍器 `_synced`（`asyncio.Event`，开始等待时复位、每轮放行一次）。操作函数**不自己 sync**：起手 `await self._synced.wait()` 即保证状态是新的，之后只等 `devices` 上出现期待值 —— 循环间隔就是它们的时延下限，忙时缩短即等待提速。取数失败也放行，由下游等待逻辑兜。例外只有 `sweep_backups`：进程刚起来时既不 busy 也没开窗口，它直接取一次。
- **等谁的值，决定等什么**：轮询里凡等 `devices` / `_raw` 上的值变（`info.status`、`data.window_visible`、实例的增删）一律 `await self._synced.wait()` ——干睡一拍未必等来新数据，白跑一轮。只有**自己去取信息**的才用 `asyncio.sleep(_BUSY_INTERVAL)`：`_window_state` 问 `GetWindowPlacement`、`_launch_app` 跑 `dumpsys`、`_close_nx_shell` 枚举窗口 ——它们不经同步，节奏与节拍器无关。另两处 `sleep` 不是轮询：`_loop` 自己的间隔（节拍源），以及 `_open` 启动后那段固定缓冲。
- **去广告分两处落**（系统级 `if_block_ad` 开关）：
  - `set_block_ad(enabled)`（基类钩子，开关变更时由 `GameManager` 统一下发）：宿主机侧两类图片缓存目录（`%APPDATA%/Netease/MuMuPlayer{,-12.0}/data/`下的 `startupImage` 与 `ProgramAds`，12.0 与 6 两套安装各占一份）**换成同名空文件**，MuMu 就写不进缓存图；关掉开关则只删我们放的空文件，目录留给 MuMu 自己重建。必须赶在实例启动前落位，故挂开关信号而非启动路径。
    - `startupImage` 是实例开屏图，但 `emulator2/master_mode:308` 实测它会被实例启动时删掉重建 —— 留着无害，单靠它不够。
    - `ProgramAds` 是小程序弹窗图，常驻的 `MuMuNxService.exe` 在实例启动等事件时直接拿它画（多开器手动起实例也会弹）；实测它遇到文件不会改回目录、只记「no cache ads」，故这条才是真正拦住弹窗的那份。
  - `_open` 内联那段（实例在线后）：`appops set … SYSTEM_ALERT_WINDOW deny` 拒商店悬浮窗权限 + `am force-stop` 掐掉已经起来的广告进程。这两笔非要实例跑起来不可，只能留在启动路径上。两笔各自独立，失败都只记警告、不拦启动。
- **`_open` 分「仅未启动可做」与「两条路都走」两段**：拉起实例、关 NX 壳、静默藏窗都只有启动那一下的时机，全部收在前段；去广告、拉应用、起来后缓一口气是收尾，已在线也要走 —— 故已在线**不**直接 return。
- **「把应用弄到前台」只有 `_launch_app` 一份实现**（官方 `app info` 判态 → `app launch` → `dumpsys` 验前台 → `monkey` 兼底 → 再验）。`_open` 带包名时直接 `await self._launch_app(...)`，`open_store` 则是公开面的 `launch_app` 带 `STORE_PACKAGE`。**实现之间互调一律走 `_` 方法**：凭据在公开入口已校过、执行器也已被外层那一笔占着，再绕一遍公开面只会重复校验并把自己卡在执行器上，故 `execute` 无需给「自己 job 内的嵌套」开任何口子。
- **关 NX 壳与静默藏窗各是一个一次性副任务**：启动前起协程自己轮询，触发一次即退出，不挤进等待循环里每拍重判。藏窗会等它落地才返回（静默启动的承诺是「返回时窗口已藏好」）；NX 壳可能整局不露面，等不得，随启动收尾一并取消。
- **触发器只开关，不改配置**：UI 的启动/关闭不再产生任何 `setting` 写入。被别的任务订阅时按钮仍可用（只在控制器 `busy` 时 `DISABLE`——忙标记只在控制器一处，配置上不存第二份）。
- **无「自定义任意实例设置」入口**：cpu / 内存 / 帧率是用户的机器预算，任务没有立场替他定；实例设置在 MuMu 界面里改。
- **能力变化**：守卫范围缩到订阅期——空闲时在 MuMu 界面改分辨率不会被还原；反之任务期间在 MuMu 界面做的任何改动会被整份写回撤销。

无 DeviceBase / `MumuManager` 兼容转发层，无单独 `cli.py`。
