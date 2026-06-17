# 案例：OK-WW / Okww 专项适配（ok-script 线）

**上游仓库**：[ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)（鸣潮 OK-WW，基于 **ok-script** 的 Python 图像识别自动化，发行物为 `ok-ww.exe`）。

**架构判断（Agent 读仓后应对用户确认的摘要）**：

| 维度 | OK-WW 事实 | 不属于 |
|------|-----------|--------|
| 框架 | **ok-script**（`from ok import OK`），非 MaaFramework / Alas / MXU / MFAA | MAA / SRC / MXU / MFAA 线 |
| 配置 | `config.py` + 运行时 `configs/` 目录（`config_folder: 'configs'`） | `interface.json`、MFAAvalonia、`mxu-*.json` |
| 自启动 | README 明确 **CLI**：`-t` / `--task`（任务序号）、`-e` / `--exit`（跑完退出） | MFAA 线「无 CLI、只靠写盘 + 程序内自动运行」 |
| 配置 UI | 自带 PyQt GUI（`use_gui: True`），用户在本体内改热键/角色等 | 不必调 Avalonia；已用 **表单化编辑器完全替代 GUI**（v5.3.0-beta.3+），AutoProxy 是唯一运行模式 |

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

## AUTO-MAS 方案

### 1. 启动后自动运行（AutoProxy）

与 **MFAA/M9A 线相反**：**应使用启动参数**，不必臆造「仅写 JSON 再裸启 exe」。

本仓 `AutoProxy` 拼接：

```text
ok-ww.exe -t {用户任务序号} -e
```

- `{用户任务序号}`：来自 `OkwwUserConfig` 或脚本级默认（与上游 **1-based** 一致）。
- 可选：按用户再追加其它上游支持的 flag（以 `ok-ww.exe --help` 为准）。

日志监控：对齐 `Script.LogPath`（常为 `data/apps/ok-ww/working/logs/ok-script.log`）。

### 2. 配置编辑器（v5.3.0-beta.3+，替代 ScriptConfig GUI 启动）

**不**再启动 `ok-ww.exe` 无参 GUI 做配置；改为**前端表单化配置编辑器**直接读写 JSON 配置文件。

| 组件 | 位置 | 说明 |
|------|------|------|
| 配置 Schema | `app/task/Okww/config_schema.py` | 半自动：JSON 值推断类型 + ok-ww 翻译文件自动加载标签 + SELECT_OPTIONS 手工维护下拉/多选选项 |
| 配置编辑器 | `frontend/src/views/OkwwUserEdit/OkwwConfigEditor.vue` | 按 schema 渲染表单，退出时自动保存 |
| 前端 Service | `frontend/src/api/services/OkwwService.ts` | `/api/scripts/okww/configs/*` 调用 |
| API 端点 | `app/api/scripts.py` | `/okww/configs/list\|update\|batch-update` |
| 自动初始化 | `configs/list` API | per-user 目录为空时从 ok-ww configs 源目录复制默认值 |

**配置落盘路径**（统一 per-user，**移除简洁/详细模式**）：
```
data/{scriptId}/{uid}/ConfigFile/
```
- 每个用户的配置独立存储在以用户 UID 命名的目录下。
- AutoProxy 同步时从该目录同步到 ok-ww 实际 configs 目录。
- **`Mode` 固定为 `"详细"`**：用户编辑页强制写入 `Mode = "详细"`，不再区分简洁/详细模式。

**Schema 字段发现**（`config_schema.py` 采用**半自动**模式）：

- **类型自动推断**：遍历 JSON 值 → `bool` / `int` / `float` / `string` / `list`
- **标签自动翻译**：从 ok-ww 安装目录搜索 `.mo` > `.po` > `.ts` 翻译文件，自动建立英文→中文映射
- **下拉/多选手工维护**：`SELECT_OPTIONS` 字典声明选项列表（源码不可读，JSON 只存当前值）
- **内部字段屏蔽**：以 `_` 开头的 ok-ww 框架字段（如 `_enabled`）不暴露给 MAS 用户编辑
- **新增字段补全**：`SELECT_OPTIONS` 中定义但 JSON 中不存在的字段也加入（ok-ww 新增配置项）

**翻译加载优先级**（`load_okww_option_labels()`）：
1. `i18n/zh_CN/LC_MESSAGES/ok.mo` > `ok.po`（扫描 root / `_internal` / `data/apps/ok-ww/` 等多候选路径）
2. `ok/gui/i18n/zh_CN.ts`（ok-script 框架级翻译补充）
3. 兜底标签：`{"Yes": "是", "No": "否", "Auto": "自动", "None": "无"}`

**Schema 字段类型**（`build_fields_for_config()`）：

| 类型 | 渲染 | 说明 |
|------|------|------|
| `bool` | a-switch | 开关 |
| `int` | a-input-number | 整数 |
| `float` | a-input-number（step=0.1） | 浮点数 |
| `string` | a-input | 文本 |
| `select` | a-select | 下拉选择 |
| `list` | a-select（mode="multiple"） | 多选列表 |
| `hotkey` | a-input | 快捷键（展示用） |

**选项翻译**：`load_okww_option_labels()` 从 ok-ww 安装目录自动加载英文→中文映射，前端统一展示（如 `"Forgery Challenge" → "凝素领域"`）。

### 3. 本仓落地 checklist

**表面**

- [x] `Scripts.vue` / `ScriptTable` / `router`：`okww`；卡片「配置 ok-ww」（非脚本编辑页）
- [x] `OkwwScriptEdit.vue`：三段式；根目录推导路径；`Game.Enabled` + `Game.CloseOnFinish`
- [x] `OkwwUserEdit.vue`：集成 `OkwwConfigEditor`，**无简洁/详细模式**
- [x] `OkwwConfigEditor.vue`：按 schema 渲染表单，退出自动保存
- [x] `OkwwService.ts`：配置编辑器 API 调用
- [x] `types/script.ts`、`useScriptApi.ts` 分支
- [x] `frontend/src/assets/ok-ww.ico`

**后端**

- [x] `OkwwConfig` / `OkwwUserConfig`；`Game.CloseOnFinish`
- [x] `app/task/Okww/`：`manager`、`AutoProxy`、`config_schema.py`（**注意：无 ScriptConfig.py**）
- [x] `config_schema.py`：`CONFIG_SCHEMA_MAP`、`OPTION_LABELS`、`get_all_config_info()`
- [x] `app/api/scripts.py`：`/okww/configs/list|update|batch-update`
- [x] `SCRIPT_BOOK`、`TYPE_BOOK`（`OkwwConfig`→`ok-ww`）、`task_manager`；OpenAPI 需 `yarn openapi` 生成（勿手改 models）

**勿套用**

- M9A `TaskQueueSection` + 写盘无 CLI（OK-WW **有** `-t`）
- MaaEnd `mxu-MaaEnd.json` / `autoRunOnLaunch`（无 PI V2 / MXU）
- ScriptConfig 调起 GUI 模式（**v5.3.1+ 已完全删除 ScriptConfig.py**，唯一运行模式为 AutoProxy）
- General `SuccessLog` / `ErrorLog` 用户配置（Okww **不暴露**判态关键词，全内置）
- General `OkwwConfig_Script` 继承 `GeneralConfig_Script`（Okww 使用独立 `BaseModel`）

---

## 实现规范（Okww 必遵守）

全仓共性见 [adapter-code-norms.md](./adapter-code-norms.md)。以下为 **Okww / ok-script** 增量，实现时按表写代码。

### CLI 与配置分工

| 层级 | 字段 | 规则 |
|------|------|------|
| 用户 | `Task.TaskIndex` | 1-based，拼 `-t N` |
| 用户 | `Task.ExitOnFinish` | 真则拼 `-e`（**固定为 true**，用户编辑器强制写入） |
| 脚本 | 判态 | **全内置**，不向用户暴露 SuccessLog/ErrorLog 配置项 |
| 配置 | 表单化编辑器 | 读写 `data/{scriptId}/{uid}/ConfigFile/` JSON |

> ⚠️ **v5.4.0-beta.1+**：`OkwwConfig.Script` **不再包含** `SuccessLog` / `ErrorLog` 字段。判态关键词完全由代码内置常量 `_OKWW_BUILTIN_FATAL` 和 `_OKWW_BUILTIN_SUCCESS` 控制，用户不可编辑。

### 参数拆分（`_split_args` 辅助函数）

**必须**抽为模块级函数，避免 inline `shlex.split` 重复：

```python
def _split_args(raw: object) -> list[str]:
    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []
```

在 `AutoProxy` 中统一使用，替代 `if raw: extra_args.extend(shlex.split(...))`（原 ScriptConfig 中已随 #222 删除）。

### `check_log`（纯内置判态，无用户可配关键词）

短路顺序：`"".join(log_content)` 后子串匹配 →

1. `_OKWW_BUILTIN_FATAL`：`connected:False`｜`游戏更新成功, 游戏即将重启`｜`info_set 错误`
2. 成功：`_OKWW_BUILTIN_SUCCESS = ("任务执行完成", "task completed")`（case-insensitive）
3. `not okww_process_manager.is_running()` → 提前退出
4. `now - latest_time > Run.RunTimeLimit`（分钟）→ 超时
5. 否则 `OK-WW 正常运行中`（**不** `wait_event.set()`）

> ⚠️ v5.4.0-beta.1+：移除用户可配置的 `Script.SuccessLog` / `Script.ErrorLog`。`_okww_log_indicates_success()` 不再接受 `success_log` 参数，`check_log()` 不再迭代 `self.error_log`。

非 `正常运行中` 时 `wait_event.set()`。`on_crash` 与关键词无关。

### 游戏与进程

| 项 | 规则 |
|----|------|
| `Game.Enabled` | 仅任务**开始前** MAS 启游戏；失败则 `continue`，**不**启 ok-ww |
| `Game.CloseOnFinish` | 仅任务**成功**后 MAS 关游戏；与 Enabled **独立** |
| `Game.LaunchBeforeTask` | 独立于 `Enabled`，仅控制是否自动拉游戏 |
| `OkwwManager.prepare` | `Enabled \|\| CloseOnFinish` 时创建 `game_manager` |
| 游戏启动检测 | 启动前 `is_process_running(Client-Win64-Shipping.exe)` → 已运行则跳过 |
| 成功轮 `main_task` | 只 `_kill_okww_process()` |
| 成功 `final_task` | `_mas_should_close_game_after_success()` 时 `_kill_game_process()` |
| 失败/重试/`on_crash` | 始终杀 ok-ww；杀游戏仅当 `_mas_should_close_game_on_retry()` |
| **游戏路径 UI** | 选鸣潮根目录 → 自动拼 `…/Client/Binaries/Win64/Client-Win64-Shipping.exe`；**强校验**：路径只接受空或正确两种状态 |
| **脚本路径 UI** | 选 ok-ww 根目录 → 自动拼 `ok-ww.exe`；**强校验**：路径只接受空或正确两种状态 |
| 追踪子进程 | `TrackProcessName=pythonw.exe`，`TrackProcessExe={RootPath}/data/apps/ok-ww/python/pythonw.exe` |
| `check()` 新增检查 | 用户配置目录是否为空 → 若空则返回 `"用户未完成 OK-WW 配置，请先在用户编辑页保存配置"` |

### AutoProxy 代码质量规范

以下规范来自 OKWW 分支上多次 review/refactor 的收敛结论，**所有 ok-script 线专项适配必须遵守**：

#### 1. hasattr() 消除

**反模式**：`if hasattr(self, "temp_path") and self.temp_path.exists():`

**正确**：在 `__init__` 中显式初始化为 `None`，再检查 truthiness：

```python
# manager.py __init__
self.temp_path: Path | None = None
self.script_config_path: Path | None = None
self.had_original_script_config = False

# later
if self.temp_path and self.temp_path.exists():
    ...
```

同样，`self.cur_user_config` **必须**在 `__init__` 完成赋值（`self.user_config[self.cur_user_uid]`），不延迟到 `check()` 或 `prepare()`。

#### 2. 原子化文件操作

配置同步使用 `.tmp` + `rename` 模式，防止写入中断导致配置损坏：

```python
# 反模式
shutil.rmtree(self.script_config_path, ignore_errors=True)
shutil.copytree(mas_config_dir, self.script_config_path, dirs_exist_ok=True)

# 正确：原子化
tmp_dst = self.script_config_path.with_name(
    self.script_config_path.name + ".tmp"
)
shutil.rmtree(tmp_dst, ignore_errors=True)
shutil.copytree(mas_config_dir, tmp_dst, dirs_exist_ok=True)
shutil.rmtree(self.script_config_path, ignore_errors=True)
tmp_dst.rename(self.script_config_path)
```

该模式用于：`set_okww()`（写入）、`_restore_script_config_from_temp()`（恢复）、`on_crash`（恢复）。

#### 3. DRY 提取复用的配置恢复逻辑

将 `final_task` 和 `on_crash` 中共用的「从 Temp 恢复配置」逻辑提取为 Manager 方法：

```python
async def _restore_script_config_from_temp(self) -> None:
    if not (
        self.task_info.mode == "AutoProxy"
        and self.temp_path
        and self.temp_path.exists()
        and self.script_config_path
    ):
        return
    if self.script_config.get("Script", "ConfigPathMode") == "Folder":
        if not self.had_original_script_config:
            # 任务期新写入的目录直接清理（原子化）
            ...
        else:
            # 原子化恢复原配置
            ...
    elif self.script_config.get("Script", "ConfigPathMode") == "File":
        ...
    shutil.rmtree(self.temp_path, ignore_errors=True)
```

**`had_original_script_config`** 标记确保区分「原本就有配置（需恢复）」和「任务期新写入（直接清理）」两种场景。

#### 4. 独立 try/except 每操作用于进程管理

**反模式**：
```python
try:
    await self.okww_process_manager.kill()
    await System.kill_process(self.script_exe_path)
except Exception as e:
    logger.exception(f"中止 OK-WW 进程失败: {e}")
```

**正确**：每个 kill 操作独立 try/except + 独立日志，防止一个失败阻塞后续清理：
```python
try:
    await self.okww_process_manager.kill()
except Exception as e:
    logger.exception(f"通过进程管理器中止 OK-WW 进程失败: {e}")
try:
    await System.kill_process(self.script_exe_path)
except Exception as e:
    logger.exception(f"中止 OK-WW 主进程失败: {e}")
track_exe = str(self.script_config.get("Script", "TrackProcessExe") or "").strip()
if not track_exe:
    track_exe = str(self.script_root_path / "data/apps/ok-ww/python/pythonw.exe")
if track_exe:
    try:
        await System.kill_process(Path(track_exe))
    except Exception as e:
        logger.exception(f"中止 OK-WW 追踪进程失败: {e}")
```

#### 5. Manager unlock-then-write 顺序

**反模式**：先 `unlock` 在 finally，再 `UserData.load()` 在 try：

**正确**：`final_task` / `on_crash` 中**先解锁再写回 UserData**（`load()` 在锁定状态下会抛异常）：
```python
# final_task(): 先解锁
if script_cfg.is_locked:
    await script_cfg.unlock()
# 再写回
if self.task_info.mode == "AutoProxy" and hasattr(self, "user_config"):
    await script_cfg.UserData.load(await self.user_config.toDict())
```

#### 6. 脚本前后任务

从 General 引入 `execute_script_task` 支持：

```python
from app.task.general.tools import execute_script_task
```

在 `main_task()` 循环中：
- `ScriptBeforeTask`：在 `_log_game_config_summary()` 之前执行
- `ScriptAfterTask`：在 `update_config()` 之后（成功和重试两种场景都执行）

> ⚠️ 用户编辑页中 `IfScriptBeforeTask` / `ScriptBeforeTask` / `IfScriptAfterTask` / `ScriptAfterTask` 已加入 `OkwwUserConfig.Info`，默认值为 `false` + 空字符串。

### Schema 模型（v5.4.0-beta.1+）

`OkwwConfig_Script` **不再继承** `GeneralConfig_Script`，改为独立 `BaseModel`（与 General 解耦，因 Okww 不暴露 SuccessLog/ErrorLog）：

```python
class OkwwConfig_Script(BaseModel):
    ScriptPath: Optional[str]
    Arguments: Optional[str]
    IfTrackProcess: Optional[bool]
    TrackProcessName: Optional[str]
    TrackProcessExe: Optional[str]
    TrackProcessCmdline: Optional[str]
    ConfigPath: Optional[str]
    ConfigPathMode: Optional[Literal["File", "Folder"]]
    UpdateConfigMode: Optional[Literal["Never", "Success", "Failure", "Always"]]
    LogPath: Optional[str]
    LogPathFormat: Optional[str]
    LogTimeStart: Optional[int]
    LogTimeEnd: Optional[int]
    LogTimeFormat: Optional[str]
```

`OkwwConfig` **移除字段**：`Script_SuccessLog`、`Script_ErrorLog`（ConfigItem 定义已删除）。

前端 `OkwwScriptEdit.vue` 使用**本地 interface**（`OkwwScriptConfigForm`）而非导入 `OkwwConfig`，字段列表中不含 `SuccessLog` / `ErrorLog`，确保用户不可编辑判态关键词。

### 重试与落盘

- `Run.RunTimesLimit` 整轮重试；非 `Success!` 且未达上限 → 按 `_mas_should_close_game_on_retry()` 清理 → `sleep(10)`。
- `final_task`：`save_general_log` → `history/{date}/{user}/{time}.log|json`。
- 调度日志前缀（`_push_dispatch_log`）在运行时推送到前端 WebSocket，**持久化到 history 仅在 save 时**（不 prepend 到历史文件）。

### Manager 用户迭代

> ⚠️ v5.3.1+：`METHOD_BOOK` 仅含 `AutoProxyTask`（**ScriptConfigTask 已删除**）。用户列表不再区分 ScriptConfig/AutoProxy 模式，统一遍历满足条件的脚本用户。

`main_task()` 遍历所有用户而非单用户：

```python
for self.script_info.current_index in range(len(self.script_info.user_list)):
    method = method_cls(...)
    sub_check = await method.check()
    if sub_check != "Pass":
        # 单独标记失败用户，continue 到下一个
        continue
    await self.spawn(method)
```

`final_task()` 聚合用户状态：
```python
if any(user.status == "完成" for user in self.script_info.user_list):
    ...  # 有成功用户
if any(user.status == "异常" for user in self.script_info.user_list):
    self.script_info.status = "异常"
```

### check() 消息规范

check() 返回的消息必须**用户可操作**，非技术描述：

| 反模式 | 正确 |
|--------|------|
| `OK-WW 根目录不存在，请检查脚本根目录` | `请设置ok-ww脚本路径` |
| `OK-WW 可执行文件不存在，请检查主程序路径` | `请设置ok-ww脚本路径` |
| — | `请设置鸣潮游戏路径` |
| — | `用户 {name} 未完成 OK-WW 配置，请先在用户编辑页保存配置` |

特殊状态：`今日代理次数已达上限, 跳过该用户`、`用户剩余天数为 0, 跳过该用户` 时设为 `"跳过"` 状态（非 `"异常"`）。

---

## 同 ok-script 生态其它项目

README 所列 [ok-script](https://github.com/ok-oldking/ok-wuthering-waves) 系项目（原神、少前2、星铁助手等）若 CLI 形态类似（`-t`/`-e` + 自带 GUI），可复用 **本案例的 ok-script 线** 流程；任务列表与配置目录名以各自仓库为准。

---

## 演进规范摘要（按 PR 阶段）

| 阶段 | PR | 规范要点 |
|------|-----|---------|
| 初始化 | #188 feat/okww-adapter | 标准 ok-script 线落地；ScriptConfig GUI 启动；简洁/详细 |
| 优化 | #197 feat/okww-optimize | 游戏启动检测跳过；调度日志展示；配置隔离对齐 General |
| 重构 | #201 feat/okww-skip-game-launch-if-running | hasattr 消除；原子化文件夹同步；崩溃恢复完善 |
| 修复 | #210 fix/okww-wuthering-game-path-validation | 关进程日志对齐 General；路径校验 → 放弃校验保留日志对齐 |
| 审查 | #211 fix/okww-adaptation-review-fixes | `_split_args` DRY；独立 try/except；pre/post 脚本；多用户迭代；unlock-then-write |
| **配置编辑器** | **#215 feat/okww-config-editor** | **表单化编辑器替代 GUI；移除简洁/详细；config_schema.py；API 端点** |
| 同步修复 | #218 fix/okww-sync-upstream-config-changes | 同步 ok-ww 最新配置项变更；全局配置中文标签对齐；移除 DailyTask 不消耗体力选项 |
| 移除 GUI 通道 | #222 feat/remove-okww-gui-config-session | **完全删除 ScriptConfig.py**；仅保留 AutoProxy；过滤 `_` 前缀框架字段 |
| 半自动发现 | #224 feat/remove-okww-gui-config-session | JSON 推断字段类型；翻译自动加载（.po/.mo/.ts）；SELECT_OPTIONS 补选项 |
| 路径强校验 | #231 feat/okww-path-strong-validation | ErrorLog 默认关键词收窄为 info_set；移除前端隐性默认值 |
| 路径强校验 | #235 feat/okww-path-strong-validation | 游戏/脚本路径选择**强校验**：只有空和正确两种状态 |
| 目录清理 | #229 fix/move-okww-config-editor-out-of-m9a | OkwwConfigEditor 移出 M9AUserEdit 目录 |
| **固定判态** | **#242 fix/okww-detail-only** | **移除 SuccessLog/ErrorLog 用户配置；全内置判态；固定详细模式；Schema 独立 BaseModel** |
| 启动任务 | #241 feat/CustomAction | 启动前/启动后功能加入 Okww；通用专项支持 |

---
