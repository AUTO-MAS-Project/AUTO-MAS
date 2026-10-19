/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ZzzOdUserConfig_Notify = {
    /**
     * 是否启用用户通知
     */
    Enabled?: (boolean | null);
    /**
     * 是否发送邮件
     */
    IfSendMail?: (boolean | null);
    /**
     * 是否发送用户统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否启用 Server 酱
     */
    IfServerChan?: (boolean | null);
    /**
     * 任务报告节点详情的推送模式（运行记录 diff 出的各任务结果）： 关闭 = 不采集；逐条 = 逐条带回时间戳；汇总 = 按状态聚合
     */
    PushLogMode?: ('关闭' | '逐条' | '汇总' | null);
    /**
     * Server 酱密钥
     */
    ServerChanKey?: (string | null);
    /**
     * 用户收件地址
     */
    ToAddress?: (string | null);
};

