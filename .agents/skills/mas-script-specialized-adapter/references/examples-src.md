# 案例：SRC 线（Alas / SRC 系）

上游参照 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) 一类基于 Alas 框架的脚本。AUTO-MAS 面向「由 MAS 拉起、监控日志的 SRC 兼容可执行体」，**不在本仓复刻其 `webapp` 配置界面**，但对接排障时应理解其框架习惯。

文件与字段现场读 `app/task/SRC/` 与 `views/SRCUserEdit/` 确认。

## 线内特征

无 MAA/MaaEnd 式全屏配置遮罩，无专用计划表；侧重 **exe 路径、模拟器、Stage、通知**。脚本页是**单文件大表单**风格（`form-section` + 字段 `@blur` 保存）——**不急于拆文件，真放不下再拆**。

## 新游戏是否要新建 ScriptType（关键判据）

| 情况 | 决定 |
| --- | --- |
| 与现有 SRC 配置 schema、任务语义**一致** | 继续用 `ScriptType === 'SRC'` |
| 配置模型或任务模式**分叉** | 新建 `ScriptType` + 复制 `app/task/SRC/` 骨架 + 新 EditView，仍走 SRC 线表面模式 |
| 出现**强队列 + 管线**语义 | 重新评估是否该归 **MFAA 线**，别硬塞进 SRC Section |

新专项前必问：可执行体是否共用同一套 schema？是否需要 `METHOD_BOOK` 之外的新任务模式（需要则同步扩展前端任务模式选项与展示文案常量）？模拟器/登录/包名是否与现有常量冲突？用户侧是否仍只需 BasicInfo + Stage + Notify？

## 上游概念对照（心智模型，非文件映射）

| 上游 | MAS 侧关注点 |
| --- | --- |
| `tasks/` `module/` `route/` 任务调度 | `AutoProxy` 主循环、任务模式、`METHOD_BOOK` |
| `webapp/` 或 GUI 配置 | **不复刻**；由编辑页写回 config |
| `config/` 与运行数据目录 | 与配置任务、用户目录读写路径对齐，遵守 `data/{scriptId}/...` 约定 |
| 模拟器 + 包名/进程 | 模拟器字段 + `manager.check()`；业务常量集中在 `app/utils/constants.py` |

## 必守不变量

- `check()` 的前置条件（任务模式在 `METHOD_BOOK` 内、配置类型正确、**模拟器 Id/Index 必填**）要与前端表单**同步**——新接入的 Alas 系脚本同理。
- 复制任务目录时保留 `METHOD_BOOK` 形状，除非明确要删模式。
- Section 通过 `emit('save')` 聚合写库，**不在 Section 内散落 API 调用**。
- Hub / 路由 / `useScriptApi` 分支补全（见 [架构线判据 · 前端表面通用约定](./script-frontend-architectures.md#前端表面通用约定)）。

## 配置恢复接入要求（MAA 孪生形态 + SRC 特有事务）

SRC 已接入通用配置恢复（mas/native 双池 + 页面字段侧车 + viewOnly 查看会话），形态与 MAA 几乎同构（ConfigFile 目录副本 + 快速配置覆盖 + ScriptConfig 会话 + manager 任务级原生快照），后续改动必须符合 [config-restore.md](config-restore.md) 通用要求，另守以下 SRC 特有项：

- **native 恢复前必须守卫 Temp 快照**：manager 的任务级 Temp 快照（`data/{script_id}/Temp.ready` 提交标记）在下次任务 `_recover_previous_run` 时会被**无条件**回滚覆盖安装目录 config/（MAA 是「检测到改动保留当前」，SRC 不是）——待恢复快照残留时拒绝恢复并提示先完成一次任务，否则刚恢复的备份会被冲掉。
- **viewOnly 会话不得登记 config_user_id**：ScriptConfigTask 会把会话归属写进进程状态，中断恢复路径（manager `_save_pending_config_session`）只对「归属可验证」的会话把原生配置保存回 ConfigFile——查看会话写 `None`，否则查看期间的注入现场会污染用户配置。
- **会话包络与运行包络同源**：ScriptConfigTask 曾硬编码用户目录，脚本态用户的会话改动运行时不读（改了白改）、备份采不到会话现场——对齐 `_mas_owner`（脚本级入口恒 Default、脚本态用户共享 Default、用户态独立目录、直控零写入含归档）。
- **侧车范围**：Stage 段全部字段 + Info 的 Server（注入 PackageName）+ Mode（仅预览，决定恢复目标目录）；Id/Password/前后置脚本/通知由 MAS 自己消费（登录与执行域）**不进侧车**；IfQuickConfig 是门控开关不进。
- **关卡值翻译用后端 `STARRAIL_STAGE_BOOK`**（constants.py 的 MAS 自持固化词表，约 100 项）：两池同源天然同口径，不复制到前端、不读 SRC 本体运行时资源；哨兵语义 `do_not_use`=未启用（native）、`-`=禁用（mas）。native 预览反读 src.json 的关键分支（调度开关 + 关卡名 + 后备开拓力 + PackageName 反查服名），字段以 template.json 实测为准、不臆造。
- **前端遮罩用 `GuiSessionMask`**：配置会话与查看会话两个实例（查看用专项 `srcViewing*` 词条）；脚本级查看会话以**脚本 ID** 为 dispatch 的 taskId 启动（调度层把脚本级设置任务归属解析为 Default、跳过下发——原生目录即备份；传 `"Default"` 会因后端 UUID 解析直接 500）。
