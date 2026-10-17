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
     * 状态: DONE 完成, SKIP 跳过(如停服维护), ERROR 失败
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
     * 状态: DONE 完成, SKIP 跳过(如停服维护), ERROR 失败
     */
    export enum status {
        DONE = 'DONE',
        SKIP = 'SKIP',
        ERROR = 'ERROR',
    }
}

