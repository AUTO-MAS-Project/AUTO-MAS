/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HistoryIndexItem = {
    /**
     * 日期
     */
    date: string;
    /**
     * 状态
     */
    status: HistoryIndexItem.status;
    /**
     * 对应JSON文件
     */
    jsonFile: string;
    /**
     * 运行结果文本，可能带运行阶段前缀
     */
    result?: (string | null);
};
export namespace HistoryIndexItem {
    /**
     * 状态
     */
    export enum status {
        DONE = 'DONE',
        ERROR = 'ERROR',
    }
}

