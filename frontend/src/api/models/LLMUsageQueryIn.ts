/* LLM Usage Query In */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LLMUsageQueryIn = {
    /**
     * 开始日期，格式 YYYY-MM-DD
     */
    start_date?: (string | null);
    /**
     * 结束日期，格式 YYYY-MM-DD
     */
    end_date?: (string | null);
    /**
     * 查询周期类型
     */
    period?: ('daily' | 'weekly' | 'monthly' | null);
};
