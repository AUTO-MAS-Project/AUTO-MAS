/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AbyssSnapshotImportItem } from './AbyssSnapshotImportItem';
import type { HSRUserConfig } from './HSRUserConfig';
/**
 * 娴?M7A config.yaml 鐎电厧鍙嗘稉澶嬬箒濞撳﹤鎻╅悡褏娈戠紒鎾寸亯
 */
export type AbyssSnapshotImportOut = {
    /**
     * 閻樿埖鈧胶鐖?
     */
    code?: number;
    /**
     * 閹垮秳缍旈悩鑸碘偓?
     */
    status?: string;
    /**
     * 閹垮秳缍斿☉鍫熶紖
     */
    message?: string;
    /**
     * 鐠囪褰囬惃?M7A config.yaml 鐠侯垰绶?
     */
    m7aConfigPath: string;
    /**
     * 娑撳閲滃ǎ杈ㄧ瑐閻ㄥ嫬顕遍崗銉х波閺嬫粍鎲崇憰?
     */
    items?: Array<AbyssSnapshotImportItem>;
    /**
     * 閺囧瓨鏌婇崥搴ｆ畱鐎瑰本鏆?HSR 閻劍鍩涢柊宥囩枂閿涘牆澧犵粩顖氬讲閻劍娼甸崥灞绢劄 formData閿?
     */
    updatedUserData: HSRUserConfig;
};
