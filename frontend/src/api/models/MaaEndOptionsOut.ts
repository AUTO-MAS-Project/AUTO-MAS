/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
import type { MaaEndAutoCollectGroup } from './MaaEndAutoCollectGroup';
import type { MaaEndEssenceTargetGroup } from './MaaEndEssenceTargetGroup';
export type MaaEndOptionsOut = {
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
     * MaaEnd 自动采集地区与分类
     */
    autoCollectGroups?: Array<MaaEndAutoCollectGroup>;
    /**
     * 从游戏 Unity 注册表读取的原始分辨率
     */
    originalResolution?: (string | null);
    /**
     * MaaEnd 控制器选项
     */
    controllers: Array<ComboBoxItem>;
    /**
     * 控制器协议类型映射
     */
    controllerTypes: Record<string, string>;
    /**
     * MaaEnd 基质刷取地点选项
     */
    essenceLocations: Array<ComboBoxItem>;
    /**
     * MaaEnd 基质刷取模式选项
     */
    essenceMenus: Array<ComboBoxItem>;
    /**
     * MaaEnd 基质目标武器分组
     */
    essenceTargetWeaponGroups: Array<MaaEndEssenceTargetGroup>;
};

