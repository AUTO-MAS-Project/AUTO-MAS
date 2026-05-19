# 专项脚本类型适配（完整说明）

对应 Skill：`mas-script-specialized-adapter`。基于已合并 PR 归纳，适用于 MaaEnd、M9A 及后续同类专项。

参考 PR：

- [#133](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/133) — MaaEnd 全量适配
- [#152](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/152) — MaaEnd 计划表 / 理智任务扩展
- [#154](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/154) — M9A 全量适配
- [#183](https://github.com/AUTO-MAS-Project/AUTO-MAS/pull/183) — M9A 用户编辑体验（Draft，可单独跟进）

---

## 1. 命名约定

| 层级 | 示例（MaaEnd） |
|------|----------------|
| 配置类名 | `MaaEndConfig`, `MaaEndUserConfig` |
| Schema / API book 键 | `MaaEndConfig` |
| 前端 ScriptType | `'MaaEnd'` |
| 任务目录 | `app/task/MaaEnd/` |
| Manager 类 | `MaaEndManager` |
| 路由片段 | `/edit/maaend`, `/users/.../edit/maaend` |

保持 **Config 后缀**、**UserConfig 后缀**、**Manager** 与现有 MAA/SRC 一致，避免与 `General` 混用。

---

## 2. 后端检查清单

### 2.1 模型与 Schema

- [ ] `app/models/config.py`：`XxxConfig`、`XxxUserConfig`（ConfigItem 分块：Info / Run / Game / Task…）
- [ ] `app/models/schema.py`：对应 `XxxConfig_*`、`XxxUserConfig_*`；`UserUpdateIn.data` 联合类型扩展
- [ ] `app/core/config.py`：`add_script` / `add_user` / `update_user` 等 `isinstance` 分支
- [ ] `app/utils/constants.py`：类型标签、任务模式映射、计划 consumer 等（若需要）

### 2.2 API 注册

- [ ] `app/api/scripts.py`：`SCRIPT_BOOK`、`USER_BOOK` 增加条目
- [ ] 其它 combox / plan / queue API 若按 consumer 过滤，增加 `Xxx` 分支（见 MaaEnd 计划表）

### 2.3 任务模块（`app/task/Xxx/`）

- [ ] `manager.py`：`METHOD_BOOK`（AutoProxy / ManualReview / ScriptConfig）、`check()`、`prepare()`、用户列表构建
- [ ] `AutoProxy.py`：主循环、游戏/模拟器启动、配置写入、日志与通知
- [ ] `ScriptConfig.py`：`data/{scriptId}/{userId}/ConfigFile` 备份与回写
- [ ] `ManualReview.py`（若该专项需要）
- [ ] `tools/`：notify、login、与外部 exe 交互等
- [ ] `__init__.py` 导出 `XxxManager`
- [ ] `app/task/__init__.py` 汇总导出
- [ ] `app/core/task_manager.py`：`isinstance(..., XxxConfig)` → `XxxManager`

### 2.4 横切能力（可选）

- [ ] `runtime_bridge`：运行前生成外部程序所需 JSON/配置
- [ ] `app/MaaFW/*`：PC 自动化自定义动作（命名带 `[ArknightsPC]` 等后缀，#133）
- [ ] 计划表：`XxxPlanConfig`、`app/api/plan.py` 类型构造、前端 `planTypeRegistry`（#152）

---

## 3. 前端检查清单

### 3.1 类型与 API 层

- [ ] `frontend/src/types/script.ts`：`ScriptType`、`*ScriptConfig` 接口
- [ ] `frontend/src/composables/useScriptApi.ts`：读写、默认结构、类型判断
- [ ] OpenAPI 重新生成后的 `frontend/src/api/models/*`（**勿手改**）
- [ ] `ScriptIndexItem.type` 枚举（生成模型）

### 3.2 路由与导航

- [ ] `frontend/src/router/index.ts`：脚本编辑、用户添加/编辑路由
- [ ] `frontend/src/views/Scripts.vue`：创建脚本、跳转编辑、专项按钮（如「配置 MaaEnd」）
- [ ] `frontend/src/components/ScriptTable.vue`：图标、类型标签、专项操作

### 3.3 编辑页

- [ ] `EditView/Script/XxxScriptEdit.vue`：脚本级配置（路径、游戏/模拟器、运行参数）
- [ ] `EditView/User/XxxUserEdit.vue`：用户级配置；复杂 UI 拆 `XxxUserEdit/*Section.vue`
- [ ] 与 `ScriptConfig` 任务联动：WebSocket 遮罩、保存配置（参照 MAA/MaaEnd）

### 3.4 其它前端模块

- [ ] 计划表：`views/plan/tables/XxxPlanTable.vue`、`usePlanApi` consumer（#152）
- [ ] 队列：`QueueItemManager` / `TimeSetManager` 对 script type 的分支（#154 M9A）
- [ ] 资源文件：`frontend/src/assets/Xxx.png`

---

## 4. 推荐 PR 拆分

| 阶段 | 内容 | 参考 |
|------|------|------|
| P0 全量适配 | 模型 + Manager + 基础编辑页 + 注册 | #133, #154 |
| P1 横切 | 计划表、队列、错误码与重试 | #152, #154 后续 |
| P2 体验 | 用户编辑重构、预设模板、虚拟用户 | #183 |

---

## 5. 与通用脚本（General）的区别

- **General**：`app/task/general/`，配置路径模式、游戏管理通用化。
- **专项**：强绑定外部程序（MaaEnd.exe、M9A 管线等），常有 ScriptConfig 落盘目录、登录/切号、专用计划表。

新增专项时**不要**塞进 `general/`，应独立 `app/task/Xxx/`。

---

## 6. 执行顺序（与 mas-skills 一致）

1. `mas-code-standards` — 对齐 dev 风格  
2. `mas-module-boundary` — 文件归属  
3. `mas-data-model` + `mas-schema-naming` — 配置与字段  
4. 本 Skill — 端到端切面  
5. `mas-function-design` + `mas-api-contract` — 实现细节与接口  
