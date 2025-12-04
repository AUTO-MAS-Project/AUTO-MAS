/**
 * 统一日志颜色配置文件
 * 与loguru默认颜色完全一致
 */

// 日志级别枚举
export enum LogLevel {
    TRACE = 'TRACE',
    DEBUG = 'DEBUG',
    INFO = 'INFO',
    SUCCESS = 'SUCCESS',
    WARN = 'WARN',
    ERROR = 'ERROR',
    CRITICAL = 'CRITICAL'
}

// ANSI颜色代码
export const ANSI_COLORS = {
    RESET: '\x1b[0m',
    BOLD: '\x1b[1m',
    TRACE: '\x1b[36m',      // 青色
    DEBUG: '\x1b[34m',      // 蓝色
    INFO: '',               // 默认白色（无颜色代码）
    SUCCESS: '\x1b[32m',    // 绿色
    WARN: '\x1b[33m',       // 黄色
    ERROR: '\x1b[31m',      // 红色
    CRITICAL: '\x1b[91m'    // 亮红色
} as const;

// 十六进制颜色值
export const HEX_COLORS = {
    TRACE: '#00ffff',       // 青色
    DEBUG: '#0000ff',       // 蓝色
    INFO: '#ffffff',        // 白色
    SUCCESS: '#00ff00',     // 绿色
    WARN: '#ffff00',        // 黄色
    ERROR: '#ff0000',       // 红色
    CRITICAL: '#ff0000'     // 亮红色（与ERROR相同但显示更亮）
} as const;

// RGB颜色值（从十六进制转换）
export const RGB_COLORS = {
    TRACE: { r: 0, g: 255, b: 255 },         // 青色
    DEBUG: { r: 0, g: 0, b: 255 },           // 蓝色
    INFO: { r: 255, g: 255, b: 255 },         // 白色
    SUCCESS: { r: 0, g: 255, b: 0 },         // 绿色
    WARN: { r: 255, g: 255, b: 0 },          // 黄色
    ERROR: { r: 255, g: 0, b: 0 },           // 红色
    CRITICAL: { r: 255, g: 0, b: 0 }         // 亮红色
} as const;

// CSS颜色类名
export const CSS_CLASSES = {
    TRACE: 'log-trace',
    DEBUG: 'log-debug',
    INFO: 'log-info',
    SUCCESS: 'log-success',
    WARN: 'log-warning',
    ERROR: 'log-error',
    CRITICAL: 'log-critical'
} as const;

// 完整的颜色配置接口
export interface LogLevelColorConfig {
    level: LogLevel;
    ansi: string;
    hex: string;
    rgb: { r: number; g: number; b: number };
    cssClass: string;
}

// 日志级别颜色配置映射
export const LOG_LEVEL_COLORS: Record<LogLevel, LogLevelColorConfig> = {
    [LogLevel.TRACE]: {
        level: LogLevel.TRACE,
        ansi: ANSI_COLORS.TRACE,
        hex: HEX_COLORS.TRACE,
        rgb: RGB_COLORS.TRACE,
        cssClass: CSS_CLASSES.TRACE
    },
    [LogLevel.DEBUG]: {
        level: LogLevel.DEBUG,
        ansi: ANSI_COLORS.DEBUG,
        hex: HEX_COLORS.DEBUG,
        rgb: RGB_COLORS.DEBUG,
        cssClass: CSS_CLASSES.DEBUG
    },
    [LogLevel.INFO]: {
        level: LogLevel.INFO,
        ansi: ANSI_COLORS.INFO,
        hex: HEX_COLORS.INFO,
        rgb: RGB_COLORS.INFO,
        cssClass: CSS_CLASSES.INFO
    },
    [LogLevel.SUCCESS]: {
        level: LogLevel.SUCCESS,
        ansi: ANSI_COLORS.SUCCESS,
        hex: HEX_COLORS.SUCCESS,
        rgb: RGB_COLORS.SUCCESS,
        cssClass: CSS_CLASSES.SUCCESS
    },
    [LogLevel.WARN]: {
        level: LogLevel.WARN,
        ansi: ANSI_COLORS.WARN,
        hex: HEX_COLORS.WARN,
        rgb: RGB_COLORS.WARN,
        cssClass: CSS_CLASSES.WARN
    },
    [LogLevel.ERROR]: {
        level: LogLevel.ERROR,
        ansi: ANSI_COLORS.ERROR,
        hex: HEX_COLORS.ERROR,
        rgb: RGB_COLORS.ERROR,
        cssClass: CSS_CLASSES.ERROR
    },
    [LogLevel.CRITICAL]: {
        level: LogLevel.CRITICAL,
        ansi: ANSI_COLORS.CRITICAL,
        hex: HEX_COLORS.CRITICAL,
        rgb: RGB_COLORS.CRITICAL,
        cssClass: CSS_CLASSES.CRITICAL
    }
};

// 工具函数：获取日志级别的ANSI颜色代码
export function getAnsiColor(level: LogLevel): string {
    return LOG_LEVEL_COLORS[level]?.ansi || ANSI_COLORS.RESET;
}

// 工具函数：获取日志级别的十六进制颜色值
export function getHexColor(level: LogLevel): string {
    return LOG_LEVEL_COLORS[level]?.hex || '#000000';
}

// 工具函数：获取日志级别的RGB颜色值
export function getRgbColor(level: LogLevel): { r: number; g: number; b: number } {
    return LOG_LEVEL_COLORS[level]?.rgb || { r: 0, g: 0, b: 0 };
}

// 工具函数：获取日志级别的CSS类名
export function getCssClass(level: LogLevel): string {
    return LOG_LEVEL_COLORS[level]?.cssClass || '';
}

// 工具函数：应用ANSI颜色到文本（包含粗体样式）
export function applyAnsiColor(text: string, level: LogLevel): string {
    const color = getAnsiColor(level);
    // 为所有级别添加粗体样式
    if (color) {
        return `${ANSI_COLORS.BOLD}${color}${text}${ANSI_COLORS.RESET}`;
    } else {
        // INFO级别无颜色，但仍需粗体
        return `${ANSI_COLORS.BOLD}${text}${ANSI_COLORS.RESET}`;
    }
}

// 工具函数：检查是否为有效的日志级别
export function isValidLogLevel(level: string): level is LogLevel {
    return Object.values(LogLevel).includes(level as LogLevel);
}

// 工具函数：从字符串解析日志级别
export function parseLogLevel(level: string): LogLevel | null {
    const upperLevel = level.toUpperCase();
    if (isValidLogLevel(upperLevel)) {
        return upperLevel as LogLevel;
    }
    return null;
}