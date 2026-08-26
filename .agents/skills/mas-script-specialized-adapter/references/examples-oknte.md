# 案例：OkNte（异环 / OK-NTE）

OkNte 与 [Okww](./examples-okww.md) 同属 `ok-script` 家族、同用 `-t N -e` 启动，但配置方案是与 Okww **并行且都有效**的另一套。维护 OkNte 时不要套用 Okww 的三态来源、固定 schema 或「仅 GUI 遮罩」约束。

具体文件、字段、端点签名现场读 `app/task/OkNte/` 与 `app/api/scripts.py` 确认。本文件只记推不出来的部分。

## 为何必须动态推断（最关键的一条）

Okww 的字段可静态声明；**OkNte 上游打包后源码不可读**，配置项随版本漂移，JSON 配置文件又只存当前值、不存候选列表。因此采用**半自动 schema**，三部分职责固定：

| 部分 | 来源 | 说明 |
| --- | --- | --- |
| 字段名 + 类型 | working 目录 JSON 值**自动推断** | 上游加字段无需改 MAS |
| 中文标签 | 安装目录 `.po` / `.mo` + ok-script 框架 `.ts` **自动加载** | 跟随上游翻译 |
| 下拉 / 多选候选项 | `config_schema.py` 的 `SELECT_OPTIONS` **手工维护** | 无法从值推断，**唯一需人工同步上游的地方** |

**不要把能推断的字段也写进手工表。** 看到 `SELECT_OPTIONS` 里只有下拉字段、没有布尔和整数字段，那是对的，不是遗漏。

## 两条配置通道并存，都是合法实现

OkNte 同时有：

1. **动态表单 + REST 端点**：前端按后端下发的 `field.type` 渲染，经 `/api/scripts/oknte/configs*` 直接读写 per-user JSON。
2. **ScriptConfig GUI 遮罩会话**：无参启动本体 GUI，会话结束回存 MAS 目录。

**审查 OkNte 时不得按 Okww「无配置 REST API / 无动态表单」的标准判其违规**——`config_schema.py`、配置端点、`OkNteConfigEditor.vue` 都是 OkNte 的正常组成部分。反过来也不要给 Okww 加这套。

动态表单按 `field.type` 渲染，**新增下拉字段扩展后端 `SELECT_OPTIONS`，不在 Vue 里加分支**（与 HSR 的后端下发字段定义同思路）。

## 必守的不变量

- **`ConfigPathMode`（`Folder` / `File`）两分支必须在三处一致处理**：AutoProxy 下发、ScriptConfig 回写、Manager 恢复。漏一处即配置错位。
- **旧版 → 新版迁移只在目标文件不存在时用旧值初始化，绝不覆盖用户现值**（旧 `DailyTask.json` → 新 `DailyRoutineTask.json`）。
- per-user 配置目录是事实来源；旧版共享目录仅作升级初始化来源，不是运行时读取位置。
- JSON 写入走临时文件 + `replace`，并在模块写锁内；目录同步用 `.tmp` + `rename`。
- 来源模式是两态（`Info.Mode`），**不是** Okww 三态。不要为对齐 Okww 增加"直控"。

## 判态陷阱

- **日常任务（`-t 2`）命中 `SuccessLog` 还不够**，必须再过专项校验（DailyRoutine 需完成日常领取 / 旧版需完成每日活跃度）才算成功。只看 `SuccessLog` 会把没做完日常的运行误报为成功。
- 内置 fatal 片段优先于用户配置的 `ErrorLog`；`ErrorLog` 清洗后为空要回退内置默认，不能留空放过所有错误。
- 进程在成功标记前退出视为异常，不是正常结束。
- **启动器按固定相对路径校验，解析不出有效路径时跳过清理而非误杀**——异环启动器路径写错会杀掉无关进程。
- 客户端进程已在运行时只接管、不重复拉起。

## 审查清单

- [ ] 三部分职责清晰：类型推断 / 标签加载 / `SELECT_OPTIONS` 手工候选，无越界
- [ ] 两条配置通道读写同一 per-user 目录，未各自维护一份
- [ ] `ConfigPathMode` 两分支在下发、回写、恢复三处一致
- [ ] 迁移逻辑不覆盖用户现值
- [ ] `-t 2` 成功过专项校验，不只看 `SuccessLog`
- [ ] 进程清理每步独立捕获；启动器路径无效时跳过
- [ ] working 配置在成功、失败、取消、异常四条路径都恢复；先解锁再写回 UserData
- [ ] schema、动态表单、运行时三者无虚假功能分支
