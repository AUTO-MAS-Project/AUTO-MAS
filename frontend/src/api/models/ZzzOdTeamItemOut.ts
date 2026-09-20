/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 预备编队条目（team.yml；成员为游戏内识别结果，MAS 不编辑）
 */
export type ZzzOdTeamItemOut = {
    /**
     * 编队在列表中的下标
     */
    idx: number;
    /**
     * 编队名称（与游戏内编队名一致）
     */
    name: string;
    /**
     * 绑定的配队方案（自动战斗配置名）
     */
    autoBattle: string;
    /**
     * 成员代理人ID列表
     */
    agents?: Array<string>;
};

