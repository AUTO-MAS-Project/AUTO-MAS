/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHUserConfigInput } from './BAAHUserConfigInput';
import type { BetterGIUserConfigInput } from './BetterGIUserConfigInput';
import type { GeneralUserConfigInput } from './GeneralUserConfigInput';
import type { HSRUserConfigInput } from './HSRUserConfigInput';
import type { M9AUserConfigInput } from './M9AUserConfigInput';
import type { MaaEndUserConfigInput } from './MaaEndUserConfigInput';
import type { MaaFWUserConfigInput } from './MaaFWUserConfigInput';
import type { MaaUserConfigInput } from './MaaUserConfigInput';
import type { MSSUserConfigInput } from './MSSUserConfigInput';
import type { OkNteUserConfigInput } from './OkNteUserConfigInput';
import type { OkwwUserConfigInput } from './OkwwUserConfigInput';
import type { SrcUserConfigInput } from './SrcUserConfigInput';
import type { WhimboxUserConfigInput } from './WhimboxUserConfigInput';
import type { ZzzOdUserConfigInput } from './ZzzOdUserConfigInput';
export type UserUpdateIn = {
    /**
     * 所属托管ID
     */
    scriptId: string;
    /**
     * 账号ID
     */
    userId: string;
    /**
     * 账号更新数据
     */
    data: (SrcUserConfigInput | GeneralUserConfigInput | OkwwUserConfigInput | OkNteUserConfigInput | MaaEndUserConfigInput | M9AUserConfigInput | MaaFWUserConfigInput | HSRUserConfigInput | BetterGIUserConfigInput | ZzzOdUserConfigInput | BAAHUserConfigInput | WhimboxUserConfigInput | MSSUserConfigInput | MaaUserConfigInput);
};

