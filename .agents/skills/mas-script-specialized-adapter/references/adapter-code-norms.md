# 专项适配 · 代码规范（必遵守）

新增或维护 `ScriptType` 时按表实现，**不要**依赖事后排查叙事。Okww 专项增量见 [examples-okww.md](./examples-okww.md#实现规范okww-必遵守)。

## 1. 注册与 API

| 必做 | 位置 |
|------|------|
| `XxxConfig` / `XxxUserConfig` + `schema.py` | `app/models/` |
| `SCRIPT_BOOK`、`USER_BOOK`、`task_manager` 分支 | `app/core/`、`app/models/config.py` |
| `TYPE_BOOK["XxxConfig"]` → 展示文案 | `app/utils/constants.py`（否则调度 `combox/task` KeyError） |
| 后端改 schema 后 `yarn openapi` | `frontend/`；**禁止**手改 `src/api/models/*` |
| OpenAPI 生效 | 重启后端 → `openapi.json` **文本**含新类型名（勿只靠 PowerShell 对象键）→ 确认 36163 为当前 `main.py` |

## 2. 前端表面

| 必做 | 位置 |
|------|------|
| Hub 片段、`ScriptTable` 卡片图标与文案 | `Scripts.vue`、`ScriptTable.vue` |
| 脚本编辑三段 + 用户编辑三段 | `EditView/Script/`、`EditView/User/` |
| `useScriptApi`：**脚本类型**与 **UserConfig→users[]** 两处分支 | 漏后者则列表 NO DATA |
| 用户 **add**：先 `addUser` 再 `router.replace` 到带 `userId` 路由 | 参考 `GeneralUserEdit` |
| WebSocket | `@/composables/useWebSocket`（勿造 `@/utils/websocketClient`） |
| 展示文案 vs 技术标识分离 | 文案如 `ok-ww`；`ScriptType`/路由/OpenAPI 名保持 `Okww` 等 |

## 3. 任务模块（`app/task/Xxx/`）

| 必做 | 类 |
|------|-----|
| 实现 `final_task`、`on_crash` | `Manager`、`AutoProxy`、`ScriptConfig` |
| `final_task` 解锁配置、清进程、写 `history/`（或专项 `save_*_log`） | `AutoProxy` |
| `on_crash` 设异常 + WebSocket `Error` | 同上 |

### AutoProxy 日志与状态（通用）

| 规则 | 实现 |
|------|------|
| `LogMonitor` 构造 | 必须传 `time_stamp_range`、`time_format`、`check_log`（对齐 `general/AutoProxy.py`） |
| 任务结果 | 每轮 `log_record[start_time] = LogRecord()`，只写 **`log_record.status`** |
| 禁止 | 对 `UserItem.result` 赋值（只读 property） |
| 用户配置索引 | `cur_user_uid = uuid.UUID(user_id)`，再 `user_config[cur_user_uid]` |

### AutoProxy 进程（有 `IfTrackProcess` 时）

| 规则 | 实现 |
|------|------|
| `ProcessInfo` | 至少一项非空（ok-script 默认 `pythonw.exe` + `{RootPath}/data/apps/ok-ww/python/pythonw.exe`） |

## 4. 简洁 / 详细（架构线选型决定）

部分架构线**无**简洁/详细区分，取决于专项设计决策：

| 架构线 | 模式区分 | 配置落盘 |
|--------|----------|----------|
| Okww（ok-script） | **无**：统一表单化编辑器 | `data/{scriptId}/Default/ConfigFile/` |
| General | 简洁/详细 | 简洁→`Default/`；详细→`{userId}/` |
| MaaEnd | 简洁/详细 | 同上 |
| M9A | **无** | 队列 JSON，不套用此模式 |

**规则**：
- 如有简洁/详细：`AutoProxy.check()` 须按 `Mode` 校验对应目录存在；用户页仅 **详细** 显示配置按钮。
- 如无简洁/详细（Okww 等）：配置编辑器始终可用，不因模式隐藏。

## 5. 架构线选型（实现前只读）

| 线 | 自启动 | 用户改设置 |
|----|--------|------------|
| ok-script（Okww） | CLI `-t`/`-e`，`AutoProxy` 拼 argv | 表单化编辑器读写 JSON（v5.3.0-beta.3+） |
| MFAA（M9A） | 写盘 + exe，无稳定 CLI | 写 JSON，勿套 ScriptConfig 壳 |
| MXU（MaaEnd） | 文档化参数 / `mxu-*.json` | ScriptConfig + `mxu-*.json` |

细节：[script-frontend-architectures.md](./script-frontend-architectures.md)、各 `examples-*.md`。

---

## 6. 任务模块代码质量（通用，所有专项适配）

以下规范来自 OKWW 专项 review/refactor 收敛结论，**所有新 `ScriptType` 必须遵守**。

### 6.1 hasattr() 消除

**反模式**：
```python
if hasattr(self, "temp_path") and self.temp_path.exists():
```

**正确**：在 `__init__` 中显式初始化所有实例属性为 `None`/`False`，再检查 truthiness：
```python
# __init__
self.temp_path: Path | None = None
self.script_config_path: Path | None = None
self.had_original_script_config = False

# later - 简单 truthiness 检查
if self.temp_path and self.temp_path.exists():
    ...
```

### 6.2 原子化文件操作

涉及配置目录/文件写入时，使用 `.tmp` + `rename` 模式：

```python
# 反模式：直接 rm + copy（中断即配置损坏）
shutil.rmtree(target, ignore_errors=True)
shutil.copytree(source, target, dirs_exist_ok=True)

# 正确：tmp → rename（原子化）
tmp_dst = target.with_name(target.name + ".tmp")
shutil.rmtree(tmp_dst, ignore_errors=True)
shutil.copytree(source, tmp_dst, dirs_exist_ok=True)
shutil.rmtree(target, ignore_errors=True)
tmp_dst.rename(target)
```

### 6.3 DRY：提取复用的配置恢复/清理逻辑

`final_task` 和 `on_crash` 共用的恢复逻辑**必须**提取为独立方法（如 `_restore_script_config_from_temp()`），避免重复。

**必提取**：
- 配置还原/清理逻辑
- 参数拆分（`_split_args`）
- 错误日志清洗（`_sanitize_*`）

### 6.4 独立 try/except 每操作

进程清理、文件操作的每个步骤独立 try/except，防止一个失败阻塞后续清理：

```python
# 反模式：一个 try 包多个操作
try:
    await process_manager.kill()
    await System.kill_process(main_exe)
    await System.kill_process(track_exe)
except Exception as e:
    logger.exception("失败")  # 不知道哪个失败了

# 正确：分散 try/except + 独立日志
try:
    await process_manager.kill()
except Exception as e:
    logger.exception(f"进程管理器中止失败: {e}")
try:
    await System.kill_process(main_exe)
except Exception as e:
    logger.exception(f"主进程中止失败: {e}")
try:
    await System.kill_process(track_exe)
except Exception as e:
    logger.exception(f"追踪进程中止失败: {e}")
```

### 6.5 显式属性类型声明

所有实例属性在 `__init__` 中带类型注记：

```python
self.cur_user_config: OkwwUserConfig = self.user_config[self.cur_user_uid]
self.task_index: int = 0
```

**禁止**延迟赋值（先 `= None` 再在 `check()/prepare()` 赋值）——这迫使下游代码用 `hasattr` 或 `is not None` 守卫。

---

## 7. Manager 规范（通用）

### 7.1 unlock-then-write 顺序

`final_task` / `on_crash` 中**必须先解锁再写回 UserData**（`load()` 在锁定状态下抛异常）：

```python
# final_task()
if script_cfg.is_locked:
    await script_cfg.unlock()

# 解锁之后再写回
if self.task_info.mode == "AutoProxy" and hasattr(self, "user_config"):
    await script_cfg.UserData.load(await self.user_config.toDict())
```

### 7.2 多用户迭代

`main_task()` 遍历所有用户；每个用户的 `check()` 失败单独标记，`continue` 到下一个：

```python
for self.script_info.current_index in range(len(self.script_info.user_list)):
    method = method_cls(...)
    sub_check = await method.check()
    if sub_check != "Pass":
        # 标记当前用户失败，继续下一个
        current_user = self.script_info.user_list[self.script_info.current_index]
        if current_user.status == "等待":
            current_user.status = "异常"
        continue
    await self.spawn(method)
```

### 7.3 状态聚合

`final_task()` 聚合所有用户状态：
```python
if any(user.status == "完成" for user in self.script_info.user_list):
    ...  # 有成功用户
if any(user.status == "异常" for user in self.script_info.user_list):
    self.script_info.status = "异常"
else:
    self.script_info.status = "完成"
```

### 7.4 配置 Temp 备份与恢复

在 `prepare()` 备份原配置到 Temp → `main_task()` 执行 → `final_task()` / `on_crash()` 恢复。

**`had_original_script_config` 标记**用于区分：
- 任务前已有配置 → 任务后恢复原配置
- 任务前无配置（新创建） → 任务后清理

---

## 8. check() 消息规范（通用）

`check()` 返回的消息必须**用户可操作**，告知用户需要做什么操作：

| 反模式（技术描述） | 正确（用户操作） |
|--------------------|------------------|
| `根目录不存在，请检查脚本根目录` | `请设置脚本路径` |
| `可执行文件不存在` | `请设置脚本路径` |
| `配置文件不存在` | `请先在脚本页完成「配置 XX」步骤` |

跳过类消息设为 `"跳过"` 状态（非 `"异常"`）：
- `今日代理次数已达上限, 跳过该用户`
- `用户剩余天数为 0, 跳过该用户`

---

## 9. 与 General 的对齐原则

专项适配**优先对齐 General 模式**，仅在明确不可用时自行设计：

| 对齐点 | 规则 |
|--------|------|
| 日志 | `get_logger("XX 自动代理")` 中文名，与 General 一致 |
| 进程管理 | `ProcessManager`、`ProcessInfo`、`System.kill_process` |
| 日志监控 | `LogMonitor` 三参构造 |
| 状态 | `log_record[start_time] = LogRecord()`，只写 `status` |
| pre/post 脚本 | `from app.task.general.tools import execute_script_task` |
| 配置同步 | `ConfigFile` 目录约定 |
| 跨类型重构 | `refactor(game): 为End、Okww和通用都加上防止重复启动` — 共用逻辑上提到 `app/task/general/tools` |

**勿**为专项 fork 配置模型（`OkwwConfig_Game` 等）——在 task 代码中处理业务逻辑，配置模型保持与 General 结构对齐。

---

## 10. 提交前自检

- [ ] hasattr() 消除：所有属性在 `__init__` 显式初始化
- [ ] 原子化 I/O：配置写入用 tmp+rename
- [ ] DRY：`final_task` / `on_crash` 共用逻辑已提取
- [ ] try/except：进程清理每操作独立
- [ ] unlock-then-write：`final_task` 中先解锁再写回
- [ ] check() 消息：用户可操作
- [ ] Manager 多用户迭代
- [ ] 参数拆分 `_split_args` 已提取为模块级函数
- [ ] 对齐 General：勿 fork 配置模型，用 task 代码处理差异
