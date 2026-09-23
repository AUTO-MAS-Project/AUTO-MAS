/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 切换账号配置（切换账号多模式脚本专项适配）
 */
export type BetterGIUserConfig_Switch = {
    /**
     * 游戏服务器：官服/B服/亚服/欧服/美服/港澳台服
     */
    Resource?: (string | null);
    /**
     * 账号 UID（可不填，切换前识别一致将不执行切换动作）
     */
    Uid?: (string | null);
    /**
     * 游戏客户端路径（用户级覆盖，可空）：官服/B服/国际服是不同客户端，留空使用 BetterGI 全局配置；填写后该用户运行时由 MAS 写入 BetterGI 配置并按此路径拉起
     */
    GamePath?: (string | null);
};

