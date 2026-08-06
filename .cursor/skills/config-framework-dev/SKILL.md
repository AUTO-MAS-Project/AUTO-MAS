---
name: config-framework-dev
description: >-
  实现配置基类时的架构约定与编码规范。规格见 配置基类.md。
---

# 配置基类开发约定

- 工作区 / 事务见 §3.2、§3.2.1；信号见 §3.3–§3.4。
- **写路径**：字段 `setattr` / `add` / `remove` / `set_order` / `add_type` / `remove_type` / `reload_type` → 仅 stage，须显式 `await commit()`；`commit` 经 **`manager.node_commit`**（同 Task 嵌套空过；其它 Task 的 `commit` **等待**；持锁期间其它 Task `_stage` **入 pending**，释放时并入）；入口快照并清空 `_staged_ops`，再用 **`while batch` 排空**；**`send` 后若 `_staged_ops` 非空则 RAISE**（失败 ROLLBACK 本笔）。信号内嵌套 `commit` 须办完当次 stage。入口删/锁拒绝则保留 stage。Cancel 时 `batch` 非空则归还。
- **类型表**：`add_type` / `remove_type` / `reload_type` 均为单条 StageKind；后两者的多成员变更在 **同一** `manager.transaction()` 内完成（禁止拆成多条 `COLLECTION_REMOVE`/`ADD` 冒充整笔回滚）。`reload_type`：导出 Wire → 删旧实例 → 换类 → 同 uid 原位 `build`+`activate`；不跑 remove_guard、不发中间 `remove`/`add`。规格 §5.4。`_COMMIT` 须写回 `_entry_types`。
- **`activate`**：外层 `transaction()` + `_build_workspace()`。Entry/Collection 热化统一为 **赋值/结构 API → `commit`**；`_commit_op` 在 `INITIALIZING` 时走 `init_transaction` + `_build_init_workspace`（`ws._workspace`），`ACTIVE` 时走普通事务。Init **嵌套独立 ctx**；**禁止同节点重复建 init 壳**。详见 §3.2.1。
- **工作区**：普通 `live._workspace`；init 为 `live._workspace._workspace`（`init_workspace` 属性）；无独立 `_init_workspace` 字段。
- **`_delete`**：内部软删；外部勿直接调用（用 `Collection.remove` / 框架生命周期）。
- **ref `on_delete` 例外**：`SET_DEFAULT` → stage default 后 **自动 `await entry.commit()`**；`CASCADE` → 仅 Collection 成员，走 **`parent.remove` + `await parent.commit()`**（须在 `send` 内办完）；非成员禁止。重复删等异常 **自然上抛并回滚**，不做幂等特判。
- **`entry.update(other)` 例外**：接收同类冷态 Entry，只同步 **已赋值** Group 字段（跳过虚拟与 `model_fields_set` 未含项），**自动 commit**；失败 `raise ConfigAggregateError`（FastAPI Body 热补丁可直接 `await cfg.update(body)`）。
- **信号**：同 `(phase, group, field, sender)` **禁止重复 connect**（以 **signal 是否已连接该 wrapped** 为准；须先 disconnect）。`__signal_wrappers__` **只增不减**，仅作包装挂载点防 GC，不参与事务语义。

## 编码：减少调用层级，能内联就内联

> 与 `.agents/skills/mas-skills` **Global Constraints §9** 一致，配置基类与业务代码均适用。

- **禁止**为一两行逻辑（如 `isinstance` / `issubclass`、`dict.get` + 类型断言、单次 `validate_assignment`）再包一层 helper。
- **禁止**薄转发：`_update_x` 只调用 `_apply_x`、或单次使用的 `_collection_view` / `_redact_*` 等。
- 调用点直接写清楚；若因循环导入拿不到类型名，在**该调用点** `from ... import ...`（推迟导入），不要为此发明 `is_xxx()` 包装函数。
- **仅调用一次的逻辑直接内联**；函数过长时用**功能块注释**分段，不要为分段再抽一层函数。
- **已有模块级 import 的，不要在同一函数里再推迟导入同一符号**；只有 import 图形成环时才推迟。
- 典型：`entry.py` 可顶层 `import ConfigCollection`；`manager.is_registered_collection` / `node._SignalDescriptor.__get__` 须推迟（`collection ↔ manager/node`）；`signals._wrap` 与 `manager.COMMIT` 可顶层或文件末尾 import `ConfigNode`（`node` 将 `signals` 放在类定义之后导入即可）。
- 不要用 ClassVar 布尔标记（如 `_is_collection`）代替真实 `isinstance` / `issubclass`。
- 仅当同一非平凡逻辑多处复用、抽出后显著降低维护成本时才抽函数。

## 嵌套 Collection

- Entry 上嵌套集合字段 **只能** `collection(*types)` 声明；其它 `Field`/`ConfigCollection(...)` 写法在 `__pydantic_init_subclass__` 以 `TypeError` 拒绝。
- 不设 `_nested`；工厂永不传 `name=`/`file=`。事后 ref 池用 `register_collection` / `register_self`。
- `model_post_init`：绑 Group（`_entry` / `_group`）；嵌套 Collection 若 `parent is None` 则写 `_parent_ref`（工厂无 parent，不重建）。成员 Entry 经 `parent=` 在子 `__init__` 绑定。读路径统一用 **`node.parent`**（已解析的父节点）。

## 工作区 API

| | Node（实例） | Signal（类） |
|---|--------------|--------------|
| **读** | `self.effective`（init 壳 → 普通 ws → live） | `cls.signal_effective()` |
| **写（普通）** | `_build_workspace()` → `effective` | `_build_workspace()` → `effective()` |
| **写（Init）** | `_build_init_workspace()` → `_make_workspace_shell(init=True)` 挂到 `ws._workspace` | — |

## 事务

- **普通入口**：`async with manager.transaction()` — 外层 COMMIT/ROLLBACK（→ live，可落盘）；嵌套空转
- **Init 入口**：`async with manager.init_transaction()` — **须已在**普通事务中；**嵌套压入独立 ctx**（非空开），本层结束才 `COMMIT_init`/`ROLLBACK_init`；合并 → 普通 ws，**不落盘**；**禁止同节点重复 `_build_init_workspace`**
- **节点 commit**：`async with manager.node_commit(node)` — 外层抢节点锁；同 Task 嵌套空过；释放时并入 pending
- **事务预演**：改 `effective` → `send` → 失败则本层回滚

## 信号（与 blinker 一致）

| 术语 | 含义 |
|------|------|
| **发送者** | `entry.connect(接收者)` 的 **entry**；`send(sender=…)` / `connect(sender=…)` / 回调首参 **同义** |
| **接收者** | 用户 **fn**；blinker receiver；`__signal_wrappers__[(phase, group, field, sender_id)]` 钉 wrapped |

- 发送者 deleted → **仅 `Cls.send`**；`_wrap` deleted → **仅** `receiver.__self__`（ConfigNode 实例方法；ref 用 `MethodType` 绑定 entry）
- 发送者 **软删** → **仅 `Cls.send`**；**真 GC** → blinker 内置 `_make_cleanup_sender`（框架不实现）

## 反模式

- 混淆发送者与接收者
- connect 后对**同一接收者 + 同一 (phase, group, field, sender)** 再 connect 而未 disconnect（键已被占用；框架 **报错**）
- 一层套一层的薄封装（尤其类型判定、Wire 窄化、单字段校验）
- 在无普通事务 / 无 `_workspace` 时调用 `init_transaction`
- init handler 内对**同节点**再 `commit`（重复开启 init）
