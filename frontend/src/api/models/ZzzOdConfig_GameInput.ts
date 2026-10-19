/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ZzzOdConfig_GameInput = {
    /**
     * 多用户账号切换方式（脚本级下拉，value 对应 manager 的分派分支）： 单实例切换（默认，推荐）= 逐用户独立会话：注入该用户配置 → 单实例 运行（仅运行当前，无槽间切换）→ 跑完关闭 → 下一个用户。失败域 隔离最好，重试只重启失败用户； 多实例切换（不推荐）= 全部启用用户合并为一轮多账号运行，一条龙内部 依次切换账号。总时长最短，但单槽失败会拖整轮重试、切换次数随 用户数线性增长； MAS切换 = MAS 侧 OCR 操控游戏完成账号切换后交一条龙运行（暂未开放）。
     */
    AccountSwitch?: ('单实例切换' | '多实例切换' | 'MAS切换' | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 任务结束后由 MAS 关闭游戏（收尾/手动停止时按进程名结束游戏本体， 覆盖失败重试与手动停止场景，是「结束后操作」的兜底）。与用户级 OneDragon.AfterDone 下发的 --close-game 相互独立，同时配置会各 执行一次（无害）
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 是否由 MAS 管理游戏进程（任务前启动游戏由此开关总控）
     */
    Enabled?: (boolean | null);
    /**
     * 任务前由 MAS 启动游戏（检测到游戏进程正在运行时跳过重复启动）
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 游戏路径（游戏本体 ZenlessZoneZero.exe）
     */
    Path?: (string | null);
    /**
     * 启动游戏后的等待时间（秒）
     */
    WaitTime?: (number | null);
};

