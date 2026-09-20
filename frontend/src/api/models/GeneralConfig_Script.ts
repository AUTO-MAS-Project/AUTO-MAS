/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GeneralConfig_Script = {
    /**
     * 脚本可执行文件路径
     */
    ScriptPath?: (string | null);
    /**
     * 脚本启动附加命令参数
     */
    Arguments?: (string | null);
    /**
     * 是否追踪脚本子进程
     */
    IfTrackProcess?: (boolean | null);
    /**
     * 追踪进程名称
     */
    TrackProcessName?: (string | null);
    /**
     * 追踪进程文件路径
     */
    TrackProcessExe?: (string | null);
    /**
     * 追踪进程启动命令行参数
     */
    TrackProcessCmdline?: (string | null);
    /**
     * 配置文件路径
     */
    ConfigPath?: (string | null);
    /**
     * 配置文件类型: 单个文件, 文件夹
     */
    ConfigPathMode?: ('File' | 'Folder' | null);
    /**
     * 更新配置时机, 从不, 仅成功时, 仅失败时, 任务结束时
     */
    UpdateConfigMode?: ('Never' | 'Success' | 'Failure' | 'Always' | null);
    /**
     * 日志文件路径
     */
    LogPath?: (string | null);
    /**
     * 日志文件名格式
     */
    LogPathFormat?: (string | null);
    /**
     * 日志时间戳开始位置
     */
    LogTimeStart?: (number | null);
    /**
     * 日志时间戳结束位置
     */
    LogTimeEnd?: (number | null);
    /**
     * 日志时间戳格式
     */
    LogTimeFormat?: (string | null);
    /**
     * 日志处理钩子启用开关
     */
    LogHookEnabled?: (boolean | null);
    /**
     * 日志处理钩子规则(JSON 数组，每项形如 {"type":"drop|replace","match":正则,"replace":替换文本})；先于任务日志、推送采集与成功/失败判定执行
     */
    LogHookRules?: (string | null);
    /**
     * 成功时日志
     */
    SuccessLog?: (string | null);
    /**
     * 成功时日志匹配模式: 关键字子串包含, 正则表达式
     */
    SuccessLogMode?: ('Split' | 'Regex' | null);
    /**
     * 错误时日志
     */
    ErrorLog?: (string | null);
    /**
     * 错误时日志匹配模式: 关键字子串包含, 正则表达式
     */
    ErrorLogMode?: ('Split' | 'Regex' | null);
    /**
     * 推送日志采集启用开关
     */
    PushLogEnabled?: (boolean | null);
    /**
     * 推送日志高级模式匹配(JSON 数组，每项为 PushLogPattern 对象：type 为 split/regex/multiline，按类型使用对应字段)
     */
    PushLogPatterns?: (string | null);
};

