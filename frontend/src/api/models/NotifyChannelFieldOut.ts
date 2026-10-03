/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { NotifyChannelOptionOut } from './NotifyChannelOptionOut';
/**
 * 渠道在某个作用域暴露的一个配置字段描述。
 */
export type NotifyChannelFieldOut = {
    /**
     * 配置组，如 Notify
     */
    group: string;
    /**
     * 配置字段名
     */
    name: string;
    /**
     * 字段标签词表键
     */
    labelKey: string;
    /**
     * 控件类型：bool/text/password/url/select/json
     */
    control: string;
    /**
     * 下拉选项
     */
    options?: Array<NotifyChannelOptionOut>;
    /**
     * 占位文案词表键
     */
    placeholderKey?: string;
    /**
     * 提示文案词表键
     */
    tipKey?: string;
};

