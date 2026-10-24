/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GeneralConfig_ScriptInput = {
    /**
     * 脚本参数
     */
    Arguments?: (string | null);
    /**
     * 配置文件路径
     */
    ConfigPath?: (string | null);
    /**
     * 配置路径模式
     */
    ConfigPathMode?: ('File' | 'Folder' | null);
    /**
     * 错误日志匹配
     */
    ErrorLog?: (string | null);
    /**
     * 错误日志匹配模式：Split = 「|」分隔关键字子串包含；Regex = 正则表达式
     */
    ErrorLogMode?: ('Split' | 'Regex' | null);
    /**
     * 是否追踪进程
     */
    IfTrackProcess?: (boolean | null);
    /**
     * 日志预处理启用开关：关闭时保留规则配置，行为与未配置预处理完全一致
     */
    LogHookEnabled?: (boolean | null);
    /**
     * 日志预处理规则（JSON 数组，每项形如 {"type":"drop|replace",...}）； 预处理先于任务日志、推送日志采集与成功/失败判定执行，丢弃的行不进入下游
     */
    LogHookRules?: (string | null);
    /**
     * 日志路径
     */
    LogPath?: (string | null);
    /**
     * 日志路径格式
     */
    LogPathFormat?: (string | null);
    /**
     * 日志时间戳结束位置
     */
    LogTimeEnd?: (number | null);
    /**
     * 日志时间格式
     */
    LogTimeFormat?: (string | null);
    /**
     * 日志时间戳开始位置
     */
    LogTimeStart?: (number | null);
    /**
     * 推送日志启用开关：关闭后保留高级正则配置，但不会实际采集推送日志
     */
    PushLogEnabled?: (boolean | null);
    /**
     * 推送日志高级模式（JSON 数组，每项形如 {"type":"regex|multiline",...}）
     */
    PushLogPatterns?: (string | null);
    /**
     * 脚本路径
     */
    ScriptPath?: (string | null);
    /**
     * 成功日志匹配
     */
    SuccessLog?: (string | null);
    /**
     * 成功日志匹配模式：Split = 「|」分隔关键字子串包含；Regex = 正则表达式
     */
    SuccessLogMode?: ('Split' | 'Regex' | null);
    /**
     * 追踪进程的启动命令行参数
     */
    TrackProcessCmdline?: (string | null);
    /**
     * 追踪进程的文件路径
     */
    TrackProcessExe?: (string | null);
    /**
     * 追踪进程的名称
     */
    TrackProcessName?: (string | null);
    /**
     * 更新配置模式
     */
    UpdateConfigMode?: ('Never' | 'Success' | 'Failure' | 'Always' | null);
};

