# Windows 手测卡 — 游戏/模拟器管理（GM-001 ~ GM-014）

> Subagent C 维护。这些测试卡需由用户在真实 Windows + Electron 环境中亲自执行。
> 工作树：`AUTO-MAS-workspace/worktrees/all-plugins-integration` @ `integration/dev-v2-dev-all-plugins` (HEAD `b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e`)
> 生成时间：2026-07-23 (Asia/Shanghai)
>
> 标注规则：
> - `observed` = 代码静态阅读确认的行为
> - `inferred` = 基于代码推断但未实机验证
> - `proposed` = 提议的重构后预期行为（B 实装后验证）
> - `unverified` = **必须用户手测回填**，未回填前不得标 pass
>
> 所有涉及真实模拟器进程、ADB 连接、窗口操作、硬件渲染的步骤均标 `unverified`。
> 用户执行后将结果填入「实测结果」栏，并附截图/日志路径。

---

## 通用前置条件

| 编号 | 条件 | 说明 |
|------|------|------|
| PRE-01 | Windows 10/11 x64 | 生产目标平台 |
| PRE-02 | AUTO-MAS Electron 应用已启动 | 后端服务正常运行，前端可访问 `/emulators` 路由 |
| PRE-03 | 至少一个已安装模拟器 | MuMu / LDPlayer / BlueStacks / Nox 之一；若无，GM-001 可在零模拟器下执行 |
| PRE-04 | DevTools 可用 | `Ctrl+Shift+I` 打开，用于检查 console / network / WS |
| PRE-05 | 后端日志可访问 | 终端窗口或日志文件，用于交叉验证前端行为 |

---

## GM-001 — 无模拟器空态与手动添加

**目标**：验证空列表时的空态展示和手动新增模拟器流程。

### 前置条件
- 已安装 AUTO-MAS 但未配置任何模拟器（或已删除全部模拟器配置）
- 后端运行正常

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 导航到 `/emulators` 页面 | 显示空态：大按钮「添加模拟器」或空态提示文案 | `unverified` |
| 2 | 检查空态组件 | 当前实现用 `a-empty`（`observed` Emulator.vue:823-839）；v6 重构后应使用 `EmptyState` | `observed` (当前) / `proposed` (重构后) |
| 3 | 点击「添加模拟器」按钮 | 新增一个 Tab，默认名称「未命名」，类型 `general`，路径为空 | `unverified` |
| 4 | 检查 Tab 是否自动激活 | 新 Tab 应自动选中，右侧显示配置表单 | `unverified` |
| 5 | 输入名称「测试模拟器」，按 Tab/失焦 | 触发 `@blur` 保存（`observed` Emulator.vue:882-893） | `unverified` |
| 6 | 打开 DevTools Network 面板 | 应看到 `POST /emulator/add` 和 `POST /emulator/update` 请求 | `unverified` |
| 7 | 刷新页面（F5） | 新增的模拟器配置应持久化，Tab 和名称仍在 | `unverified` |

### 期望结果
- 空态正确展示，无 JS 报错
- 新增后 Tab 自动激活
- 保存后刷新数据持久

### 需回传证据
- [ ] 空态截图
- [ ] 新增后截图（含 Tab 和配置表单）
- [ ] DevTools Network 截图（add + update 请求）
- [ ] 刷新后截图

### 安全退出
- 删除测试创建的模拟器配置（Tab 右键 → 删除 → popconfirm 确认）
- 若无法删除，通过 DevTools Console 手动调用 `POST /emulator/delete`

---

## GM-002 — 自动搜索、去重与导入

**目标**：验证自动搜索已安装模拟器、结果去重和从搜索结果导入的流程。

### 前置条件
- 系统已安装至少一个模拟器（MuMu / LDPlayer / BlueStacks / Nox）
- GM-001 已完成或已有至少一个模拟器配置

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 点击「搜索已安装」按钮 | 弹出搜索模态框，显示 loading 状态 | `unverified` |
| 2 | 等待搜索完成 | 显示搜索结果列表，含 type/path/name 三列 | `unverified` |
| 3 | 检查去重 | 后端按 path 大小写不敏感去重（`observed` `app/utils/emulator/tools.py`）；前端当前**无去重标记**（`observed` Q9a） | `observed` (后端) / `unverified` (前端展示) |
| 4 | 点击一条结果的「导入」按钮 | 调用 `add` + `update`，新 Tab 出现并自动激活 | `unverified` |
| 5 | 再次打开搜索，导入同一条结果 | 当前行为：可重复导入，产生重复 uid（`observed` Q9a）；v6 重构后应标记「已导入」并禁用 | `observed` (当前) / `proposed` (重构后) |
| 6 | 检查导入后路径字段 | 路径应自动填充搜索结果的 path | `unverified` |
| 7 | 检查导入后类型字段 | 类型应自动填充搜索结果的 type | `unverified` |

### 期望结果
- 搜索结果正确列出已安装模拟器
- 导入后配置完整（name/type/path）
- 重复导入行为符合预期（当前可重复，v6 后应禁止）

### 需回传证据
- [ ] 搜索结果截图
- [ ] 导入后配置截图
- [ ] 重复导入行为截图
- [ ] DevTools Network 截图（search + add + update）

### 安全退出
- 删除通过搜索导入的全部测试模拟器配置

---

## GM-003 — 无效/被后端纠正的路径

**目标**：验证输入无效路径时后端纠正行为和前端提示。

### 前置条件
- 已有至少一个模拟器配置
- 后端运行正常

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 选中一个模拟器 Tab，清空路径字段 | 路径为空 | `unverified` |
| 2 | 输入不存在的路径 `C:/fake/nonexistent.exe`，失焦 | 触发保存 | `unverified` |
| 3 | 检查后端响应 | 后端 `emulator_manager.py:129-132` 校验 Path 不存在 → `FileNotFoundError` → HTTP 400（`observed`） | `observed` (后端) |
| 4 | 检查前端行为 | 当前实现：`message.error` 提示（`observed`）；v6 重构后应显示 `ErrorState` | `observed` (当前) / `proposed` (重构后) |
| 5 | 输入会被后端纠正的路径（如大小写不一致、尾部多余斜杠） | 后端可能返回纠正后的路径，前端应显示 `->` 提示（`observed` Emulator.vue:606-609） | `unverified` |
| 6 | 检查路径纠正提示文案 | 应包含 `->` 符号表示纠正 | `unverified` |
| 7 | 在 DevTools Console 检查是否有路径相关的 warning | 不应有未捕获异常 | `unverified` |

### 期望结果
- 无效路径被后端拒绝，前端有错误提示
- 后端纠正路径时前端显示纠正提示
- 无未捕获异常

### 需回传证据
- [ ] 无效路径报错截图
- [ ] 路径纠正提示截图（如能复现）
- [ ] DevTools Console 截图
- [ ] 后端日志相关行

### 安全退出
- 将路径恢复为有效值或删除测试配置

---

## GM-004 — 单实例启动、状态变迁、显示、关闭

**目标**：验证单实例模拟器的完整操作生命周期：启动 → 显示 → 关闭。

### 前置条件
- 已配置一个有效的模拟器（路径指向真实可执行文件）
- 模拟器当前未运行（OFFLINE 状态）
- `unverified` — 需真实模拟器环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 选中模拟器 Tab，查看设备列表 | 设备状态显示 OFFLINE，启动按钮可用 | `unverified` |
| 2 | 点击「启动」按钮 | 触发 `POST /emulator/operate` (operate=open) | `unverified` |
| 3 | 检查后端响应 | 后端返回 `accepted=true` + `operationId`（`observed` B-OP-01，A 已修复假成功） | `observed` (后端) / `unverified` (前端消费) |
| 4 | 检查前端行为 | 当前实现：`message.success` 假成功（`observed` Q1）；v6 重构后应显示 pendingWs 状态 | `observed` (当前) / `proposed` (重构后) |
| 5 | 等待模拟器进程实际启动 | 设备状态应从 OFFLINE → STARTING → ONLINE | `unverified` |
| 6 | 检查轮询是否反映状态变迁 | 5s 轮询周期内状态应更新（`observed` POLLING_INTERVAL=5000） | `unverified` |
| 7 | 状态为 ONLINE 后，点击「显示」按钮 | 触发 `operate=show`，模拟器窗口应前置 | `unverified` |
| 8 | 点击「关闭」按钮 | 触发 `operate=close` | `unverified` |
| 9 | 等待模拟器进程关闭 | 设备状态应从 ONLINE → CLOSING → OFFLINE | `unverified` |
| 10 | 检查 ADB 地址字段 | ONLINE 时显示 `127.0.0.1:xxxx`，OFFLINE 时清空（`observed` FE-CONTRACT-10） | `unverified` |

### 期望结果
- 完整生命周期：OFFLINE → STARTING → ONLINE → CLOSING → OFFLINE
- ADB 地址随状态正确变化
- 操作不假成功（v6 重构后）

### 需回传证据
- [ ] 每个状态截图（OFFLINE / STARTING / ONLINE / CLOSING）
- [ ] ADB 地址字段截图（ONLINE 和 OFFLINE）
- [ ] DevTools Network 截图（operate 请求）
- [ ] WS 消息截图（如有 `emulator.notice` 推送）
- [ ] 后端日志相关行

### 安全退出
- 确保模拟器进程已完全关闭
- 若模拟器卡在 STARTING/CLOSING，通过任务管理器结束进程

---

## GM-005 — 多开 index 与 ADB 地址

**目标**：验证多开实例（multi-instance）的 index 编号和 ADB 地址分配。

### 前置条件
- 已配置一个支持多开的模拟器（如 MuMu / LDPlayer）
- 模拟器支持 `-multi` 或等效多开参数
- `unverified` — 需真实多开环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 查看设备列表 | 应显示多个 index（0, 1, 2...），每个有独立状态 | `unverified` |
| 2 | 检查 ADB 地址分配 | 每个 index 应有不同 ADB 端口（如 `127.0.0.1:7555`, `127.0.0.1:7557`...） | `unverified` |
| 3 | 启动 index=0 的实例 | 仅 index=0 状态变为 ONLINE，其他不变 | `unverified` |
| 4 | 启动 index=1 的实例 | index=1 也变为 ONLINE，ADB 地址不同 | `unverified` |
| 5 | 检查 per-device in-flight | 快速连点同一 index 的启动按钮，不应重复请求（`observed` F-OP-04，Set<string> key=`${uuid}-${index}`） | `observed` (代码) / `unverified` (实机) |
| 6 | 关闭 index=0 | 仅 index=0 变为 OFFLINE，index=1 不受影响 | `unverified` |
| 7 | 检查 ADB 地址清空 | index=0 的 ADB 地址清空，index=1 保持 | `unverified` |

### 期望结果
- 多开 index 独立操作，互不影响
- ADB 地址按 index 分配，不同实例端口不同
- per-device in-flight 防重入有效

### 需回传证据
- [ ] 多开设备列表截图（含 index 和 ADB 地址）
- [ ] 分别启动后的状态截图
- [ ] 关闭一个 index 后的截图（验证互不影响）
- [ ] DevTools Network 截图（per-index operate 请求）

### 安全退出
- 关闭所有已启动的多开实例
- 确保无残留模拟器进程

---

## GM-006 — 操作失败/超时不得假成功

**目标**：验证操作失败或超时时前端不会误报成功。

### 前置条件
- 已配置一个模拟器，路径有效但可人为制造失败
- DevTools 可用
- `unverified` — 需真实环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 将模拟器路径改为指向一个不可执行文件（如 .txt） | 路径存在但非可执行 | `unverified` |
| 2 | 保存配置 | 后端可能接受路径（文件存在），但启动时会失败 | `unverified` |
| 3 | 点击「启动」 | 后端返回 `accepted=true` + operationId（`observed` B-OP-01） | `observed` (后端) / `unverified` (前端) |
| 4 | 等待后台操作完成 | 后端 `_run_operate` 失败 → WS `emulator.notice` `{level=error, operationId, message}`（`observed` B-OP-02/B-OP-04） | `observed` (后端) / `unverified` (WS 到达前端) |
| 5 | 检查前端行为 | 当前实现：未订阅 WS，无反馈（`observed` Q2）；v6 重构后应显示 WS error toast | `observed` (当前) / `proposed` (重构后) |
| 6 | 检查设备状态 | 应为 ERROR 或保持 OFFLINE，不应变为 ONLINE | `unverified` |
| 7 | 制造超时场景：设置 `MaxWaitTime` 为极小值（如 1 秒） | 启动应超时 | `unverified` |
| 8 | 点击「启动」并等待 | 超时后状态应为 ERROR 或 STARTING（卡住） | `unverified` |
| 9 | 检查前端是否假成功 | 当前实现：`message.success` 假成功（`observed` Q1）；**这是 P0 缺陷** | `observed` (当前缺陷) |

### 期望结果
- 操作失败时前端不得显示 `message.success`
- WS error 消息应到达前端并显示（v6 重构后）
- 设备状态不假变为 ONLINE

### 需回传证据
- [ ] 操作失败时前端截图（验证是否假成功）
- [ ] DevTools WS 消息截图（emulator.notice level=error）
- [ ] 后端日志（_run_operate 失败记录）
- [ ] 超时场景截图

### 安全退出
- 将路径恢复为有效值
- 若模拟器进程卡住，通过任务管理器结束

---

## GM-007 — 后端离线、重连、刷新

**目标**：验证后端服务不可用时的前端行为和重连后恢复。

### 前置条件
- 已有模拟器配置
- 可手动停止/启动后端服务
- `unverified` — 需真实环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 在 `/emulators` 页面正常加载 | 模拟器列表和设备状态正常显示 | `unverified` |
| 2 | 停止后端服务（关闭后端进程或终端） | 后端不可达 | `unverified` |
| 3 | 等待 5s（轮询周期） | 轮询请求应失败 | `unverified` |
| 4 | 检查前端行为 | 当前实现：`message.error`（`observed`）；v6 重构后应显示 `OfflineSkeleton`（`observed` F-STA-04 未实现） | `observed` (当前) / `proposed` (重构后) |
| 5 | 检查轮询是否继续 | 当前实现：轮询继续但每次失败（`observed` Q5 无 visibility 暂停） | `observed` (代码) / `unverified` (实机) |
| 6 | 尝试点击「启动」按钮 | 请求应失败，前端有错误提示 | `unverified` |
| 7 | 重启后端服务 | 后端恢复 | `unverified` |
| 8 | 等待下一轮轮询 | 轮询应成功，设备状态恢复更新 | `unverified` |
| 9 | 手动刷新页面（F5） | 列表和设备状态应正常加载 | `unverified` |
| 10 | 检查是否有残留错误状态 | 重连后不应残留离线错误提示 | `unverified` |

### 期望结果
- 后端离线时前端有明确提示
- 重连后自动恢复，无需手动刷新
- 无残留错误状态

### 需回传证据
- [ ] 后端离线时前端截图
- [ ] DevTools Network 截图（失败的轮询请求）
- [ ] 重连后恢复截图
- [ ] 后端日志（停止/启动记录）

### 安全退出
- 确保后端服务已重启并正常运行

---

## GM-008 — provider 插件启用/禁用/失败 fallback

**目标**：验证 emulator provider 插件启用、禁用和失败时的 host fallback 行为。

### 前置条件
- 了解 AUTO-MAS 插件系统
- 可通过插件管理界面启用/禁用 emulator provider 插件
- `unverified` — 需真实插件环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 确认 emulator provider 插件未安装/未启用 | 后端回退到 `LegacyEmulatorService`（host fallback）（`observed` B-PFB-05） | `observed` (后端) / `unverified` (实机) |
| 2 | 在 `/emulators` 页面操作 | 应通过 host fallback 正常工作 | `unverified` |
| 3 | 检查后端日志 | 应有 host fallback 注册记录 | `unverified` |
| 4 | 安装/启用 emulator provider 插件 | 后端应 drop host fallback，使用 real provider（`observed` B-PFB-01） | `observed` (后端) / `unverified` (实机) |
| 5 | 在 `/emulators` 页面操作 | 应通过 real provider 正常工作 | `unverified` |
| 6 | 检查后端日志 | 应有 provider 切换记录 | `unverified` |
| 7 | 禁用/卸载 emulator provider 插件 | 后端应恢复 host fallback（`observed` B-PFB-02/B-PFB-03） | `observed` (后端) / `unverified` (实机) |
| 8 | 在 `/emulators` 页面操作 | 应恢复通过 host fallback 正常工作 | `unverified` |
| 9 | 模拟 provider 插件异常（如配置损坏） | 后端应 catch 异常并回退（`observed` B-PFB-02 异常路径 drop+restore） | `observed` (后端) / `unverified` (实机) |

### 期望结果
- host fallback 与 real provider 可平滑切换
- 插件异常时自动回退到 host
- 用户无感知（功能不中断）

### 需回传证据
- [ ] 插件禁用时后端日志（host fallback 注册）
- [ ] 插件启用时后端日志（provider 切换）
- [ ] 插件禁用后后端日志（fallback 恢复）
- [ ] 各状态下 `/emulators` 页面截图

### 安全退出
- 恢复插件到初始状态（启用或禁用）
- 确保后端正常运行

---

## GM-009 — 老板键录制与 Esc/失焦

**目标**：验证老板键录制的完整交互，包括 Esc 取消和窗口失焦处理。

### 前置条件
- 已配置一个非 MuMu 类型的模拟器（MuMu 不支持老板键）
- `unverified` — 需真实环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 选中模拟器 Tab，找到老板键输入框 | 应显示录制按钮或可点击的输入框 | `unverified` |
| 2 | 点击「录制」按钮 | 进入录制状态，UI 应有视觉提示 | `unverified` |
| 3 | 按下 Ctrl+Shift+Q | keydown 收集修饰键 + 主键（`observed` FE-BOSS-01） | `observed` (代码) / `unverified` (实机) |
| 4 | 释放按键（keyup） | 提交录制，老板键显示为 `["Ctrl","Shift","Q"]` | `unverified` |
| 5 | 再次点击「录制」，按 Esc | 当前实现：Esc 被录入为按键（`observed` Q7a 缺陷）；v6 重构后应取消录制 | `observed` (当前缺陷) / `proposed` (重构后) |
| 6 | 再次点击「录制」，然后 Alt+Tab 切换窗口 | 当前实现：录制状态残留（`observed` Q7b 缺陷）；v6 重构后应 blur 自动取消 | `observed` (当前缺陷) / `proposed` (重构后) |
| 7 | 再次点击「录制」，只按 Ctrl 然后释放（无主键） | 当前实现：保存 `["Ctrl"]`（`observed` Q7f 缺陷）；v6 重构后应不保存，等待主键 | `observed` (当前缺陷) / `proposed` (重构后) |
| 8 | 切换到中文输入法，点击「录制」并打字 | 当前实现：中文字符可能被录入（`observed` Q7c 缺陷）；v6 重构后应忽略 IME | `observed` (当前缺陷) / `proposed` (重构后) |
| 9 | 检查 MuMu 类型模拟器 | 不应显示老板键输入框，显示「MuMu 不支持」提示（`observed` FE-BOSS-MUMU） | `observed` (代码) / `unverified` (实机) |

### 期望结果
- 正常录制组合键
- Esc 应取消录制（当前缺陷）
- 失焦应自动取消（当前缺陷）
- 纯修饰键不应保存（当前缺陷）
- IME 输入应被忽略（当前缺陷）
- MuMu 不显示老板键输入框

### 需回传证据
- [ ] 正常录制截图
- [ ] Esc 录制行为截图（验证当前缺陷）
- [ ] 失焦行为截图
- [ ] 纯修饰键截图
- [ ] MuMu 不显示老板键截图

### 安全退出
- 清空录制的老板键或恢复为有效值

---

## GM-010 — MuMu 强力关闭风险确认

**目标**：验证 MuMu 模拟器的 `ForceKillOnClose`（强力关闭）功能。

> ⚠️ **此测试仅在用户明确愿意执行时才运行。** 强力关闭会终止 MuMu 相关进程，可能影响其他正在运行的 MuMu 实例。

### 前置条件
- 已配置 MuMu 类型模拟器
- MuMu 模拟器已安装且可运行
- **用户已明确同意执行此测试**
- `unverified` — 需真实 MuMu 环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 选中 MuMu 模拟器 Tab | 配置表单应显示「强力关闭」开关（`observed` FE-BOSS-MUMU，Emulator.vue:999-1012） | `observed` (代码) / `unverified` (实机) |
| 2 | 确认强力关闭开关当前为关闭状态 | 默认应为关闭 | `unverified` |
| 3 | 启动 MuMu 模拟器实例 | 状态变为 ONLINE | `unverified` |
| 4 | 打开「强力关闭」开关 | 保存 `ForceKillOnClose=true` | `unverified` |
| 5 | 点击「关闭」按钮 | 触发 `operate=close` | `unverified` |
| 6 | 检查后端行为 | 后端调用 MuMu close + `_force_kill_mumu_processes`（`observed` B-ADB-04） | `observed` (后端) / `unverified` (实机) |
| 7 | 检查 MuMu 残留进程 | 通过任务管理器检查 `MuMuNxMain.exe` 等进程是否被清理 | `unverified` |
| 8 | 检查 `MUMU_FORCE_KILL_KEYWORDS` 白名单 | 是否覆盖所有残留进程（`observed` UV-03 待验证） | `observed` (待验证) |
| 9 | 关闭「强力关闭」开关 | 保存 `ForceKillOnClose=false` | `unverified` |
| 10 | 再次启动并关闭 MuMu | 仅正常关闭，不强杀进程 | `unverified` |

### 期望结果
- 强力关闭开启时，MuMu 残留进程被清理
- 强力关闭关闭时，仅正常关闭
- 不影响其他非 MuMu 模拟器

### 需回传证据
- [ ] 强力关闭开关截图
- [ ] 任务管理器进程列表（强力关闭前后对比）
- [ ] 后端日志（force-kill 相关记录）
- [ ] `MUMU_FORCE_KILL_KEYWORDS` 覆盖情况记录

### 安全退出
- 关闭所有 MuMu 进程
- 将强力关闭开关恢复为关闭状态
- 通过任务管理器确认无残留 MuMu 进程

---

## GM-011 — 主题/性能/动效模式

**目标**：验证 light/dark 主题、background、low-perf、reduced-motion 模式下的展示。

### 前置条件
- AUTO-MAS 支持主题切换
- 系统支持 prefers-reduced-motion
- `unverified` — 需真实环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 切换到浅色（light）主题 | `/emulators` 页面应使用浅色配色 | `unverified` |
| 2 | 检查组件配色 | 当前实现：局部 CSS 变量并行（`observed` F-RSP-03）；v6 重构后应统一 v6 token | `observed` (当前) / `proposed` (重构后) |
| 3 | 切换到深色（dark）主题 | 页面应使用深色配色 | `unverified` |
| 4 | 检查局部变量是否跟随 | 当前实现：局部变量可能不跟随（`observed` Q12） | `observed` (当前缺陷) / `unverified` (实机) |
| 5 | 最小化窗口或切换到其他应用 | 应用进入 background 模式 | `unverified` |
| 6 | 检查轮询行为 | 当前实现：轮询继续（`observed` Q5 缺陷）；v6 重构后应暂停 | `observed` (当前缺陷) / `proposed` (重构后) |
| 7 | 设置 `perfMode=low`（低性能模式） | 当前实现：无降级（`observed` F-RSP-04 未实现）；v6 重构后应关闭动效/vibrancy | `observed` (当前未实现) / `proposed` (重构后) |
| 8 | 系统设置开启 prefers-reduced-motion | 当前实现：无响应（`observed` F-RSP-05 未实现）；v6 重构后应减弱动效 | `observed` (当前未实现) / `proposed` (重构后) |
| 9 | 检查设备状态标签对比度 | ERROR/NOT_FOUND 应用 error 色但 text 不同（`observed` FE-STATUS-04 色盲可读） | `observed` (代码) / `unverified` (实机对比度) |
| 10 | 检查 a-table 横向溢出 | 代码已设 `scroll: { x: 'max-content' }`（`observed` A11Y-07） | `observed` (代码) / `unverified` (实机) |

### 期望结果
- 浅色/深色主题正确切换
- 低性能模式有降级（v6 重构后）
- 减弱动效有响应（v6 重构后）
- 对比度满足 WCAG AA

### 需回传证据
- [ ] 浅色主题截图
- [ ] 深色主题截图
- [ ] background 模式轮询行为截图
- [ ] 低性能模式截图（如有）
- [ ] reduced-motion 截图（如有）

### 安全退出
- 恢复默认主题和性能模式

---

## GM-012 — 缩放与键盘操作

**目标**：验证不同缩放比例和纯键盘操作下的可用性。

### 前置条件
- AUTO-MAS Electron 窗口可调整大小
- `unverified` — 需真实环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 调整窗口到 960×900 | 页面不应溢出或截断 | `unverified` |
| 2 | 检查 a-table 横向滚动 | 应可横向滚动，不截断列 | `unverified` |
| 3 | 检查 @media 768px 断点 | 当前实现：@media 768px 不适用 Electron（`observed` F-RSP-01） | `observed` (当前缺陷) / `unverified` (实机) |
| 4 | 设置系统缩放为 125% | 页面应自适应 | `unverified` |
| 5 | 检查表格高度 | 当前实现：可能溢出（`observed` Q13 magic 560px） | `observed` (当前缺陷) / `unverified` (实机) |
| 6 | 设置系统缩放为 140% | 页面应自适应 | `unverified` |
| 7 | 检查表格和表单溢出 | 不应溢出或截断 | `unverified` |
| 8 | 纯键盘 Tab 导航 | 所有可交互元素应可 Tab 聚焦 | `unverified` |
| 9 | 检查焦点环可见性 | 当前实现：未用 v6 FocusRing（`observed` F-RSP-06）；但 Ant Design 原生 outline 应可见 | `observed` (当前) / `unverified` (实机) |
| 10 | 检查 Tab 顺序 | 应符合视觉顺序（左到右、上到下） | `unverified` |
| 11 | 用 Enter/Space 激活按钮 | 启动/关闭/显示按钮应可键盘激活 | `unverified` |
| 12 | 检查图标按钮 aria-label | 当前实现：未设 aria-label（`observed` A11Y-03）；屏幕阅读器无法识别 | `observed` (当前缺陷) / `unverified` (实机) |

### 期望结果
- 960×900 / 125% / 140% 下无溢出
- 键盘 Tab 导航覆盖所有可交互元素
- 焦点环可见
- 图标按钮有 aria-label（v6 重构后）

### 需回传证据
- [ ] 960×900 截图
- [ ] 125% 缩放截图
- [ ] 140% 缩放截图
- [ ] 键盘 Tab 焦点截图（含焦点环）
- [ ] 屏幕阅读器读取截图（如有）

### 安全退出
- 恢复默认窗口大小和缩放

---

## GM-013 — 应用退出后无遗留计时器/假状态

**目标**：验证应用退出后无遗留的 setInterval 计时器或假状态残留。

### 前置条件
- AUTO-MAS Electron 应用
- DevTools 可用
- `unverified` — 需真实环境

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 打开 `/emulators` 页面 | 轮询启动（`observed` FE-POLL-01） | `observed` (代码) / `unverified` (实机) |
| 2 | 在 DevTools Console 执行 `setInterval` 计数 | 记录当前计时器数量 | `unverified` |
| 3 | 导航到其他页面（如 `/scripts`） | 轮询应停止（`observed` FE-POLL-06 route watch 启停） | `observed` (代码) / `unverified` (实机) |
| 4 | 检查计时器是否清理 | onUnmounted stopPolling（`observed` FE-POLL-04） | `observed` (代码) / `unverified` (实机) |
| 5 | 导航回 `/emulators` | 轮询应重新启动 | `unverified` |
| 6 | 启动一个模拟器操作（不等待完成） | 操作 in-flight | `unverified` |
| 7 | 立即导航到其他页面 | in-flight 操作不应被中断（后端继续执行） | `unverified` |
| 8 | 检查前端是否清理 in-flight 标记 | onUnmounted 应清理 `startingDevices`/`stoppingDevices`（`observed` F-OP-04） | `observed` (代码) / `unverified` (实机) |
| 9 | 关闭 AUTO-MAS 应用 | 应用应正常退出 | `unverified` |
| 10 | 检查后端日志 | 应有正常关闭记录，无残留计时器报错 | `unverified` |
| 11 | 重新打开应用 | 无假状态残留（如设备状态不应显示 ONLINE 但实际未运行） | `unverified` |

### 期望结果
- 路由切换时计时器正确清理
- 应用退出时无残留计时器
- 重新打开后无假状态

### 需回传证据
- [ ] DevTools Console 计时器计数截图（各步骤）
- [ ] 后端关闭日志
- [ ] 重新打开后状态截图

### 安全退出
- 正常关闭应用
- 确保无残留进程

---

## GM-014 — 脚本联动（emulator id/index）

**目标**：验证 MAA/MaaEnd/SRC/M9A/MaaFW/General/OK Script 选中模拟器后的 id/index 联动。

### 前置条件
- 已配置至少一个模拟器且可启动
- 各脚本类型有可用配置
- `unverified` — 需真实环境和脚本配置

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 在 `/emulators` 页面记录一个模拟器的 uid 和 index | 如 `emu-0001`, index=`0` | `unverified` |
| 2 | 导航到 MAA 脚本编辑页 | 应有模拟器选择器 | `unverified` |
| 3 | 选择模拟器 `emu-0001`，选择 index `0` | 写入 `Emulator.Id=emu-0001`, `Emulator.Index=0`（`observed` LINK-MAA） | `observed` (代码) / `unverified` (实机) |
| 4 | 检查配置文件 | `Emulator.Id` 和 `Emulator.Index` 字段正确 | `unverified` |
| 5 | 导航到 MaaEnd 脚本编辑页 | 应有模拟器选择器（ADB 模式） | `unverified` |
| 6 | 选择模拟器和 index | 写入 `Game.EmulatorId=emu-0001`, `Game.EmulatorIndex=0`（`observed` LINK-MaaEnd） | `observed` (代码) / `unverified` (实机) |
| 7 | 导航到 SRC 脚本编辑页 | 应有模拟器选择器 | `unverified` |
| 8 | 选择模拟器和 index | 写入 `Emulator.Id` / `Emulator.Index`（`observed` LINK-SRC） | `observed` (代码) / `unverified` (实机) |
| 9 | 导航到 M9A 脚本编辑页 | 应有模拟器选择器 | `unverified` |
| 10 | 选择模拟器和 index | 写入 `Emulator.Id` / `Emulator.Index`（`observed` LINK-M9A） | `observed` (代码) / `unverified` (实机) |
| 11 | 导航到 General 脚本编辑页 | 应有模拟器选择器（Type=Emulator） | `unverified` |
| 12 | 选择模拟器和 index | 写入 `Game.EmulatorId` / `Game.EmulatorIndex`（`observed` LINK-General） | `observed` (代码) / `unverified` (实机) |
| 13 | 导航到 MaaFW 脚本编辑页 | 应有模拟器选择器 | `unverified` |
| 14 | 选择模拟器和 index | 前端写入 `Emulator.Id` / `Emulator.Index`（`observed` LINK-MaaFW）；后端走 plugin（`inferred`） | `observed` (前端) / `inferred` (后端) |
| 15 | 导航到 OK Script 脚本编辑页 | 不直接消费 emulator id（`observed` LINK-OkScript，plugin 内部处理） | `observed` (前端无引用) |
| 16 | 运行一个脚本（如 MAA） | 后端应调用 `EmulatorManager.get_emulator_instance(Emulator.Id)` 获取实例（`observed` `app/task/MAA/manager.py`） | `observed` (代码) / `unverified` (实机运行) |
| 17 | 检查后端是否正确启动指定模拟器 | 应启动选中的 index 实例 | `unverified` |
| 18 | 脚本执行完成后 | 后端应调用 `emulator_manager.close(...)` 收尾（`observed` 各 manager.py） | `observed` (代码) / `unverified` (实机) |
| 19 | 删除选中的模拟器配置 | 各脚本编辑页的模拟器选择器应更新（移除已删除项） | `unverified` |
| 20 | 检查脚本配置中的悬空引用 | `Emulator.Id` 可能指向已删除的 uid，运行时应报错或提示 | `unverified` |

### 期望结果
- 各脚本类型正确写入对应字段（`Emulator.Id/Index` 或 `Game.EmulatorId/EmulatorIndex`）
- 后端正确获取实例并启动指定 index
- 脚本完成后正确关闭模拟器
- 删除模拟器后脚本配置无悬空引用（或运行时有明确报错）

### 需回传证据
- [ ] 各脚本编辑页模拟器选择器截图
- [ ] 配置文件截图（验证字段写入）
- [ ] 脚本运行后端日志（get_emulator_instance / close）
- [ ] 删除模拟器后脚本配置截图

### 安全退出
- 恢复脚本配置到测试前状态
- 关闭已启动的模拟器

---

## 汇总清单

| 卡片 | 目标 | 优先级 | 真实设备 | 状态 |
|------|------|--------|----------|------|
| GM-001 | 空态与手动添加 | P2 | 否（可无模拟器） | `unverified` |
| GM-002 | 自动搜索、去重与导入 | P1 | 是（需已安装模拟器） | `unverified` |
| GM-003 | 无效/被后端纠正的路径 | P2 | 否 | `unverified` |
| GM-004 | 单实例启动、状态变迁、显示、关闭 | P0 | 是 | `unverified` |
| GM-005 | 多开 index 与 ADB 地址 | P1 | 是（需多开支持） | `unverified` |
| GM-006 | 操作失败/超时不得假成功 | P0 | 是 | `unverified` |
| GM-007 | 后端离线、重连、刷新 | P1 | 否（需控制后端） | `unverified` |
| GM-008 | provider 插件启用/禁用/失败 fallback | P1 | 是（需插件环境） | `unverified` |
| GM-009 | 老板键录制与 Esc/失焦 | P1 | 否 | `unverified` |
| GM-010 | MuMu 强力关闭风险确认 | P2 | 是（需 MuMu + 用户同意） | `unverified` |
| GM-011 | 主题/性能/动效模式 | P2 | 否 | `unverified` |
| GM-012 | 缩放与键盘操作 | P2 | 否 | `unverified` |
| GM-013 | 应用退出后无遗留计时器/假状态 | P1 | 否 | `unverified` |
| GM-014 | 脚本联动（emulator id/index） | P0 | 是（需脚本环境） | `unverified` |

---

> 本文档完毕。所有真实设备/GUI 项标 `unverified`，需用户手测回填。
> 执行后将结果填入对应步骤的「实测结果」栏，并附截图/日志路径。
