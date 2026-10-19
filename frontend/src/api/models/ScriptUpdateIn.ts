/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHConfigInput } from './BAAHConfigInput';
import type { BetterGIConfigInput } from './BetterGIConfigInput';
import type { GeneralConfigInput } from './GeneralConfigInput';
import type { HSRConfigInput } from './HSRConfigInput';
import type { M9AConfigInput } from './M9AConfigInput';
import type { MaaConfigInput } from './MaaConfigInput';
import type { MaaEndConfigInput } from './MaaEndConfigInput';
import type { MaaFWConfigInput } from './MaaFWConfigInput';
import type { MSSConfigInput } from './MSSConfigInput';
import type { OkNteConfigInput } from './OkNteConfigInput';
import type { OkwwConfigInput } from './OkwwConfigInput';
import type { SrcConfigInput } from './SrcConfigInput';
import type { WhimboxConfigInput } from './WhimboxConfigInput';
import type { ZzzOdConfigInput } from './ZzzOdConfigInput';
export type ScriptUpdateIn = {
    /**
     * 脚本ID
     */
    scriptId: string;
    /**
     * 脚本更新数据
     */
    data: (MaaConfigInput | SrcConfigInput | GeneralConfigInput | OkwwConfigInput | OkNteConfigInput | MaaEndConfigInput | M9AConfigInput | MaaFWConfigInput | HSRConfigInput | BetterGIConfigInput | ZzzOdConfigInput | BAAHConfigInput | WhimboxConfigInput | MSSConfigInput);
};

