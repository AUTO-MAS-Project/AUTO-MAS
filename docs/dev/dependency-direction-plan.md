# 依赖方向治理方案

> 适用分支：`refactor/Win32-Cleanup`（PR #423）
>
> 状态：阶段一、二已执行并验证；阶段三及以后不进本 PR。

平台层引入后出现了反向依赖。本方案定位到唯一根因，用一次文件移动消除它，并用一个测试锁死方向，让它回不去。

| 指标 | 结果 |
|---|---|
| 平台层反向依赖 | **2 → 0** |
| 测试 | 109 passed（唯一失败为既有的 sentry 用例） |
| 入口顺序导入冒烟 | 6 / 6 通过 |

## 1. 诊断：问题只有一个根因

全仓 AST 扫描，区分顶层导入与函数内延迟导入。平台层共两个包，扫描结果很干净：

- `app/utils/platform/**` —— 反向依赖 **0** 条
- `app/services/platform/**` —— 反向依赖 **2** 条

而这 2 条来自同一个文件：

```text
app/services/platform/common/system.py:98   from app.core import Config
app/services/platform/common/system.py:141  from app.core import Config
```

根因不是导入写法，是**归属错了**：336 行的业务编排类 `System` 被放进了 `platform/common/`，连同 `Config.server`、WebSocket 通知和 `KillSelf` 生命周期一起。业务编排进了平台层，反向依赖是必然结果。

同一个根因还产出了另一条 review 意见——`taskkill` 这个 Windows 专属命令出现在名为 `common`（跨平台通用）的目录里。**一次移动，两个问题一起消失。**

## 2. 全局：八对双向依赖

| 依赖对 | 正向（应保留） | 反向（应消除） |
|---|---:|---:|
| `task ↔ models` | 93 顶层 | 2 延迟 |
| `task ↔ core` | 32 顶层 | 1 顶层 |
| `core ↔ utils` | 13 顶层 | 3 延迟 |
| `api ↔ utils` | 10 顶层 | 1 延迟 |
| `tools ↔ core` | 5 顶层 | 3 延迟 |
| **`core ↔ services`** | 1 顶层 | 4 延迟 |
| `MaaFW ↔ core` | 2 顶层 | 1 延迟 |
| `models ↔ utils` | 双向都是顶层（4 / 6）—— 唯一的真静态环 | |

加粗行为本 PR 涉及的一对，它其实是八对里最小的。

这张表最有用的一点：**正确方向是自明的**。反向边全是少数，多数是延迟导入。治理不需要重排架构，只需要逐条拆掉少数派。

## 3. 目标依赖方向

```text
app.core  ──▶  app.services  ──▶  services/platform + utils/platform
   ▲                                        │
   └────────────  ✗ 已切断，由测试锁定  ◀────┘
```

平台层只回答「当前环境能不能做」和「底层如何执行」，不读配置、不碰编排。

## 4. 阶段一（已执行）：把 System 移回服务层

`app/services/system.py` 当时只是 3 行转发壳，把实现搬回去即可。纯文件移动，不改一行逻辑。

```bash
rm app/services/system.py
git mv app/services/platform/common/system.py app/services/system.py
```

仅调整两行导入（绝对 → 相对）：

```diff
-from app.services.platform.power import power
-from app.services.platform.startup import startup
+from .platform.power import power
+from .platform.startup import startup
```

- 改动：1 次移动 + 2 行导入
- 逻辑变更：无
- 风险：低

移动后 `app/services/platform/common/` 只剩 `power.py` 与 `startup.py`，即真正的平台兜底实现。

## 5. 阶段二（已执行）：用测试锁死方向

新增 `tests/platform/test_layer_boundary.py`。关键在于它检查**顶层和函数体内的所有 import**——「用延迟导入绕过」这条路也被堵死，这正是「函数内导入只是把依赖藏起来」的机器化版本。

```python
_FORBIDDEN_PREFIXES = (
    "app.core", "app.task", "app.api",
    "app.tools", "app.MaaFW", "app.services.system",
)

# ast.walk 遍历整棵树，不区分导入位置
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom) and node.level == 0:
        ...
```

- 新增：约 60 行测试，无新依赖
- 已反向验证：在 `platform/common/power.py` 的方法体内塞回一条 `from app.core import Config`，测试立即变红并指出 `power.py:8 -> app.core`

## 6. 执行结果与遗留说明

六种入口顺序导入冒烟全部通过：`app.core`、`app.services`、`app.services.system`、`app.utils.platform`、`app.services.platform.power`、`main`。

需要说清楚的是：`System` 对 `Config` 的两条延迟导入**没有消失，而是换了位置**——从平台层挪回服务层，与 `notification.py:40`、`update.py:39`、`matomo.py:33` 的既有写法完全同构。它们不是本 PR 引入的，留给阶段三。

## 7. 后续阶段（各自独立成 PR）

### 阶段三：参数化 power_sign

`System` 不再自己读 `Config`，改由调用方传入，消除 services → core 的剩余延迟导入。

```diff
- await System.start_power_task()
+ await System.start_power_task(Config.power_sign)
+ Config.power_sign = "NoAction"
```

波及：`core` / `api` / `update` 一批调用方。

### 阶段四：KillSelf 移出电源能力

关闭 WebSocket、设置 `should_exit` 是应用生命周期，不是操作系统电源能力。平台电源接口只保留 shutdown / reboot / sleep。

波及：`api/core.py`、`update.py`。

### 阶段五：包级聚合导入改为具体模块

`from app.core import Config` 改为 `from app.core.config import Config`，让 `__init__.py` 不再主动加载业务模块，导入结果不再取决于包初始化顺序。

波及：全仓。

## 8. 记录：两个更大的环

都不该进本 PR，但值得记下来，免得下次从头分析。

**`models ↔ utils` 是唯一的真静态环。** 双向都有顶层导入（models→utils 4 条，utils→models 6 条），比 `core ↔ services` 危险得多——后者反向全是延迟导入，前者现在不炸只是因为初始化顺序恰好成立。

```text
app.utils.emulator.{general,ldplayer,mumu}  →  app.models.{config,emulator}   [顶层]
app.models.{ConfigBase,config}              →  app.utils{,.constants,.io}     [顶层]
```

**`task ↔ core` 有 32 条反向边，但只需断一条。** task → core 有 32 条顶层导入，方向极其一致；反向只有 `core/task_manager.py` 一条。真要治，断那一条就够，不必动 32 条。`task ↔ models` 同理：93 对 2。
