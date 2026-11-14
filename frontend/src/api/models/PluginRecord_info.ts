/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginCodeDrift } from './PluginCodeDrift';
import type { PluginState } from './PluginState';
export type PluginRecord_info = {
    /**
     * 发行包名
     */
    package_name?: (string | null);
    /**
     * 插件名
     */
    plugin_name?: (string | null);
    /**
     * 版本
     */
    version?: (string | null);
    /**
     * 文档 URL
     */
    docs_url?: (string | null);
    /**
     * 主页 URL
     */
    homepage?: (string | null);
    /**
     * 源码仓库 URL
     */
    repository?: (string | null);
    /**
     * 作者
     */
    author?: (string | null);
    /**
     * 许可证
     */
    license?: (string | null);
    /**
     * 发行包依赖
     */
    requires_dist?: (Array<string> | null);
    readonly display_name?: (string | null);
    readonly description?: (string | null);
    readonly tags?: (Array<string> | null);
    /**
     * 可 import 的顶层包名；发现刷新写入；load 读 __init__.PLUGIN
     */
    import_name?: (string | null);
    /**
     * 硬依赖服务名（load 后由类属性写入；启用级联）
     */
    requires?: (Array<string> | null);
    /**
     * 弱依赖服务名（load 后由类属性写入；缺失降级）
     */
    wants?: (Array<string> | null);
    /**
     * 发现源：installed | local
     */
    source?: (string | null);
    /**
     * 插件状态（PluginState；Manager 回写）
     */
    state?: (PluginState | null);
    /**
     * 生命周期语境（LifecycleContext；Manager 写入，非 Trigger）
     */
    lifecycle_context?: (string | null);
    /**
     * 是否启用（意图；Manager 回写）
     */
    enabled?: (boolean | null);
    /**
     * 最近错误
     */
    last_error?: (string | null);
    /**
     * 是否核心插件
     */
    is_core?: (boolean | null);
    /**
     * 是否本地目录插件
     */
    is_local?: (boolean | null);
    /**
     * 与最近一次发现/磁盘的差异：normal=一致；needs_reload=需重载；package_removed=包缺失
     */
    code_drift?: (PluginCodeDrift | null);
};

