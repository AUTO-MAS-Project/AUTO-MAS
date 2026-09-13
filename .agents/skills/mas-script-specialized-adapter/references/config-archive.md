# 配置存档（Archive）：收录什么、何时存、存到哪

> 适用：专项把「运行或配置会话前会被 MAS 触碰的配置文件」做**跨会话持久快照**
> 时。本文件讲「存」这一半——**收录逻辑、归档时机、目录布局、去重保留、预览
> 内容的来源**；「读」的那一半（恢复语义、前端弹窗一致性、可自定义点、调用
> 方法）见 [config-restore.md](config-restore.md)。
>
> 原语在 `app/utils/config_archive.py`，只做文件级快照/回写，不认识任何脚本结构；
> 「什么算配置、何时存、恢复后干嘛」由专项负责。
>
> 参考实现（按优先级）：
> - **OkNte**（首选范本，Folder/File 双模式 + 运行时双池）：
>   `app/task/OkNte/tools/backup_archive.py`
> - ZzzOd（整目录/文件集两视角 + 槽排除 + MAS 终态物化）：
>   `app/task/ZzzOd/tools/backup_archive.py`

---

## 1. 存档逻辑（整体流程）

```
专项在「动手前」喂备份对象 + store_root ─→ 原语时间戳归档/指纹去重/保留清理
 ─→ 备份池 {store_root}/<时间戳>/ ─→ 读档时按时间倒序列出、预览、恢复
```

### 1.1 归档时机（固定三时机 + 覆盖性操作）

| 时机 | 存什么 | 触发方 |
| --- | --- | --- |
| 进入编辑页 | 脚本**原生配置**原始态（MAS 触碰前） | 前端 `onMounted` → ensure(native) |
| 退出编辑页 | **MAS 侧配置终态**（编辑会话包络） | 前端 `onUnmounted` → ensure(mas) |
| 运行/会话下发前 | 双池（mas 下发源 + native 原生现状） | OkNte：native 在 `manager.prepare` 任务级一次、mas 在专项 `set_<script>` 最前面（按用户）；ZzzOd：`_prepare_injection` 单处双归档（后端钩子） |
| 导入/恢复等覆盖性操作前 | 将被覆盖的目标配置 | 专项操作函数内，`force=True` |

- 全部**指纹去重**：与最近一份一致则跳过（读档列表里不重复出现）。
- 归档**必须 `suppress` + 日志**，绝不阻断业务（归档失败不中止运行/会话）。
- 恢复前必须 `force=True` 归档当前——保证「恢复前的配置」有独立时间戳条目，
  误恢复可找回。

### 1.2 去重 / 保留 / 强度

- 去重：原语对文件集算指纹（相对键 + 大小 + 字节），与最近一份相同即跳过。
- 保留：每个 store_root 独立保留池，超出清理最旧，默认 `KEEP_COUNT = 10`。
- `force=True`：内容一致也强制归档（恢复前存底）。
- 目录名即时间戳 `%Y%m%d-%H%M%S`，同秒冲突自动加 `-N` 后缀。

### 1.3 目录布局（专项独立，互不干扰）

mas（MAS 侧用户配置）池按脚本、按用户分目录；native（脚本原生配置）池分两级：

```
data/OkNteBackups/                    ← 原生池「项目级根」（跨脚本共享、不随脚本删除）
└── native/{fingerprint}/…            ← 脚本原生配置池（script 级，物理根指纹分桶）
    └── 20260910-215808/…             ← 单份时间戳归档
data/{script_id}/OkNteBackups/
└── mas/<user_id>/…                   ← MAS 侧用户配置池（user 级，按用户分）
    └── 20260910-215808/…             ← 单份时间戳归档
```

- **项目级（自包含式适配器默认，OkNte/ZzzOd 原生池）**：native 挂到项目级根
  （`data/{Script}Backups`，脚本目录之外）并按**物理配置根指纹分桶**——
  `config_root_key(路径)` = 规范化绝对路径的短哈希：同一份物理配置无论被哪
  个脚本引用都归同一个池，跨脚本共享、不随脚本删除（同一路径必然同格式，
  不会混池）。
- **脚本级（通用适配器兜底，如 General）**：native 仍挂在自己脚本目录下
  `data/{script_id}/{Script}Backups/native`——配置路径可随意更改、无法判定
  软件身份，项目级会键漂移混池。
- **判定标准**：能否明确「路径对应的软件」——能（专项安装目录/配置路径）才
  允许项目级；不能（通用脚本任意路径）保持脚本级或明确警示风险。

布局函数（`project_backup_root` / `mas_backup_root` / `native_backup_root(config_path)`
/ `mas_config_dir`）必须落在专项模块内，命名与路径规则对齐 OkNte 范本。

## 2. 存档内容（什么算「配置」由专项收集函数决定）

原语只认识 `{相对键: 文件路径}` 的文件集（`archive_files`）或整目录
（`archive_dir`）。**什么进存档**是专项职责：

- 专项收集函数（如 OkNte `collect_config_files(config_path, mode)`）换算
  「配置路径 + 模式」→ 文件集：
  - `Folder` 模式：`dir_files(config_path)` 整目录；
  - `File` 模式：单文件 `{文件名: 路径}`；
  - 配置不存在 / 目录为空 → 返回 `None`（不产生空备份）。
- **空名路径守卫是硬性要求**：`ConfigPath` 为空时 `Path('')` 解析为 `.`，
  不守卫会把整个仓库递归归档进池（OkNte 已踩坑）——收集函数第一行
  `if not config_path.name: return None`，必须配单测。
- 排除运行时内容（Temp、进程临时文件、会随运行变化的 sidecar）由收集阶段的
  过滤负责；ZzzOd 例：整目录存档时排除 `MAS-` 槽（那是运行时注入目标，不是
  要存档的基线）。

## 3. 适配性（不同专项的差异如何被接口吸收）

| 专项差异 | 吸收方式 | 谁写的 |
| --- | --- | --- |
| 配置是整目录 / 单文件 / 多路径 | `archive_dir` / `archive_files` / 收集函数多文件 | 原语参数 + 专项收集 |
| 槽/目录布局不同 | `store_root` 由专项定义（布局函数归专项） | 专项 |
| 保留份数不同 | `keep` 参数 | 专项 |
| 恢复后语义（字段回填/重建视图/清残留） | 专项恢复后钩子；原语只回写文件 | 专项 |
| 运行中实时共享配置文件 | 用专项既有锁（SRC 式）防恢复与运行抢文件 | 专项 |
| 非文件状态（注册表分辨率、进程态） | 原语不覆盖，专项自理 | 专项 |
| **MAS 侧「终态」在 UserData 字段而非文件副本** | **必须先把字段物化进副本再归档**（见 §3.1） | 专项 |

### 3.1 「MAS 侧终态」陷阱（ZzzOd 案例，必读）

目录副本类专项（OkNte：MAS 目录里就是用户配置，天然终态）直接存档即可。

字段化 + 物化副本类专项（ZzzOd）：**账号字段与 AppList 编排都只存在
UserData 字段**，备份池物化的是绑定槽目录，而槽只有「在一条龙内配置」
会话或运行时才被注入——直接快照会**漏掉账号（账号/密码/游戏路径/区服/
语言/B服名）与刚保存的编排，预览读取与恢复回填都会把它们清空**。

解法：**「以本页配置为准」的 MAS 槽快照一律走唯一入口**
`archive_mas_config_backup(script_id, slot, slot_dir, user_config, force=, meta=)`
（内部先物化账号+编排进槽再快照：账号写非空字段、编排整表含未启用项、
与注入同款写盘、不清运行记录；账号缺省不落盘、槽内既有值保持）；编辑页
退出 / 会话启动 / 运行注入前 / 实例导入覆盖前 / 恢复前存底全走它，**禁止
直接调裸快照 `archive_mas_backup`**——正是曾漏物化导致备份缺账号。拿不准
「终态」真实位置时，先问用户确认（见 §6）。

## 4. 专项调用样例

### 4.1 OkNte（Folder/File 双模式，最小可复制）

```python
# app/task/OkNte/tools/backup_archive.py（节选，签名与实装一致）
def native_backup_root(config_path: Path) -> Path:
    """项目级原生池：data/OkNteBackups/native/{物理根指纹}，跨脚本共享。"""
    return project_backup_root() / "native" / config_root_key(config_path)

def archive_native_backup(config_path: Path, mode: str):
    files = collect_config_files(config_path, mode)
    if files is None:
        return None
    return archive_files(files, native_backup_root(config_path), keep=KEEP_COUNT)

def restore_native_backup(config_path: Path, ts: str, mode: str) -> None:
    # 1) 恢复前 force 归档当前（误恢复可找回）
    archive_files(
        collect_config_files(config_path, mode) or {},
        native_backup_root(config_path), keep=KEEP_COUNT, force=True,
    )
    # 2) 回写：Folder 用 restore_dir 整目录替换；File 模式抄回原文件名
    backup = get_backup_dir(native_backup_root(config_path), ts)
    if backup is None:
        raise ValueError(f"备份不存在: {ts}")
    if mode == "Folder":
        restore_dir(native_backup_root(config_path), ts, config_path)
    else:  # File
        for rel, src in dir_files(backup).items():
            src.replace(config_path.parent / rel)   # 写回同目录同名文件
    # 3) 恢复后语义（如有）放这里：字段回填 / 重建视图 / 清残留（原语不管）

def archive_mas_runtime_backup(script_id, user_id) -> None:
    """运行/会话下发前归档 mas 下发源；失败只记日志，绝不抛出。"""
    with suppress(Exception):
        archive_mas_backup(script_id, user_id, mas_config_dir(script_id, user_id))
```

挂点分两处：`manager.prepare`（任务级、任何下发之前）调 `archive_native_backup(...)`
**一次**——原生配置物理上跨用户共享，只在任务级归档一次代表「本轮动手前的原生
状态」，放到按用户/重试的 `set_<script>` 里会把上一轮下发的 MAS 配置误当原生
内容挤进保留池；`ScriptConfigTask.set_<script>` 最前面（kill 进程之后、任何
覆盖动作之前）调 `archive_mas_runtime_backup(...)` 归档按用户的 mas 下发源。
前端 `onMounted / onUnmounted` 走 `/backup/ensure`（见读档文档 §2）。

### 4.2 ZzzOd（整目录 / 文件集两视角）

- MAS 槽配置快照走统一入口 `archive_mas_config_backup`（先物化账号+编排进槽
  再快照，见 §3.1）；原生配置用收集函数 + `archive_files` 存文件集；
- 恢复回调内先 `force=True` 归档当前再 `restore_dir` 回写。

## 5. 原语与可自定义接口清单

### 5.1 固定接口（`app/utils/config_archive.py`，**签名不可改**）

| 函数 | 职责 |
| --- | --- |
| `archive_dir(src, store_root, *, keep=KEEP_COUNT, force=False)` | 整目录快照；内容一致跳过，返回时间戳目录或 None |
| `archive_files(files, store_root, *, keep=KEEP_COUNT, force=False)` | 文件集快照（`{rel_key: Path}`），保留相对结构 |
| `restore_dir(store_root, ts, target)` | 整目录回写 `target`（先删后拷） |
| `list_times(root)` | 时间倒序时间戳 |
| `get_backup_dir(store_root, ts)` | 定位单份归档；非法/不存在返回 None |
| `dir_files(source)` | 目录 → 相对文件集 |
| `file_set_hash(files)` | 文件集指纹（rel 键 + 大小 + 字节） |
| `config_root_key(config_path)` | 物理配置根的稳定身份指纹（规范化绝对路径短哈希），项目级原生池分桶用 |

### 5.2 专项必须提供 / 可自定义的接口（放专项模块）

| 接口 | 可自定义内容 | 必须满足的约束 |
| --- | --- | --- |
| 布局函数 | 目录名、池分法、是否按用户分目录 | 统一 `<Script>Backups/{pool}` 命名 |
| 收集函数 | 什么算配置、排除规则、多路径合并 | 空名守卫；不存在 → None；可单测 |
| 归档时机 | 在「动手前」编排挂点 | 三时机 + 覆盖性操作前，suppress |
| 归档强度 | `keep`、是否 `force` | 恢复前必 force |
| 预览构建器 | 摘要行内容、行数/值长上限、结构 | 载荷 dict；见 §6 预览规则 |
| 恢复后语义钩子 | 字段回填/重建视图/清残留 | 在恢复函数内、原语之后 |

**红线**：不往公共原语加专项分支或 any 类型参数；专有逻辑一律进专项或邻近
helper。

## 6. 预览内容规则（内容侧；展示侧见读档文档 §4）

预览能看到什么，取决于**存档收录了什么 + 预览构建器输出什么**。遵循通用原则，
超越原则的判断交给用户（见「AI 必须提问」）。

### 6.1 放预览（应可读、有业务含义）

- **编排/主配置摘要**：用户打开编辑页最关心「我编排了什么」。
  - ZzzOd：编排清单（AppList 任务 `{app_id, app_name, enabled}`）；
  - OkNte：任务配置两件套（`DailyRoutineTask.json` + `DailyRoutineTaskConfigs.json`），
    一行一个事实，任务用「已启用任务：…」聚合。
- 一行一个键值对，键尽量用业务词（有字段标签字典用字典）。

### 6.2 不放预览（即使存档里有）

| 内容 | 原因 |
| --- | --- |
| 运行时临时文件 / 进程态 | 非用户可读配置 |
| `_` 前缀内部框架字段 | 与用户业务无关 |
| 敏感凭据 / 密钥字段 | 预览是纯读弹窗，但默认不展示密文 |
| 单一备份内的海量文件 | 预览弹窗限高滚动，撑爆没法读 |
| 无可展示摘要的文件 | 空卡无意义——构建器应跳过（OkNte 案例：顶层全嵌套对象的文件需展一层，否则整卡消失） |

### 6.3 摘要行与载荷约束

- 行数上限（OkNte `_SUMMARY_ROW_LIMIT=8`）、值长上限（`_SUMMARY_VALUE_LIMIT=50`），
  超长截断。
- **载荷必须是 dict**（通用响应模型的 `data` 字段；返回 list 会校验炸 500，
  OkNte 踩过）。文件集结构挂 `files` 键；字段型专项用 `#preview` 插槽自由结构。
- 备份不存在抛 `ValueError`（由服务层转 400/中文提示）。
- 其余文件**全部**走「查看详细配置」：恢复该时点 + 拉起查看会话在原生 GUI 里看
  （见读档文档 §5）。

### 6.4 AI 必须主动提问（拿不准就 AskUserQuestion，别猜）

接入存档时遇到下列二义性，**先问用户再写代码**，选项里给出建议项：

1. **备份对象模糊**：哪些目录/文件算「配置」？哪些要排除（运行时产物、账号
   缓存、凭据）？
2. **配置路径模式**由用户配置决定（Folder/File/多路径），收集逻辑拿不准时。
3. **预览放什么、不放什么**：超出 §6.1/§6.2 通用原则的业务取舍（如“某个文件
   摘要很重要，要不要进预览”）。
4. **恢复后语义**：恢复需不需要字段回填到 MAS 表单 / 重建合成视图 / 清 sidecar。
5. **MAS 侧「终态」真实位置**：在 UserData 字段还是文件副本（§3.1 陷阱）。
6. **敏感内容与保留份数**：凭据是否落盘、keep 是否要改默认 10。

提问模板：说明你的场景 → 列出候选方案 + 影响 → 询问用户选择。**不要**用“默认
行为”一言带过。

## 7. 存档侧检查清单

- [ ] 布局统一 `<Script>Backups/{pool}`，专项独立
- [ ] 收集函数：空名守卫、不存在 → None、排除运行时内容、可单测
- [ ] 三时机齐全（进入 native / 退出 mas / 运行与会话前双池）+ 覆盖性操作前
- [ ] 全部指纹去重；归档 `suppress` 不阻断业务；恢复前 force 存底
- [ ] MAS 终态真实位置确认过（字段类 → 已物化再归档）
- [ ] 预览构建器：只输出「编排/主配置摘要」，载荷 dict，无可展示内容跳过，
      行数/值长有上限
- [ ] 拿不准的备份对象/预览内容/恢复语义已先问用户
- [ ] `tests/task/test_<script>_backup.py` 覆盖：收集（含空名守卫）、去重跳过、
      恢复闭环（含恢复前 +1）、Folder/File、缺目录容错、预览形状