/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Cloud = {
    /**
     * 云·星穹铁道是否消耗付费时长走快速排队通道
     */
    UsePaidTime?: (boolean | null);
    /**
     * 云·星穹铁道最长排队时间（分钟）
     */
    MaxQueueMinutes?: (number | null);
    /**
     * 云·星穹铁道等待手动登录的时间（分钟）
     */
    LoginTimeoutMinutes?: (number | null);
    /**
     * 各用户最近一次确认已登录的时间 JSON（用户 ID → ISO 时间），只读
     */
    LastLogin?: (string | null);
};

