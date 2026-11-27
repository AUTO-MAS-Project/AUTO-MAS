---
name: mas-script-specialized-adapter
description: >-
  Review, add, or refactor AUTO-MAS specialized script adapters by upstream
  architecture, including MAA, SRC, MaaEnd/MXU, General, ok-script
  adapters such as Okww and OkNte, multi-engine adapters such as HSR, and the
  one-dragon line such as BetterGI, as well as per-adapter issue-bundle
  exports. Use when lowering user setup friction, judging whether a change
  stays inside the black-box boundary (barrier first, then capability
  ownership), or changing ScriptType registration, task lifecycle, config
  ownership, ScriptConfig sessions, Desktop Session (桌面分身), Electron
  integration, frontend edit surfaces, and verification.
---

# 专项适配

本 Skill 只写读代码推不出来的红线、判据与陷阱；文件清单、字段与签名一律现场 `rg` / 读源码确认。

## 核心红线：先降门槛，再守黑箱

1. **推进顺序固定**：先降配置门槛（消除安装导入、路径选择、首配与编排手工步骤），再补 MAS 领域缺位。立项前必须答出**消除了用户哪一步手工操作**；禁止把上游原始面板原样搬进 MAS 或新增运行时不消费的字段。
2. **黑箱边界（详读 [blackbox-boundary.md](references/blackbox-boundary.md)）**：
   - **上游领域**（游戏内操作、任务执行与成败、脚本配置语义）：有上游入口必须复用；无入口先评估向上游提 PR，受阻才可临时补位并标注「上游实现后移除」。
   - **MAS 领域**（托管/账号、调度、计划、通知、统计、模拟器、跨脚本编排）：可自实现，但**禁止读取或反推上游内部状态**。
   - **上游私有格式**：只允许透传读写，不建平行语义模型，上游任务的成败必须取自上游结果面。

## 开工顺序与按需参考

1. 读上游发行版/源码（CLI、进程、日志、配置目录与 UI）。
2. 按 [script-frontend-architectures.md](references/script-frontend-architectures.md) 归类，**先让用户确认架构线**。
3. 必读 [adapter-code-norms.md](references/adapter-code-norms.md)，再按需只读对应参考：
   - 案例：[SRC](references/examples-src.md) · [MaaEnd](references/examples-maaend.md) · [M9A（MFW 特调）](references/examples-m9a.md) · [Okww](references/examples-okww.md) · [OkNte](references/examples-oknte.md) · [HSR](references/examples-hsr.md) · [ZzzOd](references/examples-zzzod.md) · [BAAH](references/examples-baah.md) · [BetterGI](references/examples-bettergi.md) · [Whimbox](references/examples-whimbox.md)
   - 子能力：日志管线 [logbox-api.md](references/logbox-api.md) · OCR [ocr-tools.md](references/ocr-tools.md) · 归档 [config-archive.md](references/config-archive.md) · 恢复 [config-restore.md](references/config-restore.md) · 问题包 [issue-report.md](references/issue-report.md)
   - 桌面分身：新增或迁移插件专项、加入桌面分身清单、处理子会话进程时读 [desktop-session.md](references/desktop-session.md)。
4. 联动 Skill：调度/会话/锁加 `mas-task-scheduler`；前端/UI 加 `mas-frontend-standards` + `mas-frontend-ui`；配置加 `mas-data-model`。

## 关键架构约定

- **全切面反查**：增改内置 `ScriptType` 时现场 grep 核对配置/schema、`TYPE_BOOK`、任务模块、前端入口、Electron 能力及 OpenAPI 生成（**禁手改 `frontend/src/api/**`**）。独立插件通过自身声明注册，桌面分身复用宿主的通用派发。自动发现、手动选择与后端 `check()` 须用**同一组哨兵文件**。
- **日志与报告**：`app.utils.log_box` 只提供纯文本处理；专项自持开关、路径、线程/取消收尾与账号归属，增量读复用 `LogSource`，翻译复用 `PoTranslator`，排版复用 `app.core.notify.report`。含采集的专项必查「采集→报告」闭环与账号级开关隔离。
- **配置备份恢复（新专项标配）**：原语用 `archive.py`，恢复用 `restore.py` + `/backup/*` + `ConfigRestoreSection.vue`，遮罩用 `GuiSessionMask.vue`；**归档三时机**：进编辑页归档原生、退编辑页归档 MAS、运行前归档原生（覆盖操作前强制归档）。
- **OCR**：新画面文字识别用共享工具 `app/tools/common/ocr/__init__.py`，交互层由专项自持。
- **独立 PyPI 适配器**：用户可见变更写入插件仓 `CHANGELOG.md` 并核对 `pyproject.toml` 的 `Changelog` URL。

## `Info.Base` 与覆写常规配置（`Info.IfQuickConfig`）

| 专项 | 来源模式与有效行为 |
| --- | --- |
| MAA / SRC / MaaEnd / Okww / OkNte | 共享（`Default`）/ 独立（账号目录）/ 原生 三态；OkNte 另存 `QuickConfig` 覆写 |
| General | 原生用脚本原配置；非原生恒按账号 `ConfigFile`（`shared` 等同 `independent`） |
| HSR | 共享（同名组共享计划）/ 独立 / 原生；**不支持覆写常规配置** |
| BetterGI / ZzzOd | 界面仅独立 / 原生（禁用共享，不提供独立覆写开关） |
| Whimbox | 保留三项；`shared`/`independent` 均物化本账号面板至原生 `config.json`；`native` 仅覆写开启时临时物化 |
| BAAH | 按 `Info.ConfigName` 引用 BAAH JSON；运行不消费 `Base`/`IfQuickConfig` |
| MaaFW / M9A | 通用引擎非专项，仅用账号任务快照，不消费 `Base`/`IfQuickConfig` |

- **唯一越界判据**：运行期写入任务结束能还原（overlay）即合法；**不能还原即越界**（整目录快照外的同级文件如 Okww `app.json` 必须自带键级快照）。
- **`ScriptConfig` 会话**：不得把 overlay 固化进 base；覆盖成功/失败/取消/超时/崩溃全路径快照恢复，保护外侧新修改。旧 `Info.Mode` 仅作输入兼容，新逻辑只用 `Info.Base`。

## 专项特殊约束

- **ok-script 家族（Okww / OkNte）**：均提供 REST 动态面板 + `ScriptConfig` 遮罩，保留未知字段与原生键值，严禁跨子项目照搬任务语义。
- **HSR（唯一一对多）**：编排 M7A + SRA，**无 `ScriptConfig.py`**（仅 `AutoProxy`/`ManualReview`）；任务模块在 `task_mapping.py` 单点声明；托管字段由后端下发动态渲染；备份清单中 `existed=False` 恢复时须**删除任务期新增路径**；切号统一走 SRA StartGame；路径锁冲突抛可读错误。
- **MAA 配置恢复**：`ScriptConfigTask` 与 `AutoProxy` 必须共用 `_mas_owner`；退出编辑页必须串行 `stopSession → ensure(mas)`；新建账号 `onMounted` 先 `await loadScriptInfo()` 再 `ensure(native)`；`Base` 只进预览不回填；`viewOnly` 结束不回写 MAS 配置。

## 验收

按 `tests/AGENTS.md` 跑对应最小专项测试（缺测试不硬补，如实报缺口）；涉及任务生命周期或新专项时声明 `mas-e2e` `@real` 前置条件与证据。
