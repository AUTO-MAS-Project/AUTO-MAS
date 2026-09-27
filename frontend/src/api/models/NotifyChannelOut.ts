/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { NotifyChannelFieldOut } from './NotifyChannelFieldOut';
/**
 * 一个通知渠道的展示元数据；服务无鉴权，负载不得出现任何配置值。
 */
export type NotifyChannelOut = {
    /**
     * 渠道标识
     */
    key: string;
    /**
     * 渠道名称词表键
     */
    nameKey: string;
    /**
     * 渠道一句话说明词表键
     */
    descKey?: string;
    /**
     * 图标标识，policy 段为空串
     */
    icon?: string;
    /**
     * 分组：builtin/custom
     */
    group: string;
    /**
     * 排序值，与投递顺序一致
     */
    order: number;
    /**
     * 使用文档链接
     */
    docUrl?: (string | null);
    /**
     * 可用作用域：global/user
     */
    scopes?: Array<string>;
    /**
     * 渲染类型：fields/custom/policy
     */
    kind: string;
    /**
     * 自定义块标识：claw:qq/webhook_list
     */
    customBlock?: (string | null);
    /**
     * 启用开关的 [配置组, 字段名]
     */
    enableField?: (Array<string> | null);
    /**
     * 卡片摘要词表键
     */
    summaryKey?: (string | null);
    /**
     * 参与摘要插值与空值判定的字段名
     */
    summaryFields?: Array<string>;
    /**
     * 按作用域分组的字段列表
     */
    fields?: Record<string, Array<NotifyChannelFieldOut>>;
};

