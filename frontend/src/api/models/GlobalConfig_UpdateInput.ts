/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_UpdateInput = {
    /**
     * 更新频道
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * GitHub 加速镜像 **只影响 MFW 项目包从 GitHub Release 下载这一条路**（脚本的 `Update.Source` 选 GitHub 时）：国内直连 GitHub 常年 100 多 KB/s， 359MB 的全量包要四十分钟。`Auto` 依次试镜像、全部失败再回直连； `Off` 只直连。MAS 自身的更新与初始化 clone 走前端 mirrorService， 不读这一项；Mirror 酱是另一个源，也不受它影响。
     */
    GitHubMirror?: ('Auto' | 'Off' | null);
    /**
     * 是否自动更新
     */
    IfAutoUpdate?: (boolean | null);
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

