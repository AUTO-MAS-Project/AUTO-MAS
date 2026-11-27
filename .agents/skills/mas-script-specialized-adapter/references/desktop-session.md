# 插件专项接入桌面分身

## 声明能力与分身清单

1. 在现有 `ScriptTypeDecl` 中支持 `TaskMode.AUTO_PROXY`，并传入 `desktop_session_check`。回调接收当前托管配置和宿主是否已提权，同步返回 `None`（可用）、`admin_required`（需要管理员权限）或 `unsupported_config`（当前配置不兼容）。回调可重复执行，只读配置和权限，避免阻塞 I/O、写配置或启动进程。省略回调时插件仍可在主会话运行。
2. 哪些托管和队列在分身运行，由宿主在「设置 → 功能」桌面分身卡片里集中管理，分两份全局设置：`DesktopSession.Targets` 是单独启动时进分身的托管，`DesktopSession.StartOnOpen` 是「打开分身并启动任务」一并派发的队列和托管。新插件不必声明 `Run.ExecutionSession`。已经继承 SDK `DesktopSessionRunFields` 或自行声明该字段的保留即可：宿主只在升级时读一次，把取值为 `desktop` 的托管只并入 `Targets`，之后不再读取，也不写回。单独启动托管只看 `Targets`；队列只在从桌面分身卡片派发时整条进分身，手动启动队列和定时任务在主会话运行。
3. 宿主按托管实际注册的配置类查找已启用插件，通过调用门检查能力。详情、预览和正式受理共用检查，持有托管锁后执行前再复核。托管在清单里但暂时不可用时，保留清单条目并返回原因，不悄悄改到主会话。需要改在主会话运行时，由用户把它移出清单，或在派发确认里选择主会话。

需要宿主提权的适配器可在其现有 `ScriptTypeDecl(...)` 中传入下面的 `desktop_session_check`，奇想盒采用此条件。

```python
from auto_mas_core import DesktopSessionCheckReason, ScriptEntry


def desktop_session_check(
    config: ScriptEntry, elevated: bool
) -> DesktopSessionCheckReason | None:
    return None if elevated else "admin_required"
```

插件使用 [SDK 导出](../../../../plugins/auto_mas_core/src/auto_mas_core/adapters/script.py) 接入，宿主无需为每个专项新增分身注册项。发布前按目标宿主核对实际提供的 SDK 符号。如果要兼容同版本号且缺少接口的旧宿主，像奇想盒一样探测声明参数和 SDK 字段，旧宿主继续使用主会话，并按原路径保留 `Run.ExecutionSession` 的值。

## 进程启动与收尾

- L2、L3、L4 的 Python 编排和配置锁在宿主进程里。通过 `auto_mas_core.utils.ProcessRunner.run_process()` 或 `ProcessManager.open_process()` 启动外部命令，宿主才会按任务上下文把进程放进分身。直接使用 `subprocess` 或从宿主 Python 操作窗口时，执行位置仍是主会话。
- 持有调用 `open_process()` 的 `ProcessManager`，并在收尾时调用 `await manager.kill()`。清理依据本任务持有的进程归属，避免按名称扫描并结束进程。需要在启动器退出后继续管理其派生进程时，按需选用 `retain_desktop_descendants=True`，用 `manager.launched_process.returncode` 读取启动器的退出状态。
- 分身隔离 Windows 会话，安装目录和上游配置文件仍可能共享。若专项依赖独占安装目录或临时覆盖上游配置，主会话与分身都应使用同一套占用检查及还原逻辑。

## 验证入口

- 派发与持锁复核优先复用 [任务树派发测试](../../../../tests/core/test_task_tree_dispatch.py)，进程归属与停止优先复用 [分身进程范围测试](../../../../tests/platform/test_desktop_session_process_scope.py)。专项仓验证自己的权限条件、进程启动方式和配置写盘行为。迁移样本至少覆盖缺字段默认 `main`、已有 `desktop` 保存并重新加载后仍保留。
- 声称支持 Windows 分身时，走适用的公开派发入口验证。如果要证明 L2、L3、L4 的命令进入子会话，记录各层命令的进程会话 ID。停止任务或断开后，检查本次任务拥有的进程已经退出，同时主会话中的同名进程仍在。按实际运行范围记录是否覆盖游戏。
