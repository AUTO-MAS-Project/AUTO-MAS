/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 通用脚本记录。
 */
export type ScriptRecord = {
    /**
     * 脚本 ID
     */
    id: string;
    /**
     * 脚本类型键
     */
    type: string;
    /**
     * 脚本名称
     */
    name: string;
    /**
     * 脚本配置内容
     */
    config: Record<string, any>;
    /**
     * 脚本配置表单描述
     */
    schema: Record<string, any>;
    /**
     * 编辑器类型
     */
    editor_kind: string;
    /**
     * 支持的任务模式
     */
    supported_modes: Array<string>;
    /**
     * 当前脚本记录是否可用
     */
    available?: boolean;
    /**
     * 当前脚本记录不可用原因
     */
    unavailable_reason?: (string | null);
    /**
     * 图标标识
     */
    icon?: (string | null);
    /**
     * 图标资源地址
     */
    icon_url?: (string | null);
    /**
     * 主题颜色
     */
    theme_color?: (string | null);
    /**
     * 文档地址
     */
    docs_url?: (string | null);
    /**
     * 脚本编辑页底部提示
     */
    edit_hint?: (Record<string, any> | null);
    /**
     * 用户数量
     */
    user_count?: number;
};

