/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Cloud = {
    /**
     * 各用户最近一次确认已登录的时间（user_id → ISO 时间），只读展示用， 由运行结束后的写回与「登录云游戏」接口维护
     */
    LastLogin?: (string | null);
    /**
     * 等待用户在浏览器窗口里手动登录的时间（分钟）
     */
    LoginTimeoutMinutes?: (number | null);
    /**
     * 最长排队时间（分钟），同时计入每个模块的超时预算
     */
    MaxQueueMinutes?: (number | null);
    /**
     * 云·星穹铁道（Game.Platform = Cloud）专用，映射到三月七的 cloud_game_* 键 是否允许消耗付费时长走快速排队通道（花钱的开关，默认关）
     */
    UsePaidTime?: (boolean | null);
};

