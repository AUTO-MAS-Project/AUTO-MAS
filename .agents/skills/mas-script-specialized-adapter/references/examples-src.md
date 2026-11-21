# 案例：SRC 线（Alas / SRC 系）

上游参照 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) 一类基于 Alas 框架的脚本。AUTO-MAS 面向「由 MAS 拉起、监控日志的 SRC 兼容可执行体」，**不在本仓复刻其 `webapp` 配置界面**，但对接排障时应理解其框架习惯。

SRC 后端由独立仓库 [AUTO-MAS-SRC-Adapter](https://github.com/AUTO-MAS-Project/AUTO-MAS-SRC-Adapter) 持有，Python 包为 `src_adapter`。桌面编辑页及会话入口见 `frontend/src/views/src/` 和 `frontend/src/views/Scripts.vue`。新托管通过插件声明启用，存量配置继续沿用 `SrcConfig` 和 `SrcUserConfig`。

插件声明 `AutoProxy`、`ScriptConfig`、`ScriptView` 三种模式并复用原生 WebUI，无专项计划表。新接入脚本先判断原生配置、执行和结果能否共用，存在差异时按实际模式声明新的专项适配器。

## 上游概念对照（心智模型，非文件映射）

| 上游 | MAS 侧关注点 |
| --- | --- |
| `tasks/` `module/` `route/` 任务调度 | 插件 L3 展开与各任务模式的 L4 执行器 |
| `webapp/` 或 GUI 配置 | **不复刻**；由编辑页写回 config |
| `config/` 与运行数据目录 | 与配置任务、账号目录读写路径对齐，遵守 `data/{scriptId}/...` 约定 |
| 模拟器 + 包名/进程 | 模拟器字段 + `manager.check()`；业务常量集中在 `app/utils/common/constants.py` |

## 必守不变量

- 模拟器使用当前账号的游戏与设备绑定，未覆盖时继承托管目标。托管锁与账号锁由调度层持有。
- 按声明选择执行器。只读查看与编辑分别保存恢复意图，再启动原生 GUI。
- Section 通过 `emit('save')` 聚合写库，**不在 Section 内散落 API 调用**。
- Hub / 路由 / `useScriptApi` 分支补全（见 [架构线判据 · 前端表面通用约定](./script-frontend-architectures.md#前端表面通用约定)）。

## 配置恢复接入要求（MAA 孪生形态 + SRC 特有事务）

SRC 已接入通用配置恢复（mas/native 双池 + 页面字段侧车 + viewOnly 查看会话），形态与 MAA 几乎同构（ConfigFile 目录副本 + 覆写常规配置覆盖 + ScriptConfig 会话 + manager 任务级原生快照），后续改动必须符合 [config-restore.md](config-restore.md) 通用要求，另守以下 SRC 特有项：

- **native 恢复前必须守卫 Temp 快照**：manager 的任务级 Temp 快照（`data/{script_id}/Temp.ready` 提交标记）在下次任务 `_recover_previous_run` 时会被**无条件**回滚覆盖安装目录 config/（MAA 是「检测到改动保留当前」，SRC 不是）——待恢复快照残留时拒绝恢复并提示先完成一次任务，否则刚恢复的备份会被冲掉。
- **viewOnly 会话不得登记 config_user_id**：ScriptConfigTask 会把会话归属写进进程状态，中断恢复路径（manager `_save_pending_config_session`）只对「归属可验证」的会话把原生配置保存回 ConfigFile——查看会话写 `None`，否则查看期间的注入现场会污染账号配置。
- **会话包络与运行包络同源**：ScriptConfigTask 曾硬编码账号目录，共享来源账号的会话改动运行时不读（改了白改）、备份采不到会话现场——对齐 `_mas_owner`（托管级入口恒 Default、共享来源账号共享 Default、独立来源独立目录、原生来源零写入含归档）。
- **侧车范围**：Stage 段全部字段 + Info 的 Server（注入 PackageName）+ Base（仅预览，决定恢复目标目录）；Id/Password/前后置脚本/通知由 MAS 自己消费（登录与执行域）**不进侧车**；IfQuickConfig 是门控开关不进。
- **关卡值翻译用后端 `STARRAIL_STAGE_BOOK`**（插件 `src_adapter/constants.py` 的词表）：两池同源天然同口径，不复制到前端、不读 SRC 本体运行时资源；哨兵语义 `do_not_use`=未启用（native）、`-`=禁用（mas）。native 预览反读 src.json 的关键分支（调度开关 + 关卡名 + 后备开拓力 + PackageName 反查服名），字段以 template.json 实测为准、不臆造。
- **前端遮罩用 `GuiSessionMask`**：配置会话与查看会话两个实例（查看用专项 `srcViewing*` 词条）；托管级查看会话以**托管 ID** 为 dispatch 的 taskId 启动（调度层把托管级设置任务归属解析为 Default、跳过下发——原生目录即备份；传 `"Default"` 会因后端 UUID 解析直接 500）。
