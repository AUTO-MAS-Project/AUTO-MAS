/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRDynamicStageM7A } from './HSRDynamicStageM7A';
import type { HSRDynamicStageSRA } from './HSRDynamicStageSRA';
export type HSRDynamicStageOption = {
    /**
     * 閸擃垱婀扮仦鏇犮仛閸氬秶袨
     */
    label: string;
    /**
     * 閸擃垱婀扮拠瀛樻
     */
    detail?: (string | null);
    /**
     * 閸擃垱婀伴柅澶愩€嶉崐?
     */
    value: string;
    /**
     * 閸擃垱婀伴崚鍡欒闁?
     */
    categoryKey: string;
    /**
     * 閸擃垱婀伴崚鍡欒閸氬秶袨
     */
    categoryLabel: string;
    /**
     * 閸楁洘顐兼担鎾冲濞戝牐鈧?
     */
    cost?: (number | null);
    /**
     * 閺堚偓婢堆勫⒔鐞涘本顐奸弫?
     */
    maxCount?: (number | null);
    /**
     * M7A 閸樼喓鏁撶€涙顔?
     */
    m7a?: (HSRDynamicStageM7A | null);
    /**
     * SRA 閸樼喓鏁撶€涙顔?
     */
    sra?: (HSRDynamicStageSRA | null);
};
