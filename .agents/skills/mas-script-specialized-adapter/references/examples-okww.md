# 案例：ok-script 家族中的 OK-WW / Okww 专项适配

本案例描述当前 `dev` 的 Okww 实现。`ok-script` 是脚本家族，不是单一脚本；OkNte 等子项目必须单独确认启动参数、配置目录和原生 GUI。维护 Okww 或复用 ok-script 架构时，以代码和专项测试为准，不沿用旧版本的表单化配置编辑器方案。

## 架构事实

| 维度 | 当前实现 |
| --- | --- |
| 上游形态 | ok-script 发行物 `ok-ww.exe`，本体提供 GUI |
| 自动运行 | `ok-ww.exe -t N -e` |
| MAS 任务 | `1 = DailyTask`、`7 = MultiAccountDailyTask`；旧值 `2` 自动纠正为 `7` |
| 配置 UI | `ScriptConfig.py` 无参数启动本体 GUI，前端用 WebSocket 遮罩会话控制保存 |
| 配置来源 | `脚本`、`用户`、`直控` 三级；旧值 `简洁`/`详细` 读取时迁移为 `脚本`/`用户` |
| 脚本配置归属 | `脚本`：`data/{scriptId}/Default/ConfigFile`；`用户`：`data/{scriptId}/{userId}/ConfigFile`；`直控`直接读取 Okww 脚本原有 working 配置 |
| 快速配置 | 独立于三态来源；`Info.IfQuickConfig` 开启时，仅用快速配置面板的高频字段覆盖当前脚本配置；关闭时保留来源配置中的完整任务设置 |
| 运行时配置 | 自动代理前备份脚本原有 `working/configs`；按用户来源加载或覆盖；任务成功、失败、取消、异常后恢复原目录 |
| 路径发现 | Electron 只发现 Okww 官方资源与官方启动器；不读取、不保存、不接管 WeGame 侧资源 |
| 游戏控制 | `Game.Enabled` 为总开关：任务前启动或接管，结束、失败和异常时关闭 |
| 判态 | 内置 fatal 日志 + `Window closed exit_event.is_set` 成功标记 |

## 关键调用链

### 自动代理

1. `OkwwManager.check()` 校验模式和用户列表。
2. `OkwwManager.prepare()` 锁定脚本配置、复制用户配置、备份 OK-WW working 配置目录。
3. `AutoProxyTask.check()` 校验根目录、游戏启动器、次数限制；仅 `脚本`/`用户` 来源初始化 MAS 配置目录，`直控`直接使用脚本原配置。
4. `AutoProxyTask.set_okww()`：
   - 设置 `app.json` 的 `auto_start`、`current_profile`、`update_method`。
   - `脚本`/`用户`来源将对应 MAS 配置原子同步到 working 配置目录；`直控`先恢复脚本原配置。
   - 启用快速配置时，再用快速配置面板的字段覆盖 `DailyTask.json` 的 MAS 管理字段；始终补齐 `Basic Options.json` 的退出设置。
5. 使用 `-t {TaskIndex} -e` 启动，并监控 `ok-script.log`。
6. `final_task()` 保存历史日志和用户运行结果；Manager 解锁、写回用户数据并恢复 working 配置。

### 配置会话

- 脚本列表的“配置 ok-ww”以脚本 ID 启动 `ScriptConfig`，目标为脚本级共享配置。
- 用户编辑页以用户 ID 启动 `ScriptConfig`，`脚本`使用共享脚本配置，`用户`使用用户独立脚本配置，`直控`直接打开脚本原生配置。
- `ScriptConfigTask` 只有在 `脚本`/`用户`来源时才把 MAS 配置复制到 working 目录并保存回 MAS 目录；`直控`不另建一份全量 MAS 配置，保存由 Okww 原生 GUI 写回脚本配置。
- Manager 始终负责备份和恢复 OK-WW 原 working 配置，避免配置会话污染本体原状态。
- 前端遮罩必须处理启动失败、WebSocket 错误、任务完成、主动保存、超时和组件卸载；清理 UI 订阅不能替代停止后端任务。

## 路径契约

### ok-ww 根目录

有效根目录必须同时存在：

```text
ok-ww.exe
data/apps/ok-ww/app.json
```

自动发现、手动选择、前端保存和后端 `check()` 必须使用同一组哨兵。只校验 exe 会把不完整安装保存为看似有效的路径。

### 鸣潮官方启动器

- 前端和后端只接受官方 `launcher.exe` 完整路径。
- 后端读取官方启动器缓存解析实际 `Client-Win64-Shipping.exe`。
- 不接受、不解析、不回退到 WeGame 路径；官方启动器接管游戏更新等未来能力也只针对官方资源。
- 启动前若客户端已运行，只接管进程，不重复启动。

## 配置与运行字段

### 用户配置

- `Info.Mode`：`脚本` / `用户` / `直控`（旧 `简洁` / `详细` 仅用于兼容迁移）
- `Info.IfQuickConfig`：是否启用快速配置覆盖层；启用时快速配置面板的高频字段覆盖当前脚本配置，关闭时使用来源配置中的完整任务设置
- `Info.Resource`：`官服` / `国际服`，映射到 OK-WW `China` / `Global` profile
- `Task.TaskIndex`：仅 `1` / `7`
- DailyTask 高频字段：体力用途、无音区/凝素序号、材料、梦魇巢穴、附加任务
- `Info.IfScriptBeforeTask` / `Info.IfScriptAfterTask`：复用 General 的前后脚本能力

### 脚本配置

- `Info.RootPath`
- `Game.Enabled`、`Game.Path`、`Game.Arguments`、`Game.WaitTime`
- `Run.ProxyTimesLimit`、`Run.RunTimesLimit`、`Run.RunTimeLimit`

审查时以 UI 与运行时实际消费字段为准。`LaunchBeforeTask` 等仅存在于兼容 config/schema、但未被当前 UI 或任务逻辑读取的字段，不得写成现行功能；移除前仍需评估旧配置兼容。

## 日志与进程

判态顺序：

1. 命中内置 fatal 日志，标记异常。
2. 命中 `Window closed exit_event.is_set`，标记成功。
3. 未见成功标记而进程退出，标记异常。
4. 日志长期无变化超过 `RunTimeLimit`，标记超时。

进程清理至少覆盖：

- ProcessManager 管理的进程
- `ok-ww.exe`
- `data/apps/ok-ww/python/pythonw.exe`
- `Game.Enabled` 时解析出的鸣潮客户端进程

每个清理操作独立捕获异常，避免一个失败阻断后续清理。

## 实现规范（Okww 必遵守）

- 所有 RootPath 派生路径集中在 Okww 任务模块；前端只保留选择时必需的哨兵常量。
- JSON 更新和目录同步使用临时路径 + `replace` / `rename`。
- `final_task` 与 `on_crash` 共用 Manager 的 working 配置恢复逻辑。
- 生命周期后期才可用的属性在 `__init__` 显式声明为 Optional；不要用 `hasattr` 代替状态建模。
- 脚本配置锁必须先解锁，再将任务副本写回 `UserData` 并保存。
- 配置会话只有后端任务结束后才能提示“已保存”。
- 手动路径选择失败时恢复旧值，并显示可操作的错误原因。
- 不添加 `config_schema.py`、Okww 配置 REST API 或前端 JSON 表单编辑器，除非产品明确重新采用该方案。
- 不手改 OpenAPI 生成文件。

## 审查清单

- [ ] `OkwwManager` 同时支持 `AutoProxy` 与 `ScriptConfig`
- [ ] 脚本级和用户级配置入口传入正确目标 ID
- [ ] 脚本/用户/直控模式映射到正确配置 owner
- [ ] 旧简洁/详细配置读取后迁移且不改变用户实际来源
- [ ] 快速配置开关真实控制是否覆盖 DailyTask 高频字段
- [ ] 直控直接读取脚本原配置，并在任务前后保留原配置快照
- [ ] 自动发现与手动选择校验同一组 ok-ww 哨兵
- [ ] 启动器路径与实际游戏进程路径职责分离
- [ ] `app.json` profile 与用户资源一致，GUI 配置时保留当前 profile
- [ ] working 配置在成功、失败、取消、异常时都能恢复
- [ ] 配置会话离开页面或超时时会停止任务并释放锁
- [ ] schema、前端表单与运行时字段没有虚假功能分支
- [ ] 仅在改动需要固定可复现回归时补最小专项测试
- [ ] 仅在前端行为实际变更时补对应的前端最小测试

## 最小验证

按仓库根目录的 [`tests/AGENTS.md`](../../../../tests/AGENTS.md) 选择受影响的最小测试。当前 `dev` 不保留散落在 `tests/` 根目录的 Okww 测试入口；需要固定回归时，测试文件放入 `tests/task/`，并只运行该文件。前端测试同理，仅在实际存在且受影响时运行对应文件。
