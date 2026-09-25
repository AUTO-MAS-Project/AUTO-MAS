"""OK-WW 推送日志采集参数（log_box 实例的喂参方）

OK-WW 专项作为 log_box 的一个实例：本模块只提供参数（i18n 翻译文件、补充
翻译 .po、规则、后置处理器），日志获取、前置处理、规则匹配、后置处理与推送
全部由 log_box 完成。

规则说明：
- 翻译器在 open() 前置处理器逐行执行；此后匹配与提取均作用于翻译后的行。
- 匹配正则对应翻译后的节点内容（英文标识未翻译则保留，翻译了则匹配中文），
  与 ok.po / 补充 .po 的译文耦合，改译文时需同步核对规则。
- 规则产出「状态标记」，最终状态由 okww_resolve 后处理解析：
  - 裸节点名 = 开始/动作标记，默认成功，除非存在失败/跳过标记
  - "❌ 失败: 节点" = 失败（匹配源码 log_error 的专属失败日志，排除战斗噪音）
  - "⏭ 跳过: 节点" = 跳过（如每周乐园已完成）
  - "NO_DISCARDED_ECHO" / "BATTLE_PASS_ENDED" = 该节点这一次没做（已弃置声骸不足
    1000、战令已结束，上游分别走提示行与 log_error），收尾按「⏭ 跳过: 节点（原因）」
    呈现，真正的异常仍判失败，且标记只作用于当次尝试（跨会话或重试不延续）
  - "✅ 成功: 节点" = 明确成功（源码有成功/完成日志的节点）
  - "⚡ 剩余体力: N" = 刷完后的剩余体力（取最后一条 `体力当前:`；上游是领奖时
    才扣体力，故最后一次领奖的 `current stamina: N` 优先于开刷前的
    `info_set current_stamina N`，独立成行不参与状态聚合）；"体力刷本" 保留为
    成功节点
  后处理按节点聚合，状态优先级 失败 > 跳过 > 成功。
- 补充翻译为 AutoMAS 项目自带的 .po 文件（res/i18n/ 内置资源），与 ok-ww 自带
  的 ok.po 一同加载，补充优先；.po 为可读源码，可直接维护。
"""

import re
from pathlib import Path

from app.log_box.logtype import LogType
from app.utils import resource_path

# ok-ww 自带翻译文件相对路径（从 RootPath 派生，不硬编码绝对路径）
OKWW_REL_I18N_PO = "data/apps/ok-ww/repo/i18n/zh_CN/LC_MESSAGES/ok.po"


def _okww_supplement_po() -> Path:
    """AutoMAS 项目自带的补充翻译 .po（res/ 内置资源，按源码位置解析，不随
    工作目录变化；.po 为可读源码，可直接维护）。
    """
    return resource_path("i18n", "okww.po")


# 推送规则：(匹配正则, 提取表达式)；匹配与提取均在翻译后行。
# 提取表达式输出状态标记（裸节点名 / "状态: 节点"），由 okww_resolve 解析。
# 顺序敏感：先约电台失败须在成功前（"先约电台已结束" 含 "先约电台"）。
OKWW_PUSH_RULES: list[tuple[str, str]] = [
    # ── 开始/动作标记（后处理默认解析为成功）──
    (r"ok:OK start", r'"启动"'),
    (r"opened gray_book_boss", r'"梦魇巢穴"'),
    # 活跃奖励：领取动作（info_set 开始行不含 "reward"，仅此领取行命中）
    (r"领取每日奖励 reward", r'"活跃奖励"'),
    # 邮件：源码无成功日志，仅 info_set 开始标记（无失败即成功）
    (r"领取邮件", r'"邮件"'),
    # 每周乐园 / 合并声骸：开始标记，最终状态由跳过/成功/失败标记决定
    (r"检查每周乐园", r'"每周乐园"'),
    (r"检查已弃置声骸", r'"合并声骸"'),
    # 多账号：切换账号开始
    (r"正在返回登录界面", r'"切换账号"'),
    # ── 失败标记（源码 log_error 专属失败日志）──
    # 节点级失败始终展示（类型保持普通，状态由文本「❌ 失败:」体现，不被
    # 未完成用户过滤；推送时机由 SendTaskResultTime 全局控制，与逐条类型无关）
    # 注意：ok.po 是「长键优先」的子串替换，会把类名里的裸 token 一并译掉，
    # 如 Echo→声骸 使 `MergeEchoTask` 变 `Merge声骸Task`。因此含类名的英文规则
    # 须写成「译文形式|英文原形式」，只写英文原形式在译文生效时永不命中
    # 战令失败与开始标记同节点（「先约电台已结束」只是原因），收尾按 _REASON_MARKS
    # 呈现为「⏭ 跳过: 先约电台（已结束）」，不再另起一个「先约电台已结束」节点
    (r"先约电台已结束", r'"BATTLE_PASS_ENDED"'),  # 须在成功前
    (r"NightmareNestTask Failed", r'"❌ 失败: 梦魇巢穴"'),
    (r"GardenTask Failed", r'"❌ 失败: 每周乐园"'),
    (r"Merge声骸Task Failed|MergeEchoTask Failed", r'"❌ 失败: 合并声骸"'),
    # 合并声骸「不足 1000」不是异常：源码用 `if self.click_dialog_left_button():`
    # 判断融合弹窗是否出现，意图是没弹窗就走 else 提示 `Must have 1000 discarded
    # Echo to Run` 后返回。该 else 可达时日志直接给出提示行；若该 helper 找不到按钮
    # 时抛 CannotFindException，else 便成死代码，「没到 1000 个」改以异常形式落进
    # `MergeEchoTask Failed`——后者只能靠 traceback 回显的调用点源码行识别（该行
    # 文本只在 MergeEchoTask.py 出现，融合流程内部报错回显的是别的行）。
    # 两种签名统一产出 NO_DISCARDED_ECHO（不直接产出带后缀的节点名，否则会与开始
    # 标记的「合并声骸」并存成两个节点），由 okww_resolve 把该节点按跳过呈现
    (
        r"Must have 1000 discarded 声骸 to Run|Must have 1000 discarded Echo to Run",
        r'"NO_DISCARDED_ECHO"',
    ),
    (r"if self\.click_dialog_left_button\(\):", r'"NO_DISCARDED_ECHO"'),
    # 多账号：切换账号环节失败（源码 _select_and_login_account 内 log_error/抛异常）
    (r"click drop down no effect", r'"❌ 失败: 切换账号"'),
    (r"账号选择失败", r'"❌ 失败: 切换账号"'),
    (r"切换账号失败", r'"❌ 失败: 切换账号"'),
    # 多账号每日任务整体异常：MultiAccountDailyTask 任一账号轮次抛异常，日志统一
    # 收尾为 `TaskExecutor:👥 多账号每日任务 exception stopped`（翻译后 `多账号
    # 每日任务` + `exception stopped`）。该信号表示「多账号每日任务」整体失败
    # （如游戏未进入主世界），不是单一"切换账号"环节失败。注意不能光凭裸露的
    # `exception stopped` 匹配——普通每日任务异常终止是 `TaskExecutor:📅 每日任务
    # exception stopped`，会误判；必须用 `多账号每日任务` 作前缀锚点
    (r"多账号每日任务 exception stopped", r'"❌ 失败: 多账号每日任务"'),
    # 英文原行经 ok.po 译作 `多账号一条龙`（`Multi Account Daily Task` 的译文），
    # 故兜底规则同样写成「译文形式|英文原形式」
    (
        r"多账号一条龙 exception stopped|Multi Account Daily Task exception stopped",
        r'"❌ 失败: 多账号每日任务"',
    ),
    # ── 跳过标记 ──
    (r"每周乐园已完成", r'"⏭ 跳过: 每周乐园"'),
    # ── 明确成功标记 ──
    # 战令成功无日志（battle pass 为开始），靠无失败判定；此规则置于失败规则后
    (r"先约电台", r'"先约电台"'),
    (r"乐园任务完成", r'"✅ 成功: 每周乐园"'),
    # 体力刷本：must_use completed = 一次刷本完成（保留成功节点）。同一行的 N 是
    # 上游 use_stamina 领奖扣体力后算出的真实剩余（`current -= used`，单把消耗随
    # 任务不同：无音区 60、铸潮/模拟 40，双倍按两把计），故一并产出最终剩余体力；
    # 一条规则的两个标记用换行拼接，由 okww_resolve 按行拆分
    (
        r"must_use completed",
        r'"体力刷本"; "体力当前:" + $((?:current stamina: )(\d+))',
    ),
    # 另一条终止分支「体力不足以继续」（补充 .po 的译文）同样在领奖后打印，
    # N 也是扣完后的真实剩余，只补剩余体力、不做节点标记；前缀锚定同时兼容
    # 英文原行（补充译文缺失时生效）
    (
        r"current stamina: (\d+)",
        r'"体力当前:" + $((?:current stamina: )(\d+))',
    ),
    # 开刷前读数：`info_set current_stamina N` 是进入 F2 图鉴时读到的值，仅作兜底
    # （本把之后若发生领奖，终值由上面的领奖行覆盖）。
    # 上游 ok.po 把 current_stamina 译作「当前体力」，翻译后行须匹配译文；
    # 英文原行规则保留兜底（翻译文件缺失或上游回退时生效）。
    (r"当前体力 (\d+)", r'"体力当前:" + $((?:当前体力 )(\d+))'),
    (r"current_stamina (\d+)", r'"体力当前:" + $((?:current_stamina )(\d+))'),
    (r"每日任务已完成", r'"✅ 成功: 每日完成"'),
    (r"MainWindow:退出", r'"✅ 成功: 退出"'),
    # 多账号：登录成功
    (r"登录成功", r'"✅ 成功: 登录"'),
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


def okww_resolve(results: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
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
    ts_of: dict[str, float] = {}
    last_stamina: int | None = None
    last_stamina_ts: float = 0.0
    active_marks: set[str] = set()

    def _mark(status: str, node: str, ts: float) -> None:
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
    # 规则均为二元组，经 LogCollect.collect 后 log_type 恒为 LogType.NORMAL；
    # 节点级失败由文本「❌ 失败:」体现，不依赖逐条类型过滤，故直接输出普通
    forced: dict[str, tuple[str, str]] = {
        node_name: (status, reason)
        for key, (node_name, status, reason) in _REASON_MARKS.items()
        if key in active_marks
    }
    status_lines: list[tuple[str, str, float]] = []
    for node in order:
        if node in forced:
            status, reason = forced[node]
            status_lines.append(
                (LogType.NORMAL, f"{status}: {node}（{reason}）", ts_of[node])
            )
        else:
            status_lines.append((LogType.NORMAL, f"{states[node][1]}: {node}", ts_of[node]))
    if last_stamina is not None:
        status_lines.append(
            (LogType.NORMAL, f"⚡ 剩余体力: {last_stamina}", last_stamina_ts)
        )
    return status_lines
