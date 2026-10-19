/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_RunInput = {
    /**
     * 每天正常完成一次后，当天剩余时间跳过的 MaaFW 任务名列表
     */
    DailyOnceTasks?: (string | null);
    /**
     * 游戏客户端更新：Off 不检查 / Check 只检查，落后时本次判失败并提示手动更新 / AutoInstall 落后时自动下载安装包并 adb 安装（保留游戏数据）。只在特调实现了 游戏更新钩子（当前只有 M9A）且 controller 是 ADB 时生效，通用 MaaFW 不读。 Off 必须排第一：OptionsValidator 纠错回退的是 options[0]。
     */
    GameUpdateMode?: ('Off' | 'Check' | 'AutoInstall' | null);
    /**
     * 原地打转检测（实验性，默认关）。任务在短周期里反复执行同一串节点（周期 ≤ 8 步、每轮都有点击 / 滑动等物理动作）、识别结果又几乎不变时判定卡死：≥ 200 轮且持续 ≥ 10 分钟就停掉这个任务，收尾与单任务超时同一口径（截图、第一个任务或关键任务 结束本轮，其余记失败后继续）。判据见 tools/core/runner/loop_guard.py。
     */
    LoopGuard?: (boolean | null);
    /**
     * 每月正常完成一次后，本月剩余时间跳过的 MaaFW 任务名列表
     */
    MonthlyOnceTasks?: (string | null);
    /**
     * 运行引擎，决定「谁来跑」： 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 单次运行时间限制（分钟），套在单个用户的整次运行上。截止时刻随 job 文件交给 worker：到点它自己停掉当前任务、截一张超时图、带回已完成的任务；宿主只在 worker 没能及时停下时才强杀（那时既没有截图也没有进度）。MaaFW 项目一轮日常 动辄几十分钟，30 分钟默认值实测常被误伤，放宽到 120。
     */
    RunTimeLimit?: (number | null);
    /**
     * 运行次数限制。重试不关游戏、不再等启动，从当前画面接着跑； 脚本自己的加载超时（MaaEnd 回大世界 20s）一次抖动就把整轮判失败， 只给一次机会时用户看到的就是「从来没成功过」，默认与其他专项一样 3 次。
     */
    RunTimesLimit?: (number | null);
    /**
     * 单个任务的时限（分钟），0 表示不限。某个任务卡住时到点只停它、截一张超时图， 记一条任务失败后接着跑后面的任务（计划里第一个任务超时则结束本轮）；不再让 一个卡住的任务吃掉整轮 RunTimeLimit 的时间。 默认 45 而不是 30：M9A 智能均衡刷材料正常 1–22 分钟，自动深眠在新内容日 实测 33.7 分钟，30 会误伤正常运行。
     */
    TaskTimeLimit?: (number | null);
    /**
     * 按任务名覆盖的单任务时限（分钟），键是 MaaFW 任务名；值 0 表示该任务不限。 默认值由类属性 DEFAULT_TASK_TIME_LIMIT_OVERRIDES 决定（特调可内置几条）； 只在配置里没有这个键时生效，用户存过的值（含清空成 {}）原样保留。
     */
    TaskTimeLimitOverrides?: (string | null);
    /**
     * 每周正常完成一次后，本周剩余时间跳过的 MaaFW 任务名列表
     */
    WeeklyOnceTasks?: (string | null);
};

