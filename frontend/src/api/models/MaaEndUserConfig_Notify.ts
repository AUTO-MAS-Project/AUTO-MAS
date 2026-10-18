/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_Notify = {
    /**
     * 是否启用通知
     */
    Enabled?: (boolean | null);
    /**
     * 任务报告节点详情的推送模式：关闭=不采集；逐条=采集并逐条带回时间戳；汇总=采集并按状态聚合
     */
    PushLogMode?: ('关闭' | '逐条' | '汇总' | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否发送邮件
     */
    IfSendMail?: (boolean | null);
    /**
     * 收件地址
     */
    ToAddress?: (string | null);
    /**
     * 是否启用Server酱
     */
    IfServerChan?: (boolean | null);
    /**
     * Server酱密钥
     */
    ServerChanKey?: (string | null);
};

