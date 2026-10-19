/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkNteUserConfig_NotifyInput = {
    /**
     * 是否启用通知
     */
    Enabled?: (boolean | null);
    /**
     * 是否发送邮件通知
     */
    IfSendMail?: (boolean | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否使用Server酱推送
     */
    IfServerChan?: (boolean | null);
    /**
     * 任务报告节点详情的推送模式（log_box 采集的关键节点）： 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合
     */
    PushLogMode?: ('关闭' | '逐条' | '汇总' | null);
    /**
     * ServerChanKey
     */
    ServerChanKey?: (string | null);
    /**
     * 邮件接收地址
     */
    ToAddress?: (string | null);
};

