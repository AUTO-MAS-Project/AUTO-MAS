/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BAAHUserConfig_Info = {
    /**
     * 账号名称
     */
    Name?: (string | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 账号标签信息
     */
    readonly Tag?: (string | null);
    /**
     * 仅用于 MAS 活动日历提醒的服务器，不参与 BAAH 扫荡或任务编排
     */
    ActivityLineType?: ('JP' | 'Globle' | 'CN' | null);
    /**
     * 默认使用的 BAAH 配置文件名（BAAH_CONFIGS 目录下的文件名，不含 .json 后缀）
     */
    ConfigName?: (string | null);
    /**
     * 兼容字段；BAAH 运行不消费此开关，运行期写入仅由配置托管开关决定
     */
    IfQuickConfig?: (boolean | null);
};

