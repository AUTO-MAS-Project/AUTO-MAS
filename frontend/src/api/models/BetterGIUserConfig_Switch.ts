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
     * 账号 UID（可不填，切换前识别一致将不执行切换动作；仅 BetterGI 脚本方式生效）
     */
    Uid?: (string | null);
    /**
     * 使用已有米游社会话启动官服原神，替代账号密码切换
     */
    MiyousheLogin?: (boolean | null);
    /**
     * 已有米游社社区账号组 ID，不保存凭据副本
     */
    MiyousheAccountUid?: (string | null);
    /**
     * 原神角色 UID，启动后须核对一致才能执行任务
     */
    MiyousheRoleUid?: (string | null);
    /**
     * 原神角色服务器，首期仅支持 cn_gf01
     */
    MiyousheRoleRegion?: (string | null);
    /**
     * 游戏客户端路径（用户级覆盖，可空）：官服/B服/国际服是三个互相隔离的客户端（B站账号只能登录B服客户端）。留空跟随 BetterGI 全局配置；填写后该用户运行时由 MAS 按此路径临时拉起游戏（不修改 BetterGI 配置），同脚本不同服务器的用户可各配各的客户端
     */
    GamePath?: (string | null);
};

