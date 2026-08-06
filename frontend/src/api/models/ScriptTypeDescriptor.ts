/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 脚本类型描述。
 */
export type ScriptTypeDescriptor = {
    /**
     * 脚本类型键
     */
    type_key: string;
    /**
     * 脚本类型显示名称
     */
    display_name: string;
    /**
     * 脚本类型图标标识
     */
    icon?: (string | null);
    /**
     * 脚本类型图标资源地址
     */
    icon_url?: (string | null);
    /**
     * 脚本类型主题颜色
     */
    theme_color?: (string | null);
    /**
     * 新建脚本时的展示分组
     */
    create_group?: ScriptTypeDescriptor.create_group;
    /**
     * 脚本类型是否显式声明了创建分组
     */
    create_group_declared?: boolean;
    /**
     * 文档地址
     */
    docs_url?: (string | null);
    /**
     * 编辑器类型
     */
    editor_kind: string;
    /**
     * 支持的任务模式
     */
    supported_modes: Array<string>;
    /**
     * 脚本配置表单描述
     */
    script_schema: Record<string, any>;
    /**
     * 用户配置表单描述
     */
    user_schema: Record<string, any>;
    /**
     * 供宿主通用插件编辑器消费的客户端声明
     */
    client?: Record<string, any>;
    /**
     * 旧脚本配置类名
     */
    legacy_config_class_name?: (string | null);
    /**
     * 旧用户配置类名
     */
    legacy_user_config_class_name?: (string | null);
    /**
     * 是否为内建脚本类型
     */
    is_builtin?: boolean;
    /**
     * 当前是否可用
     */
    available?: boolean;
    /**
     * 当前不可用原因
     */
    unavailable_reason?: (string | null);
};
export namespace ScriptTypeDescriptor {
    /**
     * 新建脚本时的展示分组
     */
    export enum create_group {
        GENERAL = 'general',
        SPECIALIZED = 'specialized',
    }
}

