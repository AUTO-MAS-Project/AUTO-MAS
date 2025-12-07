/**
 * 颜色处理器
 * 将HTML颜色标签转换为ANSI颜色代码，用于控制台输出
 */

import {
    LogLevel,
    ANSI_COLORS,
    LOG_LEVEL_COLORS,
    getAnsiColor,
    parseLogLevel
} from './logColors';

export class ColorProcessor {
    // 颜色映射表：HTML标签 -> ANSI颜色代码
    private static readonly COLOR_MAP: Record<string, string> = {
        // 基本颜色
        'black': '\x1b[30m',
        'red': '\x1b[31m',
        'green': '\x1b[32m',
        'yellow': '\x1b[33m',
        'blue': '\x1b[34m',
        'magenta': '\x1b[35m',
        'cyan': '\x1b[36m',
        'white': '\x1b[37m',
        'orange': '\x1b[38;5;214m',   // 橙色 - 用于后端日志模块名
        'purple': '\x1b[35m',          // 紫色 - 用于前端日志模块名

        // 亮色
        'bright-black': '\x1b[90m',
        'bright-red': '\x1b[91m',
        'bright-green': '\x1b[92m',
        'bright-yellow': '\x1b[93m',
        'bright-blue': '\x1b[94m',
        'bright-magenta': '\x1b[95m',
        'bright-cyan': '\x1b[96m',
        'bright-white': '\x1b[97m',

        // 背景色
        'bg-black': '\x1b[40m',
        'bg-red': '\x1b[41m',
        'bg-green': '\x1b[42m',
        'bg-yellow': '\x1b[43m',
        'bg-blue': '\x1b[44m',
        'bg-magenta': '\x1b[45m',
        'bg-cyan': '\x1b[46m',
        'bg-white': '\x1b[47m',

        // 特殊样式
        'bold': '\x1b[1m',
        'dim': '\x1b[2m',
        'italic': '\x1b[3m',
        'underline': '\x1b[4m',
        'blink': '\x1b[5m',
        'reverse': '\x1b[7m',
        'hidden': '\x1b[8m',

        // 重置
        'reset': '\x1b[0m',
    }

    // 日志级别到颜色的映射，使用统一颜色配置
    private static readonly LOG_LEVEL_COLORS: Record<string, string> = {
        'TRACE': 'bright-black',
        'DEBUG': 'bright-black',
        'INFO': 'green',
        'SUCCESS': 'bright-green',
        'WARN': 'yellow',      // 添加WARN级别，与backendService.ts保持一致
        'WARNING': 'yellow',    // 兼容WARNING级别
        'ERROR': 'red',
        'CRITICAL': 'bright-red',
    }

    /**
     * 将HTML颜色标签转换为ANSI颜色代码
     * @param text 包含HTML颜色标签的文本
     * @returns 转换后的文本（带ANSI颜色代码）
     */
    static htmlToAnsi(text: string): string {
        // 匹配 <color>content</color> 格式的标签
        const colorTagRegex = /<(\w+?)>(.*?)<\/\1>/g

        return text.replace(colorTagRegex, (match, color, content) => {
            // 检查是否是日志级别标签
            if (color === 'level') {
                // 对于level标签，我们需要从内容中提取日志级别
                const levelMatch = content.trim().match(/^(\w+)/)
                if (levelMatch) {
                    const level = levelMatch[1].toUpperCase()
                    const parsedLevel = parseLogLevel(level)

                    // 使用统一颜色配置获取ANSI颜色代码
                    if (parsedLevel) {
                        const ansiCode = getAnsiColor(parsedLevel)
                        return `${ansiCode}${content}${ANSI_COLORS.RESET}`
                    }

                    // 如果无法解析为标准日志级别，使用旧的映射方式
                    const colorName = this.LOG_LEVEL_COLORS[level] || 'white'
                    const ansiCode = this.COLOR_MAP[colorName]
                    return `${ansiCode}${content}${this.COLOR_MAP.reset}`
                }
            }

            // 普通颜色标签
            const ansiCode = this.COLOR_MAP[color] || ''
            return ansiCode ? `${ansiCode}${content}${this.COLOR_MAP.reset}` : content
        })
    }

    /**
     * 移除所有ANSI颜色代码
     * @param text 包含ANSI颜色代码的文本
     * @returns 移除颜色代码后的纯文本
     */
    static stripAnsiColors(text: string): string {
        // 匹配ANSI转义序列的正则表达式
        const ansiRegex = /\x1b\[[0-9;]*[mGKHJABCDsuPLfhnqrp]/g
        return text.replace(ansiRegex, '')
    }

    /**
     * 移除所有HTML颜色标签
     * @param text 包含HTML颜色标签的文本
     * @returns 移除标签后的纯文本
     */
    static stripHtmlColors(text: string): string {
        // 匹配 <color>content</color> 格式的标签
        const colorTagRegex = /<\w+?>(.*?)<\/\w+?>/g
        return text.replace(colorTagRegex, '$1')
    }

    /**
     * 获取日志级别对应的颜色名称
     * @param level 日志级别
     * @returns 颜色名称
     */
    static getLevelColor(level: string): string {
        const upperLevel = level.toUpperCase()
        const parsedLevel = parseLogLevel(upperLevel)

        // 如果是标准日志级别，使用统一颜色配置
        if (parsedLevel) {
            return getAnsiColor(parsedLevel)
        }

        // 否则使用旧的映射方式
        return this.COLOR_MAP[this.LOG_LEVEL_COLORS[upperLevel] || 'white'] || ''
    }

    /**
     * 检查文本是否包含颜色标签
     * @param text 文本
     * @returns 是否包含颜色标签
     */
    static hasColorTags(text: string): boolean {
        const colorTagRegex = /<\w+?>.*?<\/\w+?>/g
        return colorTagRegex.test(text)
    }

    /**
     * 应用颜色到文本（使用ANSI代码）
     * @param text 文本
     * @param colorName 颜色名称
     * @returns 带颜色的文本
     */
    static applyColor(text: string, colorName: string): string {
        // 首先尝试解析为日志级别
        const parsedLevel = parseLogLevel(colorName.toUpperCase())
        if (parsedLevel) {
            return `${getAnsiColor(parsedLevel)}${text}${ANSI_COLORS.RESET}`
        }

        // 如果不是日志级别，使用原有的颜色映射
        const ansiCode = this.COLOR_MAP[colorName]
        return ansiCode ? `${ansiCode}${text}${this.COLOR_MAP.reset}` : text
    }
}