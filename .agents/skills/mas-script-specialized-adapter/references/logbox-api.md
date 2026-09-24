# log_box：通用日志采集推送组件用法

> 适用：专项适配需要把脚本运行日志的关键节点推送至任务报告时。log_box 只对
> 日志本身负责，与具体脚本解耦——专项只是它的**参数提供方**（日志位置 + 规则
> + 处理器），不关心日志怎么取得、怎么处理、怎么进 push_log。

一句话链路：调用方喂参数（日志位置 + 规则 + 处理器）→ log_box 自采集 →
前置处理（open）→ 规则匹配/提取 → 后置处理（close）→ 结果推送。

## 目录

- [进程与推送边界](#进程与推送边界关键)
- [get_collect 工厂](#get_collect-工厂)
- [日志轮转补偿](#日志轮转补偿跨零点必读)
- [LogCollect 采集会话](#logcollect-采集会话)
- [与通用脚本 web 配置推送日志的分工](#与通用脚本-web-配置推送日志的分工重要)
- [日志类型与推送时机语义](#日志类型与推送时机语义)
- [推送详情开关](#推送详情开关在专项侧不在-log-box)
- [表达式引擎自定义函数](#表达式引擎自定义函数)
- [专项喂参示例](#专项喂参示例mas-进程宿主)
- [推送落地](#推送落地聚合通用工具)
- [脚本宿主示例](#脚本宿主示例用户脚本子进程)
- [常见坑](#常见坑)

## 命名约定（大小写）

| 类别 | 大小写 | 示例 |
|---|---|---|
| 类（类型名） | PascalCase | `LogCollect`、`LogSource`、`LogType` |
| 模块 / 包 | snake_case | `app/log_box/`、`collect.py` |
| 实例 / 工厂对象 | snake_case | `log_collect`（`LogCollect` 实例）、`log_box`（工厂对象） |
| 常量 | UPPER_SNAKE | `MSG_PREFIX`、`OKWW_PUSH_RULES` |

> `log_box` 同时是「包名」与「工厂对象名」：`from app.log_box import log_box`，
> 包=代码组织、对象=入口，语义不同，属 Python 常见写法。

---

## 顶层入口

```python
from app.log_box import log_box, LogType
```

`log_box` 同时是「包名」与「工厂对象名」：`app/log_box/` 为代码组织，工厂对象
`log_box` 提供 `get_collect()` 创建采集会话。

## 进程与推送边界（关键）

log_box 是**进程无关**的组件，结果落点由**宿主**决定：

- **宿主 = MAS 进程**（专项适配器内实例化）：构造时注入 `sink(log_type, text, ts)`
  直接写 `cur_user_item.push_log`，对适配器完全透明。**这是当前唯一已接通的宿主路径**。
- **宿主 = 用户脚本子进程**（`from app.log_box import log_box`）：不注入 sink，
  box 把处理结果渲染为 `@@LOGBOX@@` 受控 stdout 标记回传，MAS 侧
  `check_log` 嗅探后写入 `cur_user_item.push_log`。

> ⚠️ **脚本宿主目前是能力预留，尚未端到端接通**：box 的 `@@LOGBOX@@` 标记渲染/
> 解析、MAS 侧 `check_log` 单行嗅探逻辑均已就位，但 MAS 尚未把「用户脚本进程
> stdout」接入 `check_log`（脚本 stdout 现为 DEVNULL 丢弃，`check_log` 只读
> `LogPath` 日志文件），也未设置 `MAS_SCRIPT_LOG_PATH` 与 `import app.log_box`
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
    rotated_name=None,                     # 轮转文件名 strftime 模板（见下节「日志轮转补偿」）
)
```

### 日志源行为（LogSource）

单个被采集文件按 **offset 增量读取**，`close()` 收尾时一次性读完会话剩余内容：

- **轮转补偿**：检测到文件身份变化（inode/Windows 创建时间任一变化）时，先找回被
  轮换的旧日志中**尚未读过**的部分，再从头读新文件，避免轮转前内容静默丢失。有
  inode 时一律按 inode 在同目录找回被重命名的旧文件（与运行日志监控 LogMonitor
  同逻辑，见下节）；inode 不可用时按 `rotated_name` 模板或 `.bak` 约定探测
  （日期式命名需声明模板）。
- **截断**：文件变小但身份未变时，重置到文件头重读。
- **会话外内容**：`start_from_end=True` 时只采会话内新增，会话开始（`open()`）前的
  历史内容不进入结果。

> 单次任务日志量大时，结果是一次性入内存的（`close()` 时整体采集）。专项若运行极长、
> 日志极大，需自行评估该内存占用（当前 okww 单会话日志量在可接受范围）。

## 日志轮转补偿（跨零点必读）

脚本日志在任务运行期间被脚本自身滚动（最典型：跨零点按天滚动，如
`log.txt` → `log.txt.YYYY-MM-DD`）时，LogSource 靠「轮转补偿」把旧文件里尚未
读过的部分接回来。各脚本滚动命名各不相同，但缺省逻辑与命名无关：

**找回优先级（与运行日志监控 LogMonitor 同一逻辑）**：有 inode（本地 NTFS
均可用）时**一律按 inode** 在同目录找回被重命名的旧文件并从未读 offset 续读
——不依赖命名猜测、不会误读同名旧残留，声明模板也不参与；inode 可用但未命中
（删除重建等非重命名式换身份）时宁缺勿错，不猜名字。`.bak` 改名式滚动
（``xxx.log`` → ``xxx.log.bak``）同样命中。

**rotated_name 模板（仅无 inode 文件系统生效）**：文件系统不提供 inode
（`st_ino` 为 0，如 FAT32 / exFAT / 部分网络盘）时 inode 找回不可用，按模板
探测——完整轮转文件名的 strftime 模板（相对日志所在目录，log_box 按昨天/
今天生成候选）；未声明回退 `.bak` 约定猜测。日期式命名**必须声明**，不在
通用组件里猜测。

| 脚本 | 轮转命名 | rotated_name（仅无 inode 文件系统生效） |
|---|---|---|
| ZZZ-OD | `log.txt` → `log.txt.2026-09-07`（日期在名字末尾） | `f"{path.name}.%Y-%m-%d"` |
| OK 系（ok-script 家族） | `ok-script.log` → `ok-script.2026-09-04.log`（日期在中段） | `f"{path.stem}.%Y-%m-%d{path.suffix}"` |
| BetterGI | `better-genshin-impact20260822.log`（紧凑日期嵌 stem） | `better-genshin-impact%Y%m%d.log` |

**接入前必须确认的事**：

1. 脚本滚动是**重命名式**还是**删除重建 / 原地截断式**（查脚本源码的
   `TimedRotatingFileHandler`/自定义 namer 配置，或实测跨零点）。重命名式
   缺省即覆盖；删除重建式旧文件已不存在、截断式内容被销毁，均无法自动找回，
   需专项另行评估。
2. 运行日志盘是否提供 inode（本地 NTFS 均提供）：不提供且滚动命名是日期式
   时传 `rotated_name`（唯一兜底）；有 inode 时模板不参与、无需声明，
   `.bak` 式同样无需声明。
3. offset 续读语义不变：找回的旧文件与 open 时是同一文件，从记录的 offset
   续读恰好是未读内容；比 offset 还小时回退从头读（既有行为）。

参考实现：ZzzOd / Okww / OkNte 的 `AutoProxy` 中 `get_collect(rotated_name=...)`
（日期式命名声明）。

## LogCollect 采集会话

| 方法 | 说明 |
|---|---|
| `open(processor=None)` | 启动采集（幂等）；可传前置处理器（逐行 map/filter），也可 `@col.open()` 装饰器。前置处理器返回 `None` 丢弃该行 |
| `collect(regex, expr="", type=NORMAL)` | 声明式单行规则：匹配正则 + `$()` 提取表达式（可多条） |
| `collect_scope(start_re, end_re="", expr="", max_lines=50, type=NORMAL)` | 多行聚合规则 |
| `postprocess(processor)` | 登记后置处理器，作用于捕捉完的**最终结果集**（去重/规整），可 `@col.postprocess()` 装饰器 |
| `close(processor=None)` | 结束会话：冲刷多行残留 → 后置处理 → 完成推送（幂等）；脚本宿主下 atexit 兜底 |

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

**LogType（`collect`/`collect_scope` 的 type 参数，逐条）** 与 **推送任务结果时机（通知设置 `SendTaskResultTime`，全局）** 是两层独立语义（与 MAS 原生推送一致）：

- **`LogType.NORMAL`（普通）**：该条目**任何推送报告均包含**。
- **`LogType.FAIL`（失败）**：该条目**仅在任务存在未完成用户时纳入报告**。
- **`SendTaskResultTime`（不推送 / 任何时刻 / 仅失败时）**：决定**是否推送整份报告**：
  - `不推送`：永不推送
  - `任何时刻`：任务结束即推送整份报告
  - `仅失败时`：**仅当任务存在未完成用户时**推送整份报告

## 推送详情开关（在专项侧，不在 log_box）

「任务报告中是否展示采集的节点详情」由**专项（或其用户配置）**决定，log_box 对此
无感知——它只负责把结果写进 `push_log`。开关在专项**是否创建/启用 log_box** 的入口
消费（从源头决定是否产生数据），而不是在聚合层做事后过滤：

- **通用脚本**：`PushLogEnabled`（web UI 配置）控制是否采集并聚合推送日志。
- **OK-WW专项**：用户级 `Notify.PushLogMode`（关闭/逐条/汇总三态，旧版布尔
  `PushLogEnabled` 已由迁移逻辑统一转为三态）——「关闭」时 **AutoProxy 侧不创建
  log_box**（不读日志、不翻译、不匹配），该用户 push_log 为空，报告聚合
  （`build_user_result_text`）自然只有结果行、不含其节点详情；「逐条/汇总」决定
  报告中节点详情的呈现形态（见下文「推送落地」）。参考实现：
  `app/task/Okww/AutoProxy.py` 的 `prepare()` 按模式启停 + `final_task()` 判空收尾。

**给未来适配器的模式**：开关 = 专项自己的配置项，在专项**是否创建/启用 log_box** 的
入口（如 AutoProxy `prepare()`）消费——关闭即不创建（省采集开销），**不要**在 log_box
里加通用开关，也不要在聚合层做采后过滤；各专项的开关语义、默认值、UI 位置不同，
放 log_box 只会强塞专项语义。


## 表达式语法（权威文档在前端目录）

`collect(regex, expr)` / `collect_scope(..., expr)` 的提取表达式与通用脚本
web 推送配置用的是**同一套表达式引擎**，完整语法文档维护在
`frontend/src/views/EditView/Script/docs/`（web 配置界面内嵌「说明文档」的
同源文件，随前端一起分发）：

- [expression-doc.md](../../../../frontend/src/views/EditView/Script/docs/expression-doc.md) — 表达式指南（函数 / 正则 / 混合模式，**首选入口**）
- [regex-doc.md](../../../../frontend/src/views/EditView/Script/docs/regex-doc.md) — 正则语法
- multiline-doc.md / split-doc.md — 多行聚合与分割

专项内建规则最常用的语义速查（详见上方文档）：

| 语法 | 语义 |
| --- | --- |
| `$()`（空） | 返回整行（可多次复用），常接函数链 `.cutby("定位",0,1)` 截取 |
| `$(正则)` | 取捕获组中的非空组（多组以 `\n` 拼接）；无捕获组 → 空串 |
| `+` / `;` | 同行拼接 / 换行拼接；一行内所有 `$()` 必须全命中该行才输出 |
| 函数链 | `.cut/.get/.cutby/.subby/.replace/.trim/.upper/.lower`；定位失败时跳过、返回原文（不报错） |

> `$()` 内正则默认 DOTALL（`.` 跨行）；单行内提取用 `[^\n]+`。
> 文档里 missing 语义「找不到定位文本跳过处理」同样适用于专项规则——规则
> 匹配正则先行过滤、表达式只做提取，失败面最小。

## 规则调试 API（debug_pattern）

`app.utils.LogPatternExtractor.debug_pattern` 是规则调试的现成入口（web 推送
配置的 🐛 调试按钮即基于它，与「日志提取」功能共用同一引擎）。专项排查
规则命中/提取问题直接用它，**不要手工拼 RegexMatcher**：

```python
from app.utils.LogPatternExtractor import debug_pattern

config = {"type": "regex", "match": r"...", "extract": r"..."}  # split/multiline 同理
error, is_multiline, results = debug_pattern(config, log_text)
# error: 配置级错误（正则/表达式语法错误等），None=通过
# results: 逐行 {"idx", "hit", "extracted", "line"}——含未命中行，
#          对整份日志一次跑完即可看清「哪些行命中、各自提取了什么」
```

与 `apply_patterns` 的差异：apply_patterns 只回首个命中且不含未命中信息，
调试场景一律用 debug_pattern（入口统一 strip、不受 enabled 开关影响）。

## 表达式引擎自定义函数

表达式函数链（`.cut(...)` 等）的实现在 `app/utils/expression/functions.py`：每个函数
接收 `(text, args)` 返回处理后的字符串，注册在模块级 `FUNCTIONS` 字典中，由
`apply_function(name, args, text)` 按名调用。新增自定义函数 = 往 `FUNCTIONS` 加一条
「名字 → `fn(text, args)`」映射，表达式里即可按 `.名字(...)` 调用；对 web 前端面板
不暴露。

```python
# app/utils/expression/functions.py
def fn_suffix(text: str, args: list[Arg]) -> str:
    """suffix(str) — 追加后缀"""
    return text + (str(args[0]) if args else "")

FUNCTIONS["suffix"] = fn_suffix  # 注册后表达式可用 .suffix(" 剩余电量")
```

在 `$()` 表达式中按函数名调用（作用于捕获组文本）：

```python
col.collect(r"current_stamina (\d+)", r'$((\d+)).suffix(" 剩余电量")')
```

> **为什么函数是具名注册而不是匿名传入**：规则是「参数」形态（正则 + 表达式
> 字符串），脚本子进程宿主跨进程只传规则参数、不传函数体（契约不含闭包/状态）；
> 自定义处理一律具名登记进 `FUNCTIONS`，规则字符串可序列化、跨宿主一致、
> 编译期函数名校验。

## 专项喂参示例（MAS 进程宿主）

专项只做：实例化一个 log_box、塞入日志路径与规则、注入 sink、挂前置翻译与
后置状态解析；其余全由 box 完成（参见 okww 的 `app/task/Okww/`）：

```python
from app.log_box import log_box, LogType

self.log_collect = log_box.get_collect(
    paths=[self.script_log_path],  # 相对 RootPath 派生，不硬编码绝对路径
    sink=self._append_push_log,    # 注入到 cur_user_item.push_log
    start_from_end=True,
    rotated_name=...,              # 仅无 inode 文件系统生效（日期式滚动唯一兜底）
)
self.log_collect.open(translator.translate)          # 前置翻译
for match_re, expr, log_type in PUSH_RULES:          # 喂规则参数（状态标记规则）
    self.log_collect.collect(match_re, expr, log_type)
# 结束时机（如进程关闭判定 / final_task）：col.close(resolve)
```

> okww 实际用法：在 `AutoProxy.prepare()` 里先读用户级「是否采集节点详情」开关，关闭则
> **不创建 log_box**（`final_task` 判空收尾），见上文「推送详情开关」；规则为二元组时
> 用 `collect(*rule)` 展开即可。

后处理示例：按节点解析最终状态（失败 > 跳过 > 成功），裸节点名 = 开始标记默认成功
（需消费并返回 `(log_type, text, ts)` 元组，日志类型与时间戳随元组一并保留）：

```python
import re
_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}

def resolve(results):
    """输入/输出均为 (log_type, text, ts) 元组，日志类型与时间戳随元组一并保留"""
    order, states = [], {}
    for _log_type, text, ts in results:
        m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", text)
        status, node = (m.group(1), m.group(2)) if m else ("✅ 成功", text)
        rank = _STATUS_RANK[status]
        if node in states:
            order.remove(node)  # 保留最后一次出现顺序
        order.append(node)
        if rank > states.get(node, (0, "", 0.0))[0]:
            states[node] = (rank, status, ts)
    # 规则通常统一产出普通类型，节点级失败由文本「❌ 失败:」体现，
    # 直接以 LogType.NORMAL 输出即可（无需按节点重建类型映射）
    return [
        (LogType.NORMAL, f"{states[node][1]}: {node}", states[node][2])
        for node in order
    ]
```

> 节点级失败用 `LogType.NORMAL` + 文本「❌ 失败:」始终展示；推送时机由全局
> `SendTaskResultTime` 控制（见上文「日志类型与推送时机语义」）。

## 推送落地：聚合（通用工具）

push_log 落进 `cur_user_item.push_log`（`list[tuple]`，元素为 `(log_type, text)`
或 `(log_type, text, ts)`）后，聚合统一走 `app/tools/push_log.py` 的
`build_user_result_text`，专项**不要**自行拼接实现：

- `build_user_result_text(users, has_uncompleted)`：按用户交错组装「用户结果行 +
  该用户节点详情」报告文本——每个用户先输出 `用户名: 用户result` 结果行，随后
  紧跟该用户的节点详情，多账号任务时各用户节点归属清晰；「失败」类型条目仅在
  任务存在未完成用户时纳入（与 MAS 原生推送策略一致）。节点详情按用户级
  `push_log_mode`（`Notify.PushLogMode`）三态呈现：关闭 = 不输出；逐条 = 逐条带
  采集时间戳（HH:MM）前缀；汇总 = 按（账号, 状态）聚合为一行；未设置模式的用户
  （如通用脚本）保持逐条原样输出。
- 注入端点 = **专项 `manager.final_task` 汇总**：用它替代原 result 拼接，产物写入
  报告的 `result` 字段，随后 `push_notification("代理结果")` 交
  `app/task/notify_core.py` 的 `push_proxy_result` 推送。现行参考实现：okww 与
  ZzzOd 的 manager/notify（采集结果全部并入 result，通知侧不再单独追加节点）。

```python
# manager.final_task：按用户交错组装（节点并入 result）
has_uncompleted = len(error_user) + len(wait_user) > 0
user_result_text = build_user_result_text(self.script_info.user_list, has_uncompleted)
```

## 脚本宿主示例（用户脚本子进程）

> ⚠️ **预留示例，尚未端到端接通**：见上方「进程与推送边界」说明，脚本 stdout 尚未
> 接入 MAS 的 `check_log`。以下仅为将来接通后的用法示意，当前不可交付。

```python
from app.log_box import log_box, LogType

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
   不是「第 1 个捕获组」。要取正则分组，在 `collect(match_re, expr)` 的表达式里
   用捕获组包裹，如 `$((捕获组))`。

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

8. **脚本滚动不是重命名式**：找回按 inode 定位被重命名的旧文件，只对
   「改名旧文件后新建」式滚动生效；脚本若删除重建或原地截断日志，旧内容无从
   找回（有 inode 时声明模板也不猜名字，宁缺勿错）。仅无 inode 文件系统需要
   声明 `rotated_name`，接入前按「日志轮转补偿」确认滚动方式。
