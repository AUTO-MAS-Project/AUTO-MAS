/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CoreUpgradePrecheckIn = {
    version: string;
    /**
     * 目标版本的完整 pyproject.toml
     */
    project: string;
    /**
     * 同一目标版本的 uv.lock
     */
    lockfile: string;
    /**
     * 目标版本 .python-version 中的精确 Python 版本
     */
    python_version: string;
};

