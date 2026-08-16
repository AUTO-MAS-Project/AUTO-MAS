/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PullCountStatistics = {
    /**
     * 资源折算抽数
     */
    resource_pulls: number;
    /**
     * 可留到下版本的凭证抽数
     */
    carry_over_pulls: number;
    /**
     * 下版本商店抽数
     */
    next_pool_shop_pulls: number;
    /**
     * 下版本签到抽数
     */
    next_pool_signin_pulls: number;
    /**
     * 当前卡池可用抽数
     */
    current_pool_total: number;
    /**
     * 下版本卡池预计总抽数
     */
    next_pool_total: number;
};

