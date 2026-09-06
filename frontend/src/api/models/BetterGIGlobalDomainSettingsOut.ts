/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 全局 config.json 的「秘境刷取配置」段（autoDomainConfig/autoArtifactSalvageConfig）
 */
export type BetterGIGlobalDomainSettingsOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 秘境刷取配置键值（camelCase 扁平键：specifyResinUse/originalResinUseCount/condensedResinUseCount/transientResinUseCount/fragileResinUseCount/autoArtifactSalvage/maxArtifactStar/rewardRecognitionEnabled）
     */
    data?: Record<string, any>;
};

