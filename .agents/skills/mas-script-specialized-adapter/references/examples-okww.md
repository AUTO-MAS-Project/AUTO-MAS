# 案例：Okww（鸣潮 / OK-WW）

Okww 与 [OkNte](./examples-oknte.md) 同属 `ok-script` 家族、同用 `-t N -e` 启动，配置方案是两条并行且都有效的路（对照表见 [SKILL.md](../SKILL.md#ok-script-家族两种并行范式)）。Okww 走**固定字段 + 仅 ScriptConfig 遮罩调本体 GUI**；不要给 Okww 加 OkNte 那套 REST 动态表单，也不要用 Okww 标准判 OkNte 违规。

具体字段、路径、函数名现场读 `app/task/Okww/` 确认。本文件只记推不出来的部分。

## 产品决策（读代码看不出为什么）

- **只支持官方资源与官方启动器，不接管 WeGame 侧**。Electron 发现、前端保存、后端解析都不得回退到 WeGame 路径。这是产品决定，不是尚未实现。
- 前端只存**官方启动器完整路径**，由后端读启动器缓存解析真实客户端 exe——**启动器路径与游戏进程路径职责分离**，不要在前端直接存客户端路径。
- MAS 任务只开放 `1`（DailyTask）与 `7`（MultiAccountDailyTask）；旧值 `2` 读取时纠正为 `7`。

## 三态来源 + 快速配置覆盖层

`Info.Mode` 三态只决定**脚本配置 owner**：

| 来源 | 配置归属 |
| --- | --- |
| 脚本 | `data/{scriptId}/Default/ConfigFile`，所有用户共用 |
| 用户 | `data/{scriptId}/{userId}/ConfigFile`，用户独立 |
| 直控 | 直接读取脚本原有 working 配置，由原生 GUI 维护，**不另建全量 MAS 配置** |

`Info.IfQuickConfig` 是**独立覆盖层**，不是第四种来源：开启时仅用快速配置面板的高频字段覆盖当前脚本配置；关闭时使用来源配置中的完整任务设置。

旧值 `简洁` / `详细` 读取时迁移为 `脚本` / `用户`，**迁移不得改变用户实际生效的来源**。

配置初始化、AutoProxy、ScriptConfig 三处必须用**同一套来源规则**；直控不得为了"字段齐全"复制脚本全量配置。

## 哨兵契约

有效 ok-ww 根目录必须**同时**存在 `ok-ww.exe` 与 `data/apps/ok-ww/app.json`。

**只校验 exe 会把不完整安装保存为看似有效的路径**——自动发现、手动选择、前端保存、后端 `check()` 四处必须用同一组哨兵。

## 判态与清理

判态顺序：内置 fatal 日志 → `Window closed exit_event.is_set` 视为成功 → 未见成功标记而进程退出视为异常 → 日志停滞超 `RunTimeLimit` 视为超时。

进程清理至少覆盖：ProcessManager 管理的进程、`ok-ww.exe`、`data/apps/ok-ww/python/pythonw.exe`、`Game.Enabled` 时解析出的客户端进程。**每步独立捕获异常**，一个失败不阻断后续。

## 账号切换（MAS 强制切号）

游戏配置区 `Game.AccountSwitch`（是/否，默认否）控制游戏启动后是否由 MAS 按
用户手机号后 4 位强制切换登录账号；开关依赖 `Game.Enabled`（未启用游戏配置
则不生效），用户未填写手机号时跳过不切换。

OCR 走共享工具 `app/tools/ocr.py`（用法见 [ocr-tools.md](./ocr-tools.md)），
交互层在 `app/task/Okww/tools/account_switch.py`：

- 判据要点：弹窗「确认登出」按钮按文本精确定位，**排除说明文本「确认登出账号？」**，
  且不认裸「退出」（主菜单右侧有退出游戏按钮）。
- 切换失败留 OCR 文本 + 原图截图到 `debug/okww-account-switch/`，经
  `handle_pre_okww_error` 走调度台报错 + 通知 + 重试，不回退静默。

## 陷阱

- **兼容字段不等于现行功能**：`LaunchBeforeTask` 等仅存在于 config/schema、未被当前 UI 或任务逻辑读取的字段，不得写成现行功能；移除前仍要评估旧配置兼容。`Game.Enabled` 才是当前的游戏启停总开关。
- 客户端已运行时只接管进程，不重复启动。
- **配置会话只有后端任务结束后才能提示"已保存"**；清理 UI 订阅不能替代停止后端任务。遮罩必须处理启动失败、WebSocket 错误、任务完成、主动保存、超时、组件卸载六条路径。
- Manager 始终负责备份与恢复本体原 working 配置，避免配置会话污染脚本原状态。
- 手动路径选择失败时恢复旧值并显示可操作原因。
- 所有 RootPath 派生路径集中在任务模块，前端只留选择时必需的哨兵常量。

## 审查清单

- [ ] Manager 同时支持 `AutoProxy` 与 `ScriptConfig`；脚本级与用户级入口传对目标 ID
- [ ] 三态映射到正确 owner；旧简洁/详细迁移不改变实际来源
- [ ] 快速配置开关真实控制是否覆盖高频字段
- [ ] 直控直接读脚本原配置，任务前后保留原配置快照
- [ ] 自动发现与手动选择校验同一组哨兵
- [ ] 启动器路径与客户端进程路径职责分离
- [ ] `app.json` profile 与用户资源一致，GUI 配置时保留当前 profile
- [ ] working 配置在成功、失败、取消、异常四条路径都恢复
- [ ] 配置会话离开页面或超时会停止任务并释放锁
- [ ] schema、表单、运行时三者无虚假功能分支
