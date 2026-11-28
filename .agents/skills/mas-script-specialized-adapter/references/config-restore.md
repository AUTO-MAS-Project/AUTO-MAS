# 配置读档（Restore）：接入契约与反模式

> 新专项一律主动接入配置恢复（仅确无配置文件落盘可豁免）；归档原语见 [config-archive.md](config-archive.md)。

## 一、三层解耦与接入模板

**通用层零专项分支**：
- **后端基座**：`app/utils/common/config/restore.py`（`RestoreContext` / `ConfigRestorePool` / `build_restore_service`），在 `Config.restore_service()` 加一个 `elif` 懒导入分支即可；通用端点已固定为 `/api/scripts/backup/{list,ensure,restore,preview,file}`，**禁止新增专项端点/模型/门面方法**。
- **前端组件**：`ConfigRestoreSection.vue` + `GuiSessionMask.vue` + `configRestoreMode.ts`（`buildRestoreConfirm` 统一跨来源确认）。
- **接入模式参考**：
  - 自包含式（仅靠 `script_config` + 文件）：`app/task/OkNte/tools/restore_service.py`（目录池）、`Okww`/`MAA`/`MaaEnd`（目录+侧车）、`HSR`/`MaaFW`（纯字段侧车）。
  - 服务装配式（需跨托管集合/建号）：`ZzzOd`（从 `ctx.config` 注入窄能力，池函数调专项服务）。

```python
# 池声明最小骨架：普通函数显式收 RestoreContext（禁闭包捕获），backup_root 返回 None 报无变化不抛错
RESTORE_POOLS = [
    ConfigRestorePool(
        key="mas",
        kind="user",  # user 池恒在前，决定前端 segmented 顺序
        mas_base="tri_state",  # tri_state | user_only | sidecar_only（仅 user 池可声明）
        files=_mas_files,  # 返回 dict[rel_path, Path | str | bytes] | None
        backup_root=_mas_root,
        set_base=_set_base,  # tri_state 必填：跨来源恢复时写回 Info.Base
        preview=_preview_mas,  # 可选；勿手拼 files 字段，基座自动注入
        restore=_restore_mas,  # 回调内先 force=True 存底当前配置，再恢复/回填
    ),
    ConfigRestorePool(
        key="native",
        kind="script",
        files=_native_files,
        backup_root=_native_root,
        restore=_restore_native,
    ),
]
```

## 二、高频反模式与真实事故解读（必读）

| ❌ 错误做法（反模式） | 💥 会导致什么真实事故 | ✅ 正确做法 |
| --- | --- | --- |
| 三态专项按共享目录 `Default` 分桶 | 多账号共享同一个池，账号 A 会看到并恢复账号 B 的覆盖层侧车，造成**跨账号污染 `UserData`**（Okww 踩过） | **分桶恒按账号** `mas/{user_id}`；只有恢复目标路径才按三态 owner 解析 `Default` / 账号目录 |
| `ScriptConfigTask` 硬编码账号目录，而 `AutoProxy` 按 `Default` 读 | 共享来源账号在原生 GUI 改完后运行时根本不读，且退出归档因目标目录不对**静默跳过、不生成备份**（MAA 踩过） | **会话包络 = 运行包络 = 归档目标**，三处共用同一套 `_mas_owner` 规则，且归档前确保目录已播种 |
| `onUnmounted` 并行调 `stopSession()` 和 `ensure('mas')` | 与 `final_task` 的 `rmtree/copytree` 回写撞车，**归档到写到一半的损坏目录** | 严格串行：`await stopSession()` → `await ensure('mas')`；新建账号 `onMounted` 先 `await loadScriptInfo()` 再 `ensure('native')` |
| `tri_state` 池只设 `mas_base` 不传 `set_base`，或运行前归档漏传 `base` | 跨来源恢复时文件写回去了但 `Info.Base` 没切回（半恢复）；漏标 `base` 会被当旧备份跳过切来源 | `tri_state` 必须同时提供 `set_base`，且**所有**归档入口（含运行前/恢复前 force）均显式传入 `base` |
| 恢复时把 `Info.Base` 也从侧车回填回 `UserData` | 恢复旧备份会**静默翻转用户当前的共享/独立来源**，导致后续全读写错目录 | `Info.Base` 等决定路径的危险字段**只进预览、排除出回填** |
| 通用性专项（General / MaaFW）把 native 池放全局 `data/XxxBackups/native/` | 通用性专项的项目属于单个托管，删托管后留一堆无主跨托管垃圾备份 | 仅多托管真共享的外部目录（SRA/BGI）用全局指纹桶；通用性专项必须**收敛到托管级** `data/{sid}/{Xxx}Backups/native/{config_root_key}` |
| 兜底恢复按钮条件只写主入口条件的一半（如只写 `!dailyStageEngine`） | 当主入口同时受 `controlMode === 'managed'` 约束时，原生模式+有引擎会导致**主入口和兜底按钮双双消失**（HSR 踩过） | 兜底条件必须是主入口不可见条件的**完整补集**；`@click` 用单表达式或方法（防 oxfmt 折叠多语句炸模板） |
| 预览只在 `#preview` 插槽里再画一遍文件列表，或漏接 `api.readFile` | 页面出现两个重复文件区；漏接 `readFile` 点备份文件直接报不支持 | 预览摘要区只展示核心业务字段（两池同概念同标签、敏感值脱敏、源码固化词表不读本体）；文件列表统一交基座 `raw.files`，**必填 `api.readFile`** |
| 「查看详细配置」确认弹窗写“即将注入/回写备份目录” | 暴露后端内部机制，误导普通用户不敢点 | 照抄共用词条 `configRestoreDetailView` / `configRestoreDetailConfirm`（只说临时覆盖当前配置、勿同时运行同名脚本） |
| 只单测预览载荷构造函数，不直接测池回调 | `_preview_mas` 签名改动漏改调用点时，单测全绿但线上预览 500（MaaEnd 踩过） | 必须有**直接调用池回调**（`snapshot`/`preview`/`restore`）的测试，并跑通 `tests/utils/test_config_restore.py` |

## 三、查看会话（`viewOnly`）固定流程

- 前端固定顺序：`Modal.confirm(buildRestoreConfirm)` → `api.restore` → 关弹窗 → `startSession(userId 或 scriptId, true)`；查看会话 30 分钟静默关闭（配置会话提前 30 秒提醒并自动保存）。
- 后端 `ScriptConfigTask` 收到 `view_only=True`：托管级跳过下发、账号级按专项形态决定是否下发，**`final_task` 跳过一切回写**（原生现场由 manager 任务前快照还原）。
