/* Token Usage Record */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TokenUsageRecord = {
    /**
     * 记录 ID
     */
    id: string;
    /**
     * 时间戳
     */
    timestamp: string;
    /**
     * 提供商名称
     */
    provider_name: string;
    /**
     * 模型名称
     */
    model_name: string;
    /**
     * 输入 Token 数
     */
    input_tokens: number;
    /**
     * 输出 Token 数
     */
    output_tokens: number;
    /**
     * 总 Token 数
     */
    total_tokens: number;
    /**
     * 关联任务 ID
     */
    task_id?: string;
};
