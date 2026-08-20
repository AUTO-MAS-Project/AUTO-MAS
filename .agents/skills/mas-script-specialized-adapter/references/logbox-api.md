# log_box：通用日志采集推送组件用法

> 适用：专项适配需要把脚本运行日志的关键节点推送至任务报告时。log_box 只对
> 日志本身负责，与具体脚本解耦——专项只是它的**参数提供方**（日志位置 + 规则
> + 处理器），不关心日志怎么取得、怎么处理、怎么进 push_log。

一句话链路：调用方喂参数（日志位置 + 规则 + 处理器）→ log_box 自采集 →
前置处理（open）→ 规则匹配/提取 → 后置处理（close）→ 结果推送。

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

## 日志类型与推送时机语义

**LogType（`collect`/`rule` 的 type 参数，逐条）** 与 **推送任务结果时机（通知设置 `SendTaskResultTime`，全局）** 是两层独立语义（与 MAS 原生推送一致）：

- **`LogType.NORMAL`（普通）**：该条目**任何推送报告均包含**。
- **`LogType.FAIL`（失败）**：该条目**仅在任务存在未完成用户时纳入报告**。
- **`SendTaskResultTime`（不推送 / 任何时刻 / 仅失败时）**：决定**是否推送整份报告**：
  - `不推送`：永不推送
  - `任何时刻`：任务结束即推送整份报告
  - `仅失败时`：**仅当任务存在未完成用户时**推送整份报告

**okww 专项约定**：节点级失败（如 `❌ 失败: 先约电台`）**始终展示**——`LogType` 用 `NORMAL`、状态由文本「❌ 失败:」体现，不被「未完成用户」过滤；推送时机由 `SendTaskResultTime` 全局控制，**不做专项 LogType/推送逻辑**（与上游语义保持一致）。

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

后处理示例：按节点解析最终状态（失败 > 跳过 > 成功），裸节点名 = 开始标记默认成功：

```python
import re
_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}

def resolve(lines):
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
    return [f"{states[n][1]}: {n}" for n in order]
```

> 节点级失败用 `LogType.NORMAL` + 文本「❌ 失败:」始终展示；推送时机由全局
> `SendTaskResultTime` 控制（见上文「日志类型与推送时机语义」）。

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
