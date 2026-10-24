/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIUserConfig_Switch = {
    /**
     * 游戏客户端路径（用户级覆盖，可空）：官服/B服/国际服是三个互相隔离的客户端， B站账号只能登录B服客户端。留空 = 跟随 BetterGI 全局配置的游戏路径；填写后该 用户运行时由 MAS 按此路径临时拉起游戏（不修改 BetterGI 配置），实现同脚本 混服用户各用各的客户端
     */
    GamePath?: (string | null);
    /**
     * 切换账号配置（BetterGI「切换账号多模式」脚本专项适配） 账号/密码复用 Info.Id / Info.Password（密码经 EncryptValidator 加密） 切换模式不再由用户配置，运行时按密码是否填写推断： 填密码 → 「账号+密码+OCR」，未填 → 「下拉列表」；B服 强制「B服切换另一个账号匹配+键鼠」。 游戏服务器（账号所在服务器：官服/B服/国际服各服务器）
     */
    Resource?: ('官服' | 'B服' | '亚服' | '欧服' | '美服' | '港澳台服' | null);
    /**
     * 账号 UID（可不填，切换前识别一致将不执行切换动作；仅 BetterGI 脚本方式生效）
     */
    Uid?: (string | null);
};

