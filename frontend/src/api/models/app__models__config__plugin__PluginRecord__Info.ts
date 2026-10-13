/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginCodeDrift } from './PluginCodeDrift';
import type { PluginState } from './PluginState';
import type { Virtual_list_str__ } from './Virtual_list_str__';
import type { Virtual_str_ } from './Virtual_str_';
export type app__models__config__plugin__PluginRecord__Info = {
    /**
     * 发行包名
     */
    package_name?: string;
    /**
     * 插件名
     */
    plugin_name?: string;
    /**
     * 版本
     */
    version?: string;
    /**
     * 文档 URL
     */
    docs_url?: string;
    /**
     * 主页 URL
     */
    homepage?: string;
    /**
     * 源码仓库 URL
     */
    repository?: string;
    /**
     * 作者
     */
    author?: string;
    /**
     * 许可证
     */
    license?: string;
    /**
     * 发行包依赖
     */
    requires_dist?: Array<string>;
    display_name_i18n?: Record<string, string>;
    description_i18n?: Record<string, string>;
    tags_i18n?: Record<string, Array<string>>;
    display_name?: Virtual_str_;
    description?: Virtual_str_;
    tags?: Virtual_list_str__;
    /**
     * 可 import 的顶层包名；发现刷新写入；load 读 __init__.PLUGIN
     */
    import_name?: string;
    /**
     * 硬依赖服务名（load 后由类属性写入；启用级联）
     */
    requires?: Array<string>;
    /**
     * 弱依赖服务名（load 后由类属性写入；缺失降级）
     */
    wants?: Array<string>;
    /**
     * 发现源：installed | local
     */
    source?: string;
    /**
     * 插件状态（PluginState；Manager 回写）
     */
    state?: PluginState;
    /**
     * 生命周期语境（LifecycleContext；Manager 写入，非 Trigger）
     */
    lifecycle_context?: string;
    /**
     * 是否启用（意图；Manager 回写）
     */
    enabled?: boolean;
    /**
     * 最近错误
     */
    last_error?: string;
    /**
     * 是否核心插件
     */
    is_core?: boolean;
    /**
     * 是否本地目录插件
     */
    is_local?: boolean;
    /**
     * 与最近一次发现/磁盘的差异：normal=一致；needs_reload=需重载；package_removed=包缺失
     */
    code_drift?: PluginCodeDrift;
    /**
     * 启用（写 True 开闸）
     */
    enable?: boolean;
    /**
     * 禁用（写 True 开闸）
     */
    disable?: boolean;
    /**
     * 重载（写 True 开闸）
     */
    reload?: boolean;
    /**
     * 卸载（写 True 开闸）
     */
    uninstall?: boolean;
};

