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
     * 成功时日志
     */
    SuccessLog?: (string | null);
    /**
     * 错误时日志
     */
    ErrorLog?: (string | null);
};

