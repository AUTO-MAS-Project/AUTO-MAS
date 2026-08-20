# log_box：通用日志采集推送组件用法

> 适用：专项适配需要把脚本运行日志的关键节点推送至任务报告时。log_box 只对
> 日志本身负责，与具体脚本解耦——专项只是它的**参数提供方**（日志位置 + 规则
> + 处理器），不关心日志怎么取得、怎么处理、怎么进 push_log。

一句话链路：调用方喂参数（日志位置 + 规则 + 处理器）→ log_box 自采集 →
前置处理（open）→ 规则匹配/提取 → 后置处理（close）→ 结果推送。

## 目录

- [进程与推送边界](#进程与推送边界关键)
- [get_collect 工厂](#get_collect-工厂)
- [LogCollect 采集会话](#logcollect-采集会话)
- [与通用脚本 web 配置推送日志的分工](#与通用脚本-web-配置推送日志的分工重要)
- [日志类型与推送时机语义](#日志类型与推送时机语义)
- [Rule 编程式构建](#rule-编程式构建)
- [表达式引擎自定义算子](#表达式引擎自定义算子)
- [专项喂参示例](#专项喂参示例mas-进程宿主)
- [推送落地](#推送落地聚合与追加通用工具)
- [脚本宿主示例](#脚本宿主示例用户脚本子进程)
- [常见坑](#常见坑)

## 命名约定（大小写）

| 类别 | 大小写 | 示例 |
|---|---|---|
| 类（类型名） | PascalCase | `LogCollect`、`LogSource`、`LogType`、`Rule` |
| 模块 / 包 | snake_case | `app/log_box/`、`collect.py` |
| 实例 / 工厂对象 | snake_case | `log_collect`（`LogCollect` 实例）、`log_box`（工厂对象） |
| 常量 | UPPER_SNAKE | `MSG_PREFIX`、`OKWW_PUSH_RULES` |

> `log_box` 同时是「包名」与「工厂对象名」：`from app.log_box import log_box`，
> 包=代码组织、对象=入口，语义不同，属 Python 常见写法。

---

## 顶层入口

```python
from mas_script import log_box, Rule, LogType
```

`log_box` 同时是「包名」与「工厂对象名」：`app/log_box/` 为代码组织，工厂对象
`log_box` 提供 `get_collect()` 创建采集会话。

## 进程与推送边界（关键）

log_box 是**进程无关**的组件，结果落点由**宿主**决定：

- **宿主 = MAS 进程**（专项适配器内实例化）：构造时注入 `sink(log_type, text)`
  直接写 `cur_user_item.push_log`，对适配器完全透明。**这是当前唯一已接通的宿主路径**。
- **宿主 = 用户脚本子进程**（`from mas_script import log_box`）：不注入 sink，
  box 把处理结果渲染为 `@@LOGBOX@@` 受控 stdout 标记回传，MAS 侧
  `check_log` 嗅探后写入 `cur_user_item.push_log`。

> ⚠️ **脚本宿主目前是能力预留，尚未端到端接通**：box 的 `@@LOGBOX@@` 标记渲染/
> 解析、MAS 侧 `check_log` 单行嗅探逻辑均已就位，但 MAS 尚未把「用户脚本进程
> stdout」接入 `check_log`（脚本 stdout 现为 DEVNULL 丢弃，`check_log` 只读
> `LogPath` 日志文件），也未设置 `MAS_SCRIPT_LOG_PATH` 与 `import mas_script`
> 所需的 PYTHONPATH。接通需增强 general 自动代理的进程启动（stdout PIPE 逐行
> 喂 `check_log` + 启动前注入 env），不改核心框架。**在接通之前，脚本宿主请勿
> 作为可交付使用**；有真实脚本宿主需求时再落地该改造。

两者共用同一套采集/前置/匹配/后置逻辑，仅「结果如何落进 push_log」这一跳因宿主而异。

## get_collect 工厂

```python
col = log_box.get_collect(
    paths=["workdir/logs/ok-script.log"],  # str | Path | 可迭代；None → 环境变量 MAS_SCRIPT_LOG_PATH
    sink=None,                             # MAS 宿主注入 push_log 回调；缺省走 @@LOGBOX@@ 回传
    start_from_end=True,                   # 从文件末尾起始采集，仅采会话内新增
)
```

## LogCollect 采集会话

| 方法 | 说明 |
|---|---|
| `open(processor=None)` | 启动采集（幂等）；可传前置处理器（逐行 map/filter），也可 `@col.open()` 装饰器。前置处理器返回 `None` 丢弃该行 |
| `collect(regex, expr="", type=NORMAL)` | 声明式单行规则：匹配正则 + `$()` 提取表达式（可多条） |
| `collect_scope(start_re, end_re="", expr="", max_lines=50, type=NORMAL)` | 多行聚合规则 |
| `rule(regex, type=NORMAL) -> Rule` | 编程式规则构建器 |
| `postprocess(processor)` | 登记后置处理器，作用于捕捉完的**最终结果集**（去重/规整），可 `@col.postprocess()` 装饰器 |
| `close(processor=None)` | 结束会话：冲刷多行残留 → 后置处理 → 完成推送（幂等）；脚本宿主下 atexit 兜底 |
| `print(text)` | 调试打印（Flink print 语义），**不作为推送通道** |
| `push(text, type=NORMAL)` | 手动直推最终结果（host 在脚本/进程关闭等时机触发） |

处理管线：**前置处理（翻译/过滤）→ 匹配与提取均在处理后行 → 后置处理**。
前置处理器逐行翻译后，规则匹配与提取都作用于翻译后的行，翻译对下游整体生效。

## 与通用脚本 web 配置推送日志的分工（重要）

MAS 有两套日志推送配置面，**保持两套并存、分工明确**，不要互相迁移：

| 方案 | 适配对象 | 规则来源 | 面向 |
|---|---|---|---|
| 通用脚本 web 配置推送日志（`PushLogConfig`） | 通用脚本（用户直接编辑） | 前端 UI 可视化配置 | 最终用户 |
| 通用 log_box | 专项 / 由 MAS 驱动的可编辑 `.py` 脚本 | 代码内建（专项 `push_log.py` / `collect`） | 适配器开发者 / 脚本作者 |

判据：**通用脚本走 web UI 配置，专项才用 log_box 内建**。两者命中后都汇入
`cur_user_item.push_log`，由 `app/tools/push_log.py` 统一聚合推送。通用侧不要迁去
log_box（会失去可视化 UI），log_box 也不要反向暴露 web 配置（会破坏内建纯度）。

## 日志类型与推送时机语义

**LogType（`collect`/`rule` 的 type 参数，逐条）** 与 **推送任务结果时机（通知设置 `SendTaskResultTime`，全局）** 是两层独立语义（与 MAS 原生推送一致）：

- **`LogType.NORMAL`（普通）**：该条目**任何推送报告均包含**。
- **`LogType.FAIL`（失败）**：该条目**仅在任务存在未完成用户时纳入报告**。
- **`SendTaskResultTime`（不推送 / 任何时刻 / 仅失败时）**：决定**是否推送整份报告**：
  - `不推送`：永不推送
  - `任何时刻`：任务结束即推送整份报告
  - `仅失败时`：**仅当任务存在未完成用户时**推送整份报告


## Rule 编程式构建

```python
# 提取「current_stamina 240」中的数字 240（regex 作用域必须用捕获组，$() 取捕获组内容）
col.rule(r"current_stamina (\d+)").regex(r"(\d+)").trim().end()
# 函数链：cut/sub/replace/trim 与自定义算子 func
col.rule(r"xxx").regex(r"(\d+)").cut(2).sub(0, 3).replace("a", "b").trim().end()
```

`regex(pattern)` 设置提取作用域（缺省 `$()` 取整行）；提取内容取捕获组中的
非空组（无捕获组时为空串，继续走函数链）。函数链支持 `func(name, *args)`
（含注入 REGISTRY 的自定义 Process 算子）、`get`、`cut`、`sub`、`cutby`、
`subby`、`replace`、`trim`、`upper`、`lower`；`end()` 完成构建并注册。

> 注意：`get(n)`/`cut(n)` 是按**字符数**保留/切除（n>0 取开头、n<0 取结尾），
> 不是正则分组提取；要取正则分组请用 `regex(r"捕获组正则")` 作用域。

## 表达式引擎自定义算子

```python
from app.utils.expression import register_process, Process

@register_process
class Translate(Process):
    name = "translate"
    def run(self, text: str, args: list) -> str:
        ...
```

`@register_process` 把自定义 `Process` 子类登记进引擎 REGISTRY，表达式可调用
`.translate(...)`；对 web 前端面板不暴露。用 `Rule.func()` 在函数链中调用：

```python
@register_process
class Suffix(Process):
    name = "suffix"
    def run(self, text, args):
        return text + (str(args[0]) if args else "")

col.rule(r"current_stamina (\d+)").regex(r"(\d+)").func("suffix", " 剩余电量").end()
# 等价表达式：$((\d+)).suffix(" 剩余电量")，作用于整行文本
```

> **为什么不能用 `.process(fn)` 直接传 Python 函数**：规则是「参数」形态
> （正则 + 表达式字符串），脚本子进程宿主跨进程只传规则参数、不传函数体
> （契约不含闭包/状态）；自定义处理一律用 `@register_process` 具名注入，
> 规则字符串可序列化、跨宿主一致、编译期函数名校验。

## 专项喂参示例（MAS 进程宿主）

专项只做：实例化一个 log_box、塞入日志路径与规则、注入 sink、挂前置翻译与
后置状态解析；其余全由 box 完成（参见 okww 的 `app/task/Okww/`）：

```python
from mas_script import log_box, LogType

self.log_collect = log_box.get_collect(
    paths=[self.script_log_path],  # 相对 RootPath 派生，不硬编码绝对路径
    sink=self._append_push_log,    # 注入到 cur_user_item.push_log
    start_from_end=True,
)
self.log_collect.open(translator.translate)          # 前置翻译
for match_re, expr, log_type in PUSH_RULES:          # 喂规则参数（状态标记规则）
    self.log_collect.collect(match_re, expr, log_type)
# 结束时机（如进程关闭判定 / final_task）：col.close(resolve)
```

后处理示例：按节点解析最终状态（失败 > 跳过 > 成功），裸节点名 = 开始标记默认成功
（需消费并返回 `(log_type, text)` 元组，以保留日志类型）：

```python
import re
_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}

def resolve(results):
    """输入/输出均为 (log_type, text) 元组，日志类型随元组一并保留"""
    lines = [text for _, text in results]
    order, states = [], {}
    for line in lines:
        m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", line)
        status, node = (m.group(1), m.group(2)) if m else ("✅ 成功", line)
        rank = _STATUS_RANK[status]
        if node in states:
            order.remove(node)  # 保留最后一次出现顺序
        order.append(node)
        if rank > states.get(node, (0, ""))[0]:
            states[node] = (rank, status)
    # 按节点名（去状态前缀后）重建类型映射，避免与完整文本键错配导致类型丢失
    last_type = {}
    for log_type, text in results:
        m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", text)
        node = m.group(2) if m else text
        last_type[node] = log_type
    return [(last_type.get(node, "普通"), f"{states[node][1]}: {node}") for node in order]
```

> 节点级失败用 `LogType.NORMAL` + 文本「❌ 失败:」始终展示；推送时机由全局
> `SendTaskResultTime` 控制（见上文「日志类型与推送时机语义」）。

## 推送落地：聚合与追加（通用工具）

push_log 落进 `cur_user_item.push_log`（`list[(log_type, text)]`）后，后续聚合与
追加统一走 `app/tools/push_log.py`，专项**不要**自行拼接实现：

- `build_push_log_text(users, has_uncompleted)`：聚合各用户 push_log 为报告文本，
  每条条目独占一行；「失败」类型条目仅在任务存在未完成用户时纳入（与 MAS 原生
  推送策略一致）。专项在 `manager.final_task` 汇总时调用。
- `append_push_log(message_text, push_log, separator="\n")`：把推送日志追加到通知
  正文，**默认以单个换行分隔**；专项（如 `tools/notify.py`）按默认调用即可，无需
  传 `separator`，push_log 为空时原样返回正文。

```python
# manager.final_task：聚合后放入通知消息
has_uncompleted = len(error_user) + len(wait_user) > 0
push_log_text = build_push_log_text(self.script_info.user_list, has_uncompleted)
message = {"push_log": push_log_text, ...}

# tools/notify.py：追加（默认 separator="\n"）
message_text = append_push_log(message_text, message.get("push_log"))
```

## 脚本宿主示例（用户脚本子进程）

> ⚠️ **预留示例，尚未端到端接通**：见上方「进程与推送边界」说明，脚本 stdout 尚未
> 接入 MAS 的 `check_log`。以下仅为将来接通后的用法示意，当前不可交付。

```python
from mas_script import log_box, LogType

col = log_box.get_collect(paths=["workdir/logs/xxx.log"])
col.open()                        # 记录起始位置（可选，close 收尾会自动兜底）
col.collect(r"DailyTask:open_daily", '"完成"')
col.close()   # 脚本正常退出时 atexit 也会自动收尾
```

接通后结果经 `@@LOGBOX@@` 标记出现在任务推送报告。注意：`start_from_end=True`
（默认）只采集会话内新增内容，需在日志产出**之前**调用 `col.open()` 记录起始位置；
未显式调用时 close 会自动启动日志源，但此时起点即收尾时刻，可能采不到会话内日志。

## 常见坑

1. **`start_from_end=True` 采集时机**：只采会话内新增，须在日志产出**前** `open()`。
   若在日志已写入后才 `open()`，起点即当前文件末尾，历史节点采不到。未显式 `open()`
   时 `close()` 会自动启动源，但此时起点即收尾时刻，可能什么都采不到。

2. **`get(n)`/`cut(n)` 是字符语义，不是正则分组**：`get(1)` 保留前 1 个**字符**，
   不是「第 1 个捕获组」。要取正则分组，用 `rule(regex).regex(r"捕获组正则")` 作用域
   或 `collect(match_re, expr)` 里 `$((捕获组))`。

3. **正则提取作用域必须有捕获组**：`$()` 取的是捕获组中的**非空组**；正则无捕获组
   时返回空串（继续走函数链与拼接），可能拿不到整段匹配。需要整段匹配就用捕获组包裹，
   如 `$((.*))`。

4. **前置翻译会改变匹配依据**：前置处理器（open）翻译的是整行，此后匹配与提取都作用
   于**翻译后**的行。若规则匹配关键字是英文、而前置翻译译成了中文，规则要按译文匹配
   （见 OK-WW `OKWW_PUSH_RULES` 与 i18n 的耦合）。

5. **后处理器必须消费并返回 `(log_type, text)` 元组**：不要用「后处理前文本」回查
   `log_type`——文本一旦被改写（如状态解析），按文本键会查不到而丢失类型。正确做法是
   在元组层级处理，日志类型随结果一并保留。

6. **`open()` 有参调用返回自身**，可链式：`col.open(pre).collect(...).collect(...)`；
   无参调用作为装饰器 `@col.open()` 返回注册器。两者形态不同，勿混用返回值。

7. **`MAS_SCRIPT_LOG_PATH` 与脚本宿主**：脚本宿主尚属能力预留（见「进程与推送边界」），
   MAS 未把脚本 stdout 接入 `check_log` 且未注入该环境变量。专项（MAS 宿主）请始终
   显式传 `paths`，不要依赖该 env（它只在脚本宿主接通后生效）。
