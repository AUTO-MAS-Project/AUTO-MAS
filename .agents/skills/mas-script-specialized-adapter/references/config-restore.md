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
> - **Okww（自包含式 + 覆盖层侧车）**：`app/task/Okww/tools/restore_service.py` +
>   `useOkwwGuiSession.ts` + `OkwwUserEdit.vue`——mas 池带覆盖层字段侧车，
>   三态专项的池分桶教训见 §1.1
> - **MAA（自包含式 + 任务侧车）**：`app/task/MAA/tools/restore_service.py` +
>   `useMaaGuiSession.ts` + `MAAUserEdit.vue`——mas 池带侧车（Info/Task 两段
>   的 MAS 可配置核心内容），两态 owner；新建用户首次进入必须先等 userId
>   就绪再 ensure；会话包络对齐运行包络的教训见 §1.1.3
> - **MaaEnd（自包含式 + 快速配置侧车）**：`app/task/MaaEnd/tools/restore_service.py` +
>   `useMaaEndGuiSession.ts` + `MaaEndUserEdit.vue`——mas 池带快速配置覆盖层
>   侧车（对齐 ok-ww），脚本/用户/直控三态（直控无 mas 池，见 §1.1.1）；
>   预览为「任务启用罗列 + 配置内容表单」结构，专项要求见 examples-maaend.md
> - **M9A（自包含式 + 纯字段侧车，无会话）**：`app/task/M9A/tools/restore_service.py` +
>   `M9AUserEdit.vue`——MFAA 线无 per-user ConfigFile 目录、无遮罩会话：
>   mas 池是**纯字段侧车**（无目录部分，见 §1.1.4），恢复即字段回填；
>   不提供「查看详细配置」（无 viewOnly 会话可挂，onDetail 不传即不渲染）
> - **General（自包含式 + 无侧车目录池，有会话）**：`app/task/general/tools/restore_service.py` +
>   `GeneralUserEdit.vue`——ConfigFile 恒按用户（无 owner 解耦、无侧车：
>   MAS 编辑页字段不注入原生配置，不属于配置内容，见 §1.1.4 末段）；原生
>   配置为用户自填 ConfigPath（File/Folder 两态），预览为**文件清单粒度**
>   （配置格式任意透传，不解析内容）；提供「查看详细配置」（viewOnly，
>   脚本级跳过下发直接读 `task_info.view_only`，无需构造参数与 manager 透传）
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

#### 1.1.1 池分桶必须按用户，恢复目标才按三态 owner（Okww 教训）

**三态专项（脚本/用户/直控）的「池归属」与「恢复目标路径」是两回事，必须解耦**：

- **池分桶恒按用户**（`mas/{user_id}`）。备份内容若含用户级数据（如 ok-ww 快速
  配置覆盖层字段侧车），按共享 owner（脚本态 `Default`）分桶会把多个用户的
  用户级内容混进同一个池——用户 A 会看到并恢复用户 B 的侧车，回填进自己的
  UserData，跨用户污染。
- **恢复目标路径才按三态 owner**：脚本态 `Default` 共享目录、用户态独立目录、
  直控无 MAS 配置。脚本态多用户各自持有共享目录的快照（内容重复但完整），
  恢复任一备份 = 把共享目录回滚到该用户归档时点（覆盖语义，确认弹窗已提示）。

实现上：池函数一律用 `ctx.user_id` 定位归档根；`mas_dir`（归档/恢复目标）由
专项按 owner 解析后显式传入 `archive_mas_backup` / `restore_mas_backup`。

#### 1.1.2 覆盖层字段侧车（Okww）

MAS 编辑页配置的字段可能**不落盘在被备份的文件里**（ok-ww：快速配置覆盖层
字段存在 UserData，运行时才覆盖进 DailyTask.json）。此时「MAS 用户配置」池要
在 ConfigFile 副本之外**附带一个侧车**（`_mas_overlay.json`）：

- **侧车参与指纹**——只改表单、没动文件也要新建备份（否则表单改动丢备份）；
- **预览展示侧车**（与页面认知同源），不展示 ConfigFile 里那些运行时会被表单
  覆盖、值与页面对不上的字段；
- **恢复文件回滚 + 侧车回填 UserData**（对齐 ZzzOd 字段回填模式），前端重拉
  表单；侧车落地后即从 ConfigFile 分离删除，不污染脚本 GUI；
- 旧版备份（无侧车）文件可正常恢复、预览为空、不回填。

#### 1.1.3 会话包络必须与运行包络同源（MAA 教训）

配置会话的下发源/回写目标必须与运行下发走**同一套 owner 规则**。MAA 脚本态
曾三处两张皮：运行读 `Default`，会话硬编码用户目录，备份跟运行——结果脚本态
用户的会话改动运行时根本不读（改了白改）、退出归档采不到会话现场（指纹去重
静默跳过，「改了配置却不生产备份」）、恢复也写不进会话读取的目录。对齐后三者
才自洽；排查手法：任一采集点不产生新条目时，先核对**该时刻被覆盖的目录**与
**归档目标目录**是否同一个。

另一面：归档目标目录要有**初始化保证**，否则第一次退出归档会静默空转
（目录缺失 → 无内容可归档）。ok-ww 在 add_user 时从本体 configs 播种 owner
目录；MAA 在 mas 快照时播种（MAA 路径可晚于用户配置，播种失败不挡建用户）；
OkNte 的用户目录是页面编辑对象天然存在；ZzzOd 进页即物理化槽位。

#### 1.1.4 无 ConfigFile 目录的专项：纯字段侧车（M9A）

MFAA 线（M9A）的 MAS 用户配置是**字段**（存共享 ScriptConfig.json，运行时
经 build_config 写入原生实例配置），没有 per-user ConfigFile 目录。此时
mas 池是**纯字段侧车**——归档内唯一文件就是 `_mas_overlay.json`，没有
目录部分：

- 侧车同时存**原始值**（Queue JSON 串等，回填 UserData 用）与**展示快照**
  （选项 index 翻译成中文 case 名，预览零本体依赖）。展示快照在归档时经
  任务定义翻译固化；任务定义不可用时降级保存原始值，预览仍可读；
- 自描述值（checkbox 的 selected_cases、输入值）不依赖任务定义直出；
  只有 index 类选项需要定义翻译——**能自描述的不翻译，缺定义的降级不臆造**；
- 恢复 = 回填 UserData（无目录目标、无需播种），恢复前把当前字段终态
  force 归档存底；
- 上游任务/选项定义随版本漂移、无法固化词表时，预览翻译**尽力而为**：
  归档/预览时定义可用（脚本路径存在）就翻译，不可用就显示原始值；
  与 mas 池同口径的 native 反读同此策略。

配套的 native 池形态（M9A 本体 `config/`）：实例配置文件**任意命名**
（M9A GUI 用哈希命名），预览须**全实例反读**并按实例折叠展示（ZzzOd
实例列表同语义），**实例显示名取 JSON 内的名称字段**（如 `InstanceName`），
文件名只作缺失回退——MaaFramework 线的实例文件名普遍不是显示名，只认
固定文件名（如 default.json）会漏掉用户创建的全部实例。

**侧车与否的判据（M9A 有、General 无）**：MAS 编辑页字段**会注入原生
配置**（是配置内容的一部分）→ 进侧车与预览；字段只由 MAS 自己消费
（前后置脚本、来源开关等执行域配置）→ 不进备份。ConfigFile/配置目录
本身的持久副本形态（OkNte 页面编辑对象、General 会话回写副本）同样
无需侧车。

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

### 3.3 预览内容来源约定（专项必读）

**预览必须对用户有区分价值**——用户靠它分辨「这个备份是哪个状态」，而不是
看一份无意义的文件清单：

- **覆盖面下限：至少包含 MAS 侧可配置的核心内容**。MAS 编辑页暴露给用户的
  开关与参数（任务开关、战斗参数、服务器等核心项）原则上**全部进侧车与
  预览**——只收一部分字段、预览与页面认知对不上就是缺陷；不确定哪些算
  「核心」，**列清单请维护者/用户勾选后再实现**，不要自己拍板。
- **mas 池**：优先展示**与页面表单同源的内容**。页面字段不落盘在被备份文件
  时（ok-ww 覆盖层、MAA 任务/战斗参数等），用**侧车**承载并展示（见
  §1.1.2）；页面字段就落盘在被备份文件时（OkNte 的 ConfigFile 即页面编辑
  对象），展示文件内页面管理的关键字段。侧车字段按**「原生对应 / 专项
  独有」分区**展示，**分类按概念映射，不按数据存放位置**——侧车字段的
  备份值本来就只能在预览看到（查看会话注入的是当前值），这不构成独有
  的理由：原生 GUI 有对应概念的字段（任务开关、战斗参数等）归「原生
  对应」区，与原生池同词表同口径；原生 GUI 完全没有的概念（MAS 特有的
  调度/编排字段，如 MAA 的关卡配置模式/活动关优先、MaaEnd 的每日仅执行
  一次）才归「独有」区且全量展示。内容多的专项（十几以上开关）用
  **「任务启用罗列行 + 配置内容表单行」结构**（如 MaaEnd 的「已启用任务：
  A、B」+ 各配置细节表单），比十几行是/否更可读；内容少的（MAA）逐行
  即可。「多种类型二选一」的配置（如 MaaEnd 理智任务的干员养成/武器
  养成/危境预演/基质）要记录**全类型已存配置**而不只当前选中类型——
  备份值只能在预览看，切换类型后其他类型的值就没了；另用一行标明当前
  选中类型。关卡类多槽位字段（主关卡+备选）合成**单一「具体刷什么本」
  行**，与配置界面的折叠摘要同口径（全部槽位禁用 = 原生默认行为，如
  MAA 的当前/上次）；哨兵值翻译以下拉/界面的实际标签为准，不臆造。
  取值文本的翻译用**专项自持的固化词表**（源码/前端 zh_cn 词表摘录），
  **不读本体运行时资源**（预览不应依赖本体安装与版本）；随版本漂移、
  数量大且无法固化词表的枚举（如 MaaEnd 目标武器名）展示**数量**而不
  硬编码臆造译文。影响恢复目标或危险回填的字段（如 MAA/MaaEnd 的配置
  文件来源）只进预览、不参与回填。覆盖层字段被专项开关门控生效的（如
  MaaEnd 快速配置），开关关闭时运行不生效，对应行随门控隐藏（不受门控
  的字段如账号要显式豁免）。
- **native 池**：展示脚本原生配置里**结构稳定、用户关心的字段**；随版本漂移、
  用户读不懂的内部字段不进预览（经「查看详细配置」在原生 GUI 里看）。
  **与 mas 池同字段必须同口径**——同一配置概念（任务开关、服务器、账号、
  战斗参数等）在两池用**同一标签、同一取值文本**（如 MAA 从 gui.new.json
  TaskQueue 反读出与侧车一致的「自动唤醒/理智作战/吃理智药」行；MaaEnd
  从任务 optionValues 反读理智任务/基质选项，取值文本用源码固化 zh_cn
  词表、不读本体运行时资源）；仅隶属一侧的字段（MAA 的当前方案/连接
  地址/启动游戏）才单独展示，两池行集因此允许不同，但重叠部分逐字一致。
- **敏感值脱敏**：账号等敏感字段在预览中脱敏展示（如手机号 `130****6220`），
  侧车原值仍完整保存（恢复需要）。
- **不确定展示什么 = 先询问**：专项对「这个备份对用户意味着什么」拿不准时，
  **先向维护者 / 用户确认预览内容，再实现**；不要自己拍脑袋放几个字段充数。
  预览字段选择是产品决策，不是实现细节。

## 4. 可自定义点（不符合专项实际情况时才用）

| 项 | 用途 | 说明 |
| --- | --- | --- |
| `#preview` 插槽 | **完全接管预览区** | 字段型专项（M9A/HSR…）用自身结构渲染键值摘要；OkNte 按 `raw.files` 逐文件渲染摘要表 |
| `#preview-title` 插槽 | 覆盖预览弹窗标题/说明 | 缺省「配置预览 · 时间」 |
| `fieldLabels` / `formatValue` | 预览字段标签与枚举词表 | 内置渲染用 |
| `userDesc` / `scriptDesc` | 描述文案覆写 | 专项归档时机措辞与通用不同时（如 ok-nte 的脚本级/用户级归档措辞） |
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
- [ ] 池回调（preview/restore/snapshot）要有**直接调用的测试**——只测载荷
      构建函数抓不住签名改动漏改调用点的问题（MaaEnd 曾漏：`_preview_mas`
      旧签名调用致预览 500）
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
