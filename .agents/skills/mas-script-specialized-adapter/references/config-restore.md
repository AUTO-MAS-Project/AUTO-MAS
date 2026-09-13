# 配置读档（Restore）：恢复语义、前端展示与调用方法

> 适用：专项需要在用户/脚本配置页提供「配置恢复」（历史备份列表 / 预览 /
> 查看详细配置 / 一键恢复）时。本文件讲「读」的完整链路——**恢复了什么、
> 后端怎么调、前端通用封装的一致性、专项可自定义点、查看会话**；「存」的那
> 一半（收录逻辑、时机、布局、预览内容来源）见 [config-archive.md](config-archive.md)。
>
> **接入前先定模式**：守卫/预览/快照/恢复只依赖 `script_config` + 备份文件
> → **自包含式**（逻辑全在专项 tools，范本 OkNte）；需操作门面全局状态
> （字段回填/合成视图/跨脚本锁/凭据加密落盘）→ **薄委托式**（池函数委托
> `ctx.config`，范本 ZzzOd）。两种模式池声明接口一致，同一专项不同池也可
> 分开选。
>
> 已解耦为三层，**通用层零专项分支**：
>
> - **服务层**：`app/utils/config_restore.py` —— `RestoreContext` /
>   `ConfigRestorePool` / `build_restore_service`。专项只声明池表（普通函数，
>   显式收 `RestoreContext`，可直接单测），门面 `Config.restore_service()` 按
>   脚本类型分发，一次性绑定上下文。HTTP 层只有一组通用端点。
> - **前端组件**：`frontend/src/views/EditView/User/components/ConfigRestoreSection.vue`
>   —— 恢复弹窗 + 预览弹窗 + 一键恢复，props 全部参数化，`#preview` /
>   `#preview-title` 插槽开放。
> - **会话遮罩**：`frontend/src/components/GuiSessionMask.vue` —— 拉起原生 GUI
>   时全屏遮罩，纯 UI，与会话状态解耦。
>
> 参考实现（按优先级）：
> - **OkNte（自包含式）**：`app/task/OkNte/tools/restore_service.py` +
>   `useOknteGuiSession.ts` + `OkNteUserEdit.vue`
> - ZzzOd（门面委托式）：需要门面内部状态时池函数经 `ctx.config` 薄委托**公开**
>   方法，内部 helper 留在门面

---

## 1. 读档内容（恢复什么）

### 1.1 双目标池

| 池 | `kind` | 恢复作用于 |
| --- | --- | --- |
| `mas`（MAS 用户配置） | `user`，**恒在前** | MAS 侧目录副本 / 触发字段回填 |
| `native`（脚本原生配置） | `script` | 脚本本体原生配置目录 |

池表顺序 = 前端 segmented 展示顺序。`key` 任意（`mas`/`onedragon`/`native`…），
非法 key 由服务层统一 400。

### 1.2 恢复关键语义

- **恢复前强制归档当前**（`force=True`）——「恢复前的配置」必有独立时间戳条目，
  误恢复可找回。池函数的 `restore` 回调自理（见存档文档 §1.1）。
- **MAS 终态陷阱**：恢复 mas 备份会回到该时点的目录副本；字段化 + 物化副本类
  专项（ZzzOd）恢复后需要**字段回填**到 UserData 表单（否则旧表单值下次保存会
  全量写回、静默撤销恢复）。回填逻辑在专项（见存档文档 §3.1）。
- **查看会话（viewOnly）结束不回写**配置——原生现场由 manager 任务前快照还原
  （「临时注入，看完还原」），详见 §5。

## 2. 后端调用方法

### 2.1 池声明（专项唯一要写的接入逻辑）

```python
# app/task/OkNte/tools/restore_service.py（节选，签名与实装一致）
from app.utils.config_restore import ConfigRestorePool

RESTORE_SCRIPT_NAME = "ok-nte"      # 专项统一名（文案 {script} 插值，不是脚本实例名）

async def _list_mas(ctx) -> list[str]:
    return list_mas_backups(ctx.script_id, ctx.user_id)

async def _preview_mas(ctx, ts: str) -> dict:
    return _preview_payload(ctx, ts, get_mas_backup_dir(ctx.script_id, ctx.user_id, ts))

async def _restore_mas(ctx, ts: str) -> object:
    _user_guard(ctx)  # 守卫在池函数内（自包含优先；需门面内部状态时经 ctx.config）
    restore_mas_backup(ctx.script_id, ctx.user_id, ts,
                       mas_config_dir(ctx.script_id, ctx.user_id))
    # 字段回填等恢复后语义放这里

async def _snapshot_mas(ctx) -> dict:
    dest = archive_mas_backup(ctx.script_id, ctx.user_id,
                              mas_config_dir(ctx.script_id, ctx.user_id))
    times = list_mas_backups(ctx.script_id, ctx.user_id)
    return {"created": dest is not None, "time": times[0] if times else ""}

RESTORE_POOLS = [
    ConfigRestorePool(key="mas", kind="user", list_backups=_list_mas,
                      preview=_preview_mas, restore=_restore_mas, snapshot=_snapshot_mas),
    ConfigRestorePool(key="native", kind="script", ...),  # 同上，脚本级
]
```

要点：
- 池函数是普通函数，显式收 `RestoreContext(config, script_config, script_id, user_id)`，
  **不闭包捕获** → 可直接单测。
- `snapshot` 返回 `{"created": bool, "time": str}`，供三时机 `ensure`。
- `preview` / `restore` / `snapshot` 可省略（None 表示该池不支持对应能力，服务层
  返回明确错误；`list_backups` 必填）。

### 2.2 分发接线（core 门面，接入时唯一要动的公共文件）

```python
elif isinstance(script_config, OkNteConfig):
    from app.task.OkNte.tools.restore_service import (
        RESTORE_POOLS,
        RESTORE_SCRIPT_NAME,
    )
...
return build_restore_service(
    RestoreContext(config=self, script_config=script_config,
                   script_id=script_id, user_id=user_id),
    RESTORE_SCRIPT_NAME, RESTORE_POOLS,
)
```

新专项接入 = 分发链加一个 elif 分支（懒导入）。**禁止**新增专项端点 / 模型 /
门面包装方法。

### 2.3 服务方法与 HTTP 端点（已存在，勿改勿增）

| 服务方法 | 端点 | 用途 |
| --- | --- | --- |
| `service.list(key)` | `GET /api/scripts/backup/list` | 时间倒序备份列表 |
| `service.ensure(key)` | `POST /api/scripts/backup/ensure` | 三时机按需归档（前端进入/退出编辑页调用） |
| `service.restore(key, ts)` | `POST /api/scripts/backup/restore` | 一键恢复（restore 回调内已含恢复前存底） |
| `service.preview(key, ts)` | `GET /api/scripts/backup/preview` | 预览载荷（`data` 结构由专项定义） |

`target` 是自由字符串，取值由专项池定义；非法 key 统一 400。恢复接口在专项
restore 回调返回对象（前端当前不消费，保留扩展）。

## 3. 前端展示的一致性（通用封装已就位）

`ConfigRestoreSection` 已把恢复弹窗 / 预览弹窗 / 一键恢复做成通用组件，专项
接入 = 传参 + 按需插槽。**共用行为（专项不要各自为政）：**

| 行为 | 约定 |
| --- | --- |
| 弹窗结构 | 顶部 = segmented（双池）+ 备份时间列表；点时间 → 预览弹窗 |
| 一键恢复 | 确认（`Modal.confirm`，共用词条）→ `api.restore` → 成功关弹窗 + `onRestored` |
| 查看详细配置 | 底部按钮，**onDetail 未传时不渲染**（避免无响应按钮）→ onDetail 回调 |
| 预览 | 内置渲染 or `#preview` 插槽；弹窗内 **56vh 限高滚动**（`preview-scroll`），专项不要加滚动容器 |
| 文案 | `{script}` 用 `scriptName`（专项统一名）插值 |
| 预览冲突确认 | 「查看详细配置」确认弹窗：共用词条 `configRestoreDetailView`（标题）/ `configRestoreDetailConfirm`（正文）/ `configRestoreConfirmOk`（确认），红色正文 `h('p')`。**正文必须是用户话术**（§5.1），不写后端机制 |

### 3.1 props（可传参部分）

```vue
<ConfigRestoreSection
  v-model:open="restoreOpen"
  :script-name="OKNTE_DISPLAY_NAME"
  :targets="restoreTargets"            <!-- [{key,kind}] 顺序即展示顺序，user 在前 -->
  :api="restoreApi"                     <!-- {list, preview, restore} 函数 -->
  :field-labels="previewFieldLabels"    <!-- 可选：字段 key → 标题 -->
  :user-desc="..."                      <!-- 可选：覆写描述文案（归档时机措辞不同时） -->
  :script-desc="..."                    <!-- 可选 -->
  :format-value="formatPreviewValue"    <!-- 可选：枚举值 → 词表 -->
  :on-restored="handleRestored"         <!-- 可选：一键恢复成功后（刷新表单等） -->
  :on-detail="handleRestoreView"        <!-- 可选：查看详细配置 -->
>
  <template #preview="{ data, raw, target, formatValue, fieldLabel }">…</template>
  <template #preview-title="{ time }">…</template>
</ConfigRestoreSection>
```

- `api.preview` 响应：兼容顶层 `info/account/tasks/instances` 结构**和**通用端点
  把专项载荷包进 `data` 的形态；`#preview` 插槽的 `raw` 即后端预览响应原文。
- `onRestored(target, item)`：一键恢复成功后父组件处理（mas 恢复含字段回填 →
  刷新表单；脚本级由组件自行刷新列表）。

### 3.2 内置预览渲染（适配的专项直接用，不用插槽）

- `user` 池：基本信息（`info`）+ 账号（`account`）+ 任务编排清单（`tasks`，
  `enabled` 高亮）；
- `script` 池：实例折叠列表（`instances`，每条含 account/tasks）。

预览结构约定（ZzzOd 用这套）：`info` / `account`（`{key,value}`）、`tasks`
（`{app_id, app_name, enabled}`）、`instances`（`{idx, name, active, account, tasks}`）。

## 4. 可自定义点（不符合专项实际情况时才用）

| 项 | 用途 | 说明 |
| --- | --- | --- |
| `#preview` 插槽 | **完全接管预览区** | 字段型专项（M9A/HSR…）用自身结构渲染键值摘要；OkNte 按 `raw.files` 逐文件渲染摘要表 |
| `#preview-title` 插槽 | 覆盖预览弹窗标题/说明 | 缺省「配置预览 · 时间」 |
| `fieldLabels` / `formatValue` | 预览字段标签与枚举词表 | 内置渲染用 |
| `userDesc` / `scriptDesc` | 描述文案覆写 | 专项归档时机措辞与通用不同时（如 ok-nte 无直控模式） |
| `onRestored` / `onDetail` | 一键恢复后动作 / 查看详细配置流程 | `onRestored` 刷新表单；`onDetail` 按 §5.3 固定流程执行（不应自定义流程） |
| 查看会话遮罩 | `GuiSessionMask` 是纯 UI | 专项只控制显示/隐藏与按钮行为，视觉统一复用 |

红线（不可自定义）：
- 通用组件 / 服务 / 端点零专项分支——专项形态不匹配走插槽或专项池函数，**不改
  通用件**。
- 高危操作一律 `Modal.confirm`；预览/弹窗限高且单一滚动主体；遮罩 z-index 不压
  标题栏（遵循 `mas-frontend-ui`）。

## 5. 查看详细配置与查看会话（viewOnly 任务）

### 5.1 面向用户的语义（确认弹窗文案，照抄不多写）

「查看详细配置」对用户只说一句（词条 `configRestoreDetailConfirm`），标题
`configRestoreDetailView`，按钮 `取消` / `configRestoreConfirmOk`（确认）：

> 即将打开脚本页面查看配置，请确保查看期间未运行任何同名脚本，否则可能产生
> 配置覆盖。

- **面向用户只讲「要做什么 + 别运行脚本」，绝不解释后端机制**——恢复/下发/
  复制/注入/回写等内部逻辑一律不写进弹窗：用户不关心实现，写进来反而误导。
- 文案必须**通用、易懂**：不提任何专项独有概念（如「切换任务开关」「编排」），
  专项确有额外会话内提醒时用专项词条叠加，不污染通用词条（见 §6）。
- 误覆盖有保护：恢复前系统先归档当前配置（指纹去重：与已有备份相同则不新增
  条目），可随时找回——这条写进文档与实现，不必写进弹窗。

### 5.2 后端机制（实现备注，**不是用户话术**）

链路已全通用：`TaskCreateIn.viewOnly → dispatch → TaskInfo.view_only →
manager 传参 → ScriptConfigTask`。专项实现时：

- manager spawn 时对 ScriptConfig 模式传 `view_only=self.task_info.view_only`；
- ScriptConfigTask 收 `view_only`，按“临时注入，看完还原”实现：
  - 用户级查看：按专项形态选「照常下发（目录副本型，GUI 所见即备份）」或
    「跳过基线注入（合成视图型，注入即污染）」；
  - 脚本级查看：**跳过下发**（原生目录即刚恢复的备份）；
  - `final_task`：**跳过一切回写**（原生现场由 manager 任务前快照还原）。
- 前端超时策略照 `useOknteGuiSession.ts`：查看会话 30 分钟**静默关闭**；配置
  会话提前 30 秒提醒 + 自动保存。

### 5.3 前端固定流程（对齐一条龙，禁止自创提示语）

```
Modal.confirm(共用词条, 红色正文) → api.restore → 关弹窗
  → startSession(userId, true)   // mas 备份：打开脚本查看页面（备份视角）
  → startSession(scriptId, true) // 原生备份：脚本级查看页面（原生即备份）
```

## 6. 词条规范（zh + en 必做；ja-JP 滞后可接受）

- 通用词条 `edit.configRestore*` 已存在，专项直接用。
- 查看会话词条模板（逐字照一条龙换脚本名）：
  `oknteViewingTitle / ViewingDesc / ViewingDesc2 / ViewClose / ViewOpened /
  SessionOpened / SessionFailed / StopFailed / StartFailed / SessionTimeoutWarn`。
- **清理死词条**：重构后不再被引用的词条从全部语种删除（先 `rg` 确认零引用）。
- 专项统一名只进 `scriptName` / `RESTORE_SCRIPT_NAME`，不散落进词条。

## 7. 前端接入样例（OkNte 完整片段）

```ts
// useOknteGuiSession.ts —— startSession 关键点
const response = await Service.addTaskApiDispatchStartPost({
  taskId, mode: TaskCreateIn.mode.SCRIPT_CONFIG, viewOnly,
})
showOknteConfigMask.value = !viewOnly
showOknteViewMask.value = viewOnly
// 订阅 WS_TASK_NOTICE(error→提示+stop) / WS_TASK_COMPLETED→clearSession
// 超时：viewOnly 静默关闭；否则提前 30s 提醒 + 自动保存
```

```vue
<!-- OkNteUserEdit.vue —— 双遮罩 + 恢复区 -->
<GuiSessionMask
  :open="showOknteConfigMask" :icon="SettingOutlined"
  :title="t('edit.okNteConfigurationProgress')"
  :description="`${t('edit.okNteGuiConfiguration')}\n${t('edit.clickSaveConfigurationWhen2')}`">
  <template #actions>
    <a-button type="primary" size="large" :loading="stoppingOknteConfig"
              @click="handleSaveOkNteConfig">{{ t('edit.saveConfiguration') }}</a-button>
  </template>
</GuiSessionMask>
<GuiSessionMask
  :open="showOknteViewMask" :icon="EyeOutlined"
  :title="t('edit.oknteViewingTitle')"
  :description="`${t('edit.oknteViewingDesc')}\n${t('edit.oknteViewingDesc2')}`">
  <template #actions>
    <a-button type="primary" size="large" :loading="stoppingOknteConfig"
              @click="handleCloseOknteView">{{ t('edit.oknteViewClose') }}</a-button>
  </template>
</GuiSessionMask>

<ConfigRestoreSection v-model:open="restoreOpen" ... :on-restored="handleRestored"
                      :on-detail="handleRestoreView">
  <template #preview="{ raw }">
    <div v-for="f in raw.files" :key="f.name" class="oknte-preview-box">
      <h4 class="oknte-preview-title">{{ f.display_name }}</h4>
      <a-descriptions :column="1" size="small" bordered>
        <a-descriptions-item v-for="r in f.summary" :key="r.key" :label="r.key">
          {{ r.value }}
        </a-descriptions-item>
      </a-descriptions>
    </div>
  </template>
</ConfigRestoreSection>
```

## 8. 检查清单

- [ ] 池表：`kind` user 池在前、script 池在后；`RESTORE_SCRIPT_NAME`=专项统一名，
      与前端 `scriptName` 一致
- [ ] 池函数普通函数收 `RestoreContext`；守卫在池内；非法 key 由服务层 400
- [ ] 分发链加一个 elif 分支即可；**未**新增端点/模型/门面包装方法
- [ ] 恢复回调：先 force 归档当前 → 回写 → 恢复后语义；查看会话结束不回写
- [ ] 恢复按钮放编辑器标题行右侧（`header-actions` 插槽模式），区域唯一按钮；
      无「已保存/未保存」标签、无脏点
- [ ] `onMounted` ensure(native)、`onUnmounted` ensure(mas)+stopSession；遮罩关闭
      watch 刷新表单（配置与查看会话都要）
- [ ] 「查看详细配置」= 确认（共用词条，**正文用户话术 §5.1**）→ restore → 打开
      脚本查看页面（viewOnly）+ GuiSessionMask；流程不做自创变体
- [ ] 预览：内置渲染 or `#preview`（按 `raw` 消费）；56vh 滚动；不额外加滚动容器
- [ ] 词条 zh+en；死词条已清理；`{script}` 用专项统一名
- [ ] `tests/tools/test_config_restore.py`（基座绑定）与 `tests/task/test_<script>_backup.py`
      全绿；typecheck / ruff 通过
- [ ] **未经审核不 commit、不 push**