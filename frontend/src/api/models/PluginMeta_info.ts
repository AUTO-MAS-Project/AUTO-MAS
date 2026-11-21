/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginChangelogVersions } from './PluginChangelogVersions';
import type { PluginReleaseNote } from './PluginReleaseNote';
export type PluginMeta_info = {
    /**
     * 包名
     */
    readonly package_name?: (string | null);
    /**
     * 插件名
     */
    readonly plugin_name?: (string | null);
    /**
     * 版本
     */
    readonly version?: (string | null);
    /**
     * 最近五个发行版本内的更新说明
     */
    readonly changelog?: (Array<PluginReleaseNote> | null);
    readonly changelog_versions?: (PluginChangelogVersions | null);
    /**
     * 文档 URL
     */
    readonly docs_url?: (string | null);
    /**
     * 主页 URL
     */
    readonly homepage?: (string | null);
    /**
     * 源码仓库 URL
     */
    readonly repository?: (string | null);
    /**
     * 作者
     */
    readonly author?: (string | null);
    /**
     * 许可证
     */
    readonly license?: (string | null);
    /**
     * Requires-Dist 列表
     */
    readonly requires_dist?: (Array<string> | null);
    readonly display_name?: (string | null);
    readonly description?: (string | null);
    readonly tags?: (Array<string> | null);
    readonly installed_version?: (string | null);
    readonly update_available?: (boolean | null);
    /**
     * 安装（写 True 开闸）
     */
    readonly install?: (string | null);
};

