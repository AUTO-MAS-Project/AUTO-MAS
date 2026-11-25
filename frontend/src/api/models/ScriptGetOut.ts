/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHConfig } from './BAAHConfig';
import type { BetterGIConfig } from './BetterGIConfig';
import type { GeneralConfig } from './GeneralConfig';
import type { HSRConfig } from './HSRConfig';
import type { M9AConfig } from './M9AConfig';
import type { MaaConfig } from './MaaConfig';
import type { MaaEndConfig } from './MaaEndConfig';
import type { MaaFWConfig } from './MaaFWConfig';
import type { MSSConfig } from './MSSConfig';
import type { OkNteConfig } from './OkNteConfig';
import type { OkwwConfig } from './OkwwConfig';
import type { ScriptIndexItem } from './ScriptIndexItem';
import type { SrcConfig } from './SrcConfig';
import type { UnavailableConfigItem } from './UnavailableConfigItem';
import type { WhimboxConfig } from './WhimboxConfig';
import type { ZzzOdConfig } from './ZzzOdConfig';
export type ScriptGetOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    uiSources?: Array<string>;
    /**
     * 托管索引列表
     */
    index: Array<ScriptIndexItem>;
    /**
     * 托管数据字典, key来自于index列表的uid
     */
    data: Record<string, (GeneralConfig | OkwwConfig | OkNteConfig | MaaEndConfig | HSRConfig | BetterGIConfig | ZzzOdConfig | BAAHConfig | M9AConfig | MaaConfig | MaaFWConfig | MSSConfig | SrcConfig | WhimboxConfig)>;
    /**
     * 所属插件不可用的托管，只在获取全部托管时给出；只能删除
     */
    unavailable?: Array<UnavailableConfigItem>;
};

