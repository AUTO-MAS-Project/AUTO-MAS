/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Voice = {
    /**
     * 语音功能是否启用
     */
    enabled?: boolean;
    /**
     * 语音类型, simple为简洁, noisy为聒噪
     */
    type?: Voice.type;
};
export namespace Voice {
    /**
     * 语音类型, simple为简洁, noisy为聒噪
     */
    export enum type {
        SIMPLE = 'simple',
        NOISY = 'noisy',
    }
}

