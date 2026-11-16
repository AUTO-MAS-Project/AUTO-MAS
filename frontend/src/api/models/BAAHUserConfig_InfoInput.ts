/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BAAHUserConfig_InfoInput = {
    /**
     * 活动排期按哪个服判断，供「活动关优先」使用（Kivo 时间轴的原文拼写：JP / Globle / CN）
     */
    ActivityLineType?: ('JP' | 'Globle' | 'CN' | null);
    /**
     * 兼容字段；BAAH 运行不消费此来源值，始终使用 Info.ConfigName 绑定的 BAAH 配置文件
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 默认使用的 BAAH 配置文件名（BAAH_CONFIGS 目录下的文件名，不含 .json 后缀）
     */
    ConfigName?: (string | null);
    /**
     * 活动期间自动把「活动关卡」任务排到最前并打开
     */
    IfEventFirst?: (boolean | null);
    /**
     * 兼容字段；BAAH 运行不消费此开关，运行期写入由配置托管、计划表及活动优先等实际选项决定
     */
    IfQuickConfig?: (boolean | null);
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
     * 关卡计划表；Fixed 表示沿用 BAAH 中的关卡配置
     */
    StageMode?: (string | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 账号标签信息
     */
    readonly Tag?: (string | null);
};

