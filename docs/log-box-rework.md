# log_box：日志采集推送能力（从需求重构的架构文档）

> 用途：供 AI 在全新分支上按本文档从零实现。
> 原则：**从需求出发**。log_box 是一个**与具体脚本解耦**的通用日志处理组件；垂直专项（如 ok-ww）只是它的**参数提供方**，不依赖 box 的日志获取、处理与推送细节。
> 目标读者：AUTO-MAS 后端 / 脚本功能开发者。

---

## 0. 定位

**log_box 只对日志本身负责。**

它接收"日志源 + 规则参数 + 前置/后置处理器"，在内部完成：采集日志 → 前置处理 → 规则匹配提取 → 结果推送。调用方（脚本 / 专项适配器）只需提供参数，不关心日志怎么取得、怎么处理、怎么进 `push_log`。

一句话链路：

> 调用方提供参数（日志位置 + 规则 + 处理器）→ log_box 自采集 → 前置处理（open）→ 规则匹配/提取 → 后置处理（close）→ 结果进 `push_log` 统一推送平台。

**调用方与 log_box 的关系**：纯"喂参数 → 收结果"。以 ok-ww 为例，专项适配器唯一做的是实例化一个 log_box、塞入 ok-ww 日志路径和规则，其余全由 box 完成。

---

## 1. 进程与推送边界（关键，先厘清）

log_box 是**进程无关**的日志处理组件，其 `push_log` 落点由**宿主**决定：

- **宿主 = MAS 进程**（专项适配器内实例化，如 ok-ww）：
  box 直接持有对 `cur_user_item.push_log` 的引用（由适配器在构造 box 时注入），采集/处理后的结果**由 box 内部累加进 push_log**。对适配器完全透明。
- **宿主 = 用户脚本子进程**（`from mas_script import log_box`）：
  子进程无法直接写 MAS 内存里的 push_log，box 把处理好的结果渲染为 `@@LOGBOX@@` 受控 stdout 标记回传，MAS 侧 `check_log` 嗅探后写入 `cur_user_item.push_log`。

两者共用同一套 log_box 处理逻辑；仅"结果如何落进 push_log"这一跳因宿主而异（直接写 vs 标记回传）。**对日志采集、前置处理、规则匹配、后置处理本身，不存在两套实现。**

**关于流程时序**：如果 host 的"脚本/进程关闭"无法由 box 从日志判定，则 host 可在恰当时机调用 box 暴露的 `push()`（或 `close()` 的 flush 语义）手动触发推送收尾；这是 host 对 box 的唯一"主动调用"点，不构成依赖。

---

## 2. 命名规范（以本表为准）

### 2.1 大小写约定（遵循 Python 惯例）

| 类别 | 大小写 | 示例 |
|---|---|---|
| 类（类型名） | PascalCase | `LogCollect`、`LogSource`、`LogType`、`Rule` |
| 模块 / 包 | snake_case（全小写+下划线） | `app/log_box/`、`collect.py` |
| 实例 / 工厂对象 | snake_case | `log_collect`（`LogCollect` 的实例）、`log_box`（工厂对象） |
| 常量 | UPPER_SNAKE | `MSG_PREFIX`、`OKWW_PUSH_RULES` |

> `log_box` 同时是「包名」与「工厂对象名」：`from app.log_box import log_box`。两者小写一致、语义不同（包=代码组织，对象=入口），属 Python 常见写法，不算冲突。

### 2.2 名词表（类型用类名，其余用对象名）

| 概念 | 类型名（类） | 常用实例/对象名 | 说明 |
|---|---|---|---|
| 采集工厂 | `LogBox`（或由模块导出对象 `log_box` 承载） | `log_box` | `from mas_script import log_box, Rule, LogType` |
| 采集器 | `LogCollect` | `log_collect` | `log_box.get_collect(...)` 返回的对象是 `LogCollect` 实例 |
| 可编程规则构建器 | `Rule` | `rule` | `.regex()...cut()...get()...end()` |
| 日志类型 | `LogType` | `log_type` | `NORMAL=普通` / `FAIL=失败` |
| 日志源 | `LogSource` | `source` | 单个被采集文件；`log_collect` 聚合多个 |
| 结果回传标记前缀 | 常量 | `@@LOGBOX@@` | 脚本子进程宿主下的结果标记 |
| 顶层别名模块 | 模块 `mas_script`（仓库根） | — | 导出 `log_box, Rule, LogType` |

### 2.3 包布局（建议）

```
app/log_box/
  __init__.py      # 导出 log_box, Rule, LogType
  factory.py       # log_box 工厂（get_collect）
  collect.py       # LogCollect（采集器）
  sources.py       # LogSource / 默认 MAS 日志位置解析 / 多文件
  rule.py          # Rule / RuleSpec
  logtype.py       # LogType
  markers.py       # @@LOGBOX@@ 结果标记渲染与解析（脚本宿主用）
mas_script.py      # 仓库根，顶层别名
```

---

## 3. 调用形态（最终目标）

```python
from mas_script import log_box, LogType

col = log_box.get_collect(
    paths=["workdir/logs/ok-script.log"],   # 缺省/None → MAS 配置的日志位置；支持多文件
)

@col.open()          # 可选：前置处理（翻译、过滤规则），作用于逐行，可返回 None 丢弃该行
def preprocessor(line: str) -> str | None:
    return translator.translate(line) if line else None

col.collect(r"DailyTask:open_daily", '"🚀 启动: 每日一条龙"')       # 声明式（可多条）
col.rule(r"current_stamina (\d+)").get(1).trim().end()            # 编程式

col.print(...)       # Flink print 语义：即时打印捕捉到的结果（调试观察，不进报告）

@col.close()         # 可选：后置处理，作用于捕捉完的最终多行结果集，返回处理后的结果集
def postprocessor(lines: list[str]) -> list[str]:
    return dedup(lines)   # 去重、规整等

col.close()          # 结束：固化后置处理、冲刷残留、完成推送
```

---

## 4. 三步开发路线

### 第 1 步：表达式引擎底层支持 process 自定义方法

**目标**：表达式引擎被动化，可注入自定义文本变换算子，对 web 前端面板不暴露。

改动范围：`app/utils/expression/`

- `functions.py`：
  - `class Process`：`name: str` 属性 + `run(text, args) -> str`；`__call__(text, args)` 对齐内置函数签名；构造时接收表达式调用处的静态参数 `*args`。
  - `REGISTRY: dict[str, type[Process] | Callable]` 注入注册表。
  - `@register_process(cls) -> cls`：按 `cls.name` 登记。
  - `make_process(name, cls, args) -> Process`：按表达式调用参数实例化。
- `evaluator.py`：编译期函数名校验从「仅内置」放宽为「内置 `FUNCTIONS` ∪ 注入 `REGISTRY`」；`apply_function` 先查内置、再查注入、对 `Process` 子类用 `make_process` 实例化调用。
- `rule.py` 的 `_call` 校验同步放开到 `REGISTRY`。

引擎其它能力（`$(regex)` 作用域、函数链、多行聚合 `;`/`+` 字面量、`$( )` 取整段）**复用现有 LogPatternExtractor/expression 语义**，本步只加"注入算子"。

**验收**：注入 `@register_process class Translate: name="translate"` 后 `compile_expression(r"$(...).translate()")` 可编译求值；内置函数不回退；未知函数名仍编译期报错；`py_compile` 通过。

### 第 2 步：上层 log_box（通用处理组件）+ MAS 侧回传接收

**目标**：实现进程无关的 log_collect，含 open/close 处理器钩子、自采集、print 调试、push 手动推送、push_log 落点。

**组件契约**：

- `log_box.get_collect(paths=None, *, sink=None) -> LogCollect`：
  - `paths=None` → 默认采集 MAS 配置的日志位置（`sources` 默认解析）。
  - `paths`：`str | Path | Iterable[...]` → 手动指定，支持**多文件**。
  - `sink=None`：MAS 进程宿主注入的 push_log 写入回调；缺省时走 `@@LOGBOX@@` 标记回传（脚本宿主）。
- `LogCollect`：
  - `open()`：为每个 `LogSource` 启动 tail；**可选、幂等**。可作为装饰器/接收一个**前置处理器** `processor(line) -> str | None`（可返回 `None` 丢弃该行）；也可多次添加工厂处理器，按序执行。
  - `collect(regex, expr="", type=LogType.NORMAL)`：单行正则 + `$()` 表达式（可多条）。
  - `collect_scope(start_re, end_re="", expr="", max_lines=50, type=LogType.NORMAL)`：多行聚合。
  - `rule(regex, type=LogType.NORMAL) -> Rule`：编程式构建。
  - `print(text)` / handler：**Flink print 语义**——即时打印捕捉到的结果到调试输出，用于观察，**不作为推送通道**。
  - `push(text, type=LogType.NORMAL)`：手动直推最终结果（供 host 在脚本/进程关闭等恰当时机触发）。
  - `close(processor=None)`：固化可选**后置处理器** `processor(lines: list[str]) -> list[str]`（对捕捉完的最终多行结果集做去重/规整），随后冲刷多行残留并把最终结果集完成推送。同时注册 `atexit` 兜底（宿主为脚本子进程时，脚本正常退出自动 close）。
- `LogSource`：单文件 tail（offset 增量读、轮转处理、按时间起始过滤），**独立、可被 log_collect 直接持有**（不复用回调型 LogMonitor，因其 callback 面向适配器、不支持主动拉取）。
- `markers.py`（`@@LOGBOX@@`，脚本宿主）：`render_push(text, type)` / `render_flush()` / `parse_marker(line)` / `emit(line)`；前缀独立、解析失败忽略该行。
- **MAS 侧接收**（通用 `general/AutoProxy.py`）：`check_log` 单行嗅探 `@@LOGBOX@@`：`push` → 收 `(type, text)` 入 `push_log_buffer` 并跳过该行；`flush` → 冲刷；`final_task` 统一写回 `cur_user_item.push_log`。**注意**：这是"脚本宿主"回传通道；**MAS 进程宿主的专项（如 ok-ww）直接注入 sink，不走标记**。

**验收**：
- MAS 进程宿主：注入 `sink` 的 log_collect 作用于测试日志文件，采集结果直接出现在 push_log。
- 脚本宿主：`.py` 脚本 `from mas_script import log_box` 指定 `paths`，运行后结果经 `@@LOGBOX@@` 出现在任务推送报告。
- 前置/后置处理器各生效；`print` 即时打印不影响结果；`push` 手动触发；`py_compile` 通过。

### 第 3 步：okww 只是一个 log_box 实例（喂参数）

**目标**：ok-ww 专项用 log_box 完成日志采集、i18n 翻译、关键节点推送；专项只提供参数，不碰 box 内部逻辑。

- 前置翻译（open 处理器）：`PoTranslator` 把 ok.po 一次性加载进内部 map、`load_supplement` 补充翻译（补充优先）、`translate` 逐行翻译、`clear` 释放。入 `app/utils/i18n/`（`po.py` + `translator.py` + `__init__.py`）。
- 参数源（`app/task/Okww/push_log.py`）：
  - 日志路径：ok-ww `RootPath` 派生（相对母目录地址，不硬编码绝对路径）。
  - `OKWW_REL_I18N_PO`：ok-ww 自带翻译 .po（相对 RootPath）；`OKWW_SUPPLEMENT_PO`：AutoMAS 项目自带的补充翻译 .po（`res/i18n/` 内置资源，补充优先）。
  - `OKWW_PUSH_RULES`：状态标记规则，分四类——开始/动作标记（裸节点名，后处理默认成功）、失败标记（`❌ 失败: 节点`，匹配源码 log_error 专属失败日志，排除战斗噪音）、跳过标记（`⏭ 跳过: 节点`）、明确成功标记（`✅ 成功: 节点`）；直接喂给 `log_collect.collect(...)`。
- 后置处理（close 处理器）：`okww_resolve` 按节点解析最终状态（失败 > 跳过 > 成功），保留最后一次出现顺序；节点级失败始终展示（`LogType.NORMAL` + 文本状态，不被未完成用户过滤），推送时机由 `SendTaskResultTime` 全局控制（不推送/任何时刻/仅失败时，与 MAS 原生语义一致）。
- `app/task/Okww/AutoProxy.py`：**MAS 进程宿主**——构造 log_collect，注入 `sink` 到 `cur_user_item.push_log`，传入 ok-ww 路径与规则作为参数，挂前置翻译 + `okww_resolve` 后处理；在 `final_task` 调用 `col.close()` 收尾并 `translator.clear()` 释放。专项**不感知** box 采集与处理细节。
- `app/task/Okww/manager.py`：聚合各用户 `push_log` 进任务报告（"失败"类型仅在存在未完成用户时纳入，与原生推送策略一致）。
- `app/task/Okww/tools/notify.py`：通知详情追加 push_log（与 HTML 模板 push_log 区块一致）。

**验收**（真实 ok-script 日志）：节点完整有序（启动 → 梦魇巢穴 → 体力刷本(剩余体力) → 活跃奖励 → 邮件 → 战令(成功/失败) → 每周乐园(成功/跳过) → 合并声骸 → 每日完成 → 退出）；翻译/补译生效；匹配与提取均在翻译后行；节点级失败始终展示、无失败时报告不含失败节点。

---

## 5. 明确不做

- 不做第二个采集器 / 不复现 LogMonitor 下发；采集由 LogSource 在 log_box 内完成。
- log_box 对脚本类型无感知同样处理二进制专项（ok-ww 走 MAS 宿主注入 sink）。
- 不做跨进程函数体转发（标记/契约只传"规则参数 + 处理结果"，不传 Python 闭包/状态）。
- 不新增 web 面板规则类型；`Rule.to_config()` 与 web 面板 `compile_pattern` 保持单一数据模型。

---

## 6. 回归与测试策略

按 `tests/AGENTS.md`：
- 第 1 步：表达式注入 Process 单测 + `py_compile`。
- 第 2 步：`@@LOGBOX@@` 标记往返；log_collect 作用于测试日志文件（MAS 宿主 sink、脚本宿主回传两态）；默认/手动/多文件路径；前置/后置处理器与 `print`/`push`。
- 第 3 步：真实 ok-script.log 验证节点顺序（`scripts/` 放手动诊断脚本，非 pytest 入口；仅用户要求才固化最小测试）。
- 文档修改后用 `rg` 确认无旧命名残留（MessageHub/MessageCollect/@@MSG@@）。

---

## 7. 功能登记

实现完成后在 `res/version.json` 下一未发布版本登记：

> 日志采集 API 落地为 log_box（与专项解耦的通用组件：进程无关宿主、多文件自采集、open/close 处理器钩子、print 调试、push 手动推送），表达式引擎支持注入 process 自定义算子；OK-WW专项 作为 log_box 实例，采集运行日志关键节点推送至任务报告，日志先经 i18n（ok.po）预翻译，提供补充翻译与会话结束后处理。