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
  - "✅ 成功: 节点" = 明确成功（源码有成功/完成日志的节点）
  后处理按节点聚合，状态优先级 失败 > 跳过 > 成功。
- 补充翻译为 AutoMAS 项目自带的 .po 文件（res/i18n/ 内置资源），与 ok-ww 自带
  的 ok.po 一同加载，补充优先；.po 为可读源码，可直接维护。
"""

import re
from pathlib import Path

from app.log_box import LogType

# ok-ww 自带翻译文件相对路径（从 RootPath 派生，不硬编码绝对路径）
OKWW_REL_I18N_PO = "data/apps/ok-ww/repo/i18n/zh_CN/LC_MESSAGES/ok.po"
# AutoMAS 项目自带的补充翻译 .po（res/ 内置资源，运行时以工作目录解析，
# 随打包资源分发，不依赖源码树路径；.po 为可读源码，可直接维护）
OKWW_SUPPLEMENT_PO = Path.cwd() / "res" / "i18n" / "okww.po"

# 推送规则：(匹配正则, 提取表达式, 日志类型)；匹配与提取均在翻译后行。
# 提取表达式输出状态标记（裸节点名 / "状态: 节点"），由 okww_resolve 解析。
# 顺序敏感：先约电台失败须在成功前（"先约电台已结束" 含 "先约电台"）。
OKWW_PUSH_RULES: list[tuple[str, str, str]] = [
    # ── 开始/动作标记（后处理默认解析为成功）──
    (r"ok:OK start", r'"启动"', LogType.NORMAL),
    (r"opened gray_book_boss", r'"梦魇巢穴"', LogType.NORMAL),
    # 活跃奖励：领取动作（info_set 开始行不含 "reward"，仅此领取行命中）
    (r"领取每日奖励 reward", r'"活跃奖励"', LogType.NORMAL),
    # 邮件：源码无成功日志，仅 info_set 开始标记（无失败即成功）
    (r"领取邮件", r'"邮件"', LogType.NORMAL),
    # 每周乐园 / 合并声骸：开始标记，最终状态由跳过/成功/失败标记决定
    (r"检查每周乐园", r'"每周乐园"', LogType.NORMAL),
    (r"检查已弃置声骸", r'"合并声骸"', LogType.NORMAL),
    # 多账号：切换账号开始
    (r"正在返回登录界面", r'"切换账号"', LogType.NORMAL),
    # ── 失败标记（源码 log_error 专属失败日志）──
    # 节点级失败始终展示（类型保持普通，状态由文本「❌ 失败:」体现，不被
    # 未完成用户过滤；推送时机由 SendTaskResultTime 全局控制，与逐条类型无关）
    (r"先约电台已结束", r'"❌ 失败: 先约电台"', LogType.NORMAL),  # 须在成功前
    (r"NightmareNestTask Failed", r'"❌ 失败: 梦魇巢穴"', LogType.NORMAL),
    (r"GardenTask Failed", r'"❌ 失败: 每周乐园"', LogType.NORMAL),
    (r"MergeEchoTask Failed", r'"❌ 失败: 合并声骸"', LogType.NORMAL),
    # 多账号：切换账号失败（源码 log_error / 抛异常，见 MultiAccountDailyTask）
    (r"click drop down no effect", r'"❌ 失败: 切换账号"', LogType.NORMAL),
    (r"账号选择失败", r'"❌ 失败: 切换账号"', LogType.NORMAL),
    (r"切换账号失败", r'"❌ 失败: 切换账号"', LogType.NORMAL),
    # ── 跳过标记 ──
    (r"每周乐园已完成", r'"⏭ 跳过: 每周乐园"', LogType.NORMAL),
    # ── 明确成功标记 ──
    # 战令成功无日志（battle pass 为开始），靠无失败判定；此规则置于失败规则后
    (r"先约电台", r'"先约电台"', LogType.NORMAL),
    (r"乐园任务完成", r'"✅ 成功: 每周乐园"', LogType.NORMAL),
    # 体力刷本：结束日志（must_use completed 带剩余体力）
    (r"must_use completed", r'"✅ 成功: 体力刷本 剩余" + $((?:current stamina: )(\d+))', LogType.NORMAL),
    (r"体力已用尽", r'"✅ 成功: 体力刷本（体力已用尽）"', LogType.NORMAL),
    (r"体力不足以继续", r'"✅ 成功: 体力刷本（体力已用尽）"', LogType.NORMAL),
    (r"每日任务已完成", r'"✅ 成功: 每日完成"', LogType.NORMAL),
    (r"MainWindow:退出", r'"✅ 成功: 退出"', LogType.NORMAL),
    # 多账号：登录成功
    (r"登录成功", r'"✅ 成功: 登录"', LogType.NORMAL),
]

# 状态优先级：失败 > 跳过 > 成功
_STATUS_RANK = {"✅ 成功": 1, "⏭ 跳过": 2, "❌ 失败": 3}


def okww_resolve(
    results: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """后处理：按节点解析最终状态（失败 > 跳过 > 成功），保持最后一次出现顺序

    输入/输出均为 ``(log_type, text)`` 元组（与 log_box `_PostProcessor` 契约
    一致），日志类型随元组一并保留。规则产出两类标记：裸节点名（开始/动作标记，
    默认成功）与 "状态: 节点" 标记。同一节点多次出现保留最高优先级状态，且节点
    顺序按最后一次出现排列（多会话日志时取最后会话的流程顺序）。
    """
    lines = [text for _, text in results]
    order: list[str] = []
    states: dict[str, tuple[int, str]] = {}
    for line in lines:
        m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", line)
        if m:
            status, node = m.group(1), m.group(2)
        else:
            status, node = "✅ 成功", line
        rank = _STATUS_RANK[status]
        if node in states:
            order.remove(node)  # 移至末尾：保留最后一次出现顺序
        order.append(node)
        if rank > states.get(node, (0, ""))[0]:
            states[node] = (rank, status)
    # 取最后出现节点的日志类型；按节点名（去状态前缀后）映射，避免与完整
    # 文本键不匹配而丢失类型（规则可能产出 "状态: 节点" 或裸节点名两种形态）
    last_type: dict[str, str] = {}
    for log_type, text in results:
        m = re.match(r"^(✅ 成功|⏭ 跳过|❌ 失败): (.*)$", text)
        node = m.group(2) if m else text
        last_type[node] = log_type
    return [
        (last_type.get(node, "普通"), f"{states[node][1]}: {node}")
        for node in order
    ]
