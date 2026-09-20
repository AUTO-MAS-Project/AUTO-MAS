/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWProjectUpdateData = {
    /**
     * 是否完成了一次更新检查
     */
    checked?: boolean;
    /**
     * 本次是否实际应用了更新
     */
    updated?: boolean;
    /**
     * 是否存在更新版本
     */
    updateAvailable?: boolean;
    /**
     * 更新版本是否有可安装的更新包
     */
    installable?: boolean;
    /**
     * interface 声明的当前项目版本
     */
    currentVersion?: (string | null);
    /**
     * 发现的最新项目版本
     */
    latestVersion?: (string | null);
    /**
     * 实际更新包来源：mirrorchyan / github；未下载时为空
     */
    source?: (string | null);
    /**
     * Mirror 酱返回的最新版本名；查版本失败时为空
     */
    versionName?: (string | null);
    /**
     * CDK 状态：ok / absent / expired / invalid / quota / mismatched / blocked
     */
    cdkStatus?: (string | null);
    /**
     * CDK 状态对应的用户提示；ok / absent 时为空
     */
    cdkMessage?: (string | null);
    /**
     * Mirror 酱返回的 CDK 过期时间（unix 秒），仅 ok 时有
     */
    cdkExpiredTime?: (number | null);
    /**
     * 未执行更新的原因（无 rid、已最新、锁被占等）
     */
    skippedReason?: (string | null);
};

