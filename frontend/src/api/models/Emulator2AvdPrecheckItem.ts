/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 魔改 AVD 开机前电脑检查的一项。拦截项不满足时开机直接被拒绝, 原因同 reason + advice。
 */
export type Emulator2AvdPrecheckItem = {
    /**
     * 检查项: path / emulator / acceleration / vulkan / disk / memory
     */
    id: string;
    /**
     * 检查项名称
     */
    title: string;
    /**
     * 是否满足; null 表示现在查不了 (如模拟器组件还没装)
     */
    ok?: (boolean | null);
    /**
     * 不满足时是否拒绝开机; 显卡 Vulkan 只提示不拦截
     */
    blocking?: boolean;
    /**
     * 检查结果或不满足的原因
     */
    reason?: string;
    /**
     * 不满足时给用户的处理建议
     */
    advice?: string;
    /**
     * 界面可以一键处理的动作: enable_hypervisor_platform 开启「Windows 虚拟机监控程序平台」 (调 /avd/hypervisor/enable); 没有为空
     */
    action?: string;
};

