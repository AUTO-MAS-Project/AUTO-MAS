/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { VirtualDisplayCheckResultItem } from './VirtualDisplayCheckResultItem';
export type VirtualDisplayCheckOut = {
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
     * 驱动次版本号
     */
    driverVersion?: (number | null);
    /**
     * 检测时的显示器概况
     */
    monitors?: string;
    /**
     * 守卫此刻挂着的虚拟显示器（设备名与模式），没挂时为空；设置页据此决定「立即拆除」按钮能不能按
     */
    holding?: (string | null);
    results?: Array<VirtualDisplayCheckResultItem>;
};

