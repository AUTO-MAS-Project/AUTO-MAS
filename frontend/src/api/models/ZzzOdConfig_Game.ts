/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * ZZZ-OD 游戏配置
 */
export type ZzzOdConfig_Game = {
    /**
     * 是否由 MAS 管理游戏进程（任务前启动游戏由此开关总控）
     */
    Enabled?: (boolean | null);
    /**
     * 任务前由 MAS 启动游戏（检测到游戏进程正在运行时跳过重复启动）
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 游戏路径（游戏本体 exe）
     */
    Path?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 启动游戏后的等待时间（秒）
     */
    WaitTime?: (number | null);
    /**
     * 任务结束后是否由 MAS 关闭游戏
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 多用户账号切换方式：单实例切换=逐用户独立会话（默认，推荐）；多实例切换=全部用户合并一轮多账号运行（不推荐）；MAS切换=MAS侧切换账号后交一条龙（暂未开放）
     */
    AccountSwitch?: ('单实例切换' | '多实例切换' | 'MAS切换' | null);
};

