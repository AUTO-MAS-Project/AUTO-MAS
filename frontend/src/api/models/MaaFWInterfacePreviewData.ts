/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWControlCapabilitiesInfo } from './MaaFWControlCapabilitiesInfo';
import type { MaaFWControllerInfo } from './MaaFWControllerInfo';
import type { MaaFWGroupInfo } from './MaaFWGroupInfo';
import type { MaaFWOptionInfo } from './MaaFWOptionInfo';
import type { MaaFWPresetInfo } from './MaaFWPresetInfo';
import type { MaaFWProjectInfo } from './MaaFWProjectInfo';
import type { MaaFWResourceInfo } from './MaaFWResourceInfo';
import type { MaaFWSettingInfo } from './MaaFWSettingInfo';
import type { MaaFWTaskInfo } from './MaaFWTaskInfo';
/**
 * MaaFW interface 预览数据。
 *
 * 外层字段在宿主 schema 中明确建模；各列表条目的字段与 Phase 1
 * ``build_interface_preview_data`` 返回的 MaaFWInterfacePreviewData 契约一致。
 */
export type MaaFWInterfacePreviewData = {
    /**
     * MaaFW 项目根目录
     */
    path: string;
    /**
     * 项目基础信息
     */
    project: MaaFWProjectInfo;
    /**
     * 全局选项
     */
    globalOption?: Array<string>;
    /**
     * MaaFW control capabilities
     */
    controlCapabilities?: MaaFWControlCapabilitiesInfo;
    /**
     * 控制器列表
     */
    controllers?: Array<MaaFWControllerInfo>;
    /**
     * 资源列表
     */
    resources?: Array<MaaFWResourceInfo>;
    /**
     * 任务分组列表
     */
    groups?: Array<MaaFWGroupInfo>;
    /**
     * 设置分组列表
     */
    settings?: Array<MaaFWSettingInfo>;
    /**
     * 任务列表
     */
    tasks?: Array<MaaFWTaskInfo>;
    /**
     * 选项列表
     */
    options?: Array<MaaFWOptionInfo>;
    /**
     * 预设列表
     */
    presets?: Array<MaaFWPresetInfo>;
    /**
     * 根 interface import 数量
     */
    importCount?: number;
    /**
     * agent 配置数量
     */
    agentCount?: number;
};

