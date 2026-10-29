/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FluxdownRecord } from './FluxdownRecord';
export type GlobalConfig_Update = {
    /**
     * 更新频道
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * 下载器: builtin 用内置 httpx, fluxdown 调 FluxDown CLI 多线程
     */
    Downloader?: ('builtin' | 'fluxdown' | null);
    /**
     * FluxDown CLI 所在目录（包含 portable 标记文件）；空则自动查找
     */
    FluxdownPath?: (string | null);
    /**
     * FluxDown 多线程分段数 (1-32)
     */
    FluxdownSegments?: (number | null);
    /**
     * FluxDown 断点续传服务（server 模式）：常驻 agent+daemon，跨进程续传
     */
    FluxdownServerMode?: (boolean | null);
    /**
     * 已接入脚本的 GitHub 更新使用 FluxDown 下载；关闭使用内置下载器，不控制专项更新接管
     */
    FluxdownTakeoverAll?: (boolean | null);
    /**
     * GitHub 加速镜像 **只影响 MFW 项目包从 GitHub Release 下载这一条路**（脚本的 `Update.Source` 选 GitHub 时）：国内直连 GitHub 常年 100 多 KB/s， 359MB 的全量包要四十分钟。`Auto` 依次试镜像、全部失败再回直连； `Off` 只直连。MAS 自身的更新与初始化 clone 走前端 mirrorService， 不读这一项；Mirror 酱是另一个源，也不受它影响。
     */
    GitHubMirror?: ('Auto' | 'Off' | null);
    /**
     * 是否自动更新
     */
    IfAutoUpdate?: (boolean | null);
    /**
     * 最近的下载历史记录（最多保留 50 条）
     */
    LastUpdateHistory?: (Array<FluxdownRecord> | null);
    /**
     * 镜像站 CDK
     */
    MirrorChyanCDK?: (string | null);
    /**
     * 暂停更新截止时间，截止日期当天恢复；空值表示未暂停
     */
    PauseUntil?: (string | null);
    /**
     * 代理地址
     */
    ProxyAddress?: (string | null);
    /**
     * 更新源
     */
    Source?: ('GitHub' | 'MirrorChyan' | 'AutoSite' | 'CNB' | null);
};

