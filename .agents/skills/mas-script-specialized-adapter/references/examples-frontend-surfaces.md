# 多类型前端表面对照

用于选择「最接近的专项模板」。后端路径见各类型 `app/task/<Name>/`。  
**架构线**（MAA / SRC / MXU / MFAA / ok-script / 多引擎）定义见 [script-frontend-architectures.md](./script-frontend-architectures.md)。

---

## 架构线 → 本仓参照

| 架构线 | `ScriptType` | 新专项开场上：请用户**贴脚本/Git 仓库**（Agent 读后判型）或口述是否属下列线 |
|--------|--------------|------------------------------|
| MAA 线 | `MAA` | 是否要 MAA 式配置遮罩、关卡/理智、MAA 计划表？ |
| SRC 线 | `SRC` | 是否 Alas/SRC 系 exe（如 [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) 同类）+ 脚本大表单 + 用户 Section？同框架扩展见 [examples-src.md](./examples-src.md)。 |
| MXU 线 | `MaaEnd` | 是否 [MaaEnd 项目](https://github.com/MaaEnd/MaaEnd) + [MXU](https://github.com/MistEO/MXU)（PI V2）？需 `mxu-*.json` / ScriptConfig 遮罩？详见 [examples-maaend.md](./examples-maaend.md)。 |
| MFAA 线 | `M9A` | 是否 [M9A/MaaFramework](https://github.com/MAA1999/M9A) 类管线 + 任务队列 JSON？任务勾选/顺序语义是否对齐 [MFAA↔interface.json](https://github.com/trler/MFAA)？详见 [examples-m9a.md](./examples-m9a.md)。 |
| General | `General` | 是否先走通用再专项化？ |
| ok-script 家族（Okww） | `Okww` | 是否 [OK-WW](https://github.com/ok-oldking/ok-wuthering-waves) / ok-script：`-t`/`-e` CLI + 本体 GUI 配置？见 [examples-okww.md](./examples-okww.md)。 |
| ok-script 家族（OkNte） | `OkNte` | 是否 OK-NTE 子项目？请单独确认其 CLI、配置目录和原生 GUI，不得套用 Okww 契约。 |
| 多引擎编排线 | `HSR` | 是否需要**一个类型同时编排多个上游脚本**、按任务模块分配引擎？见 [examples-hsr.md](./examples-hsr.md)。 |

## 表面对照总表

| 表面 | MAA 线 | SRC 线 | MXU 线（MaaEnd） | MFAA 线（M9A） | ok-script（Okww） | ok-script（OkNte） | 多引擎（HSR） | General |
|------|--------|--------|------------------|----------------|---------------------|----------------------|----------------|---------|
| Hub 片段 | `maa` | `src` | `maaend` | `m9a` | `okww` | `oknte` | `hsr` | `general` |
| ScriptEdit | `MAAScriptEdit` | `SRCScriptEdit`（单文件大表单） | `MaaEndScriptEdit` | `M9AScriptEdit` | `OkwwScriptEdit` | `OkNteScriptEdit` | `HSRScriptEdit` | `GeneralScriptEdit` |
| UserEdit 编排 | `MAAUserEdit` | `SRCUserEdit` | `MaaEndUserEdit` | `M9AUserEdit` | `OkwwUserEdit` | `OkNteUserEdit` | `HSRUserEdit` | `GeneralUserEdit` |
| Section 目录 | `MAAUserEdit/` | `SRCUserEdit/` | `MaaEndUserEdit/` | `M9AUserEdit/` | 单文件编排 | 按子项目确认 | **两处并存**：`EditView/User/HSRUserEdit/` + `views/HSRUserEdit/` | （较少拆分） |
| ScriptConfig 遮罩 | 有 | 视需求 | 有 | 通常无 | 有：脚本级 + 用户级 + 直控 | 按子项目确认 | 无 | 无 |
| 计划表 | `MaaPlanTable` | — | `MaaEndPlanTable`（#152） | — | — | — | — | — |
| 任务队列 UI | — | — | TaskConfigSection | `TaskQueueSection` + draggable | `TaskIndex` + DailyTask 字段 | 按子项目确认 | `ManagedTaskSection` + `DynamicManagedFields`（后端下发字段定义） | — |

---

## Hub：`Scripts.vue` 分支模式

所有专项共用同一模式（宜复制一段后改类型名）：

```typescript
// 编辑脚本
if (script.type === 'MaaEnd') {
  router.push(`/scripts/${script.id}/edit/maaend`)
} else if (script.type === 'M9A') {
  router.push(`/scripts/${script.id}/edit/m9a`)
}
// …
```

创建脚本时 `editPath` 三元链同理（`handleConfirmAddScript`）。**新增类型必须补全所有入口**，漏一处即「列表能点、创建不能进」。

---

## 用户编辑编排模式

### A. Section 组合（MaaEnd / M9A / MAA / SRC）

```vue
<!-- EditView/User/MaaEndUserEdit.vue（结构摘要） -->
<MaaEndUserEditHeader … @handle-maa-end-config="…" />
<a-form :model="formData">
  <BasicInfoSection :form-data="formData" @save="handleFieldSave" />
  <TaskConfigSection … />
  <NotifyConfigSection … />
</a-form>
```

- `getDefaultXxxUserData()` 在编排页内或 composable  
- `handleFieldSave(group, key, value)` → `updateUser` 局部更新  

### B. ScriptConfig 遮罩表面（MAA / MaaEnd / Okww）

- `teleport` 全屏 `mask`  
- `useWebSocket` + `TaskCreateIn` 启动 ScriptConfig 任务  
- Header 上「配置 xxx」按钮触发  

**MFAA 线（`M9A`）不适用**：专项配置在 Vue 里写 `M9AUserConfig` / 任务 JSON，**不**用 ScriptConfig 调 Avalonia 壳；自动跑依赖写盘 + 启动 `exe`，见 [examples-m9a.md](./examples-m9a.md)。

Okww 同时有脚本级共享、用户级和直控配置入口，目标 ID 与配置来源共同决定 owner。OkNte 不自动复用这套会话或配置语义；新类型若需外置程序配置 UI，先对照对应子项目的任务生命周期，不复制两套未收尾的遮罩逻辑。

**多引擎线（`HSR`）不适用**：HSR 没有 `ScriptConfig.py`，任务模式只有 `AutoProxy` 与 `ManualReview`。托管配置由后端 `GET /api/scripts/hsr/managed-config` 下发字段定义，前端动态渲染后写回 `Managed.Options`；直控通过 `POST /api/scripts/hsr/direct-config/import` 导入加密的原生配置快照。见 [examples-hsr.md](./examples-hsr.md)。

### D. 能力驱动的动态字段（HSR）

```vue
<!-- EditView/User/HSRUserEdit/DynamicManagedFields.vue（结构摘要） -->
<!-- 按后端 HSRManagedField 的 type / options 渲染，不逐字段硬编码 -->
<component :is="controlFor(field.type)" v-for="field in fields" :key="field.key" … />
```

- 字段定义来源：`useHSRPluginApi().getManagedConfig()`
- 可用引擎与任务清单来源：`useHSRPluginApi().getCapabilities()` 的 `effective_engines` / `tasks`
- 新增托管字段扩展后端字段定义，**不**在 Vue 里加分支

### C. 单文件 ScriptEdit（SRC）

- 脚本级字段全部在 `SRCScriptEdit.vue`  
- `form-section` + `@blur="handleChange('Info', 'Name', …)"`  
- 适合：**脚本编辑复杂、用户编辑已 Section 化**（#727aafb）

---

## Section 组件约定

```vue
<!-- views/SRCUserEdit/BasicInfoSection.vue 风格 -->
<script setup lang="ts">
const props = defineProps<{ formData: …; loading: boolean }>()
const emit = defineEmits<{ save: [group: string, key: string, value: unknown] }>()
</script>
```

- 标签带 `a-tooltip` + 领域中文说明  
- 不直接调 API，由编排页 `handleFieldSave` 统一提交  

---

## 类型层：`types/script.ts`

- `ScriptType` 联合增加字面量  
- `XxxScriptConfig` / 默认 user 结构可与 OpenAPI 生成类型对齐，**手写扩展放本文件**  

## `useScriptApi.ts`

- 在现有 `switch (type)` / 分支中增加默认值与序列化  
- 与 `e5d72bdb` 一致：**扩展而非替换**  

---

## 选型建议（确认架构线后）

| 用户确认的架构线 | 优先参照 |
|----------------|----------|
| MFAA 线 | [examples-m9a.md](./examples-m9a.md)（[M9A](https://github.com/MAA1999/M9A) / [MFAA](https://github.com/trler/MFAA)）、`M9AUserEdit` |
| MXU 线 | [examples-maaend.md](./examples-maaend.md)（[MaaEnd](https://github.com/MaaEnd/MaaEnd) / [MXU](https://github.com/MistEO/MXU)）、遮罩 + 计划表（若需要） |
| MAA 线 | `MAAUserEdit`、`MaaPlanTable` |
| SRC 线 | [examples-src.md](./examples-src.md)、`SRCScriptEdit` |
| ok-script 家族（Okww） | [examples-okww.md](./examples-okww.md)、`OkwwScriptEdit`、`OkwwUserEdit` |
| ok-script 家族（OkNte） | `OkNteScriptEdit`、`OkNteUserEdit`，按 OkNte 原生契约单独适配 |
| 多引擎（HSR） | [examples-hsr.md](./examples-hsr.md)、`HSRScriptEdit`、`HSRUserEdit` + `DynamicManagedFields`、`useHSRPluginApi.ts` |
| General | `General*` 编辑页，再逐项专项化 |

---

## 提交前表面走查

- [ ] `router/index.ts` 路由名与 Hub 片段一致  
- [ ] `Scripts.vue` 创建/编辑/用户 共 4+ 处分支已加  
- [ ] `ScriptTable.vue` 图标与操作（若有专项按钮）  
- [ ] `assets/*.png` 与列表展示  
- [ ] 计划/队列若需要，registry 已注册  
