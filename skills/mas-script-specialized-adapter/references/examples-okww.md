# 案例：OK-WW / Okww 专项适配（ok-script 线）

**上游仓库**：[ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)（鸣潮 OK-WW，基于 **ok-script** 的 Python 图像识别自动化，发行物为 `ok-ww.exe`）。

**架构判断（Agent 读仓后应对用户确认的摘要）**：

| 维度 | OK-WW 事实 | 不属于 |
|------|-----------|--------|
| 框架 | **ok-script**（`from ok import OK`），非 MaaFramework / Alas / MXU / MFAA | MAA / SRC / MXU / MFAA 线 |
| 配置 | `config.py` + 运行时 `configs/` 目录（`config_folder: 'configs'`） | `interface.json`、MFAAvalonia、`mxu-*.json` |
| 自启动 | README 明确 **CLI**：`-t` / `--task`（任务序号）、`-e` / `--exit`（跑完退出） | MFAA 线「无 CLI、只靠写盘 + 程序内自动运行」 |
| 配置 UI | 自带 PyQt GUI（`use_gui: True`），用户在本体内改热键/角色等 | 不必调 Avalonia；宜 **ScriptConfig 拉起 exe**（无 `-t`）或映射 `configs/` |

本仓若新增 `ScriptType = 'Okww'`，归类为 **ok-script 线**（见 [script-frontend-architectures.md](./script-frontend-architectures.md)），表面与任务逻辑**优先对齐 `General` + CLI**，而非 M9A/MaaEnd 模板。

---

## 上游：命令行与任务列表

README 示例（[开发者专区 · 命令行参数](https://github.com/ok-oldking/ok-wuthering-waves)）：

```text
ok-ww.exe -t 1 -e
```

| 参数 | 含义 |
|------|------|
| `-t` / `--task` | 启动后自动执行**任务列表中第 N 个**任务（**从 1 开始**，与 GUI 列表顺序一致） |
| `-e` / `--exit` | 该次任务结束后**退出程序** |

`config.py` 中 `onetime_tasks` 定义 GUI/CLI 任务顺序（节选，以仓库当前 `master` 为准）：

| `-t` 值 | 任务类（展示名以 GUI 为准） |
|--------|---------------------------|
| 1 | DailyTask（日常类） |
| 2 | MultiAccountDailyTask |
| 3 | FarmEchoTask |
| 4 | AutoRogueTask |
| 5 | ForgeryTask |
| 6 | NightmareNestTask |
| 7 | SimulationTask |
| 8 | TacetTask |
| 9 | EnhanceEchoTask |
| 10 | ChangeEchoTask |
| 11 | DiagnosisTask |

另有 `trigger_tasks`（后台战斗、拾取等）——是否可通过 `-t` 触发需以发行版 `ok-ww.exe --help` 为准；**AUTO-MAS 对接时以 README + help 为权威**。

日志默认：`logs/ok-ww.log`（`config['log_file']`）。

---

## AUTO-MAS 拟定方案（架构确认后）

### 1. 启动后自动运行（AutoProxy）

与 **MFAA/M9A 线相反**：**应使用启动参数**，不必臆造「仅写 JSON 再裸启 exe」。

建议本仓 `AutoProxy` 拼接：

```text
ok-ww.exe -t {用户任务序号} -e
```

- `{用户任务序号}`：来自 `OkwwUserConfig` 或脚本级默认（与上游 **1-based** 一致）。
- 可选：按用户再追加其它上游支持的 flag（以 `ok-ww.exe --help` 为准）。

日志监控：对齐 `Script.LogPath`（常为 `data/apps/ok-ww/working/logs/ok-script.log`）。判态见 [实现规范](#实现规范okww-必遵守)。

### 2. 设置脚本配置（ScriptConfig + 用户编辑）

| 方式 | 适用 |
|------|------|
| **ScriptConfig 调起 `ok-ww.exe`**（不带 `-t`/`-e`） | 用户在 OK-WW GUI 内改热键、角色、月卡等；保存后结束会话（对齐 `GeneralUserEdit` 遮罩 + WebSocket，见本仓 `app/task/general/ScriptConfig.py`） |
| **AUTO-MAS 只写「跑哪条任务」** | 用户页选 `-t` 序号；不必复刻全部 `ConfigOption` |
| **同步 `configs/`** | 若需多用户隔离，在 `data/{scriptId}/{userId}/` 与 OK-WW 的 `configs/` 之间约定拷贝策略（实现阶段再定，避免手改用户 GUI 已写的文件） |

本仓 **General** 已支持「运行参数 | 配置会话参数」拆分（`Script.Arguments` 用 `|` 分隔两段 `路径%参数`）。在 **`Okww` 类型落地前**，可先用 **`General`** 验证：

| 字段 | 建议初值 |
|------|----------|
| `Info.RootPath` | OK-WW 安装目录（纯英文路径） |
| `Script.ScriptPath` | `ok-ww.exe` |
| `Script.Arguments`（代理） | `-t 1 -e`（或 `ok-ww.exe% -t 1 -e` 若需带路径段，按 General 解析规则） |
| `Script.Arguments`（配置，`|` 后段） | 留空或仅 GUI 启动参数 |
| `Script.ConfigPath` | `configs` 目录 |
| `Script.LogPath` | `logs/ok-ww.log` |

### 3. 本仓落地 `Okww` 类型时（checklist）

**表面**

- [x] `Scripts.vue` / `ScriptTable` / `router`：`okww`；卡片「配置 ok-ww」（非脚本编辑页）
- [x] `OkwwScriptEdit.vue`：三段式；根目录推导路径；`Game.Enabled` + `Game.CloseOnFinish`
- [x] `OkwwUserEdit.vue`：`TaskIndex` / `ExitOnFinish`；简洁/详细；用户页配置（详细）
- [x] `types/script.ts`、`useScriptApi.ts` 分支
- [x] `frontend/src/assets/ok-ww.ico`

**后端**

- [x] `OkwwConfig` / `OkwwUserConfig`；`Game.CloseOnFinish`
- [x] `app/task/Okww/`：`manager`、`AutoProxy`、`ScriptConfig`（含 `final_task` / `on_crash`）
- [x] `SCRIPT_BOOK`、`TYPE_BOOK`（`OkwwConfig`→`ok-ww`）、`task_manager`；OpenAPI 需 `yarn openapi` 生成（勿手改 models）

**勿套用**

- M9A `TaskQueueSection` + 写盘无 CLI（OK-WW **有** `-t`）
- MaaEnd `mxu-MaaEnd.json` / `autoRunOnLaunch`（无 PI V2 / MXU）

---

## 同 ok-script 生态其它项目

README 所列 [ok-script](https://github.com/ok-oldking/ok-wuthering-waves) 系项目（原神、少前2、星铁助手等）若 CLI 形态类似（`-t`/`-e` + 自带 GUI），可复用 **本案例的 ok-script 线** 流程；任务列表与配置目录名以各自仓库为准。

---

## 参照建议

| 阶段 | 做法 |
|------|------|
| **验证对接（必须先做）** | 先用本仓 **`General`** 跑通：启动参数 `-t 1 -e` + ScriptConfig 配置会话 + 日志识别；此阶段允许使用临时的「OK-WW 预设」辅助快速填参 |
| **正式专项（Okww）** | 新增 **`Okww`** 类型（ok-script 线），表面复制 General，后端固化 `-t`/`-e` 与任务序号（`TaskIndex`）配置；并把“通用页的预设”迁移到 `OkwwScriptEdit` / `OkwwUserEdit` 的默认值 |
| **清理回收（必须做）** | 当 `Okww` 专项可用后，**移除** `GeneralScriptEdit` 中的临时「OK-WW 预设」按钮，保证通用脚本不受专项污染；此步骤与专项落地同一批次完成 |
| **读仓排障** | [ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves) 的 README、`config.py`、`ok-ww.exe --help` |

---

## 实现规范（Okww 必遵守）

全仓共性见 [adapter-code-norms.md](./adapter-code-norms.md)。以下为 **Okww / ok-script** 增量，实现时按表写代码（源码：`app/task/Okww/`）。

### CLI 与配置分工

| 层级 | 字段 | 规则 |
|------|------|------|
| 用户 | `Task.TaskIndex` | 1-based，拼 `-t N` |
| 用户 | `Task.ExitOnFinish` | 真则拼 `-e` |
| 脚本 | `SuccessLog` / `ErrorLog` | `\|` 分段，全文子串；仅补充判态，勿单独配置整段 `ERROR` |
| 会话 | ScriptConfig | 无参启 `ok-ww.exe`；入口在脚本卡片，非编辑页 |

### `check_log`（唯一判态入口，勿用 General「先 Success 后 Error」）

短路顺序：`"".join(log_content)` 后子串匹配 →

1. `_OKWW_BUILTIN_FATAL`：`connected:False`｜`游戏更新成功, 游戏即将重启`｜`失败`
2. `self.error_log`（`prepare()` 已剔除整段 `error`/`异常`/`任务失败`；空则回退默认串）
3. 成功：内置 `任务执行完成` / `task completed` + `SuccessLog`
4. `not okww_process_manager.is_running()` → 提前退出
5. `now - latest_time > Run.RunTimeLimit`（分钟）→ 超时
6. 否则 `OK-WW 正常运行中`（**不** `wait_event.set()`）

非 `正常运行中` 时 `wait_event.set()`。`on_crash` 与关键词无关。

### 游戏与进程

| 项 | 规则 |
|----|------|
| `Game.Enabled` | 仅任务**开始前** MAS 启游戏；失败则 `continue`，**不**启 ok-ww |
| `Game.CloseOnFinish` | 仅任务**成功**后 MAS 关游戏；与 Enabled **独立** |
| `OkwwManager.prepare` | `Enabled \|\| CloseOnFinish` 时创建 `game_manager` |
| 成功轮 `main_task` | 只 `_kill_okww_process()` |
| 成功 `final_task` | `CloseOnFinish` 时 `_kill_game_process()`（Client 再 `System.kill_process(Game.Path)`） |
| 失败/重试/`on_crash` | 始终杀 ok-ww；杀游戏仅当 `Enabled \|\| CloseOnFinish` |
| 游戏路径 UI | 选鸣潮根目录 → 自动拼 `…/Client/Binaries/Win64/Client-Win64-Shipping.exe` |
| 追踪子进程 | `TrackProcessName=pythonw.exe`，`TrackProcessExe={RootPath}/data/apps/ok-ww/python/pythonw.exe` |

### 重试与落盘

- `Run.RunTimesLimit` 整轮重试；非 `Success!` 且未达上限 → 按 `_mas_should_close_game_on_retry()` 清理 → `sleep(10)`。
- `final_task`：`save_general_log` → `history/{date}/{user}/{time}.log|json`。
- 简洁/详细、`LogMonitor` 三参、`LogRecord.status`、`uuid.UUID` 索引：见 [adapter-code-norms.md](./adapter-code-norms.md)。
