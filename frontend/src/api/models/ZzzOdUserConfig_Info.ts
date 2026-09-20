/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * ZZZ-OD 用户信息
 *
 * 配置主体是本模型的 Game / OneDragon 字段（MAS ConfigItem 体系，web
 * 界面直接编辑）；运行时由字段生成配置注入 zzz-od 实例槽。
 */
export type ZzzOdUserConfig_Info = {
    /**
     * 用户名
     */
    Name?: (string | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 配置来源（脚本/用户/直控）
     */
    Mode?: ('脚本' | '用户' | '直控' | null);
    /**
     * 是否启用快速配置（与配置来源独立）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 绑定的 zzz-od 实例槽下标（-1=未分配；首次运行或「在一条龙内配置」时自动分配并持久注册 MAS-{用户名} 实例）
     */
    SlotIdx?: (number | null);
    /**
     * 一条龙启动器（直控/用户两态通用；自动=优先上次成功并失败自动切换重试，原始/集成=固定相应 exe）
     */
    LauncherMode?: ('自动' | '原始' | '集成' | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 是否在任务前执行脚本
     */
    IfScriptBeforeTask?: (boolean | null);
    /**
     * 任务前脚本路径
     */
    ScriptBeforeTask?: (string | null);
    /**
     * 是否在任务后执行脚本
     */
    IfScriptAfterTask?: (boolean | null);
    /**
     * 任务后脚本路径
     */
    ScriptAfterTask?: (string | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    Tag?: (string | null);
};

