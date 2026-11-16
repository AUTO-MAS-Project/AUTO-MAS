/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FluxdownCandidateOut } from './FluxdownCandidateOut';
/**
 * FluxDown 全盘检测结果。
 */
export type FluxdownDetectOut = {
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
     * 择优后的 FluxDown 路径；未找到为 None
     */
    path?: (string | null);
    /**
     * 选中项是否为 CLI 便携版
     */
    is_portable_cli?: boolean;
    /**
     * 设备上没有任何 CLI 便携版、选中项是全量版时为 True（前端显示污染风险警告）
     */
    only_full_warning?: boolean;
    /**
     * 扫描过的盘符
     */
    scanned_drives?: Array<string>;
    /**
     * 全部候选，按择优顺序，最多 8 条
     */
    candidates?: Array<FluxdownCandidateOut>;
};

