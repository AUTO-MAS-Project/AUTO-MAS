/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWControllerInfo = {
    /**
     * 控制器名称
     */
    name: string;
    /**
     * 控制器显示名称
     */
    label?: (string | null);
    /**
     * 控制器类型
     */
    type: string;
    /**
     * 控制器描述
     */
    description?: (string | null);
    /**
     * 控制器图标路径
     */
    icon?: (string | null);
    /**
     * 控制器选项
     */
    option?: Array<string>;
    /**
     * 是否需要管理员权限
     */
    permissionRequired?: boolean;
};

