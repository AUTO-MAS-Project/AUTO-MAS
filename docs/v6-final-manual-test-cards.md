# v6 最终收口 — 8 张关键手测卡

> 工作树：`AUTO-MAS-workspace/worktrees/all-plugins-integration`（分支 `integration/dev-v2-dev-all-plugins`）
> 生成时间：2026-07-23 (Asia/Shanghai)
> 状态：全部 `blocked`，需用户在真实 Windows + Electron 环境中执行后回填
>
> 标注规则：
> - `observed` = 代码静态阅读确认的行为
> - `inferred` = 基于代码推断但未实机验证
> - `unverified` = **必须用户手测回填**，未回填前不得标 pass
>
> 执行优先级：MC-001/002/018/039/043 为 P0（Beta 前必须）；MC-028/031/050 为 P1。

---

## 通用前置条件

| 编号 | 条件 | 说明 |
|------|------|------|
| PRE-01 | Windows 10/11 x64 | 生产目标平台 |
| PRE-02 | AUTO-MAS Electron 应用已构建 | 使用 `dist-integration-r12/win-unpacked` 或签名安装包 |
| PRE-03 | 后端固定端口 36163 可用 | 当前版本不会协商备用端口；先退出 r6/其他 AUTO-MAS。端口被其他安装占用时，新实例必须安全拒绝启动，且不得终止占用者 |
| PRE-04 | DevTools 可用 | `Ctrl+Shift+I` 打开，用于检查 console / network / WS |
| PRE-05 | 后端日志可访问 | 终端窗口或 `logs/` 目录下的日志文件 |
| PRE-06 | r6 full 包已解压（用于升级测试） | r6 冻结产物路径 |

---

## MC-001 — 双击冷启动到主界面

**门禁**：G1（首次启动）
**优先级**：P0

### 前置条件
- AUTO-MAS 未运行（任务管理器确认无 `AUTO-MAS.exe` 进程）
- 已构建的 win-unpacked 目录或已安装版本

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 在可写的新目录中双击 `AUTO-MAS.exe` | 普通用户直接启动，不应在冷启动时强制弹出 UAC | `unverified` |
| 2 | 检查任务管理器中的 AUTO-MAS 实例 | 只有一个普通权限 Electron 实例；需要管理员能力时才由具体操作触发按需 UAC | `unverified` |
| 3 | 等待后端就绪 | overlay 消失，主界面可见 | `unverified` |
| 4 | 记录从双击到主界面完全加载的时间 | 应 ≤ 10 秒 | `unverified` |
| 5 | 检查主界面无白屏/崩溃/错误弹窗 | UI 正常渲染，所有导航可见 | `unverified` |

### 端口占用与 r6 隔离子用例

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 退出 A 测版，启动冻结 r6，并记录其 PID 与窗口状态 | r6 正常占用 36163 | `unverified` |
| 2 | 保持 r6 运行，再双击 A 测版 | A 测版明确提示端口/其他实例占用并安全拒绝启动，不自动扫描备用端口 | `unverified` |
| 3 | 核对 r6 PID、窗口与功能 | r6 仍是原进程且未被终止、重启或修改 | `unverified` |
| 4 | 正常退出 r6 后再次启动 A 测版 | A 测版恢复正常冷启动 | `unverified` |

### 期望结果
- 主界面在 10 秒内加载完成
- 冷启动不强制提权；按需提权不会制造第二个失控实例
- 无白屏、崩溃或未捕获错误弹窗
- `BackendStartupOverlay` 在后端就绪后正确消失

### 需回传证据
- [ ] 主界面截图（含时间戳）
- [ ] 启动时间（秒）：____
- [ ] 事件日志（`logs/` 目录或终端输出）
- [ ] DevTools Console 截图（无红色错误）

### 关联源码
- `frontend/electron/main.ts`
- `frontend/src/composables/useAppLifecycle.ts`

---

## MC-002 — 冷启动后 health ready=true

**门禁**：G3（健康检查）
**优先级**：P0

### 前置条件
- MC-001 已通过，AUTO-MAS 正在运行
- 后端端口可访问（默认 36163）

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 启动 AUTO-MAS 后等待 10 秒 | 后端完成初始化 | `unverified` |
| 2 | 浏览器访问 `http://127.0.0.1:36163/api/core/health` | 返回 JSON 响应 | `unverified` |
| 3 | 检查 `ready` 字段 | `"ready": true` | `unverified` |
| 4 | 检查其他字段（如 `version`、`mode`） | 返回有效版本号和当前配置模式 | `unverified` |
| 5 | 检查前端 DevTools Network | 前端只访问固定的 36163；ready 后停止 health 轮询，不尝试其他端口 | `unverified` |

### 期望结果
- `{"ready": true, "version": "...", ...}`
- 前端在收到 `ready=true` 后停止 health 轮询

### 需回传证据
- [ ] health 响应 JSON 完整文本
- [ ] 后端日志（含初始化完成日志行）
- [ ] DevTools Network 截图（health 轮询请求序列）

### 关联源码
- `app/api/core.py`（health 端点）
- `frontend/src/composables/useAppLifecycle.ts`（health 轮询）

---

## MC-018 — POST /api/core/close 优雅退出

**门禁**：G9（优雅退出）
**优先级**：P0

### 前置条件
- AUTO-MAS 运行中，已通过 MC-002
- 拥有有效的 owner_token（通过前端启动获取）

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 通过 DevTools 或脚本获取当前 owner_token | token 字符串 | `unverified` |
| 2 | 发送 `POST http://127.0.0.1:36163/api/core/close`（带 token） | 返回成功响应 | `unverified` |
| 3 | 观察后端日志 | 输出关闭序列日志：config flush → WS shutdown → service cleanup | `unverified` |
| 4 | 确认进程退出 | 任务管理器中 `AUTO-MAS.exe` 和子进程消失 | `unverified` |
| 5 | 检查退出码 | `exit code = 0` | `unverified` |
| 6 | 检查无残留进程 | 无孤儿 Python/Node 进程 | `unverified` |

### 期望结果
- 后端完成 config flush 和 WS 清理后退出
- exit code = 0
- 无残留进程

### 需回传证据
- [ ] 后端日志尾部（含关闭序列）
- [ ] 任务管理器截图（退出前后对比）
- [ ] 退出码：____
- [ ] 关闭请求的 HTTP 响应

### 关联源码
- `app/api/core.py`（close 端点）
- `app/core/config_service.py`（shutdown 序列）
- `main.py`（shutdown 钩子）

---

## MC-028 — WS 429 过载保护

**门禁**：G4（WS 背压）
**优先级**：P1

### 前置条件
- AUTO-MAS 运行中，WS 连接已建立
- DevTools Console 可用

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 打开 DevTools Console | 可执行 JS | `unverified` |
| 2 | 通过 WS 发送高频消息（100+ msg/s） | 模拟过载场景 | `unverified` |
| 3 | 观察后端是否返回 429 或触发背压 | 后端限流，返回 429 或关闭连接 | `unverified` |
| 4 | 检查前端是否显示过载提示 | UI 显示过载/限流提示，不崩溃 | `unverified` |
| 5 | 停止高频发送后 | WS 自动恢复或提示手动重连 | `unverified` |
| 6 | 检查后端日志中的背压记录 | 日志记录 429/背压事件 | `unverified` |

### WS 背压参数（`observed`）
- 单连接缓冲上限：4 MiB
- 单连接消息队列上限：64 条
- 背压检测周期：5 秒

### 期望结果
- 高频消息下后端正确限流
- 前端不卡顿或崩溃，显示过载提示
- 停止后恢复正常

### 需回传证据
- [ ] 前端帧率（FPS）数据
- [ ] 后端日志（含 429/背压记录）
- [ ] DevTools Console 截图（过载提示）
- [ ] WS 消息统计（发送/接收/丢弃数量）

### 关联源码
- `app/core/ws/manager.py`（背压逻辑）
- `app/core/ws/security.py`（限流）
- `frontend/src/composables/useWebSocket.ts`（重连逻辑）

---

## MC-031 — pluginFrontendLoader 8s 超时

**门禁**：G5（插件加载）
**优先级**：P1

### 前置条件
- AUTO-MAS 运行中
- 有一个可加载的测试插件

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 准备一个不注册 customElement 的插件入口脚本 | 插件 manifest 有效但入口不调用 `customElements.define` | `unverified` |
| 2 | 安装该插件并进入其页面 | 前端开始加载插件 | `unverified` |
| 3 | 等待 8 秒 | 超时计时器触发 | `unverified` |
| 4 | 检查错误提示 | 显示"custom element 未注册"或类似超时错误 | `unverified` |
| 5 | 检查 DevTools Console | 有超时日志，无未捕获异常 | `unverified` |
| 6 | 导航离开再返回 | 错误状态清除，重新尝试加载 | `unverified` |

### 期望结果
- 8s 后显示明确的超时错误提示
- 不影响其他插件或主界面功能
- 导航离开后正确清理

### 需回传证据
- [ ] 超时错误提示截图
- [ ] DevTools Console 日志（含超时时间戳）
- [ ] 插件 manifest 文件

### 关联源码
- `frontend/src/composables/usePluginLoader.ts`（8s 超时）
- `frontend/src/components/PluginElementHost.vue`（插件宿主）

---

## MC-039 — 背景图安全 URL 校验

**门禁**：P0-SEC-02（安全 URL 校验）
**优先级**：P0

### 前置条件
- AUTO-MAS 运行中
- 安装一个测试插件，可配置背景图

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 在插件配置中设置背景图为 `javascript:alert(1)` | 被 `resolveSafeBackgroundUrl` 拒绝，fallback 到 default | `unverified` |
| 2 | 设置背景图为 `//evil.com/x.png` | 被拒绝（协议相对 URL） | `unverified` |
| 3 | 设置背景图为 `data:text/html,<script>alert(1)</script>` | 被拒绝（data URI） | `unverified` |
| 4 | 设置背景图为含凭证的 URL `https://user:pass@example.com/x.png` | 被拒绝或剥离凭证 | `unverified` |
| 5 | 检查 iframe sandbox | `sandbox` 属性阻止 `parent.document` 访问 | `unverified` |
| 6 | 在 Console 中尝试 `parent.document.location` | 抛出 SecurityError | `unverified` |
| 7 | 设置背景图为合法 HTTPS URL | 正常加载显示 | `unverified` |

### 期望结果
- 所有危险 URL 被 `resolveSafeBackgroundUrl` 拒绝
- iframe sandbox 阻止 parent 访问
- 合法 URL 正常工作

### 需回传证据
- [ ] 每种危险 URL 的 Console 截图（被拒绝日志）
- [ ] iframe sandbox 属性截图
- [ ] SecurityError 截图
- [ ] 合法 URL 正常加载截图

### 关联源码
- `frontend/src/utils/safeUrl.ts`（`resolveSafeBackgroundUrl`）
- `frontend/src/components/PluginElementHost.vue`（iframe sandbox）

---

## MC-043 — 100/125/150% Windows 缩放渲染

**门禁**：G8（DPI 缩放）
**优先级**：P0

### 前置条件
- Windows 显示设置可调
- AUTO-MAS 已构建

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 设置 Windows 缩放为 100% | 桌面右键 → 显示设置 → 缩放 → 100% | `unverified` |
| 2 | 启动 AUTO-MAS，截图 | UI 元素正确渲染，无溢出/裁剪 | `unverified` |
| 3 | 改为 125%，重新启动 AUTO-MAS，截图 | UI 正确缩放 | `unverified` |
| 4 | 改为 150%，重新启动 AUTO-MAS，截图 | UI 正确缩放 | `unverified` |
| 5 | 检查导航栏、按钮、文字 | 三种缩放下均清晰可读 | `unverified` |
| 6 | 检查插件 iframe 内容缩放 | 插件内容与主 UI 缩放一致 | `unverified` |
| 7 | 检查模态框/弹窗位置 | 居中显示，不超出窗口边界 | `unverified` |

### 期望结果
- UI 在 100/125/150% 三种缩放下均正确渲染
- 无元素溢出、裁剪或错位
- 文字清晰可读

### 需回传证据
- [ ] 100% 缩放截图
- [ ] 125% 缩放截图
- [ ] 150% 缩放截图
- [ ] 每种缩放下的 DevTools Console（无布局错误）

### 关联源码
- `frontend/src/styles/`（响应式样式）
- `frontend/electron/main.ts`（DPI 感知设置）

---

## MC-050 — 真实 Authenticode 签名验证

**门禁**：P0-REL-03（签名验证）
**优先级**：P1（需先触发 SignPath 签名）

### 前置条件
- 已通过 SignPath CI workflow_dispatch 触发签名
- 签名后的 `AUTO-MAS.exe` 可用

### 精确步骤

| 步骤 | 操作 | 期望结果 | 标注 |
|------|------|----------|------|
| 1 | 获取签名后的 `AUTO-MAS.exe` | 文件来自 SignPath 签名产物 | `unverified` |
| 2 | 打开 PowerShell，运行 `Get-AuthenticodeSignature .\AUTO-MAS.exe` | 返回签名信息 | `unverified` |
| 3 | 检查 `Status` 字段 | `Valid` | `unverified` |
| 4 | 检查 `SignerCertificate.Subject` | 包含签发者名称 | `unverified` |
| 5 | 检查 `SignerCertificate.Thumbprint` | 非空 | `unverified` |
| 6 | 双击运行签名后的 `AUTO-MAS.exe` | Windows SmartScreen 不拦截（或显示已验证发布者） | `unverified` |
| 7 | 检查安装包签名（若有 .exe installer） | installer 同样具有有效签名 | `unverified` |

### 期望结果
- `Status = Valid`
- `Subject` 包含签发者名称
- `Thumbprint` 非空
- SmartScreen 不拦截或显示已验证发布者

### 需回传证据
- [ ] `Get-AuthenticodeSignature` 完整 PowerShell 输出
- [ ] 签名后的 exe 文件 SHA-256
- [ ] SignPath CI 构建日志链接
- [ ] 运行时 SmartScreen 截图（若有）

### 关联源码
- `.github/workflows/signpath.yml`（SignPath 签名工作流）
- `electron-builder.yml`（签名配置）

---

## 执行记录模板

执行完每张卡后，将结果填入下表：

| 卡片 ID | 执行日期 | 执行人 | 结果 (pass/fail) | 实测备注 |
|---------|----------|--------|------------------|----------|
| MC-001 | | | | |
| MC-002 | | | | |
| MC-018 | | | | |
| MC-028 | | | | |
| MC-031 | | | | |
| MC-039 | | | | |
| MC-043 | | | | |
| MC-050 | | | | |

> 全部 8 张卡回填 `pass` 后，方可将 GO/NO-GO 复评中"真实设备手测"硬阻断标记为已解除。
