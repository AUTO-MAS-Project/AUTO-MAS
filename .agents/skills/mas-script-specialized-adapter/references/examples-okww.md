# 案例：Okww（鸣潮 / OK-WW）

Okww 与 [OkNte](./examples-oknte.md) 同属 `ok-script` 家族、同用 `-t N -e` 启动，配置方案是两条并行且都有效的路（对照表见 [SKILL.md](../SKILL.md#ok-script-家族两种并行范式)）。Okww 走**固定字段 + 仅 ScriptConfig 遮罩调本体 GUI**；不要给 Okww 加 OkNte 那套 REST 动态表单，也不要用 Okww 标准判 OkNte 违规。

具体字段、路径、函数名现场读 `app/task/Okww/` 确认。本文件只记推不出来的部分。

## 产品决策（读代码看不出为什么）

- **只支持官方资源与官方启动器，不接管 WeGame 侧**。Electron 发现、前端保存、后端解析都不得回退到 WeGame 路径。这是产品决定，不是尚未实现。
- 前端只存**官方启动器完整路径**，由后端读启动器缓存解析真实客户端 exe——**启动器路径与游戏进程路径职责分离**，不要在前端直接存客户端路径。
- MAS 任务只开放 `1`（DailyTask）与 `7`（MultiAccountDailyTask）；旧值 `2` 读取时纠正为 `7`。

## 三态来源与独立快速配置

`Info.Mode` 三态只决定**脚本配置 owner**：

| 来源 | 配置归属 |
| --- | --- |
| 脚本 | `data/{scriptId}/Default/ConfigFile`，所有用户共用 |
| 用户 | `data/{scriptId}/{userId}/ConfigFile`，用户独立 |
| 直控 | 直接读取脚本原有 working 配置，由原生 GUI 维护，**不另建全量 MAS 配置**（仍有一处运行时必需写入，见下节） |

`Info.IfQuickConfig` 是独立的用户级快速配置开关，三种来源均可使用：开启时用该用户快速配置面板的高频字段覆盖当前原生配置；关闭时使用来源配置中的完整任务设置。直控+关闭只使用脚本原生配置（不含 MAS 侧全量配置，仅有运行时必需写入，见下节）；直控+开启则任务前注入、任务后按快照策略恢复。

旧值 `简洁` / `详细` 读取时迁移为 `脚本` / `用户`，**迁移不得改变用户实际生效的来源**。

配置初始化、AutoProxy、ScriptConfig 三处必须用**同一套来源规则**；直控不得为了"字段齐全"复制脚本全量配置。

## 直控下的原生配置写入：例外与来源守卫

直控**不等于** MAS 对原生配置零写入。为让 OK-WW 按用户所选 `Info.Resource` 正确启动，`set_okww()` 在直控判定**之前**无条件调用 `_configure_okww_launcher()`，直控用户同样会走到。这是经裁定的**运行时必需写入**，不是覆盖用户配置。

| 原生目标 | 写入内容 | 触发条件 |
| --- | --- | --- |
| `data/apps/ok-ww/app.json` | `auto_start=True` | 缺省才补（已是 `True` 不写） |
| 同上 | `update_method=AUTO_UPDATE` | 键不存在才补 |
| 同上 | `current_profile`（按 `Resource` 映射官服/国际服） | 与目标 profile 不同才写 |

三项共用 `changed` 标志：无事即**零写入**并直接返回，属幂等最小补齐。写入经 `write_file` 原子落盘（tmp + rename），不会产生半写文件。

**判别判据（最易混淆处）**：区分「例外」与「来源守卫」看的是**幂等最小补齐 vs 按来源条件写入**，不是代码位置或先后顺序。

- `_configure_okww_launcher()`（于 `set_okww()` 内调用）→ **真例外**：缺省才补 + `changed` 早退 + 原子落盘，无事零写入，属运行时必需，保留。
- `_apply_mas_overrides()` 对 `Basic Options.json` 的写入（`Exit App when Game Exits: True`）→ **已纳入来源守卫（F13 已修复）**：该文件是全局运行选项、不属于快速配置子集，只有脚本/用户来源（MAS 配置整体落盘）才写它，直控来源下零写入。

修复后的守卫行为：直控下 `Basic Options.json` 写入次数必须为 0（`Info.IfQuickConfig` 开与关都为 0）；`DailyTask.json` 是快速配置子集，由 `Info.IfQuickConfig` 守卫、与来源独立——直控+开启写入、直控+关闭零写入，任务结束由 manager 既有快照恢复。

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

## 配置恢复（mas 池带覆盖层侧车）

ok-ww 已接入通用配置恢复（`ConfigRestoreSection`），mas 池形态与其他专项不同：

- **mas 池 = ConfigFile 副本 + 覆盖层字段侧车**：页面任务配置卡片的字段存在
  MAS 用户配置（`UserData.Task`）、运行时才覆盖进 DailyTask.json，不在
  ConfigFile 中。备份/恢复两端都带侧车，预览展示侧车（与页面认知同源），
  恢复时文件回滚 + 侧车回填 UserData + 前端重拉表单（对齐 ZzzOd 字段回填）。
- **池恒按用户分桶**（`OkwwBackups/mas/{user_id}`），三态 owner 只决定归档/
  恢复目标路径（脚本=Default 共享目录、用户=独立目录、直控=无）——脚本态多
  用户若共享一个 Default 池，各自的侧车会混池、跨用户污染。通用教训见
  [config-restore.md §1.1](config-restore.md#111-池分桶必须按用户恢复目标才按三态-ownerokww-教训)。
- **原生池恒为 working/configs 整目录**（ok-ww 无 Folder/File 双模式），项目级
  按物理路径指纹分桶。

## 审查清单

- [ ] Manager 同时支持 `AutoProxy` 与 `ScriptConfig`；脚本级与用户级入口传对目标 ID
- [ ] 三态映射到正确 owner；旧简洁/详细迁移不改变实际来源
- [ ] 快速配置开关真实控制是否覆盖高频字段
- [ ] 直控直接读脚本原配置，任务前后保留原配置快照
- [ ] 直控下的写入区分「例外」与「来源守卫」：启动器补齐属幂等最小补齐（缺省才写、无事零写入），是例外；`Basic Options.json` 属全局运行选项、仅脚本/用户来源写入
- [x] 直控下 `Basic Options.json` 写入次数为 0（开关皆然）；直控+开启只写 `DailyTask.json` 快速配置子集（F13 已修复）
- [ ] 自动发现与手动选择校验同一组哨兵
- [ ] 启动器路径与客户端进程路径职责分离
- [ ] `app.json` profile 与用户资源一致，GUI 配置时保留当前 profile
- [ ] working 配置在成功、失败、取消、异常四条路径都恢复
- [ ] 配置会话离开页面或超时会停止任务并释放锁
- [ ] schema、表单、运行时三者无虚假功能分支
