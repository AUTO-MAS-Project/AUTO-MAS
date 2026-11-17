/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 后端核心服务与后台初始化状态。
 */
export type BackendHealthOut = {
    /**
     * 核心 API 是否可用
     */
    ready: boolean;
    /**
     * 后台初始化状态
     */
    backgroundStatus: string;
    /**
     * 插件与业务初始化状态；完成前不得放行自动任务
     */
    businessStatus: string;
    /**
     * 当前插件或配置初始化步骤
     */
    businessMessage?: (string | null);
    /**
     * 后台初始化失败原因
     */
    backgroundError?: (string | null);
    /**
     * 后台初始化中失败但不影响就绪的可选步骤，每项为「步骤名（异常）」
     */
    backgroundWarnings?: Array<string>;
    /**
     * 后端自身支持的健康检查协议版本
     */
    protocol: number;
    /**
     * 后端版本号
     */
    version: string;
    /**
     * 后端所在提交哈希，未受监督或监督器未注入时为空
     */
    commit: string;
    /**
     * 自动业务是否已由监督器放行
     */
    startupActivation?: ('pending' | 'active' | 'closed' | null);
};

