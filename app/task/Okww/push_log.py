"""OK-WW 推送日志采集参数（log_box 实例的喂参方）

OK-WW 专项作为 log_box 的一个实例：本模块只提供规则与后置处理器，文本内核
只执行规则匹配与后处理；文件读取、用户归属和交付由 AutoProxy 负责。

上游日志在运行时按界面语言翻译（`self.tr`），`info_set` 行则始终输出英文键，
因此规则直接匹配「当前用户实际写出的日志」：同一节点同时给出英文源文案与
中文界面文案，不再读取上游 ok.po 做前置翻译。节点名与状态由规则提取表达式
统一输出中文，与界面语言无关。

规则说明：
- 匹配正则直接作用于原始日志行；同一节点可能以英文或中文出现，规则须同时
  覆盖两种形态。上游改动源文案或中文译文时需同步核对规则。
- 规则产出「状态标记」，最终状态由 okww_resolve 后处理解析：
  - 裸节点名 = 开始/动作标记，默认成功，除非存在失败/跳过标记
  - "❌ 失败: 节点" = 失败（匹配源码 log_error 的专属失败日志，排除战斗噪音）
  - "⏭ 跳过: 节点" = 跳过（如每周乐园已完成）
  - "NO_DISCARDED_ECHO" / "BATTLE_PASS_ENDED" = 该节点这一次没做（已弃置声骸不足
    1000、战令已结束），收尾按「⏭ 跳过: 节点（原因）」呈现；真正的异常仍判失败，
    且标记只作用于当次尝试（跨会话或重试不延续）
  - "✅ 成功: 节点" = 明确成功（源码有成功/完成日志的节点）
  - "⚡ 剩余体力: N" = 刷完后的剩余体力（取最后一条 `current stamina:`；上游是领奖时
    才扣体力，故最后一次领奖的 `current stamina: N` 优先于开刷前的
    `info_set current_stamina N`，独立成行不参与状态聚合）；"体力刷本" 保留为
    成功节点
  后处理按节点聚合，状态优先级 失败 > 跳过 > 成功。
- 不再读取上游 ok.po、不做前置翻译：上游资源文件属私有布局，且译文变化会让
  规则静默失效；节点展示统一由规则提取表达式输出中文。
"""

import re

from app.utils import LOG_TYPE_NORMAL

# 推送规则：(匹配正则, 提取表达式)；匹配与提取均在原始日志行。
# 提取表达式输出状态标记（裸节点名 / "状态: 节点"），由 okww_resolve 解析。
# 顺序敏感：先约电台失败须在成功前（"先约电台已结束" 含 "先约电台"）。
OKWW_PUSH_RULES: list[tuple[str, str]] = [
    # ── 开始/动作标记（后处理默认解析为成功）──
    (r"ok:OK start", r'"启动"'),
    (r"opened gray_book_boss|已打开残象探寻", r'"梦魇巢穴"'),
    # 活跃奖励：领取动作（log_info 的领取行；info_set 行只有任务名，不单独匹配）
    (r"领取每日奖励|claim daily reward", r'"活跃奖励"'),
    # 邮件：源码仅 info_set 任务名，无成功日志（无失败即成功）
    (r"领取邮件|claim mail", r'"邮件"'),
    # 每周乐园 / 合并声骸：开始标记，最终状态由跳过/成功/失败标记决定
    (r"检查每周乐园|check weekly garden", r'"每周乐园"'),
    (r"检查已弃置声骸|check discarded echo", r'"合并声骸"'),
    # 多账号：切换账号开始
    (r"正在返回登录界面|Switching back to login screen", r'"切换账号"'),
    # ── 失败标记（源码 log_error 专属失败日志）──
    # 节点级失败始终展示（类型保持普通，状态由文本「❌ 失败:」体现，不被
    # 未完成用户过滤；推送时机由 SendTaskResultTime 全局控制，与逐条类型无关）
    # 战令失败与开始标记同节点（「已结束」只是原因），收尾按 _REASON_MARKS
    # 呈现为「⏭ 跳过: 先约电台（已结束）」，不再另起一个「先约电台已结束」节点
    (
        r"(?:先约电台|battle pass).*(?:已结束|maybe ended)",
        r'"BATTLE_PASS_ENDED"',
    ),  # 须在成功前
    (r"NightmareNestTask Failed|梦魇巢穴任务失败", r'"❌ 失败: 梦魇巢穴"'),
    (r"GardenTask Failed|乐园任务失败", r'"❌ 失败: 每周乐园"'),
    (r"MergeEchoTask Failed|声骸合成任务失败", r'"❌ 失败: 合并声骸"'),
    # 合并声骸开包失败：上游只打 log_error 后直接 return，不会抛进 DailyTask 的
    # `MergeEchoTask Failed` 分支；不认这条会把本次合并误报为成功
    (
        r"can not open bag with hotkey|无法使用快捷键",
        r'"❌ 失败: 合并声骸"',
    ),
    # 合并声骸「不足 1000」不是异常：上游在融合弹窗未出现时直接打印
    # `Must have 1000 discarded Echo to Run`，中文界面输出其译文。该标记不直接
    # 产出带后缀的节点名（否则会与开始标记的「合并声骸」并存成两个节点），由
    # okww_resolve 把该节点按跳过呈现。异常路径不读 traceback 回显的源码行——
    # 那会依赖上游内部写法；没有这条公开日志时按失败呈现
    (
        r"Must have 1000 discarded Echo to Run|需要至少 1000 个已弃置声骸才能运行",
        r'"NO_DISCARDED_ECHO"',
    ),
    # 多账号：切换账号环节失败（源码 log_error/抛异常）
    (r"click drop down no effect|点击下拉列表无效", r'"❌ 失败: 切换账号"'),
    (r"账号选择失败|Account selection failed", r'"❌ 失败: 切换账号"'),
    (r"切换账号失败|Failed to switch account", r'"❌ 失败: 切换账号"'),
    # 多账号每日任务整体异常：MultiAccountDailyTask 任一账号轮次抛异常，日志统一
    # 收尾为 `TaskExecutor:👥 多账号每日任务 exception stopped`（英文界面为
    # `👥 Multi Account Daily Task exception stopped`）。该信号表示「多账号每日
    # 任务」整体失败（如游戏未进入主世界），不是单一"切换账号"环节失败。注意不能
    # 光凭裸露的 `exception stopped` 匹配——普通每日任务异常终止会误判；必须用
    # 任务名作前缀锚点
    (
        r"多账号每日任务 exception stopped|Multi Account Daily Task exception stopped",
        r'"❌ 失败: 多账号每日任务"',
    ),
    # ── 跳过标记 ──
    # 上游当前中文译文是「每周乐园任务已完成」（旧译文为「每周乐园已完成」），
    # 两种都要认；该行表示本轮不再跑乐园，按跳过呈现
    (
        r"每周乐园(?:任务)?已完成|weekly garden already completed",
        r'"⏭ 跳过: 每周乐园"',
    ),
    # ── 明确成功标记 ──
    # 战令成功无日志（battle pass 为开始），靠无失败判定；此规则置于失败规则后
    (r"先约电台|battle pass", r'"先约电台"'),
    (r"乐园任务完成|Garden task completed", r'"✅ 成功: 每周乐园"'),
    # 体力刷本：must_use completed = 一次刷本完成（保留成功节点）。同一行的 N 是
    # 上游 use_stamina 领奖扣体力后算出的真实剩余（`current -= used`，单把消耗随
    # 任务不同：无音区 60、铸潮/模拟 40，双倍按两把计），故一并产出最终剩余体力；
    # 一条规则的两个标记用换行拼接，由 okww_resolve 按行拆分
    (
        r"must_use completed",
        r'"体力刷本"; "体力当前:" + $((?:current stamina: )(\d+))',
    ),
    # 另一条终止分支「体力不足以继续」同样在领奖后打印，N 也是扣完后的真实剩余，
    # 只补剩余体力、不做节点标记
    (r"current stamina: (\d+)", r'"体力当前:" + $((?:current stamina: )(\d+))'),
    # 开刷前读数：`info_set current_stamina N` 是进入 F2 图鉴时读到的值，仅作兜底
    # （本把之后若发生领奖，终值由上面的领奖行覆盖）。info_set 行始终输出英文键，
    # 中文界面也不例外
    (r"current_stamina (\d+)", r'"体力当前:" + $((?:current_stamina )(\d+))'),
    # 每日完成：行尾锚定——上游 farm 4C 追加阶段会先打预告行「每日任务已完成，
    # 开始传送并刷取4C声骸」（含该子串），无锚定会提前产出「每日完成」节点；
    # 真正的完成行（中英文）都以该文案结尾
    (r"每日任务已完成$|Daily Task Completed$", r'"✅ 成功: 每日完成"'),
    # 多账号：登录成功
    (r"登录成功|Login successful", r'"✅ 成功: 登录"'),
]

# 状态优先级：失败 > 跳过 > 成功
_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}

# 带原因的节点标记：标记 → (节点名, 呈现状态, 原因)。这类情况是「该节点这一次没做」
# （已弃置声骸不足 1000、战令已结束），既不是成功也不是失败，统一按「跳过」呈现并
# 把原因附在节点名后；只作用于当次尝试——遇到该节点新的开始标记即清除对应标记。
# 规则里节点名是字面量，改名时须同步
_REASON_MARKS: dict[str, tuple[str, str, str]] = {
    "NO_DISCARDED_ECHO": ("合并声骸", "⏭ 跳过", "已弃置声骸不足 1000"),
    "BATTLE_PASS_ENDED": ("先约电台", "⏭ 跳过", "已结束"),
}


def okww_resolve(
    results: list[tuple[str, str, float | None]],
) -> list[tuple[str, str, float | None]]:
    """后处理：按节点解析最终状态（失败 > 跳过 > 成功），保持最后一次出现顺序

    输入/输出均为 ``(log_type, text, ts)`` 元组（与 log_box `_PostProcessor`
    契约一致），日志类型与采集时间戳随元组一并保留。规则产出两类标记：裸节点
    名（开始/动作标记，默认成功）与 "状态: 节点" 标记；另外 ``体力当前:`` 为
    体力刷本的当前体力追踪标记，只保留最后一次，结束后独立输出一行
    「⚡ 剩余体力: N」，不参与状态聚合。体力刷本收尾的必须成功标记与剩余体力
    由同一条规则产出（换行拼接多个标记），故先按行拆分再逐行解析。「该节点这一次
    没做」的情况（已弃置声骸不足 1000、战令已结束）由 _REASON_MARKS 的标记标出，
    收尾按跳过呈现并把原因附在节点后（不论该节点此前是成功还是失败）；标记在遇到
    该节点新的开始标记（新一次尝试）时清除，不跨会话/重试生效。其余异常仍判失败。
    同一节点多次出现保留最高优先级状态，且节点顺序与时间戳都按最后一次出现排列
    （多会话日志时取最后会话的流程顺序），同优先级后出现也刷新时间戳，与排序逻辑
    保持一致。
    """
    order: list[str] = []
    states: dict[str, tuple[int, str]] = {}
    ts_of: dict[str, float | None] = {}
    last_stamina: int | None = None
    last_stamina_ts: float | None = 0.0
    active_marks: set[str] = set()

    def _mark(status: str, node: str, ts: float | None) -> None:
        rank = _STATUS_RANK[status]
        if node in states:
            order.remove(node)  # 移至末尾：保留最后一次出现顺序
        order.append(node)
        if rank >= states.get(node, (0, ""))[0]:
            states[node] = (rank, status)
            ts_of[node] = ts

    for _, text, ts in results:
        # 一条规则可产出多个换行拼接的标记（如「体力刷本」+「体力当前: N」），
        # 逐行解析，避免多个标记被当成一个节点名
        for marker in text.split("\n"):
            # 当前体力：仅记录最后一次，结束后据此输出「⚡ 剩余体力: N」
            if marker.startswith("体力当前:"):
                try:
                    last_stamina = int(marker[len("体力当前:") :])
                    last_stamina_ts = ts
                except ValueError:
                    pass
                continue
            if marker in _REASON_MARKS:
                # 「该节点这一次没做」：不产出节点，仅记标记供收尾呈现
                active_marks.add(marker)
                continue
            m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", marker)
            if m is None:
                # 裸节点名 = 开始/动作标记；该节点新一次尝试开始，上一轮的标记作废
                # （跨会话或重试时不让旧标记影响新结果）
                active_marks = {
                    key for key in active_marks if _REASON_MARKS[key][0] != marker
                }
                _mark("✅ 成功", marker, ts)
            else:
                _mark(m.group(1), m.group(2), ts)
    # 规则均为二元组，经文本管线 add_rule 后 log_type 恒为 LOG_TYPE_NORMAL；
    # 节点级失败由文本「❌ 失败:」体现，不依赖逐条类型过滤，故直接输出普通
    forced: dict[str, tuple[str, str]] = {
        node_name: (status, reason)
        for key, (node_name, status, reason) in _REASON_MARKS.items()
        if key in active_marks
    }
    status_lines: list[tuple[str, str, float | None]] = []
    for node in order:
        if node in forced:
            status, reason = forced[node]
            status_lines.append(
                (LOG_TYPE_NORMAL, f"{status}: {node}（{reason}）", ts_of[node])
            )
        else:
            status_lines.append(
                (LOG_TYPE_NORMAL, f"{states[node][1]}: {node}", ts_of[node])
            )
    if last_stamina is not None:
        status_lines.append(
            (LOG_TYPE_NORMAL, f"⚡ 剩余体力: {last_stamina}", last_stamina_ts)
        )
    return status_lines
