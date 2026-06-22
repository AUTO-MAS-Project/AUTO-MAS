/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 閸楁洑閲滄稉澶嬬箒濞撳﹤鎻╅悡褏娈戠€电厧鍙嗙紒鎾寸亯閹芥顩?
 */
export type AbyssSnapshotImportItem = {
    /**
     * 濞ｈ鲸绗傝箛顐ゅ弾闁? ForgottenHall / PureFiction / Apocalyptic
     */
    snapshotKey: string;
    /**
     * 閺勵垰鎯侀幋鎰娴?M7A config.yaml 鐠囪褰囬獮璺哄晸閸?
     */
    success: boolean;
    /**
     * 閸忓啿宕遍懠鍐ㄦ纯閿涘溂min, max]閿涘绱濈紓鍝勩亼閺冩湹璐?None
     */
    level?: null;
    /**
     * 韫囶偆鍙庢稉顓炲瘶閸氼偆娈戦梼鐔剁礊鐎涙顔岄敍灞筋洤 team1/team2/team3
     */
    teamKeys?: Array<string>;
    /**
     * 闁挎瑨顕ら幓蹇氬牚閿涘牆顕遍崗銉ャ亼鐠愩儲妞傞敍?
     */
    error?: (string | null);
};
