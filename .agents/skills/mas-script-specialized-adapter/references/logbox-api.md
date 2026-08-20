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
  直接写 `cur_user_item.push_log`，对适配器完全透明。
- **宿主 = 用户脚本子进程**（`from mas_script import log_box`）：不注入 sink，
  box 把处理结果渲染为 `@@LOGBOX@@` 受控 stdout 标记回传，MAS 侧
  `check_log` 嗅探后写入 `cur_user_item.push_log`。

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

## Rule 编程式构建

```python
col.rule(r"current_stamina (\d+)").get(1).trim().end()
col.rule(r"xxx").regex(r"\d+").cut(2).sub(0, 3).replace("a", "b").trim().end()
```

`regex(pattern)` 设置提取作用域（缺省取整行）；函数链支持 `func(name, *args)`
（含注入 REGISTRY 的自定义 Process 算子）、`get`、`cut`、`sub`、`cutby`、
`subby`、`replace`、`trim`、`upper`、`lower`；`end()` 完成构建并注册。

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
`.translate(...)`；对 web 前端面板不暴露。

## 专项喂参示例（MAS 进程宿主）

专项只做：实例化一个 log_box、塞入日志路径与规则、注入 sink、挂前置翻译与
后置去重；其余全由 box 完成（参见 okww 的 `app/task/Okww/`）：

```python
from mas_script import log_box, LogType

self.log_collect = log_box.get_collect(
    paths=[self.script_log_path],  # 相对 RootPath 派生，不硬编码绝对路径
    sink=self._append_push_log,    # 注入到 cur_user_item.push_log
    start_from_end=True,
)
self.log_collect.open(translator.translate)          # 前置翻译
for match_re, expr, log_type in PUSH_RULES:          # 喂规则参数
    self.log_collect.collect(match_re, expr, log_type)
# 结束时机（如进程关闭判定 / final_task）：col.close(dedup)
```

后置去重示例：按节点只留最终状态（保留顺序）：

```python
def dedup(lines):
    seen, result = set(), []
    for line in reversed(lines):
        node = line.split(": ", 1)[1] if ": " in line else line
        if node not in seen:
            result.append(line)
            seen.add(node)
    return list(reversed(result))
```

## 脚本宿主示例（用户脚本子进程）

```python
from mas_script import log_box, LogType

col = log_box.get_collect(paths=["workdir/logs/xxx.log"])
col.collect(r"DailyTask:open_daily", '"完成"')
col.close()   # 脚本正常退出时 atexit 也会自动收尾
```

运行后结果经 `@@LOGBOX@@` 标记出现在任务推送报告。
