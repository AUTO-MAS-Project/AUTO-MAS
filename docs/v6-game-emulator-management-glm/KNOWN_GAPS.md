# 已知缺陷与未修复项 — 游戏/模拟器管理（后端部分）

> Subagent A 后端可靠性研究产出
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 分支：`integration/dev-v2-dev-all-plugins`，HEAD：`b5e872815`
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断；`proposed` = 提议但未实现；`unverified` = 未验证
> 可写范围约束：仅 `app/core/emulator_manager.py`、`app/api/emulator.py`、`app/plugins/emulator_compat.py`、`app/models/emulator.py`、`app/models/config.py`/`schema.py`、`tests/**`

---

## 1. 摘要

本次审计在可写范围内已修复 4 个源码级问题（详见 `FUNCTION_MATRIX.md` B2/B3/B4 节）：

1. `operate_emulator` 假成功 → 改为 accepted/operation-id + WS 通知
2. `get_status` 单个损坏配置拖垮整张列表 → 每配置 try/except 隔离
3. `_apply_ad_blocking` 用 `suppress(Exception)` 静默所有异常 → 拆分为命名异常
4. `_run_operate` 错误路径 `Publisher.send` 失败掩盖原始操作异常 → 内层 try/except

**仍存在 2 个已知缺陷**，位于可写范围之外的 `app/utils/emulator/` 模块，本审计无权修改，需后续单独处理。另发现 1 处与模拟器管理无直接关系的 `suppress(Exception)`（信息性记录）。

---

## 2. 已知缺陷详情

### GAP-01 — MuMu `find_mumu_nx_window` 使用 `suppress(Exception)` 过宽

| 字段 | 内容 |
|------|------|
| 文件 | `app/utils/emulator/mumu.py` |
| 行号 | 376 |
| 严重度 | P2 |
| 状态 | observed |
| 可写范围 | ❌ 超出（位于 `app/utils/emulator/`，非 Subagent A 可写范围） |

**当前代码**（`observed`，行 350-379）：

```python
async def find_mumu_nx_window(self) -> int | None:
    """
    查找 MuMu 多开器窗口
    ...
    """
    def enum_cb(hwnd: int, result_list: list[int | None]) -> bool:
        if result_list[0] is not None:
            return False  # 已找到，停止枚举
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd) != 0:
            return True
        if win32gui.GetWindowText(hwnd) != "MuMu模拟器":
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name().lower()
            if proc_name == "mumunxmain.exe":
                result_list[0] = hwnd
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
        return True

    result: list[int | None] = [None]
    with suppress(Exception):  # <-- GAP-01
        # EnumWindows 在回调返回 False 时抛出异常，属正常行为
        win32gui.EnumWindows(enum_cb, result)
    return result[0]
```

**问题分析**（`inferred`）：

- 注释说明 `EnumWindows` 在回调返回 `False` 时会抛出异常（`pywintypes.error`），属正常停止枚举的机制。
- 但 `suppress(Exception)` 过宽，会同时吞掉：
  - `pywintypes.error`（预期，可吞）
  - `TypeError` / `AttributeError`（编码错误，应可见）
  - `MemoryError` / `RecursionError`（资源异常，绝不应吞）
- 内层回调 `enum_cb` 已对 `psutil.NoSuchProcess`/`AccessDenied`/`OSError` 做了精准捕获；外层 `suppress(Exception)` 进一步吞掉了 `EnumWindows` 调用本身的非预期异常。

**影响**（`inferred`）：

- `find_mumu_nx_window` 被 `open()`（行 85）和 `close_mumu_nx_window()`（行 386）调用。
- 若 `EnumWindows` 因非预期原因失败（如 win32 系统调用底层异常），函数静默返回 `None`，调用方无法区分"未找到窗口"与"枚举失败"。
- 在 `open()` 中，`if_close_mumu_nx = await self.find_mumu_nx_window() is None`（行 85）将异常吞掉后误判为"无需关闭多开器窗口"，可能导致 MuMu 多开器窗口残留。
- 不影响操作主流程的成败（启动/关闭仍以 `getStatus` 为准），仅影响多开器窗口的协同关闭行为。

**提议修复**（`proposed`）：

```python
import pywintypes  # 顶部导入

result: list[int | None] = [None]
try:
    win32gui.EnumWindows(enum_cb, result)
except pywintypes.error as e:
    # EnumWindows 回调返回 False 时抛出 pywintypes.error，属正常停止枚举
    logger.debug(f"EnumWindows 提前停止: {e}")
except Exception:
    logger.exception("EnumWindows 调用发生非预期异常")
    raise
return result[0]
```

或更保守的版本（保留静默但仅限 pywintypes.error）：

```python
import pywintypes
with suppress(pywintypes.error):
    win32gui.EnumWindows(enum_cb, result)
```

**置信度**：高。`pywintypes.error` 是 win32gui 在回调返回 False 时抛出的标准异常类型（`observed` from win32 API 文档惯例）。

---

### GAP-02 — LDPlayer `get_adb_ports` 使用裸 `except:` 吞掉所有异常

| 字段 | 内容 |
|------|------|
| 文件 | `app/utils/emulator/ldplayer.py` |
| 行号 | 329 |
| 严重度 | P2 |
| 状态 | observed |
| 可写范围 | ❌ 超出（位于 `app/utils/emulator/`，非 Subagent A 可写范围） |

**当前代码**（`observed`，行 320-330）：

```python
async def get_adb_ports(self, pid: int) -> int:
    """使用psutil获取adb端口"""
    try:
        process = psutil.Process(pid)
        connections = process.net_connections(kind="inet")
        for conn in connections:
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port != 2222:
                return conn.laddr.port
        return 0  # 如果没有找到合适的端口，返回0
    except:  # noqa: E722  # <-- GAP-02
        return 0
```

**问题分析**（`inferred`）：

- 裸 `except:`（`# noqa: E722` 仅是 lint 抑制，不改变语义）会捕获所有异常，包括：
  - `psutil.NoSuchProcess` / `psutil.AccessDenied`（预期，可吞）
  - `OSError` / `PermissionError`（系统级，应记录）
  - `KeyboardInterrupt` / `SystemExit`（**绝不应吞**，会导致 Ctrl+C 失效、SIGTERM 优雅退出失效）
  - `TypeError` / `AttributeError`（编码错误，应可见）
- 返回 `0` 表示"未找到端口"，调用方无法区分"进程不存在"与"端口确实为 0"（虽然 0 不是合法 ADB 端口，但语义模糊）。

**调用链追踪**（`inferred`）：

- `get_adb_ports` 在 `ldplayer.py` 当前版本中**未被任何调用方使用**（grep 仅在定义处命中，无调用点）。
- 推测为遗留代码或预留接口；但仍应修复，避免未来误用。

**影响**（`inferred`）：

- 当前无运行时影响（无调用方）。
- 若未来被调用，`KeyboardInterrupt`/`SystemExit` 被吞会导致进程无法优雅退出，是 PEP 8 明确禁止的反模式。

**提议修复**（`proposed`）：

```python
async def get_adb_ports(self, pid: int) -> int:
    """使用psutil获取adb端口"""
    try:
        process = psutil.Process(pid)
        connections = process.net_connections(kind="inet")
        for conn in connections:
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port != 2222:
                return conn.laddr.port
        return 0
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.debug(f"获取 LDPlayer adb 端口失败 pid={pid}: {type(e).__name__}: {e}")
        return 0
    except OSError as e:
        logger.warning(f"获取 LDPlayer adb 端口系统级失败 pid={pid}: {type(e).__name__}: {e}")
        return 0
```

**置信度**：高。PEP 8 明确禁止裸 `except:`（应至少为 `except Exception:`），且 `KeyboardInterrupt`/`SystemExit` 不应被业务代码吞掉（`observed` from PEP 8）。

---

## 3. 信息性记录 — 其他 `suppress(Exception)` 实例

本次审计使用 grep 对 `app/` 目录全量扫描 `suppress(Exception)` 与裸 `except:`，发现以下实例。**这些不在游戏/模拟器管理任务范围内**，仅作信息性记录，不分析、不提议修复：

| 文件 | 行号 | 上下文 | 是否在模拟器管理调用链上 |
|------|------|--------|--------------------------|
| `app/utils/ProcessManager.py` | 491 | `AttachThreadInput` 取消附加的 finally 清理 | 否（窗口前台操作，非模拟器管理直接调用） |
| `app/MaaFW/EndFieldPCWin32.py` | 100 | MaaFW 集成 | 否 |
| `app/configuration/v2/types.py` | 130 | `except Exception:  # noqa: BLE001`（已命名，非裸） | 否 |
| `app/task/SRC/tools/login.py` | 166 | 任务脚本 | 否 |
| `app/services/system.py` | 169 | 系统服务 | 否 |
| `app/core/ws/lifecycle.py` | 135 | WS 生命周期 | 间接（WS 推送底层，但 `Publisher.send` 已在 `emulator_manager.py` 错误路径单独保护） |
| `app/task/MaaEnd/tools/login.py` | 104/139/157/200/235 | 任务脚本 | 否 |
| `app/api/core.py` | 127 | 核心 API | 否 |
| `app/plugins/dev_hmr.py` | 399 | 开发热重载插件 | 否 |
| `app/plugins/runtime_api.py` | 290 | 运行时 API 插件 | 否 |

**说明**（`observed`）：

- `app/core/ws/lifecycle.py:135` 与 WS 推送相关，但 Subagent A 已在 `_run_operate` 错误路径对 `Publisher.send` 加了内层 try/except 保护（详见 `FUNCTION_MATRIX.md` B2/B4 节），故该底层 suppress 不会影响模拟器操作通知的可靠性。
- 其余实例与模拟器管理无调用链关系，留待相应模块的负责人处理。

---

## 4. 待验证项

以下项本次审计**未能验证**，标注为 `unverified`，需后续补充：

| ID | 待验证内容 | 原因 | 建议验证方式 |
|----|-----------|------|-------------|
| UV-01 | MuMu `_get_adb_address` 在 `get_adb_info` 失败时的默认端口兜底逻辑是否在真实 MuMu 环境下正确 | 无 MuMu 模拟器环境，仅静态阅读 | 集成测试，需 MuMu 安装环境 |
| UV-02 | LDPlayer `get_adb_ports` 当前无调用方，是否为遗留死代码 | grep 仅命中定义处 | 跨分支历史检索或询问维护者 |
| UV-03 | `MUMU_FORCE_KILL_KEYWORDS` 白名单是否覆盖所有 MuMu 残留进程 | 无运行时进程样本 | 在真实关闭场景采集进程列表 |
| UV-04 | `ForceKillOnClose` 在 `close()` finally 块中执行，若 `_force_kill_mumu_processes` 抛异常是否影响 close 返回值 | `close` 已有 try/finally，但 finally 内异常会传播 | 补充单元测试 |

---

## 5. 修复优先级汇总

| ID | 文件:行 | 严重度 | 可写范围内 | 状态 | 备注 |
|----|---------|--------|-----------|------|------|
| GAP-01 | `mumu.py:376` | P2 | ❌ | 待修复 | `suppress(Exception)` → `suppress(pywintypes.error)` |
| GAP-02 | `ldplayer.py:329` | P2 | ❌ | 待修复（且当前无调用方） | 裸 `except:` → 命名异常 |
| UV-01~04 | — | P3 | — | 待验证 | 需真实环境或维护者确认 |

---

## 6. 与已修复项的对照

| 修复 ID | 文件 | 原问题 | 修复方式 | 状态 |
|---------|------|--------|---------|------|
| FIX-01 | `app/core/emulator_manager.py` | `operate_emulator` 假成功 | accepted/operation-id + WS 通知 | ✅ fixed |
| FIX-02 | `app/core/emulator_manager.py` | `get_status` 单配置失败拖垮整列表 | 每配置 try/except 隔离 | ✅ fixed |
| FIX-03 | `app/core/emulator_manager.py` | `_apply_ad_blocking` 用 `suppress(Exception)` | 拆分为命名异常捕获 | ✅ fixed |
| FIX-04 | `app/core/emulator_manager.py` | `_run_operate` 错误路径 `Publisher.send` 失败掩盖原始异常 | 内层 try/except + `logger.warning` | ✅ fixed |

> 上述 4 项已通过确定性测试验证（58 passed），证据见 `_alpha_build/a1/glm-game-emulator-management-20260723/subagent-A/pytest-run-final.log`。
> GAP-01/GAP-02 因超出可写范围未在本任务修复，已在此文档登记。

---

> 本文档完毕。所有结论均带标注（`observed`/`inferred`/`proposed`/`unverified`）与证据路径。

---

# 已知缺陷与未修复项 — 游戏/模拟器管理（测试与可用性部分）

> Subagent C 测试与可用性研究产出
> 工作树：`D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration`
> 分支：`integration/dev-v2-dev-all-plugins`，HEAD：`b5e872815`
> 标注规则：`observed` = 直接读取确认；`inferred` = 基于代码推断；`proposed` = 提议但未实现；`unverified` = 未验证
> 可写范围约束：仅 `frontend/src/views/emulator/__tests__/**`、`docs/v6-game-emulator-management-glm/**`、`_alpha_build/a1/glm-game-emulator-management-20260723/subagent-C/**`

---

## 7. 摘要（测试与可用性）

本次审计在可写范围内已完成：

1. **5 个测试文件**（2 个 fake 夹具 + 3 个 .test.ts），共 54 个 deterministic 用例，全量 `yarn test --run` 36 文件 349 用例全过（1.87s）
2. **14 张 Windows 手测卡**（GM-001 ~ GM-014），所有真实设备项标 `unverified`
3. **可访问性审计清单**（A11Y-01 ~ A11Y-08）
4. **性能审计表**（PERF-01 ~ PERF-05）
5. **脚本联动矩阵**（LINK-MAA ~ LINK-Okww，8 个脚本类型）

**仍存在以下测试与可用性缺陷**，需后续处理。

---

## 8. 测试基础设施缺陷

### T-GAP-01 — `yarn typecheck` 基线失败

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/vite.config.ts:11` |
| 严重度 | P2 |
| 状态 | observed |
| 可写范围 | ❌ 超出（`vite.config.ts` 非 Subagent C 可写范围） |

**问题描述**（`observed`）：

- `yarn typecheck` 在 `vite.config.ts(11,33)` 报 `Property 'replaceAll' does not exist on type 'string'`
- 这是工作树既有问题，与 Emulator 专区无关
- 导致无法用 `yarn typecheck` 作为前端类型安全门禁

**影响**（`inferred`）：

- 新增的 emulator 测试文件无法通过 typecheck 验证类型安全
- 但 `yarn test --run` 和 `yarn lint` 均通过，测试本身是类型安全的

**证据**：`_alpha_build/a1/glm-game-emulator-management-20260723/subagent-C/baseline/yarn-typecheck.log` (exit 2)

---

### T-GAP-02 — 生产构建 chunk 大小未获取

| 字段 | 内容 |
|------|------|
| 严重度 | P3 |
| 状态 | unverified |
| 可写范围 | — |

**问题描述**（`observed`）：

- `yarn web` 启动的是 Vite dev server（端口 5173/5174），不是生产构建
- 未执行 `yarn build` 获取 `dist/` 下的 chunk 文件大小
- PERF-01（页面首开 chunk 大小）无法填入实际数字

**影响**（`inferred`）：

- 无法评估 Emulator 专区对首屏加载性能的影响
- 无法判断是否需要代码分割优化

**证据**：`_alpha_build/a1/glm-game-emulator-management-20260723/subagent-C/baseline/yarn-web-build-2.log`（仅 dev server 启动日志）

---

### T-GAP-03 — Python 后端测试未运行

| 字段 | 内容 |
|------|------|
| 严重度 | P2 |
| 状态 | unverified |
| 可写范围 | — |

**问题描述**（`observed`）：

- Subagent A 已创建 `tests/emulator/test_emulator_manager.py`（18 用例）、`tests/emulator/test_provider_fallback_contract.py`（17 用例）、`tests/api/test_emulator_api.py`（23 用例），共 58 用例
- Subagent C 未申请 Python 提权，未运行这些测试
- A 的产出记录 58 passed（`observed` from A 的报告），但 C 未独立验证

**影响**（`inferred`）：

- 后端测试结果依赖 A 的报告，未经 C 独立验证
- 若需交叉验证，需申请 Python 提权后运行 `pytest tests/emulator/ tests/api/test_emulator_api.py`

**处置**：记录为 barrier，不阻塞交付

---

### T-GAP-04 — Emulator 专区组件挂载测试无法执行

| 字段 | 内容 |
|------|------|
| 严重度 | P2 |
| 状态 | observed |
| 可写范围 | ❌（B 尚未实装前端重构） |

**问题描述**（`observed`）：

- 当前 `Emulator.vue`（1540 行）是 B 的重构目标，尚未释放
- Subagent C 的测试全部基于 fake/契约骨架，未挂载实际组件
- B 实装后需将 fake 测试迁移为 composable/组件挂载测试

**影响**（`inferred`）：

- 当前测试验证的是契约形状和逻辑正确性，未验证实际 UI 渲染
- B 实装后可能发现 fake 与实际实现的偏差

**处置**：全部用 fake/契约骨架替代；B 实装后迁移

---

## 9. 前端缺陷（当前 Emulator.vue，B 重构前）

以下缺陷来自 Subagent B 的前端只读研究（`FUNCTION_MATRIX.md` 前端部分），Subagent C 在测试设计中确认并标注：

### T-GAP-05 — 操作假成功（Q1，P0）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue:504,534,564` |
| 严重度 | P0 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：`startEmulator`/`stopEmulator`/`showEmulator` 在 `code===200` 后立即 `message.success`，但后端返回的是 `accepted`（操作已接受，未完成）。后端 A 已修复假成功（返回 operation-id + WS 通知），但前端当前未订阅 WS，仍假成功。

**测试覆盖**：FE-CONTRACT-10 验证 operate 状态变迁（fake 层）；GM-006 手测卡验证实机假成功行为。

---

### T-GAP-06 — WS 未订阅（Q2，P0）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue` |
| 严重度 | P0 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：前端未订阅 `emulator.notice` WS 消息，操作完成/失败无反馈。后端 A 已实现 WS 推送（`B-OP-02`），但前端当前不消费。

**测试覆盖**：BE-CONTRACT-02 验证 plugin provider 契约；GM-006 手测卡验证 WS 消息到达前端。

---

### T-GAP-07 — 轮询无 visibility 暂停（Q5，P2）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue:87-129` |
| 严重度 | P2 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：页面隐藏（最小化/切换 Tab）时轮询继续，浪费资源。

**测试覆盖**：FE-POLL-01~06 验证轮询生命周期；GM-011 手测卡验证 background 模式轮询行为。

---

### T-GAP-08 — 老板键录制缺陷（Q7a/Q7b/Q7c/Q7f，P1~P2）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue:619-698` |
| 严重度 | P1~P2 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：
- Q7a：Esc 被录入为按键，而非取消录制
- Q7b：窗口失焦时录制状态残留
- Q7c：IME 输入可能被录入
- Q7f：纯修饰键（如只按 Ctrl）可保存

**测试覆盖**：FE-BOSS-01~03 验证正常录制；FE-BOSS-MUMU 验证 MuMu 隐藏；GM-009 手测卡验证 Esc/失焦/IME/纯修饰键行为。

---

### T-GAP-09 — 保存无 epoch 防竞态（Q6，P1）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue:324-366` |
| 严重度 | P1 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：`handleSaveChange` 无 per-uuid epoch 守卫，快速连续保存可能乱序覆盖。

**测试覆盖**：FE-CONTRACT-07 验证并发 update 串行化（fake 层）；GM-001 手测卡验证快速编辑保存。

---

### T-GAP-10 — 搜索无去重标记（Q9a，P2）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue:427-459` |
| 严重度 | P2 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：前端搜索结果无去重标记，可重复导入同一条目。后端按 path 去重（`observed` `app/utils/emulator/tools.py`），但前端不标记。

**测试覆盖**：FE-CONTRACT-05 验证搜索去重（fake 层）；GM-002 手测卡验证重复导入行为。

---

## 10. 可访问性缺陷

### T-GAP-11 — 图标按钮无 aria-label（A11Y-03，P3）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue` |
| 严重度 | P3 |
| 状态 | inferred (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：`FolderOpenOutlined` / `PlayCircleOutlined` / `EyeOutlined` 等图标按钮未设 `aria-label`，屏幕阅读器无法识别。

**测试覆盖**：A11Y-03 审计清单；GM-012 手测卡验证键盘操作和屏幕阅读器。

---

### T-GAP-12 — 未用 v6 FocusRing（F-RSP-06，P3）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue` |
| 严重度 | P3 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：未使用 v6 `FocusRing` / `--v6-focus-ring`，焦点环依赖 Ant Design 原生 outline。

**测试覆盖**：A11Y-01 审计清单；GM-012 手测卡验证焦点环可见性。

---

## 11. 性能缺陷

### T-GAP-13 — 轮询串行阻塞（Q3，P1）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue:87-129` |
| 严重度 | P1 |
| 状态 | observed (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：`pollDevicesStatus` 串行 for 循环遍历模拟器，N 个模拟器时轮询延迟累积。

**测试覆盖**：FE-POLL-01~06 验证轮询生命周期；PERF-02 提议批量 `status(null)` 一次。

---

### T-GAP-14 — 模板内对象重复创建（PERF-04，P3）

| 字段 | 内容 |
|------|------|
| 文件 | `frontend/src/views/Emulator.vue` |
| 严重度 | P3 |
| 状态 | inferred (当前缺陷) / proposed (B 重构后修复) |

**问题描述**：`a-table` columns 每次渲染重建，未提取为常量。

**测试覆盖**：PERF-04 审计表；proposed 提取常量。

---

## 12. 修复优先级汇总（测试与可用性）

| ID | 文件:行 | 严重度 | 可写范围内 | 状态 | 备注 |
|----|---------|--------|-----------|------|------|
| T-GAP-01 | `vite.config.ts:11` | P2 | ❌ | 待修复 | `replaceAll` 类型错误，超出 C 可写范围 |
| T-GAP-02 | — | P3 | — | unverified | 需执行 `yarn build` 获取 chunk 大小 |
| T-GAP-03 | — | P2 | — | unverified | 需申请 Python 提权运行后端测试 |
| T-GAP-04 | — | P2 | ❌ | 待 B 实装 | 组件挂载测试需 B 释放重构 |
| T-GAP-05 | `Emulator.vue:504,534,564` | P0 | ❌ | 待 B 修复 | 操作假成功（Q1） |
| T-GAP-06 | `Emulator.vue` | P0 | ❌ | 待 B 修复 | WS 未订阅（Q2） |
| T-GAP-07 | `Emulator.vue:87-129` | P2 | ❌ | 待 B 修复 | 轮询无 visibility 暂停（Q5） |
| T-GAP-08 | `Emulator.vue:619-698` | P1~P2 | ❌ | 待 B 修复 | 老板键录制缺陷（Q7a/b/c/f） |
| T-GAP-09 | `Emulator.vue:324-366` | P1 | ❌ | 待 B 修复 | 保存无 epoch 防竞态（Q6） |
| T-GAP-10 | `Emulator.vue:427-459` | P2 | ❌ | 待 B 修复 | 搜索无去重标记（Q9a） |
| T-GAP-11 | `Emulator.vue` | P3 | ❌ | 待 B 修复 | 图标按钮无 aria-label（A11Y-03） |
| T-GAP-12 | `Emulator.vue` | P3 | ❌ | 待 B 修复 | 未用 v6 FocusRing（F-RSP-06） |
| T-GAP-13 | `Emulator.vue:87-129` | P1 | ❌ | 待 B 修复 | 轮询串行阻塞（Q3） |
| T-GAP-14 | `Emulator.vue` | P3 | ❌ | 待 B 修复 | 模板内对象重复创建（PERF-04） |

> 上述 T-GAP-05 ~ T-GAP-14 均为当前 `Emulator.vue` 的已知缺陷，Subagent B 的前端重构预计会修复。
> Subagent C 已通过 fake/契约测试和手测卡覆盖这些缺陷的验证路径，B 实装后可迁移为组件挂载测试。

---

> 测试与可用性部分完毕。所有结论均带标注（`observed`/`inferred`/`proposed`/`unverified`）与证据路径。
