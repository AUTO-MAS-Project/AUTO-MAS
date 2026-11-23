/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CollectionOrderItem } from './CollectionOrderItem';
import type { GameRuntimeData } from './GameRuntimeData';
import type { GeneralGameDocument } from './GeneralGameDocument';
import type { LDPlayerGameDocument } from './LDPlayerGameDocument';
import type { ModAvdGameDocument } from './ModAvdGameDocument';
import type { MuMuGameDocument } from './MuMuGameDocument';
import type { WinProcessGameDocument } from './WinProcessGameDocument';
export type GameGetOut = {
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
    order?: Array<CollectionOrderItem>;
    data?: Record<string, (MuMuGameDocument | LDPlayerGameDocument | ModAvdGameDocument | GeneralGameDocument | WinProcessGameDocument)>;
    runtime?: Record<string, GameRuntimeData>;
};

