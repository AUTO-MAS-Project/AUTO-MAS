/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIScriptRepoNode } from './BetterGIScriptRepoNode';
/**
 * 脚本仓库中一个分类（js / pathing / combat / tcg）。
 */
export type BetterGIScriptRepoCategory = {
    /**
     * 中文分类名
     */
    label: string;
    /**
     * 该分类下的节点树
     */
    tree?: Array<BetterGIScriptRepoNode>;
};

