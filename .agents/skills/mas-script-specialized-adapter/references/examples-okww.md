# 案例：OK-WW / Okww 专项适配（ok-script 线）

**上游仓库**：[ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)（鸣潮 OK-WW，基于 **ok-script** 的 Python 图像识别自动化，发行物为 `ok-ww.exe`）。

> **当前落地形态（v5.4.0+）**：Okww 是**独立插件** `plugins/okww_adapter`（entry_points 注册，type_key=`Okww`），
> 宿主侧无 `app/task/Okww/`、无 SCRIPT_BOOK/TYPE_BOOK/task_manager 登记。旧 `OkwwConfig(ConfigBase)`
> 仅为 v5.3.x 存量 JSON 反序列化与一次性迁移保留（见 `AppConfig._migrate_okww_scripts_to_plugin_storage`）。

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

### 2. 配置编辑器（插件形态，动态 Schema）

**不**启动 `ok-ww.exe` 无参 GUI 做配置；前端**表单化配置编辑器**直接读写 JSON 配置文件。

| 组件 | 位置 | 说明 |
|------|------|------|
| AST 解析器 | `plugins/okww_adapter/src/okww_adapter/ast_config.py` | 静态解析 ok-ww `repo/config.py` + `src/task/*.py`，不 import 项目模块 |
| 配置 Schema | `plugins/okww_adapter/src/okww_adapter/config_schema.py` | 全动态：字段/选项/翻译/显示名全部来自 ok-ww 安装目录；按 config.py `version` 缓存 |
| 配置编辑器 | `frontend/src/views/OkScriptUserEdit/OkScriptConfigEditor.vue` | ok-script 线共用组件；`endpoint-prefix="/plugin/okww/configs"` |
| 前端 Service | `frontend/src/composables/useOkScriptConfigApi.ts` | 共用 composable，按 endpointPrefix 路由 |
| API 端点 | `plugins/okww_adapter/src/okww_adapter/plugin.py` | 插件 HTTP：`/plugin/okww/configs/list\|update\|batch-update` |
| 自动初始化 | `configs/list` 端点 | per-user 目录缺失文件时从 ok-ww configs 源目录补齐（不覆盖已有） |

**配置落盘路径**（统一 per-user）：
```
data/{scriptId}/{uid}/ConfigFile/
```
- AutoProxy 同步时从该目录原子换入 ok-ww 实际 configs 目录，任务后写回并恢复原配置。

**程序不可用降级（必做）**：`RootPath` 为空或 `ok-ww.exe` 不存在时，`configs/list` 返回 **409**，
**不返回任何静态兜底字段**（无翻译/字段缺失的表单只会误导用户）。前端 `OkScriptConfigEditor` 显示
"程序不可用，返回设置"；`OkwwUserEdit.vue` onMounted 预检并拦截新建/编辑。

**动态 Schema 数据源**（全部在 ok-ww 安装目录内，AST 静态解析）：

- **任务注册表 + `-t` 序号** ← `repo/config.py` 的 `onetime_tasks` 列表顺序 + `global_configs`（ConfigOption 首参即文件名）
- **下拉/多选候选项** ← `repo/src/task/*.py` 的 `config_type`。三种写法都要覆盖：整体赋值 `self.config_type = {...}`、下标赋值 `self.config_type['X'] = {...}`、options 引用变量（`self.boss_list` 等，同文件内回溯 `= [字面量]` 赋值回填）
- **字段中文标签/选项翻译** ← ok-ww 内置 i18n（`.mo` > `.po` > `.ts`）
- **字段说明** ← `config_description.update({...})` + i18n
- **一级菜单显示名** ← 任务的 `self.name` 经 i18n 翻译（"Daily Task"→"日常一条龙"）；全局配置回退文件名 stem 翻译（"Game Hotkey"→"游戏快捷键"）
- **类型自动推断**：JSON 值 → `bool` / `int` / `float` / `string` / `list`
- **内部字段屏蔽**：`_` 前缀的 ok-ww 框架字段不暴露
- **version 缓存**：`config.py` 顶层 `version = "vX.Y.Z"` 作缓存键，同版本命中不重解析，减少每次 list 的源码 IO
- **无静态白名单**：`SELECT_OPTIONS`/`CONFIG_GROUPS`/`CONFIG_DISPLAY_NAMES`/`TASK_INDEX_MAP` 四张手工表已彻底移除；`_EXCLUDED_FILES` 仅剔除无意义项（如空的 GardenTask.json）
- ⚠️ **options 必须保持源码英文原值**（写回 ok-ww 的存储值），前端用 `optionLabels` 映射显示中文，切勿后端预翻译

**纯安装态降级**：无 `repo/` 源码时 schema 为空，字段退化为纯 JSON 值类型推断（无下拉、无翻译）；前端任务序号下拉退回静态兜底表。

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
- [x] `OkwwScriptEdit.vue`：三段式；根目录推导路径；`Game.Enabled` + `Game.CloseOnManualStop`
- [x] `OkwwUserEdit.vue`：集成共用 `OkScriptConfigEditor`；onMounted 预检 ok-ww 可用性；任务序号下拉动态来自 `configs/list`（静态表仅兜底）
- [x] `types/script.ts`、`useScriptApi.ts` 分支
- [x] `frontend/src/assets/ok-ww.ico`

**后端（插件形态）**

- [x] `plugins/okww_adapter/`：`pyproject.toml` entry_points 注册 `auto_mas.plugins`
- [x] `schema.py`：pydantic `OkwwConfig` / `OkwwUserConfig`（PluginField；`Game.CloseOnManualStop` 默认 True）
- [x] `plugin.py`：`ScriptAdapterDefinition(type_key="Okww")` + 插件 HTTP 端点 + 409 不可用降级
- [x] `adapter/runtime.py`：`OkwwAdapterHooks`（prepare/finalize/on_crash + 手动终止标记）
- [x] `adapter/autoproxy.py`：`AutoProxyTask`（`-t N -e`、内置判态、配置注入/写回/恢复）
- [x] `ast_config.py` + `config_schema.py`：动态 Schema（见上节）
- [x] 宿主侧零登记：无 SCRIPT_BOOK/TYPE_BOOK/task_manager 条目；OpenAPI 无 Okww 模型

**勿套用**

- M9A `TaskQueueSection` + 写盘无 CLI（OK-WW **有** `-t`）
- MaaEnd `mxu-MaaEnd.json` / `autoRunOnLaunch`（无 PI V2 / MXU）
- ScriptConfig 调起 GUI 模式（已完全删除，唯一运行模式为 AutoProxy）
- General `SuccessLog` / `ErrorLog` 用户配置（Okww **不暴露**判态关键词，全内置）
- 宿主内置 `app/task/Xxx/` 落地方式（新 ok-script 线专项一律走插件）

---

## 实现规范（Okww 必遵守）

全仓共性见 [adapter-code-norms.md](./adapter-code-norms.md)。以下为 **Okww / ok-script** 增量，实现时按表写代码。

### CLI 与配置分工

| 层级 | 字段 | 规则 |
|------|------|------|
| 用户 | `Task.TaskIndex` | 1-based，拼 `-t N`；下拉序号动态来自 `configs/list`（onetime_tasks 顺序） |
| 用户 | （已废弃 `Task.ExitOnFinish`） | `-e` 恒定追加，不暴露配置 |
| 脚本 | 判态 | **全内置**，不向用户暴露 SuccessLog/ErrorLog 配置项 |
| 配置 | 表单化编辑器 | 读写 `data/{scriptId}/{uid}/ConfigFile/` JSON |

> ⚠️ 判态关键词完全由代码内置常量 `_OKWW_BUILTIN_FATAL` 控制（成功=进程自然退出），用户不可编辑。

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
2. 成功：`not okww_process_manager.is_running()` → `Success!`（ok-ww 由 `-e` 任务完成后自然退出，**进程退出即成功**，无成功关键词）
3. `now - latest_time > Run.RunTimeLimit`（分钟）→ 超时

非 `正常运行中` 时 `wait_event.set()`。`on_crash` 与关键词无关。

### 游戏与进程

| 项 | 规则 |
|----|------|
| `Game.Enabled` | 总开关：任务**开始前** MAS 启游戏、结束/失败/异常后 MAS 兜底关游戏；失败则 `continue`，**不**启 ok-ww |
| `Game.CloseOnManualStop` | **手动终止**任务时是否关游戏（默认 True；关闭便于调试）。正常失败/异常不受它影响，仍兜底关闭 |
| Hooks `prepare` | `Game.Enabled` 时创建 `game_manager`；`CancelledError` 时置 `manual_stop_requested` 再重抛 |
| 游戏启动检测 | 启动前 `is_process_running(Client-Win64-Shipping.exe)` → 已运行则跳过（MAS 仍接管兜底关闭） |
| 成功轮 `main_task` | 等待 ok-ww `-e` 自然退出（超时兜底强杀），只 `_kill_okww_process()` |
| 失败/重试/`on_crash` | 始终杀 ok-ww；杀游戏由 `Game.Enabled` 控制 |
| **游戏路径 UI** | 选鸣潮任意层级目录 → 关键词锚点自动拼 `…/Client/Binaries/Win64/Client-Win64-Shipping.exe`；**强校验**：路径只接受空或正确两种状态 |
| **脚本路径 UI** | 选 ok-ww 根目录 → 校验 `ok-ww.exe` 存在；**强校验**：路径只接受空或正确两种状态 |
| 追踪子进程 | `pythonw.exe`，exe=`{RootPath}/data/apps/ok-ww/python/pythonw.exe`（`_OKWW_REL_*` 常量派生，与前端 `OKWW_EXE_NAME` 同步） |
| 同根互斥 | `get_path_runtime_lock(RootPath)`：同一 ok-ww 项目串行运行 |
| `check()` 检查 | 用户配置目录为空 → `"用户 {name} 未完成 OK-WW 配置，请先在用户编辑页保存配置"` |

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

「从 Temp 恢复脚本配置」提取为 Hooks 方法（`adapter/runtime.py::_restore_script_config_from_temp`），
`finalize` 与 `on_crash` 共用：

```python
async def _restore_script_config_from_temp(self, runtime) -> None:
    # had_original_script_config 区分「原本就有配置（原子化恢复）」
    # 和「任务期新写入（直接清理）」两种场景；恢复后删除 Temp。
    ...
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
track_exe = self.script_root_path / _OKWW_REL_PYTHONW
try:
    await System.kill_process(track_exe)
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

### Schema 模型（插件 pydantic）

插件 `schema.py` 用 **PluginField** 声明（非宿主 ConfigItem/OpenAPI 模型）：

- `OkwwConfig`：`Info(Name, RootPath)` / `Game(Enabled, CloseOnManualStop, Path, Arguments, WaitTime)` / `Run(ProxyTimesLimit, RunTimesLimit, RunTimeLimit)`。**无 Script 组**——路径/进程/日志全部由 `RootPath` + `_OKWW_REL_*` 常量派生。
- `OkwwUserConfig`：`Info` / `Task(TaskIndex)` / `Data(只读运行数据)` / `Notify`。`Password` 用 `sensitive=True`（映射 EncryptValidator，与宿主同一套加密）。
- `Game` 组 `extra="ignore"`：迁移进来的旧字段（LaunchBeforeTask/CloseOnFinish 等）静默丢弃。
- ⚠️ 前后端字段名必须一致（曾因前端写 `KillGameOnManualStop`、后端 `CloseOnManualStop` 导致开关完全失效——`extra="ignore"` 会吞掉未知键，不报错）。

### v5.3.x → 插件的一次性配置迁移

`AppConfig._migrate_okww_scripts_to_plugin_storage`（init_config 时执行，幂等）：

1. 旧 `OkwwConfig(ConfigBase)` 记录 → 白名单挑字段 → `PluginScriptConfig`（`Meta.PluginTypeKey="Okww"`，`PluginData.Config` JSON），用户 UID 保留。
2. **简洁模式 ConfigFile**：v5.3.1 `Info.Mode` 默认"简洁"，任务 JSON 共享存于 `data/<sid>/Default/ConfigFile`；迁移为每个缺失配置的用户复制副本，**save 成功后**才清理 Default（中途失败下次重试）。
3. 丢弃项：`Script_*` 全组（RootPath 派生）、`Game.LaunchBeforeTask/Type/URL/CloseOnFinish/Emulator*`、`Task.ExitOnFinish`。
4. 方针：**一次性完整迁移，不做运行期向下兼容**。旧 `OkwwConfig(ConfigBase)` 类仅为存量 JSON 反序列化保留，迁移窗口结束后随迁移函数一并删除。

### 重试与落盘

- `Run.RunTimesLimit` 整轮重试；非 `Success!` 且未达上限 → 按 `_mas_should_close_game_on_retry()` 清理 → `sleep(10)`。
- `final_task`：`save_general_log` → `history/{date}/{user}/{time}.log|json`。
- 调度日志前缀（`_push_dispatch_log`）在运行时推送到前端 WebSocket，**持久化到 history 仅在 save 时**（不 prepend 到历史文件）。

### 多用户迭代与手动终止（插件形态）

多用户遍历由**宿主插件框架**（`ScriptAdapterRuntime` 编排）负责；插件只提供：

- `run_auto_proxy(runtime)` → 单用户 `AutoProxyTask`（外包 `_CheckedAutoProxyTask`：check 不过标记状态并跳过）
- Hooks `finalize` 聚合用户状态：任一用户 `"异常"` → 脚本 `"异常"`，否则 `"完成"`
- `_CheckedAutoProxyTask.main_task` 捕获 `CancelledError` → 置 `inner.manual_stop_requested = True` 再重抛（`CancelledError` 是 `BaseException`，不进 `on_crash`，只能在此拦截打标）
- `final_task` 的关游戏决策走 `_should_close_game_after_finish()`：手动终止时由 `Game.CloseOnManualStop` 决定

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
| **插件化** | dev_v2 | **整体迁出宿主为 `plugins/okww_adapter`**；删除 `app/task/Okww|Okef|Ok`、SCRIPT_BOOK/TYPE_BOOK/OpenAPI 旧模型；手动终止开关 `Game.CloseOnManualStop` |
| **动态 Schema** | dev_v2 | AST 解析 ok-ww 源码（onetime_tasks/config_type/self.name）+ i18n；version 缓存；删除四张静态白名单表；409 不可用降级 |
| **一次性迁移** | dev_v2 | v5.3.1 → 插件存储一次性迁移（含简洁模式 Default/ConfigFile → per-user 副本）；不做运行期向下兼容 |

---
